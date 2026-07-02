-- v139 (سطر v39.5-2): جعل تدقيق رسم حدود الحقل غير قابل للتزوير — append-only.
--
-- field_geometry_history (سجلّ من/متى/ماذا لتعديلات حدود الحقل، v96) كان يوثِّق
-- المراجعات لكنّه لم يفرض immutability فعليّاً: UPDATE/DELETE مسموحان على مستوى
-- القاعدة، فيمكن إعادة كتابة أثر التدقيق بصمت. هذا يفرض append-only عبر trigger
-- ``sahool_block_mutation`` (v9_append_only_enforcement — يسبق هذا في المانيفست)،
-- تماماً كما يُحمى ``mfa_audit_events`` في v129. التصحيح يكون بإدراج مراجعة جديدة
-- (revision جديدة عبر trg_field_geometry_history_revision في v96)، لا بتحوير القديم.
-- إضافيّ idempotent؛ يرث RLS+FORCE من v96؛ بعد v138.

-- تحقّق دفاعيّ: الدالّة المساعِدة يجب أن تكون معرَّفة (v9_append_only_enforcement).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc WHERE proname = 'sahool_block_mutation'
    ) THEN
        RAISE EXCEPTION
            'sahool_block_mutation() مفقودة — طبّق v9_append_only_enforcement.sql أوّلاً';
    END IF;
END$$;

-- append-only: يمنع تزوير تاريخ حدود الحقل (يعتمد الدالّة المُعرَّفة في v9).
DROP TRIGGER IF EXISTS trg_append_only_field_geometry_history ON field_geometry_history;
CREATE TRIGGER trg_append_only_field_geometry_history
    BEFORE UPDATE OR DELETE ON field_geometry_history
    FOR EACH ROW EXECUTE FUNCTION sahool_block_mutation();
