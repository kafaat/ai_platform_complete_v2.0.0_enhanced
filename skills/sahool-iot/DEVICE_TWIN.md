# DEVICE_TWIN — التوأم الرقميّ للجهاز + ثقة الحسّاس (قراءة فقط)

لكلّ جهاز IoT للمستأجِر: **توأم رقميّ** (هويّة + حالة + صحّة) مع **درجة ثقة شفّافة**
محسوبة من نضارة آخر إرسال/البطّاريّة/عمر المعايرة/جودة الإشارة — أساس `Sensor
Confidence` في ثقة القرار. **لا أوامر تشغيل/إيقاف** (تلك طبقة Execution لاحقاً).

## API
- `GET /api/v1/devices/twin` (`routers/device_twin.py`) — محروسة بعلم
  `FEATURE_DEVICE_TWIN` (مُطفأة افتراضاً ⇒ `404`). صلاحيّة `RECOMMENDATION_VIEW`.
  تقرأ `iot_devices` + أحدث بطّاريّة من `device_telemetry` (best-effort) عبر
  `tenant_connection` (RLS)، وتُشكّل عبر الطبقة النقيّة `shape_device_twin`
  (`api/sensor_confidence.py`).

## المدخلات (شكل)
- لا جسم طلب. المستأجِر من JWT (`user.tenant_id`)، لا من الطلب.

## المخرجات (شكل، من الموجِّه)
```jsonc
{ "generated_at":"…",
  "devices":[ { "device_id":"…","name":"…","type":"weather_station","field_id":"…",
                "status":"online","firmware":"1.4.2","age_sec":600,
                "health_score":0.86,"level":"healthy","level_ar":"سليم",
                "factors":{ "freshness":1.0,"battery":0.6 },     // المتوفّرة فقط
                "missing_signals":["calibration","signal"],       // مُعلَنة لا مُفترَضة
                "note_ar":"…|null" } ],
  "device_count":1,"scored_count":1,
  "by_level":{ "healthy":1,"degraded":0,"stale":0,"offline":0,"poor":0,"unknown":0 },
  "fleet_confidence":0.86,                                        // null إن لا جهاز مُصحَّح
  "provenance":{ "calibrated":"not_applicable","note_ar":"…" }, "tenant_id":"…" }
```
- `level` ∈ `healthy|degraded|stale|offline|poor|unknown`. الأوزان: نضارة 0.5 · بطّاريّة
  0.2 · معايرة 0.2 · إشارة 0.1 (تُطبَّع على المتوفّر فقط).

## empty/loading/error
- **empty:** `devices:[]` ⇒ «لا أجهزة مُسجَّلة». `fleet_confidence:null` ⇒ «غير محسوبة» (لا 0).
- **unknown:** `level:"unknown"` و`health_score:null` ⇒ جهاز بلا إشارة = **needs_data** (رماديّ صريح، لا حالة إيجابيّة).
- **error:** `404` (الميزة مُطفأة) ⇒ إشعار تفعيل العلم؛ `503` ⇒ حالة خطأ صادقة.

## tenant/RLS
- `tenant_id` من JWT حصراً؛ كلّ قراءة عبر `tenant_connection` المعزولة بـRLS. RBAC
  `RECOMMENDATION_VIEW`. **قراءة فقط** — لا UPDATE/INSERT، لا أوامر أجهزة.

## قاعدة عدم الاختلاق
- الدرجة على **الإشارات المتوفّرة فقط**؛ الغائبة في `missing_signals` (لا تُفترَض قيمة).
- جهاز لم يُرَ قطّ (`age_sec=null`، لا إشارة) ⇒ `unknown`/needs_data لا «صحّة افتراضيّة».
- العتبات (ساعة/يوم/3 أيّام، 30/365 يوم معايرة) **تقديريّة موسومة** غير معايَرة.
- `fleet_confidence` متوسّط الدرجات المحسوبة فقط — `unknown` لا يُحتسب (لا تضخيم ثقة).
- `calibrated="not_applicable"` (تجميع عدّ، لا معايرة تنطبق).

## ربط الجهاز/الحقل
- كلّ توأم يحمل `device_id` حقيقيّاً و`field_id` (إن رُبِط) — اربط الجهاز بحقله على الخريطة/اللوحة.

## مثال نداء
```ts
const t = await kongApi.get('/api/v1/devices/twin').then(r => r.data);
// t.fleet_confidence===null ⇒ «غير محسوبة»؛ لكلّ d في t.devices: لوّن بـd.level،
// اعرض d.factors كأشرطة مصغّرة و d.missing_signals كشرائح «غائب»، و d.age_sec كـ«منذ …».
```

## اختبارات القبول
- علم مُطفأ ⇒ `404`. جهاز بلا إشارة ⇒ `unknown` لا أخضر. إشارة غائبة ⇒ تظهر في `missing_signals`.
- `fleet_confidence` يستبعد `unknown`. `tenant_id` من JWT فقط. لا مسار كتابة/أمر في هذه النقطة.
