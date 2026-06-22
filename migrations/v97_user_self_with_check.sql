-- v97: إصلاح سياسة RLS «user_self» على جدول users — إضافة WITH CHECK صريح.
--
-- السبب الجذريّ: سياسة user_self (v9_foundation) عُرّفت بـUSING فقط. في PostgreSQL،
-- حين تُحذَف WITH CHECK تُستخدَم USING نفسها كشرط إدراج. ونقطة /auth/register تُدرج
-- مستخدِماً جديداً بمستأجِر جديد (tenant_id افتراضه gen_random_uuid) دون ضبط أيّ
-- سياق app.current_* (تسجيل تأسيسيّ) ⇒ لا يتحقّق أيّ من شروط USING ⇒
-- asyncpg InsufficientPrivilegeError: new row violates RLS policy for table "users".
--
-- الإصلاح: WITH CHECK صريح يسمح بالكتابة في ثلاث حالات: (١) لا سياق مستأجِر = تسجيل
-- تأسيسيّ (auth-service الموثوق وحده يكتب users)، (٢) تطابق المستأجِر، (٣) دور admin.
-- نفس نمط tenant_isolation المعتمَد (v96 وغيره: «IS NULL OR match»). idempotent وآمن
-- على إعادة التطبيق (DROP IF EXISTS + CREATE).

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'users') THEN
        EXECUTE 'DROP POLICY IF EXISTS user_self ON users';
        EXECUTE $ddl$
            CREATE POLICY user_self ON users
            USING (
                id::TEXT = NULLIF(current_setting('app.current_user_id', true), '')
                OR tenant_id::TEXT = NULLIF(current_setting('app.current_tenant', true), '')
                OR current_setting('app.current_role', true) = 'admin'
            )
            WITH CHECK (
                NULLIF(current_setting('app.current_tenant', true), '') IS NULL
                OR tenant_id::TEXT = current_setting('app.current_tenant', true)
                OR current_setting('app.current_role', true) = 'admin'
            )
        $ddl$;
    END IF;
END $$;
