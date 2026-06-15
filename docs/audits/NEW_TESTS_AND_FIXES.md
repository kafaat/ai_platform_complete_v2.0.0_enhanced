# الجولة الرابعة — إصلاح كل الأخطاء + اختبار الجوانب غير المُختبَرة

استجابةً لـ"أصلح كل الأخطاء واختبر الجوانب التي لم تُختبَر". الكل **مُتحقَّق حيًّا**.

## أ) اختبارات جديدة لجوانب لم تُختبَر سابقاً

### ١) إنفاذ عزل المستأجرين RLS — `tests_v9/test_rls_enforcement.sh` (10/10 ✅)
لم يكن العزل مُختبَراً فعليًّا (فقط أنّه مُفعّل). الاختبار يطبّق الترحيلات على
قاعدة جديدة، ثمّ عبر **دور غير ممتاز** (محاكاة الإنتاج) يثبت:
- مستأجر A يرى صفّه فقط، **لا يرى صفّ B** (والعكس).
- بلا `app.current_tenant` ⇒ لا يُرى أيّ صفّ.
- `WITH CHECK` يرفض كتابة صفّ بـtenant مغاير للسياق.

### ٢) functional للخدمات — `tests_v9/test_services_functional.py` (10/10 ✅)
ضد Postgres حقيقي:
- **soil-service**: تحقّق **H5 end-to-end** — إدخال قراءة بـNPK واسترجاعها؛
  NPK يدور كاملًا (n=45, p=12.5, k=88) عبر المخطّط الفعلي + الحقول الأساسيّة.
- **guardrails**: إنفاذ توكن `/validate` (L5 + fail-closed).

### ٣) auth-service e2e — `tests_v9/test_auth_e2e.py` (10/10 ✅)
تدفّق المصادقة الحقيقي (bcrypt + Postgres + Redis):
register → login → `/auth/me`، رفض كلمة المرور الخاطئة، رفض البريد المكرّر،
و**منع تصعيد الصلاحيّات** (دور العميل 'owner' يُتجاهَل ⇒ 'farmer' خادم-جانبيًّا).

## ب) أخطاء جديدة اكتشفها الاختبار — وأُصلحت

### ① RLS غير مفروض على 19 من 26 جدولًا (تسرّب عبر المستأجرين) — مُصلَح
كان **7 جداول فقط** تستخدم `FORCE ROW LEVEL SECURITY`؛ الـ19 الباقية (منها
`events, commands, field_boundaries, users, audit_log, field_lifecycle,
ndvi_timeseries, edge_results, approval_workflows, sharing_keys`) تُفعّل RLS
دون FORCE — فإن اتّصل التطبيق بدور **مالك الجدول** تُتجاوَز سياسة العزل.
- **الإصلاح**: `migrations/v9_rls_force_all.sql` (يُطبَّق أخيراً) يفرض RLS على
  كلّ جدول مُفعَّل. تحقّق: **26/26 مفروضة الآن** (كان 7).
- **ملاحظة تشغيليّة موثّقة**: دور تطبيق الإنتاج يجب ألّا يكون superuser/BYPASSRLS.

### ② `statement_cache_size` في `server_settings` ⇒ فشل اتصال كل الخدمات — مُصلَح
`statement_cache_size` معامل **عميل asyncpg** لا إعداد خادم. تمريره في
`server_settings` يجعل asyncpg ينفّذ `SET statement_cache_size` فيفشل الاتصال
بـ`unrecognized configuration parameter` ضد **أيّ** Postgres. أصاب:
- `shared/helpers.py` (مصنع `create_app` ⇒ **كلّ** الخدمات المبنيّة عليه)
- `services/auth/main.py` · `services/soil-service/main.py`
- **الإصلاح**: نقله إلى kwarg مباشر `statement_cache_size=0`. تحقّق: soil/auth
  تُقلعان وتتّصلان وتعملان (الاختبارات أعلاه).

## ج) الـ118 خطأ TypeScript — مُصلَحة بالكامل
`npx tsc --noEmit` = **0 أخطاء** (كان 118 في 12 ملف UI). أُصلحت بأنواع صحيحة
(واجهات لبيانات API، تعميم useState، توقيعات معاملات، فهارس Record) دون تغيير
سلوك التشغيل ودون ترخية tsconfig. وبناء الإنتاج (`vite build`) يبقى ناجحاً.

## ملخّص التحقّق (كله أخضر)
```
verify_review_fixes ......... 23/23 ✅   RLS enforcement ......... 10/10 ✅
platform smoke+e2e .......... 13/13 ✅   services functional ..... 10/10 ✅
auth e2e .................... 10/10 ✅   migrations bootstrap .... 19/19 ✅
frontend tsc ............... 0 errors ✅  npm/pip audit ........... 0 vulns ✅
```
