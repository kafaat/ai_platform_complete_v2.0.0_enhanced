# اختبار عزل المستأجرين (RLS) والترحيل

ملفّان:
- `run_migrations.sql` — يطبّق كلّ الترحيلات بالترتيب الصحيح + يتحقّق من FORCE
- `test_tenant_isolation.sql` — يثبت العزل فعليّاً (لا تسريب + fail-closed)

## الترتيب

### ١. طبّق الترحيلات (من جذر المشروع)
```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f scripts_v9/run_migrations.sql
```
سيطبع جدول حالة RLS — تأكّد أنّ كلّ الجداول الحسّاسة:
`RLS مُفعّل = t` و `FORCE مُفعّل = t`.

### ٢. اختبر العزل (⚠️ بمستخدم عادي لا superuser)
```bash
psql "postgresql://sahool_user:PASS@host:5432/sahool" \
     -v ON_ERROR_STOP=1 -f scripts_v9/test_tenant_isolation.sql
```

## ⚠️ تحذير حرج: superuser يتجاوز RLS

PostgreSQL **يتجاوز RLS تماماً** للأدوار التي لها `SUPERUSER` أو `BYPASSRLS`،
**حتّى مع FORCE**. لو شغّلت الاختبار كـ`postgres` (superuser) ستظهر كلّ الصفوف
وتظنّ خطأً أنّ العزل فاشل.

السكربت يتحقّق من هذا في الخطوة ٠ ويتوقّف لو كان المستخدم superuser. تأكّد
يدويّاً:
```sql
SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user;
-- يجب: f | f
```

**نتيجة مهمّة لتطبيقك**: التطبيق يتّصل بـ`sahool_user`. لو كان `sahool_user`
هو نفسه `POSTGRES_USER` (المالك)، فهو **ليس superuser افتراضيّاً** لكنّه مالك
الجداول — لهذا أضفنا `FORCE` (المالك يتجاوز RLS العادي لكن لا FORCE). تأكّد
أنّ `sahool_user` **ليس** superuser:
```sql
ALTER ROLE sahool_user NOSUPERUSER;  -- لو لزم
```

## ماذا يختبر السكربت

1. **عزل أمامي**: مستأجر A يرى صفوفه فقط، صفر من B
2. **عزل خلفي (IDOR)**: مستأجر B لا يرى أيّ صفّ من A حتّى لو استعلم صراحةً
   بـ`tenant_id` الخاصّ بـA
3. **fail-closed**: اتّصال بلا `app.current_tenant` (محاكاة تجاوز
   tenant_connection) → صفر صفوف (لا تسريب)

يغطّي 3 جداول حسّاسة: `commands`, `events`, `soil_readings`.

## للعمليّات الإداريّة العابرة للمستأجرين

fail-closed يعني أنّ أيّ سكربت إداري بلا ضبط GUC يرى صفر صفوف. أنشئ دوراً
منفصلاً للإدارة:
```sql
CREATE ROLE sahool_admin WITH LOGIN BYPASSRLS PASSWORD '...';
GRANT ALL ON ALL TABLES IN SCHEMA public TO sahool_admin;
```
استخدمه فقط للصيانة، لا للتطبيق.
