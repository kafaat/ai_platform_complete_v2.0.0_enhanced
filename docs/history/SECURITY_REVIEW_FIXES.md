# إصلاح مراجعة أمنيّة — 4 ثغرات

تحقّقتُ من كلّ ادّعاء بالكود الفعلي قبل الإصلاح. النتيجة:

## ✅ حُلّت (3 حرجة + 1 متوسطة)

### ١. عدم تطابق اسم متغيّر JWT (حرجة — مؤكّدة)
المنصّة تقرأ SAHOOL_JWT_SECRET لكن compose يمرّر JWT_SECRET فقط →
المنصّة تسقط على dev-secret بينما auth يوقّع بالحقيقي → كلّ توكن يُرفض 401.
الإصلاح: compose يمرّر الآن SAHOOL_JWT_SECRET + SAHOOL_ENV + SAHOOL_CORS_ORIGINS
(مع إبقاء JWT_SECRET للتوافق). نفس السرّ على الجانبين.

### ٢. تصعيد صلاحيات في /auth/register (حرجة — مؤكّدة)
كان req.role يُدخَل مباشرةً وValidRole يقبل "admin" → أيّ مسجّل بـ
{"role":"admin"} يصبح admin. الإصلاح: INSERT يثبّت 'farmer' خادم-جانبيّاً،
وأُزيل حقل role من RegisterRequest. الترقية فقط عبر /auth/users/{id}/role
المحمي بـrequire_role("admin").

### ٣. عزل المستأجرين RLS غير مُفعّل (حرجة — مؤكّدة جزئيّاً)
السياسات موجودة لبعض الجداول لكن المنصّة لا تنفّذ set_config →
IDOR عبر المستأجرين. الإصلاح:
- tenant_connection(user): context manager يفتح معاملة ويضبط
  app.current_tenant/user_id/role عبر SET LOCAL (آمن مع pooling)
- migrations/v9_rls_tenant_isolation.sql: FORCE RLS + سياسة tenant_isolation
  على fields, field_lifecycle_transitions, field_tasks, agent_queries,
  market_sales_listings (مع حماية: فقط إن وُجد الجدول والعمود)

### ٤. get_current_user يعطي 500 بدل 401 (متوسطة — مؤكّدة)
payload["sub"]/["tenant_id"] مباشر → توكن ناقص يكسر بـ500. الإصلاح:
.get() + تحقّق صريح → 401 "Token missing required claims".

## ملاحظات تصحيحيّة (بصدق)

### ثغرة ٤ في المراجعة (.env في الـzip) — غير صحيحة لحزمتي
المراجعة فحصت حزمة على جهازك حيث .env أُنشئ بأسرار. حزمتي تحوي
.env.example فقط (قوالب) — لا .env حقيقي. تحقّقت: unzip -l لا يُظهر .env.
لكن النصيحة سليمة لجهازك: لا تضمّن .env في أيّ أرشيف توزيع، ودوّر الأسرار.

## مؤجّل (جودة، ليس حرجاً)
- RS256 بدل HS256 (فصل التوقيع عن التحقّق) — تحسين معماري
- توحيد مكتبة JWT (jose في auth، PyJWT في المنصّة)
- name_ar vs full_name (تجميلي، يسقط على "")
- تقسيم main.py (2900 سطر، 149 مسار) إلى APIRouter — تنظيمي

## التحقّق
- 4 إصلاحات مؤكّدة بنيويّاً · auth + platform يُترجمان
- 304/304 اختبار · YAML سليم (31 خدمة)

## ملاحظة صدق (الحدود)
- RLS migration يُطبَّق على قاعدتك:
    psql ... -f migrations/v9_rls_tenant_isolation.sql
  لم أشغّل PostgreSQL (لا بيئة) — تحقّقت من بنية SQL (FORCE + policy + حماية)
- tenant_connection جاهز للاستخدام، لكن endpoints الحاليّة التي تستعلم
  مباشرةً تحتاج تحويلها لاستخدامه تدريجيّاً (دفاع: RLS يحمي حتّى الاستعلام
  غير المُحدَّث لأنّ FORCE مُفعّل + السياسة تُرشّح). الأولويّة: endpoints
  fields/lineage/commands.
- الإصلاحات ١،٢،٤ كاملة وفوريّة. الـ٣ (RLS) بنيتُه كاملاً؛ تفعيله الكامل
  يحتاج تطبيق migration + تحويل الاستعلامات الحسّاسة لـtenant_connection.
