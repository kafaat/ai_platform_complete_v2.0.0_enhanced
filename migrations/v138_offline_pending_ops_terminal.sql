-- ════════════════════════════════════════════════════════════════════════
-- SAHOOL v138 (سطر v19.5-3) — offline_pending_ops: حالتان جديدتان + مطالبة
-- ════════════════════════════════════════════════════════════════════════
-- الفجوة: ‎offline_pending_ops.status‎ (v92) لا يعرف سوى ‎pending‎/‎processed‎.
-- عمليّة «سامّة» (poison) تفشل دائماً تبقى ‎pending‎ إلى الأبد — يتضخّم ‎attempts‎/
-- ‎last_error‎ فقط بلا حالة نهائيّة تُنهي الحلقة، ولا حالة «قيد المعالجة» تمنع
-- عاملَين متزامنَين من التقاط الصفّ نفسه (تنفيذ مزدوج لأثر جانبيّ).
--
-- الإصلاح (إضافيّ idempotent):
--   • توسيع الحالات المسموحة: ‎processing‎ (مُطالَب/قيد المعالجة) و‎failed‎ (نهائيّة
--     بعد استنفاد المحاولات) فوق ‎pending‎/‎processed‎ القائمتَين. يُطبَّق كـCHECK
--     صريح (لم يكن في v92) بإسقاط+إعادة إنشاء idempotent — القيم الحاليّة
--     (pending/processed) ضمن المجموعة فلا يفشل التحقّق على صفوف قائمة.
--   • ‎failed_at TIMESTAMPTZ‎: لحظة الانتقال النهائيّ (تدقيق/تنظيف)، nullable.
--   • فهرس جزئيّ على ‎processing‎ لإعادة المطالبة بالصفوف العالقة (عامل مات أثناء
--     المعالجة ⇒ عقد processing لا يُمسَح) بكفاءة — نظير فهرس pending في v92.
--
-- المطالبة (claim) في طبقة التطبيق: ‎UPDATE … SET status='processing'
-- WHERE status='pending' RETURNING‎ ذرّيّة (offline_pending_db.claim_pending) —
-- عامل واحد فقط يفوز بالصفّ. الفشل النهائيّ عند ‎attempts >= MAX‎ ⇒ ‎failed‎.
--
-- RLS: عزل المستأجِر (ENABLE+FORCE+tenant_isolation) قائم من v92 — لا يتغيّر،
-- والعمود/الفهرس الجديدان يخضعان له. idempotent بالكامل (IF NOT EXISTS + DROP …
-- IF EXISTS). يُطبَّق بعد v135 (أعلى ترحيل حاليّاً).

-- ١) عمود لحظة الفشل النهائيّ (تدقيق/تنظيف). nullable — يُملأ عند الانتقال failed.
ALTER TABLE offline_pending_ops
    ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ;

COMMENT ON COLUMN offline_pending_ops.failed_at IS
    'لحظة الانتقال النهائيّ إلى failed (بعد استنفاد MAX محاولة) — للتدقيق/التنظيف.';

-- ٢) توسيع الحالات المسموحة عبر CHECK صريح. v92 لم يحمل قيداً، فهذا يضبط العقد:
--    pending | processing | processed | failed. إسقاط+إضافة idempotent (القيم
--    القائمة ضمن المجموعة ⇒ لا فشل تحقّق على صفوف موجودة).
ALTER TABLE offline_pending_ops
    DROP CONSTRAINT IF EXISTS offline_pending_ops_status_check;
ALTER TABLE offline_pending_ops
    ADD CONSTRAINT offline_pending_ops_status_check
    CHECK (status IN ('pending', 'processing', 'processed', 'failed'));

-- ٣) فهرس جزئيّ لإعادة المطالبة بالصفوف العالقة في processing (عامل مات وسط
--    المعالجة). نظير idx_offline_pending_ops_tenant_pending (v92) — خفيف، يخصّ
--    processing فقط، ويدعم مسح FIFO لكلّ مستأجِر عند الاسترداد.
CREATE INDEX IF NOT EXISTS idx_offline_pending_ops_processing
    ON offline_pending_ops (tenant_id, created_at)
    WHERE status = 'processing';
