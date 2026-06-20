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
| WEATHER_STATION_SKILL | ⏳ | محطّة طقس: قياسات/معايرة/قواعد صحّة |
| SOIL_SENSOR_SKILL | ⏳ | رطوبة التربة موحّدة عبر Capacitive/TDR/FDR/Tensiometer |
| FLOW_METER_SKILL · VALVE_SKILL · PUMP_SKILL · PIVOT_CONTROLLER_SKILL | ⏳ | Water OS: قياس/أوامر (طبقة Execution بحُرّاسها) |
| DRONE_SKILL | ⏳ | كاميرا متعدّدة الأطياف (Crop Twin/Stress) |

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
