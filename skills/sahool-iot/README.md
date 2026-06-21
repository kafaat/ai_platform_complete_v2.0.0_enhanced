# sahool-iot-skills — حزمة مهارات IoT الداخليّة لِسهول

عائلة مهارات الأجهزة: تحوّل خبرة **طبقة تجريد الأجهزة الزراعيّة** (Device Abstraction)
إلى **Skills قابلة للاستدعاء** على البنية القائمة (`iot_devices` + `device_telemetry`،
بلا SDK جديد) — تماماً كنمط `sahool-gis-skills`. الوكيل لا يخترع تكامل جهاز من الصفر،
بل يقرأ المهارة فيعرف: أيّ API حقيقيّ، شكل القياس، قواعد الصحّة/التنبيه، حُرّاس tenant/RLS،
**قاعدة عدم الاختلاق**، واختبارات القبول.

> الفكرة المنقولة من نمط ClientX-skills: **لا ننقل SDK، ننقل عقد المهارة**. هنا نطبّقه
> على الأجهزة — لِيرى Crop Twin مفهوماً موحَّداً (مثلاً `soil_moisture`) أيّاً كان نوع
> الحسّاس المنتِج له (Capacitive/TDR/FDR/Tensiometer).

## مبدأ جوهريّ: ليس كلّ حسّاس موثوقاً

كلّ قراءة جهاز تحمل **ثقة**: جهاز صامت منذ يومين، أو بطّاريّته منخفضة، أو معايرته قديمة
⇒ قراءته أضعف. لذا تُغذّي مهارات الأجهزة طبقة **Sensor Confidence** التي تدخل لاحقاً في:

```
Decision Confidence = Satellite + Weather + Sensor Confidence + Evidence
```

## عائلة المهارات (مُخطَّطة — تُبنى تدريجيّاً)

| المهارة | الحالة | الغرض |
|---|---|---|
| [DEVICE_TWIN.md](DEVICE_TWIN.md) | ✅ مبنيّة | توأم رقميّ + درجة صحّة/ثقة لكلّ جهاز (`GET /devices/twin`) |
| [WEATHER_STATION.md](WEATHER_STATION.md) | ✅ مبنيّة | محطّة طقس: قياسات/معايرة/صحّة ⇒ ET₀/تنبيهات (قراءة فقط) |
| [SOIL_SENSOR.md](SOIL_SENSOR.md) | ✅ مبنيّة | رطوبة تربة موحّدة (`soil_moisture`) عبر Capacitive/TDR/FDR/Tensiometer |
| [WATER_METER.md](WATER_METER.md) | ✅ مبنيّة | عدّاد تدفّق/حجم (Water OS): المُنفَّذ المقيس ⇒ EXECUTION_FEEDBACK |
| [ACTUATOR.md](ACTUATOR.md) | ✅ مبنيّة | صمّام/مضخّة/محور — **حالة قراءة فقط؛ الأوامر مؤجَّلة خلف Execution** |
| DRONE_SKILL | ⏳ | كاميرا متعدّدة الأطياف (Crop Twin/Stress) — يحتاج بيانات/تكامل فعليّ |

كلّ مهارة جهاز تُحدّد: **Capabilities · Protocols · Telemetry schema · Commands ·
Calibration · Health rules · Alert rules · Decision impact** + عقد المهارة الثمانيّ
(الغرض/API/المدخلات/المخرجات/empty-error-loading/tenant-RLS/عدم الاختلاق/اختبارات القبول).

## خارطة الطريق (مُحاذاة المراجعة النهائيّة)

- **P0**: Device Registry (موجود: `iot_devices`) · **Device Twin** ✅ · Telemetry Schema (موجود) · **Sensor Confidence** ✅
- **P1**: Irrigation Network Twin (بئر→مضخّة→مرشّح→تسميد→خطّ→صمّام→منطقة) · أوامر Pump/Valve/Pivot (Execution) · Execution Feedback
- **P2**: Drone Skill Pack · Thermal Stress · Leaf Sensors
- **P3**: حسّاسات بحثيّة (Stem Flow · Wearables · Spore)

> **التنفيذ مؤجَّل**: مهارات الأوامر (صمّام/مضخّة/محور) **لا تُنفَّذ** قبل طبقة Execution
> بحُرّاسها (RBAC + permissions + guardrails). المرحلة الحاليّة **قراءة/ثقة فقط**.
