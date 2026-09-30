-- SAHOOL — فحوص قراءةٍ فقط قبل ترقية postgis/postgis:15-3.4 ⇒ 15-3.5 (قرار المالك 2026-09-30)
-- تُشغَّل في محرّر الاستعلام بلوحة Railway على sahool-postgres (الإنتاج). لا كتابة، لا DDL.
-- كلّها داخل معاملةٍ للقراءة فقط: أيّ عبارةٍ كاتبة تُرفَض.
BEGIN TRANSACTION READ ONLY;

-- 0) الهويّة: النسخة والإضافات المثبَّتة (قبل postgis_extensions_upgrade)
SELECT version();
SELECT extname, extversion FROM pg_extension ORDER BY 1;
SELECT postgis_full_version();

-- 1) pg_prepared_xacts — يجب أن يكون صفراً قبل تبديل الوسم (معاملةٌ معلّقة تمنع الإقلاع النظيف)
SELECT gid, prepared, owner, database FROM pg_prepared_xacts;

-- 2) replication slots — منفذٌ يتيم يحبس WAL ويملأ القرص بعد الترقية
SELECT slot_name, slot_type, active, restart_lsn, wal_status FROM pg_replication_slots;

-- 3) الأدوار (pg_authid يتطلّب superuser؛ pg_roles نفس الأعمدة بلا كلمة السرّ)
SELECT rolname, rolsuper, rolbypassrls, rolcanlogin, rolreplication FROM pg_roles ORDER BY 1;

-- 4) pg_proc — دوالّ SECURITY DEFINER ومالكوها وsearch_path (تُعاد مراجعتها بعد الترقية)
SELECT n.nspname, p.proname, pg_get_userbyid(p.proowner) AS owner, p.proconfig
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY 1, 2;

-- 5) الترميز والـcollation — يُقرّر هل يلزم REINDEX CONCURRENTLY (صورة Debian ⇒ glibc)
SELECT datname, pg_encoding_to_char(encoding) AS encoding, datcollate, datctype,
       datcollversion, pg_database_collation_actual_version(oid) AS actual_collversion
FROM pg_database WHERE datallowconn ORDER BY 1;

-- 6) حالة الهجرات المقروءة (قرارٌ سابق: «لا تُخطِّط للهجرة التالية قبل أن تعرف ما سبقها»)
SELECT to_regclass('public.decision_service_schema_migrations') AS decision_ledger;
-- إن وُجد السجلّ أعلاه:
-- SELECT * FROM decision_service_schema_migrations ORDER BY 1;

ROLLBACK;
