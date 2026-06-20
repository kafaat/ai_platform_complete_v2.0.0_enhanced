# EQUIPMENT_OVERLAY — overlay المعدّات والأجهزة (IoT)

طبقة overlay تعرض **المعدّات** وأجهزة **IoT** وقراءاتها فوق الخريطة/الحقل.

## API
- `GET /api/v1/equipment` (`equipment.py:92`) — معدّات المستأجِر. صلاحيّة
  `EQUIPMENT_VIEW`. واجهة: `fetchEquipment()`.
- `GET /api/v1/devices` (`devices.py:96`) — أجهزة IoT + حالة `online` المحسوبة.
  صلاحيّة `DEVICE_VIEW`. واجهة: `fetchDevices()`.
- `GET /api/v1/devices/{device_id}/telemetry?limit=` (`devices.py:166`) — قراءات
  الجهاز (الأحدث أوّلاً). صلاحيّة `DEVICE_VIEW`. واجهة: `fetchTelemetry(id, limit)`.
- (مساعِد) `GET /api/v1/devices/fleet-health` (`devices.py:191`) — صحّة الأسطول
  (أجهزة صامتة مرتّبة بالخطورة).

## المدخلات (شكل)
- `equipment`/`devices`: لا جسم. `telemetry`: query `limit` (1..1000، افتراضيّ 100).

## المخرجات (شكل، من الموجِّه)
- `equipment` (`equipment.py:99`):
```json
[ { "equipment_id":"eqp_…","name":"…","type":"tractor|…","status":"active|broken|…",
    "operating_hours":1234.0,"purchase_date":"2024-01-01|null" } ]
```
- `devices` (`devices.py:107`):
```json
[ { "device_id":"dev_…","name":"…","type":"soil_moisture|…","field_id":"fld_…|null",
    "status":"online|…","online":true,"last_seen_at":"…|null","firmware_version":"…|null" } ]
```
- `telemetry` (`devices.py:180`):
```json
[ { "sensor_type":"vwc|temp|…","value":0.31,"unit":"%|°C|…","recorded_at":"…|null" } ]
```

## empty/loading/error
- **empty:** مصفوفة فارغة ⇒ «لا معدّات/أجهزة» — لا علامات وهميّة.
- **online=false / last_seen_at=null:** اعرض الجهاز «صامت/غير متّصل» بصدق (الحقل
  محسوب خادميّاً: `last_seen_at > NOW() - نافذة`). لا تُظهره «متّصلاً» افتراضاً.
- **error:** `403` صلاحيّة، `503` قاعدة، `404` (جهاز غير مسجّل عند telemetry).

## tenant/RLS
- كلّها عبر `tenant_connection` (RLS) بصلاحيّات view المناسبة. القراءات تتطلّب توكناً.

## قاعدة عدم الاختلاق
- **لا إحداثيّات للمعدّة/الجهاز في الردّ** (إلّا `field_id` للجهاز). ضع علامة الجهاز
  على **مركز/هندسة الحقل المرتبط** (`device.field_id`) لا على موقع مخترع. المعدّة
  بلا `field_id` ⇒ لا تضعها على الخريطة (اعرضها في قائمة جانبيّة).
- اعرض آخر قراءة من `telemetry` فقط إن وُجدت؛ غيابها ⇒ «لا قراءات» لا قيمة صفر.

## ربط field_id الحقيقيّ
- `device.field_id` يربط الجهاز بمضلّع الحقل. overlay القراءات يُعرَض على الحقل
  المرتبط؛ والمعدّات تُربَط بالحقل عبر سياق العمليّة لا حقل مباشر في الجدول.

## مثال نداء
```ts
import { fetchDevices, fetchTelemetry } from '../services/api';
const devices = await fetchDevices();                     // Device[] (فيها online + field_id)
const points  = await fetchTelemetry(devices[0].device_id, 50); // TelemetryPoint[]
// ضع علامة الجهاز على مركز الحقل = devices[i].field_id (لا lat/lon مخترع)
```
