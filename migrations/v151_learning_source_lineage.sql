-- migrations/v151_learning_source_lineage.sql
--
-- v151: نَسَب مصدر التعلّم (Learning Source Lineage — جسر #2 من تدقيق إغلاق حلقة التوصية).
--
-- المشكلة (بالتدقيق 2026-07-08): online_learning_updates (v119) بلا **رابط مصدر** —
-- يتعذّر إثبات أيّ نتيجة/قرار غيّر السياسة، ولا تمييز التعلّم من الضوضاء (أخطر فجوة).
--
-- الحلّ: أعمدة نَسَب صريحة + حالة قابليّة تتبّع. **متوافق للخلف بأمان**:
--   • كلّ الأعمدة nullable؛ الصفوف القديمة تُبقى traceability_status='unverified' (لا تُكسَر).
--   • الفرض (NOT NULL source) مؤجَّل لـmigration لاحق بعد backfill (نمط «أضِف ثمّ افرض»).
--   • قابليّة التتبّع تُحكَم في طبقة القرار (core.learning_source_lineage) — traceable فقط يُطبَّق.
-- idempotent (ADD COLUMN IF NOT EXISTS). لا RLS جديد (يرث سياسة v119). بعد v150.

BEGIN;

ALTER TABLE online_learning_updates
    ADD COLUMN IF NOT EXISTS source_type          TEXT,
    ADD COLUMN IF NOT EXISTS source_id            TEXT,
    ADD COLUMN IF NOT EXISTS field_id             VARCHAR(50),
    ADD COLUMN IF NOT EXISTS season_id            TEXT,
    ADD COLUMN IF NOT EXISTS recommendation_id    TEXT,
    ADD COLUMN IF NOT EXISTS decision_id          TEXT,
    ADD COLUMN IF NOT EXISTS evidence_snapshot_id TEXT,
    ADD COLUMN IF NOT EXISTS traceability_status  TEXT NOT NULL DEFAULT 'unverified';

-- مجموعة مغلقة لنوع المصدر (تُطابِق core.learning_source_lineage.VALID_SOURCE_TYPES).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_oluj_source_type'
    ) THEN
        ALTER TABLE online_learning_updates
            ADD CONSTRAINT chk_oluj_source_type CHECK (
                source_type IS NULL OR source_type IN
                ('recommendation_outcome', 'outcome_record', 'execution_feedback', 'human_feedback')
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chk_oluj_traceability_status'
    ) THEN
        ALTER TABLE online_learning_updates
            ADD CONSTRAINT chk_oluj_traceability_status CHECK (
                traceability_status IN
                ('traceable', 'pending_review', 'rejected_untraceable', 'unverified')
            );
    END IF;
END $$;

-- فهرس جزئيّ للاستعلام السريع عن غير-المُتتبَّع (للمراجعة/الحارس).
CREATE INDEX IF NOT EXISTS idx_oluj_untraceable
    ON online_learning_updates (tenant_id, traceability_status)
    WHERE traceability_status <> 'traceable';

COMMENT ON COLUMN online_learning_updates.source_type IS
    'نوع مصدر التعلّم (recommendation_outcome/outcome_record/execution_feedback/human_feedback) — جسر #2';
COMMENT ON COLUMN online_learning_updates.traceability_status IS
    'قابليّة التتبّع: traceable يُطبَّق؛ pending_review/rejected_untraceable/unverified لا تُطبِّق سياسة';

COMMIT;
