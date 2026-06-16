-- SAHOOL v61 — migrations/v61_fields_row_version.sql
-- تزامن تفاؤليّ (Optimistic Concurrency) لتعارض تعديلات offline على نفس الحقل.
--
-- المشكلة: عاملان يعدّلان نفس الحقل دون اتّصال، ثمّ يتزامنان ⇒ الكتابة الأخيرة
-- تطمس الأولى بصمت (Last-Write-Wins ضمنيّ). idempotency يمنع تكرار نفس الإعادة،
-- لا تعارض تعديلين متباعدين.
--
-- الحلّ: عمّاد إصدار (row_version) يتزايد مع كلّ تحديث. عند الكتابة، إن مرّر
-- العميل إصداره الأساس (base_version) ولم يطابق الحاليّ ⇒ الخادم يرفض بـ409
-- (تعارض)، فيُعيد العميل المزامنة قبل تطبيق تعديله — لا فقد صامت.
--
-- متوافق رجعيّاً: العملاء الذين لا يرسلون base_version يبقون على السلوك الحاليّ
-- (لا فحص). DEFAULT 1 NOT NULL يملأ الصفوف القائمة. idempotent.

ALTER TABLE fields ADD COLUMN IF NOT EXISTS row_version INTEGER NOT NULL DEFAULT 1;

-- fields محميّ بـRLS أصلاً (v9_rls_tenant_isolation) ⇒ العمود الجديد مشمول.
