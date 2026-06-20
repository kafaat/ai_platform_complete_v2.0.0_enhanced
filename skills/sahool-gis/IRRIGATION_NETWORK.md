# IRRIGATION_NETWORK — overlay شبكة الريّ (الصمّامات والجداول)

طبقة overlay فوق الخريطة تعرض **صمّامات الريّ** وجداولها لكلّ حقل.

## API
- `GET /api/v1/irrigation/valves` (`irrigation.py:104`) — صمّامات المستأجِر.
  صلاحيّة `IRRIGATION_VIEW`. في الواجهة عبر `fetchValves()` (`api.ts`).
- `GET /api/v1/irrigation/schedules?field_id=` (`irrigation.py:221`) — جداول الريّ
  (تُرشَّح بـ`field_id` اختياريّاً). صلاحيّة `IRRIGATION_VIEW`.
- (كتابة) `POST /irrigation/valves`، `POST /valves/{id}/state`،
  `POST /schedules`، `DELETE /schedules/{id}` — صلاحيّة `IRRIGATION_MANAGE`.

## المدخلات (شكل)
- `valves`: لا جسم. `schedules`: query `field_id` اختياريّ.

## المخرجات (شكل، من الموجِّه)
- `valves` (`irrigation.py:111`):
```json
[ { "valve_id":"vlv_…","name":"…","field_id":"fld_…","device_id":"dev_…|null",
    "valve_type":"main|zone|…","status":"open|closed|…",
    "flow_rate_lpm":120.0,"last_changed_at":"2026-05-01T…|null" } ]
```
- `schedules` (`irrigation.py:240`):
```json
[ { "schedule_id":"sch_…","field_id":"fld_…","valve_id":"vlv_…","name":"…",
    "start_time":"06:00:00|null","duration_min":45,"days_of_week":[0,2,4],
    "water_target_mm":12.0,"enabled":true,"last_run_at":"…|null" } ]
```

## empty/loading/error
- **empty:** مصفوفة فارغة ⇒ «لا صمّامات/جداول مسجّلة» — لا علامات وهميّة على الخريطة.
- **loading/error:** `403` صلاحيّة، `503` قاعدة. اعرض `ErrorState`.

## tenant/RLS
- قراءة عبر `tenant_connection` (RLS) بـ`IRRIGATION_VIEW`. كلّ **كتابة** (تسجيل
  صمّام/تغيير حالة/جدول) معزولة بـRLS وتُصدِر حدث domain (outbox).
- **ملاحظة سيادة:** `POST /valves/{id}/state` **يسجّل النيّة فقط** — لا يُشغّل العتاد
  مباشرةً (التشغيل الفعليّ عبر actuator/automation بموافقة بشريّة HIL).

## قاعدة عدم الاختلاق
- **لا إحداثيّات هندسيّة للصمّام في الـAPI:** الردّ يحمل `field_id`/`device_id` لا
  `lat/lon`. ضع علامة الصمّام على **مركز/هندسة الحقل المرتبط** (أو علامة الجهاز إن
  توفّرت)، ولا تخترع موقعاً دقيقاً للصمّام. اعرض `status` كما رجع لا كحالة مفترضة.

## ربط field_id الحقيقيّ
- كلّ صمّام/جدول يحمل `field_id` ⇒ اربط overlay الريّ بمضلّع ذلك الحقل على الخريطة.
  رشّح الجداول بـ`?field_id=` للحقل النشط.

## مثال نداء
```ts
import { fetchValves } from '../services/api';
const valves = await fetchValves();                                  // Valve[]
const schedules = await kongApi
  .get('/api/v1/irrigation/schedules', { params: { field_id: fieldId } })
  .then(r => r.data);
// ضع العلامة على مركز الحقل المطابق لـ valve.field_id (لا lat/lon مخترع)
```
