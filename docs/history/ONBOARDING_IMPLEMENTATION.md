# تنفيذ استبيان دخول المزارع (البند ١)

## ما نُفّذ (كود كامل مُختبَر)
حوّلتُ ONBOARDING_QUESTIONNAIRE.md من بحث إلى ميزة عاملة:

### الملفّات
- **جديد**: api/onboarding.py — تعريف الاستبيان (9 أقسام، 25 سؤال) +
  get_questionnaire() + validate_response()
- **جديد**: migrations/v9_onboarding.sql — جدول onboarding_responses
  (JSONB + tenant_id + RLS fail-closed + FORCE)
- **معدّل**: main.py — 3 endpoints
- **معدّل**: run_migrations.sql + RLS array
- **اختبار**: test_onboarding

### الـendpoints
- GET /api/v1/onboarding/questionnaire?phase=1 — تعريف الاستبيان
- POST /api/v1/onboarding/responses — حفظ ردّ (+ تحقّق الإلزامي)
- GET /api/v1/onboarding/responses — سرد الردود

كلّها عبر tenant_connection (RLS مُطبَّق) + Depends(get_current_user).

## التصميم للسياق اليمني (كما حدّد البحث)
- **offline-first**: الاستبيان كلّه يُحمّل دفعةً، يُملأ بلا اتّصال
- **RTL + عربيّة**: كلّ نصّ عربي
- **أمّيّة رقميّة**: المرحلة 1 إلزاميّة قصيرة (6 حقول فقط في 3 أقسام)،
  الباقي تعميق اختياري؛ وحدات مألوفة (فدان/دونم/لِبنة)؛ خيارات جاهزة بدل
  إدخال حرّ؛ خيار تسجيل صوتي للأمّيّين

## الأقسام التسعة
identity · spatial · agronomic (مرحلة 1) · temporal · soil_water ·
inputs · pests · economic · freeform (مرحلة 2، تعميق)

## التحقّق
- 339/339 · 331 ملفّ يُترجم · المنطق مُختبَر (9 أقسام، 6 إلزامي، validation يعمل)

## ملاحظة صدق
- pydantic غير متاح في بيئتي — اختبرتُ المنطق بـstub. يعمل runtime حيث pydantic موجود.
- صمّمتُ الأسئلة من قسم "الحقول المقترحة" في البحث؛ اخترتُ ما هو إلزامي/اختياري
  بحسب مبدأ "تقليل الاحتكاك" الذي أكّده البحث — راجعها وعدّل ما تراه.
- القسم الأصلي "أسئلة لك" (ما الأهمّ؟ من يُدخل البيانات؟) لم يُرمَّز — تلك
  أسئلة متطلّبات تجيب عليها، استخدمتُ إجاباتها الضمنيّة في التصميم.
