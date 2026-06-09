# ربط fetch_weather بـ Open-Meteo (أتمتة حقيقيّة)

## ما كان ناقصاً
endpoints الطقس (/weather/current، /weather/forecast) تعمل **عند الطلب فقط**
— كلّ استدعاء يضرب Open-Meteo. لا سحب دوري استباقي ولا cache.
المهمّة fetch_weather في scheduler كانت **هيكليّة فقط** (غير مربوطة).

## ما بُني الآن
### api/weather_automation.py
- يعيد استخدام connector openmeteo الموجود (fetch_current) — لا تكرار
- تسجيل إحداثيّات الحقول للسحب الدوري (register_location)
- cache بالذاكرة مع TTL (ساعة) — endpoints تقرأ منه بسرعة
- refresh_all(): يسحب لكلّ إحداثيّة، معزول (فشل واحدة لا يوقف البقيّة)
- تقريب الإحداثيّات (3 خانات) يمنع ازدواج طفيف

### الربط بالـscheduler (startup)
- _weather_sweep مربوط بـregister_default_tasks(fetch_weather=...)
- يعمل ضمن دورة الجدولة (الافتراضي: يوميّاً، قابل للضبط)
- صدق: لو لا إحداثيّات مسجّلة → لا يضرب المصدر (note صريح)

### endpoints جديدة (3)
- POST /api/v1/automation/weather/register — سجّل إحداثيّة للسحب التلقائي
- GET  /api/v1/automation/weather/cached — اقرأ آخر طقس مسحوب (سريع)
- GET  /api/v1/automation/weather/status — كم مسجّل/مُخزّن

## كيف يُستخدم
1. سجّل حقلاً: POST /automation/weather/register?lat=16.79&lon=44.33&field_id=fld_1
2. الجدولة تسحب طقسه تلقائيّاً كلّ دورة
3. اقرأ بسرعة: GET /automation/weather/cached?lat=16.79&lon=44.33

## التحقّق
- backend: 293/293 (+5) · 147 endpoint · 6/6 CERTIFIED
- اختبار: تسجيل + cache + عزل الفشل + صدق (بلا إحداثيّات لا سحب)

## ملاحظة صدق (الحدود)
- Open-Meteo مجّاني بلا مفتاح ✓ — لا حاجة لإعداد credentials
- اختبرتُ المنطق بـstub للـconnector (httpx غير متاح في بيئتي، متاح في
  الحاوية) — السحب الفعلي الحيّ يحدث على خادمك
- الـcache بالذاكرة (لا DB) — يُفقد عند إعادة تشغيل الخدمة؛ كافٍ للتحديث
  الدوري، وللتخزين الدائم يلزم جدول طقس (خطوة لاحقة إن رغبت)
- التسجيل بالذاكرة أيضاً — للإحداثيّات الدائمة يُفضّل تحميلها من جدول
  الحقول عند startup (خطوة لاحقة حين يتوفّر pool)
