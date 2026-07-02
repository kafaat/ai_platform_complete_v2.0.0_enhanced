-- v140: outbox_delivery_attempts — سجلّ جنائيّ (forensic) append-only لكلّ محاولة تسليم
-- ════════════════════════════════════════════════════════════════════════
-- المشكلة (سطر v19.5-4): جدول الـoutbox المعامليّ (event_outbox — v11) يحتفظ بحالة
-- التسليم **المُجمَّعة فقط**: retry_count + last_error واحد + last_attempt_at. بعد
-- المحاولة #3 لا يمكن رؤية خطأ المحاولة #2 — يُدهَس آخر خطأ فوق سابقه. هذا يفقد
-- الأثر الجنائيّ لتشخيص التسليمات المتذبذبة/الميّتة (DLQ).
--
-- الحلّ: جدول ملحق (append-only) صفّ لكلّ **محاولة تسليم فردية** يصونه OutboxWorker —
-- طابعها الزمنيّ + الموضوع (nats_subject) + النتيجة (published/failed/skipped) + نصّ
-- الخطأ عند الفشل. الأعمدة المُجمَّعة في event_outbox تبقى دون تغيير (إضافيّ صرف).
--
-- الاقتران: يُلحَق بـ**event_outbox** (v11) — الجدول الحيّ الذي يستنزفه العامل فعلاً
-- (services/sahool-platform/api/event_bus.py: OutboxWorker._process_batch يقرأ
-- «FROM event_outbox o JOIN events e»). ليس runtime_event_outbox (v106) الذي لا
-- يستنزفه هذا العامل.
--
-- العزل: event_outbox نفسه **غير مُنطّق بالمستأجِر** (لا RLS عليه — العامل عابر
-- للمستأجِرين بالتصميم). لذا نُبقي سجلّ المحاولات متّسقاً (لا RLS/FORCE)، مع تخزين
-- tenant_id كعمود إعلاميّ (forensic) NULL-able مأخوذ من الحدث المرتبط — لا إنفاذ.
--
-- append-only: نُطبّق sahool_block_mutation (نمط mfa_audit_events / v9) — العامل
-- يُدرِج فقط (INSERT) ولا يُعدّل/يحذف أبداً، فالحظر لا يُعقّده. الـFK بلا CASCADE
-- (NO ACTION): صفّ outbox لا يُحذف أبداً في الشيفرة، والحظر يصون الأثر.
--
-- idempotent بالكامل (IF NOT EXISTS + DROP TRIGGER IF EXISTS). بعد v138.

BEGIN;

CREATE TABLE IF NOT EXISTS outbox_delivery_attempts (
    id           BIGSERIAL   PRIMARY KEY,                                   -- معرّف المحاولة (تسلسليّ)
    outbox_id    BIGINT      NOT NULL REFERENCES event_outbox(outbox_id),   -- صفّ الـoutbox (v11) — بلا CASCADE
    tenant_id    UUID,                                                       -- إعلاميّ (forensic) من الحدث — NULL إن غاب
    attempt_no   INT         NOT NULL,                                       -- رقم المحاولة (= retry_count المُتزايد)
    attempted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),                         -- لحظة المحاولة
    subject      TEXT,                                                       -- موضوع NATS (nats_subject) وقت المحاولة
    outcome      TEXT        NOT NULL
        CHECK (outcome IN ('published', 'failed', 'skipped')),              -- نتيجة المحاولة
    error        TEXT                                                        -- نصّ الخطأ عند الفشل — NULL عند النجاح
);

-- فهرس القراءة الرئيس: كلّ محاولات صفّ outbox بترتيب المحاولة (تشخيص جنائيّ/DLQ).
CREATE INDEX IF NOT EXISTS idx_outbox_delivery_attempts_outbox
    ON outbox_delivery_attempts (outbox_id, attempt_no);

COMMENT ON TABLE outbox_delivery_attempts IS
    'سجلّ جنائيّ append-only لكلّ محاولة تسليم outbox فردية (صفّ لكلّ محاولة: طابع زمنيّ/موضوع/نتيجة/خطأ). يكمّل حالة event_outbox المُجمَّعة (retry_count/last_error الواحد) بأثر كامل لا يُدهَس. يصونه OutboxWorker. v140.';
COMMENT ON COLUMN outbox_delivery_attempts.outcome IS
    'published=نُشِر بنجاح · failed=فشل (error مملوء) · skipped=تُخطّي النشر (حدث عولِج سابقاً، جُرِّد الصفّ).';
COMMENT ON COLUMN outbox_delivery_attempts.attempt_no IS
    'رقم المحاولة = retry_count+1 المُتزايد لهذا الصفّ (يميّز محاولة #2 عن #3).';

-- ── append-only: حظر UPDATE/DELETE (نمط v9 / mfa_audit_events) ──
-- INSERT يبقى مسموحاً (append). التصحيح بحدث جديد لا بتعديل قديم — أثر جنائيّ لا يُزوَّر.
-- sahool_block_mutation مُعرَّفة في v9_append_only_enforcement.sql (تُنفَّذ قبله).
DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'sahool_block_mutation') THEN
        DROP TRIGGER IF EXISTS trg_append_only_outbox_delivery_attempts
            ON outbox_delivery_attempts;
        CREATE TRIGGER trg_append_only_outbox_delivery_attempts
            BEFORE UPDATE OR DELETE ON outbox_delivery_attempts
            FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation();
    END IF;
END $$;

COMMIT;
