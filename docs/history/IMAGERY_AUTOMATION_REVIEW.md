# أتمتة سحب الصور الجوّية + المؤشّرات

## ما كان ناقصاً
raster-service يوفّر بحث الصور (/imagery/search) وحساب المؤشّرات
(/process → NDVI/EVI/...)، لكن لا شيء **يفحص دوريّاً** عن صور Sentinel
جديدة لحقول المستخدم ثمّ **يُطلق** حساب المؤشّرات. دورة Sentinel-2 ~5 أيّام،
فالفحص اليدوي يفوّت صوراً.

## اكتشاف أثناء التنفيذ
raster-service **لم يكن في docker-compose.v9.yml** (موجود في fixed.yml فقط)
— نفس نمط sahool-platform سابقاً. أُضيف للـv9.

## ما بُني
### api/imagery_automation.py (منسّق orchestrator)
- تسجيل حقول (bbox) للمتابعة الدوريّة
- كلّ دورة: يبحث عن صور جديدة عبر raster-service STAC
- يتتبّع last_image_id لكلّ حقل → لا يعيد معالجة القديم
- عند صورة جديدة: يسجّلها + يطلب حساب NDVI عبر /process
- معزول: فشل حقل لا يوقف البقيّة
- صدق: لا حقول → لا يضرب raster-service؛ لا رابط راستر → يسجّل فقط بلا معالجة

### النشر (compose v9)
- أُضيفت خدمة sahool-raster-service (Element84 Earth Search، منفذ 8001)
- أُضيف volume raster-data
- أُضيف RASTER_SERVICE_URL لبيئة sahool-platform (يطابق اسم الخدمة)

### الربط بالـscheduler
- _imagery_sweep مربوط بـscan_new_imagery (كلّ 6 ساعات، دورة القمر ~5 أيّام)
- يعمل تلقائيّاً عند إقلاع المنصّة

### endpoints جديدة (2)
- POST /api/v1/automation/imagery/register-field — سجّل حقلاً (bbox) للمتابعة
- GET  /api/v1/automation/imagery/status — الحقول المتابَعة + آخر صورة/مؤشّر

## كيف يُستخدم
1. POST /automation/imagery/register-field  {"field_id":"fld_1","bbox":[44.3,16.78,44.36,16.81]}
2. الجدولة تفحص صور Sentinel الجديدة كلّ دورة وتحسب NDVI تلقائيّاً
3. GET /automation/imagery/status  ← آخر صورة + رقم مهمّة المؤشّر لكلّ حقل

## التدفّق الكامل المُؤتمت الآن
صورة Sentinel جديدة → كشف تلقائي (scan_all) → حساب NDVI (raster /process)
→ تتبّع job_id → جاهز للقراءة. بلا تدخّل يدوي.

## التحقّق
- backend: 299/299 (+6) · 149 endpoint · 6/6 CERTIFIED
- compose: 31 خدمة (raster مُضاف) · YAML سليم · RASTER_SERVICE_URL متّسق
- اختبار: تسجيل + كشف جديد + حساب مؤشّرات + تتبّع (لا إعادة) + عزل + صدق

## ملاحظة صدق (الحدود)
- اختبرتُ المنطق بـstub لـhttpx (غير متاح في بيئتي، متاح في الحاوية) —
  السحب الفعلي يحتاج raster-service يعمل + شبكة لـElement84
- التتبّع بالذاكرة (last_image_id) — يُفقد عند إعادة تشغيل المنصّة؛ كافٍ
  للأتمتة الدوريّة. للدوام: جدول imagery_tracking (خطوة لاحقة)
- التسجيل بالذاكرة — للحقول الدائمة يُفضّل تحميلها من جدول الحقول عند
  startup (حين يتوفّر pool)
- raster-service يجب أن يكون منشوراً (أُضيف للـv9 الآن) وreachable
