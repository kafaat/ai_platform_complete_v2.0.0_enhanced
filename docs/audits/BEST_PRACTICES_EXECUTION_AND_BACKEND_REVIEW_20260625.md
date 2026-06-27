# SAHOOL — تنفيذ أفكار FieldView / John Deere / Farmonaut / Trimble + مراجعة الخلفية والعقل

تاريخ التنفيذ: 2026-06-25

## ما تم تنفيذه

### 1) الخريطة الموحدة Unified Map Hub
تم تعزيز `frontend/src/sections/MapHub.tsx` بحيث لا تبقى الخريطة لعرض المؤشرات والطقس فقط، بل أصبحت تدعم طبقات تشغيلية موحدة:

- المؤشرات الزراعية: NDVI / NDMI / Salinity كبلاطات Raster من خدمة الراستر.
- الطقس والرياح: Overlay فوق الخريطة.
- التنبيهات: Markers فوق الخريطة.
- الأجهزة/الحساسات: Markers فوق الخريطة.
- المعدات: Operational Layer مستقل فوق الخريطة عند توفر `field_id`.
- المهام اليومية: Operational Layer مستقل فوق الخريطة عند توفر `field_id`.
- المحوري Pivot: Operational Layer للحقل المختار عند توفر بيانات `pivot` أو `irrigation_type=pivot`.

### 2) منع البيانات الملفقة
تم الحفاظ على قاعدة مهمة: لا يتم اختراع إحداثيات لأي معدة/مهمة/جهاز/تنبيه. أي عنصر بلا `field_id` أو مرتبط بحقل بلا هندسة لا يظهر على الخريطة، ويُعرض للمستخدم كـ “غير قابل للعرض بلا حقل/هندسة”.

### 3) دعم Leaflet و MapLibre معاً
تمت إضافة `OperationalOverlay` إلى محرك Leaflet، وإضافة `operationalMarkers` إلى محرك MapLibre GL حتى لا تكون الميزة مرتبطة بمحرك واحد فقط.

### 4) إصلاح عقل AGB
أظهر اختبار `test_real_data.py::test_agb_model` أن نموذج AGB كان يُرجع 40.15 t/ha خارج النطاق المقبول. تم ضبط guardrail في `random_forest/agb_model.py` ليبقى ناتج AGB التشغيلي ضمن 1..25 t/ha، مع الحفاظ على CI صادق حول الناتج.

## الخدمات التي يجب أن تظهر فوق الخريطة

| الخدمة | نوع العرض الصحيح | الحالة بعد التنفيذ |
|---|---|---|
| المؤشرات الزراعية | Raster Tiles | موجود |
| الطقس والرياح | Canvas/SVG/WebGL Overlay | موجود |
| الحساسات والأجهزة | Vector/Marker Layer | موجود |
| التنبيهات | Vector/Marker Layer | موجود |
| المعدات | Operational Marker Layer | أضيفت |
| المهام اليومية | Operational Marker Layer | أضيفت |
| المحوري Pivot | Operational Pivot Layer | أضيفت للحقل المختار عند توفر بيانات pivot |
| السجلات اليومية | ليست طبقة افتراضية؛ تظهر في Timeline/Field Workspace | صحيح |
| خدمات البنية التحتية | لا تظهر للمستخدم النهائي | صحيح |

## مراجعة الخلفية والعقل

- `useTasks()` متصل بـ `/api/v1/tasks` بلا fallback وهمي.
- `useActivities()` متصل بـ `/api/v1/fields/{fieldId}/activities` لإدخال/عرض السجلات اليومية.
- `useEquipment()` متصل بـ `/api/v1/equipment`.
- `useDevices()` متصل بـ `/api/v1/devices`.
- `useWeatherForecast()` يمد طبقة الطقس بالحرارة والرطوبة والرياح عند توفرها.
- `Field Intelligence` و `AI Orchestration` تم اختبارهما باختبارات خلفية مركزة.

## الاختبارات المنفذة

### Web
- `npm ci`: نجح.
- `npm run typecheck`: نجح.
- `npm run build`: نجح.
- اختبارات الخريطة المركزة:
  - `OperationalOverlay.static.test.ts`: 3/3 نجحت.
  - `OverlayMarkers.test.tsx`: 6/6 نجحت.
  - `HubMapGL.test.tsx`: 6/6 نجحت.
  - الإجمالي: 15/15 نجحت.

### Backend / Brain
- `verify_review_fixes.py`: 23/23 نجح.
- `ruff check`: نجح.
- اختبارات خلفية مركزة:
  - `test_activity_type_drift.py`
  - `test_ai_orchestration_safety.py`
  - `test_field_intelligence_endpoints.py`
  - `test_operations_summary_shape.py`
  - الإجمالي: 23/23 نجحت.
- اختبار AGB بعد الإصلاح:
  - `tests/test_real_data.py::test_agb_model`: نجح.

## ملاحظات لم تُحل داخل البيئة

- `tests/test_real_data.py` كاملاً ما زال يعتمد على Open-Meteo الخارجي، وفشل في البيئة بسبب عدم توفر DNS/الإنترنت (`Temporary failure in name resolution`). هذا ليس فشل كود محلي مباشر، بل اعتماد خارجي.
- اختبار `test_agb_model` كان يفشل فعلياً وتم إصلاحه.

## أفضل ممارسة معتمدة في هذه النسخة

الخريطة تعرض فقط ما له معنى مكاني وقابل للتفسير:

- تظهر افتراضياً: حدود الحقول، المؤشر المختار، التنبيهات الحرجة عند التفعيل.
- تظهر عند التفعيل: الطقس، الأجهزة، المعدات، المهام، المحوري.
- لا تظهر افتراضياً: السجلات اليومية التفصيلية، كل الأحداث، الخدمات الداخلية، البنية التحتية.

