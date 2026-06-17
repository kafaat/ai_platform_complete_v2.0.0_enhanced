-- migrations/v18_entity_ids_text.sql
--
-- v18: إصلاح تناقض بنيويّ — معرّفات الكيانات الزراعيّة نصّيّة لا UUID.
--
-- الخطأ المكتشَف (بمراجعة الكود الفعليّ):
--   عالم v8: fields.field_id = VARCHAR(50) — نصّ حرّ عمداً ("fld_demo_001").
--   لكن جداول v10/v11/v12 عرّفت نفس المعرّف UUID:
--     - events.entity_id UUID          (v11) — وtrueup.py يُصدر حدثاً بـentity_id=field_id
--     - field_lifecycle.field_id UUID  (v10)
--     - trueup_calibrations.field_id UUID (v12)
--     - sharing_keys.allowed_field_ids UUID[] (v12)
--   النتيجة: أيّ إصدار حدث/معايرة/دورة حياة بمعرّف حقل نصّيّ يفشل
--   (ValueError في event_schema مبكّراً، أو خطأ cast ::uuid في PostgreSQL).
--
-- القرار: المعرّفات النصّيّة هي الواقع المعتمد (init_v8 + البيانات القائمة)،
-- فنحوّل الأعمدة إلى TEXT. التحويل ::text آمن على بيانات UUID قائمة (لا فقد).

BEGIN;

-- ════════════════════════════════════════════════════════════════
-- ١. events.entity_id: UUID → TEXT
-- ════════════════════════════════════════════════════════════════
-- الـviews تعتمد على العمود ⇒ تُسقَط قبل التحويل (ALTER ... USING يُعيد كتابة
-- العمود فيرفضه أيّ كائن تابع). v_entity_latest_event يُعاد إنشاؤه هنا أدناه؛
-- أمّا v_event_dead_letter فمصدره v48 (لاحق في MANIFEST، CREATE OR REPLACE) فيُعاد
-- إنشاؤه تلقائيّاً في نفس المرور. هذا الإسقاط يجعل v18 آمناً على **إعادة التشغيل**:
-- في تشغيل أوّل v_event_dead_letter غير موجود بعد (IF EXISTS = لا عمل)؛ في إعادة
-- تشغيل يكون قائماً من مرور v48 السابق فيُسقَط هنا فينجح ALTER (كان يفشل بـ
-- «cannot alter type of a column used by a view or rule» على entity_id).
DROP VIEW IF EXISTS v_entity_latest_event;
DROP VIEW IF EXISTS v_event_dead_letter;

ALTER TABLE events
    ALTER COLUMN entity_id TYPE TEXT USING entity_id::text;

CREATE OR REPLACE VIEW v_entity_latest_event AS
SELECT DISTINCT ON (entity_type, entity_id)
    entity_type,
    entity_id,
    event_type as last_event_type,
    occurred_at as last_occurred_at,
    payload as last_payload
FROM events
ORDER BY entity_type, entity_id, occurred_at DESC;

-- ════════════════════════════════════════════════════════════════
-- ٢. emit_event: p_entity_id TEXT
-- ════════════════════════════════════════════════════════════════
-- تغيير نوع وسيط = توقيع جديد في PostgreSQL ⇒ يجب إسقاط القديمة صراحةً
-- وإلّا أصبحت الدالّتان overload متعايشتين (التباس وقت الاستدعاء).
DROP FUNCTION IF EXISTS emit_event(TEXT, TEXT, UUID, UUID, JSONB, TEXT, TEXT, UUID, TIMESTAMPTZ);

CREATE OR REPLACE FUNCTION emit_event(
    p_event_type    TEXT,
    p_entity_type   TEXT,
    p_entity_id     TEXT,
    p_tenant_id     UUID,
    p_payload       JSONB,
    p_source        TEXT DEFAULT 'system',
    p_actor_id      TEXT DEFAULT NULL,
    p_command_id    UUID DEFAULT NULL,
    p_occurred_at   TIMESTAMPTZ DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_event_id     UUID := gen_random_uuid();
    v_payload_hash TEXT;
    v_dedup_key    TEXT;
    v_occurred_at  TIMESTAMPTZ := COALESCE(p_occurred_at, NOW());
BEGIN
    -- payload hash للـidempotency (deterministic) — نفس صيغة v11 بالضبط
    -- (p_entity_id::text على TEXT = نفسه) ⇒ dedup التاريخيّ محفوظ.
    v_payload_hash := encode(
        digest(p_event_type || p_entity_id || p_payload::text, 'sha256'),
        'hex'
    );

    v_dedup_key := p_tenant_id::text || ':' || p_event_type || ':'
                || p_entity_id || ':' || v_payload_hash || ':'
                || to_char(v_occurred_at, 'YYYY-MM-DD');

    INSERT INTO events (
        event_id, event_type, entity_type, entity_id, tenant_id,
        actor_id, command_id, payload, payload_hash, dedup_key, source, occurred_at
    ) VALUES (
        v_event_id, p_event_type, p_entity_type, p_entity_id, p_tenant_id,
        p_actor_id, p_command_id, p_payload, v_payload_hash, v_dedup_key, p_source, v_occurred_at
    )
    ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL
    DO NOTHING
    RETURNING event_id INTO v_event_id;

    IF v_event_id IS NULL THEN
        RETURN NULL;
    END IF;

    INSERT INTO event_outbox (event_id, nats_subject)
    VALUES (v_event_id, 'sahool.events.' || p_event_type);

    RETURN v_event_id;
END;
$$ LANGUAGE plpgsql;

-- ════════════════════════════════════════════════════════════════
-- ٣. field_lifecycle.field_id: UUID → TEXT
-- ════════════════════════════════════════════════════════════════
-- (الفهارس وقيد UNIQUE(field_id, season_id) يُعاد بناؤها تلقائيّاً)
ALTER TABLE field_lifecycle
    ALTER COLUMN field_id TYPE TEXT USING field_id::text;

-- ════════════════════════════════════════════════════════════════
-- ٤. trueup_calibrations.field_id: UUID → TEXT
-- ════════════════════════════════════════════════════════════════
-- (operation_id يبقى UUID: لا جدول عمليّات نصّيّ في v8، والكود يفرض UUID له
--  باتّساق — لا دليل على معرّفات عمليّات نصّيّة، فلا نغيّر بلا دليل.)
ALTER TABLE trueup_calibrations
    ALTER COLUMN field_id TYPE TEXT USING field_id::text;

-- ════════════════════════════════════════════════════════════════
-- ٥. sharing_keys.allowed_field_ids: UUID[] → TEXT[]
-- ════════════════════════════════════════════════════════════════
ALTER TABLE sharing_keys
    ALTER COLUMN allowed_field_ids TYPE TEXT[] USING allowed_field_ids::text[];

-- ════════════════════════════════════════════════════════════════
-- ٦. is_sharing_key_valid: نوع الإرجاع allowed_fields UUID[] → TEXT[]
-- ════════════════════════════════════════════════════════════════
-- دالّة v12 تُرجِع k.allowed_field_ids ضمن RETURNS TABLE(... UUID[]) — بعد
-- تحويل العمود لـTEXT[] يفشل الاستدعاء (عدم تطابق بنية النتيجة). تغيير نوع
-- الإرجاع لا يجوز بـCREATE OR REPLACE في PostgreSQL ⇒ إسقاط ثمّ إعادة إنشاء.
DROP FUNCTION IF EXISTS is_sharing_key_valid(TEXT);

CREATE OR REPLACE FUNCTION is_sharing_key_valid(p_key_hash TEXT)
RETURNS TABLE(
    valid           BOOLEAN,
    tenant_id       UUID,
    scope           TEXT,
    allowed_fields  TEXT[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        (k.revoked_at IS NULL AND k.expires_at > NOW()) AS valid,
        k.tenant_id,
        k.scope,
        k.allowed_field_ids
    FROM sharing_keys k
    WHERE k.key_hash = p_key_hash
    LIMIT 1;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;

-- ════════════════════════════════════════════════════════════════
-- Verification:
--   SELECT emit_event('field.created', 'field', 'fld_demo_001',
--       gen_random_uuid(), '{"name":"test"}'::jsonb, 'system');
--   -- يجب أن يُرجِع event_id (كان يفشل قبل v18 بخطأ cast uuid)
-- ════════════════════════════════════════════════════════════════
