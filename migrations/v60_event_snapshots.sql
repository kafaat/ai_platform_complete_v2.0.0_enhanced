-- SAHOOL v60 — migrations/v60_event_snapshots.sql
-- لقطات حالة الحقل (Field State Snapshots): مخبّأ مُشتقّ لإعادة بناء تزايديّة.
--
-- الهدف: تسريع إعادة بناء state الحقل من مخزن الأحداث. حاليّاً يُعاد تشغيل كامل
-- التاريخ في كلّ استدعاء (EventReplay.reconstruct_state)؛ هذا الجدول يخزّن لقطة
-- محسوبة مع مؤشّرها (آخر حدث طُبِّق) كي يُعاد تشغيل الأحداث الواقعة **بعد** اللقطة
-- فقط (EventReplay.reconstruct_with_snapshot).
--
-- ⚠ صدق معماريّ: اللقطة **مخبّأ مُشتقّ** (derived cache)، ليست مصدر حقيقة.
--   مصدر الحقيقة الوحيد يبقى مخزن الأحداث events (append-only). حذف هذا الجدول
--   لا يفقد أيّ بيانات — تُعاد بناؤها كاملةً من الأحداث. لا upcasting هنا.
--
-- يطبّقه CI Integration Tests على PostGIS حقيقيّ عبر تمرير كامل MANIFEST.
-- idempotent بالكامل (CREATE TABLE/INDEX IF NOT EXISTS + حارس DO على RLS) —
-- آمن إعادة التطبيق كلّ إقلاع.

-- ══════════════════════════════════════════════════════════════════
-- PART 1: جدول لقطات حالة الحقل (Field State Snapshots)
-- ══════════════════════════════════════════════════════════════════
-- كلّ صفّ = أحدث state محسوبة لكيان (entity_type, entity_id) ضمن مستأجِر، مع
-- مؤشّرها في مجرى الأحداث. المؤشّر (last_event_id, last_occurred_at): إعادة
-- التشغيل التزايديّة تطبّق فقط الأحداث الواقعة بعده (ترتيب (occurred_at, event_id)
-- الحتميّ نفسه المستعمل في reconstruct). last_seq محفوظ للتوافق (جدول events بلا
-- عمود seq حاليّاً — راجع v11_events_bus — فيبقى NULL غالباً).

CREATE TABLE IF NOT EXISTS field_state_snapshots (
    id               BIGSERIAL    PRIMARY KEY,
    tenant_id        UUID         NOT NULL,           -- عزل المستأجر (RLS أدناه)
    entity_type      TEXT         NOT NULL,           -- 'field' عادةً (يطابق events.entity_type)
    entity_id        TEXT         NOT NULL,           -- معرّف الكيان (نصّيّ منذ v18)
    state            JSONB        NOT NULL DEFAULT '{}'::jsonb,  -- الحقول الإسقاطيّة المُسلسَلة
    last_event_id    UUID,                            -- آخر حدث طُبِّق (مؤشّر اللقطة)
    last_occurred_at TIMESTAMPTZ,                     -- زمن آخر حدث (الحدّ الفاصل)
    last_seq         BIGINT,                          -- محفوظ للتوافق (events بلا seq)
    total_events     INTEGER      NOT NULL DEFAULT 0, -- عدد الأحداث المطبَّقة حتّى اللقطة
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    -- صفّ واحد لكلّ كيان لكلّ مستأجِر (upsert على هذا المفتاح) — يُمكّن البحث عن
    -- «أحدث لقطة» مباشرةً ويحرس تكرار اللقطات.
    CONSTRAINT uq_field_state_snapshots_entity UNIQUE (tenant_id, entity_type, entity_id)
);

COMMENT ON TABLE  field_state_snapshots IS 'لقطات حالة الحقل — مخبّأ مُشتقّ لإعادة بناء تزايديّة من مخزن الأحداث (append-only). ليست مصدر حقيقة؛ حذفها لا يفقد بيانات.';
COMMENT ON COLUMN field_state_snapshots.state            IS 'الحقول الإسقاطيّة المُسلسَلة (ReconstructedState.to_snapshot_dict).';
COMMENT ON COLUMN field_state_snapshots.last_event_id    IS 'مؤشّر اللقطة: آخر حدث طُبِّق (يُعاد تشغيل ما بعده فقط).';
COMMENT ON COLUMN field_state_snapshots.last_occurred_at IS 'زمن آخر حدث مطبَّق — الحدّ الفاصل لإعادة التشغيل التزايديّة.';
COMMENT ON COLUMN field_state_snapshots.last_seq         IS 'محفوظ للتوافق؛ جدول events بلا عمود seq حاليّاً (v11) فيبقى NULL غالباً.';
COMMENT ON COLUMN field_state_snapshots.total_events     IS 'عدد الأحداث المطبَّقة حتّى هذه اللقطة (تحقّق/تشخيص).';

-- فهرس البحث عن أحدث لقطة لكيان (entity_type, entity_id) عبر المستأجرين تحت RLS.
-- (مرآة UNIQUE أعلاه لكن مفهرَس tenant-first لمسح RLS الكفء.)
CREATE INDEX IF NOT EXISTS idx_field_state_snapshots_lookup
    ON field_state_snapshots (tenant_id, entity_type, entity_id);

-- ══════════════════════════════════════════════════════════════════
-- PART 2: عزل المستأجرين (RLS) — تطبيق صريح للأمان
-- ══════════════════════════════════════════════════════════════════
-- الجدول يحوي tenant_id فتغطّيه التغطية الديناميكيّة (v56). نطبّقه هنا صراحةً
-- أيضاً (مرآةً لبقيّة الجداول self-applied) لإغلاق نافذة الانكشاف قبل بلوغ v56،
-- محروساً بوجود الدالّة المساعدة (المعرّفة في v9_rls_tenant_isolation.sql).
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = '_sahool_apply_tenant_rls') THEN
        PERFORM _sahool_apply_tenant_rls('field_state_snapshots');
        RAISE NOTICE 'v60: RLS مُفعّل على field_state_snapshots';
    ELSE
        RAISE NOTICE 'v60: تخطّي تطبيق RLS الصريح — الدالّة المساعدة غير موجودة بعد (ستغطّيه v56)';
    END IF;
END $$;
