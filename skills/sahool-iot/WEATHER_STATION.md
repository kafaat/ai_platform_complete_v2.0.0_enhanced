# WEATHER_STATION — مهارة محطّة الطقس (قراءة فقط)

محطّة طقس ميدانيّة (`iot_devices.type='weather_station'`) تُغذّي ET₀/الريّ/التنبيهات.
هذه المهارة تُحدّد كيف يقرأ الوكيل قياساتها وصحّتها بصدق — **بلا تلفيق، بلا أوامر**.

## القدرات (Capabilities)
- قياسات جوّيّة: حرارة الهواء، الرطوبة النسبيّة، الإشعاع، الرياح، المطر (حسب طُرز المحطّة).
- تُغذّي حساب ET₀ (FAO-56) و`water-balance`/`irrigation-plan` و`heat_stress`/`frost_risk` للتنبيهات.

## البروتوكولات (Protocols)
- الابتلاع عبر مسار telemetry القائم (`device_telemetry`) — MQTT/HTTP حسب البوّابة. لا SDK جديد.

## مخطّط القياس (Telemetry schema)
- `device_telemetry(device_id, sensor_type, value, unit, recorded_at)`؛ `sensor_type` نصّ حرّ
  (مثل `air_temp`/`humidity`/`solar_rad`/`wind`/`rain`). القيمة `NUMERIC` + وحدتها.
- **الصدق**: `sensor_type` غير المعروف يُعرَض كما هو (لا يُخمَّن مفهومه). غياب قياس ⇒ needs_data.

## الأوامر (Commands)
- **لا أوامر** — محطّة قياس. (لا طبقة تنفيذ هنا.)

## المعايرة (Calibration)
- عمر المعايرة من `iot_devices.metadata.calibration_age_days` إن وُجد ⇒ يدخل `Sensor Confidence`
  (DEVICE_TWIN). غيابه يُعلَن (لا يُفترَض حداثة).

## قواعد الصحّة (Health rules)
- عبر `DEVICE_TWIN`: نضارة `last_seen_at` + بطّاريّة + معايرة + إشارة ⇒ مستوى صحّة.
  محطّة صامتة > 24h ⇒ `stale`؛ > 72h أو `status='offline'` ⇒ `offline`؛ بلا إشارة ⇒ `unknown`.

## قواعد التنبيه (Alert rules)
- تُولّد `alerts` (نمط v36): `heat_stress` عند تجاوز حرارة، `frost_risk` عند هبوطها،
  `heavy_rain` عند مطر غزير — كلّها من **قياس فعليّ** لا تقدير.

## أثر القرار (Decision impact)
- مدخل أساسيّ لـET₀ ⇒ يرفع/يخفض احتياج الريّ. في `decision-confidence` يدخل ضمن «نضارة
  الاستشعار/الطقس»؛ محطّة بائتة ⇒ تُخفِّض ثقة قرار الريّ صراحةً.

## tenant/RLS + عدم الاختلاق + القبول
- قراءة عبر `tenant_connection` (RLS)، `RECOMMENDATION_VIEW`. قياس غائب ⇒ needs_data لا قيمة افتراضيّة.
- قبول: جهاز offline ⇒ يُعلَن في `DEVICE_TWIN`؛ لا تنبيه دون قياس؛ لا قيمة طقس مُختلقة في القرار.
