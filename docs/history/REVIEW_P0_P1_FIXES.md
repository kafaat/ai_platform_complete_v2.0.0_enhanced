# إصلاح مراجعة P0/P1 (تحقّقتُ من كلّ بند)

## 🔴 P0 — حرج (مُصلَح)

### P0-1: تضارب متغيّر RLS — مؤكّد وأخطر ممّا ذُكر
- v10 (commands, field_lifecycle) + v11 (events) كانت تقرأ app.tenant_id
  بينما كلّ الكود يضبط app.current_tenant → الجداول تحجب كلّ الصفوف.
- **اكتشاف إضافي**: v12 (trueup_calibrations, sharing_keys) فيها نفس الخطأ —
  لم تذكرها المراجعة. أصلحتُ الخمسة (v10×2، v11×1، v12×2).
- الصيغة الموحّدة الآمنة (تطابق نمط v9، تعالج NULL/فارغ):
    tenant_id::TEXT = NULLIF(current_setting('app.current_tenant',true),'')
    OR ... IS NULL OR ... = ''
- اختبار: test_rls_variable_consistency (صفر app.tenant_id، 17 موضع موحّد).

### P0-2: واجهة تمنح admin وهمي — مؤكّد
- tryReal كان يسقط على fallback عند أيّ فشل، وlogin يرجع role:'admin'
  بـdemo_token. أُصلح:
  - login يفشل بوضوح في الإنتاج (لا fallback)؛ التجريب فقط عبر MOCK_MODE صريح
  - دور التجريب = farmer لا admin (في api.ts + useAuth.loginDemo)

## 🟠 P1 — مهم (مُصلَح)

### P1-1: تثبيت الإصدارات
- وحّدتُ الأطر المشتركة عبر 18 خدمة: fastapi==0.115.0، uvicorn==0.30.6،
  pydantic==2.8.2 (مع [email] حيث يلزم). أزال التضارب (كان 3 إصدارات لكلّ).
- صدق: 91 تبعيّة أخرى ما زالت >= — تثبيتها الكامل يحتاج pip-compile مقابل
  فهرس حيّ (الشبكة محظورة في بيئتي). وثّقتُ هذا — يُنفَّذ في CI لديك.

### P1-2: reload=True
- صار reload=os.getenv("SAHOOL_ENV")=="development" (مطفأ في الإنتاج).

### P1-3: raster CORS=* + root
- CORS: الافتراضي الآمن http://localhost:3000 (مطابق لباقي الخدمات).
- Dockerfile: أُضيف useradd -u 10001 + USER appuser + chown /data/rasters
  (الخدمة الـ18 صارت غير root مثل البقيّة).

## التحقّق
- 317/317 (+3 RLS) · 329 ملفّ يُترجم · YAML 31 خدمة
- fastapi/uvicorn/pydantic موحّدة · صفر app.tenant_id

## ملاحظة صدق (الحدود)
- لم أشغّل PostgreSQL — إصلاح RLS تحقّق بنيويّ (توحيد الاسم + الصيغة). التحقّق
  الوظيفي (عزل صفوف فعلي) يحتاج قاعدة حيّة + اختبار P0-1 الذي اقترحته المراجعة.
- التثبيت الكامل لـ91 تبعيّة يحتاج pip-compile (CI لديك) — وحّدتُ الأطر الحرجة
  فقط لأنّ تثبيت إصدار خاطئ أعمى قد يكسر البناء.
- P2/P3 (print→logger، توحيد CORS، فرض طول JWT) لم تُنفَّذ بعد — تحسينات
  جودة، أقلّ أولويّة. أستطيع تنفيذها إن أردت.
