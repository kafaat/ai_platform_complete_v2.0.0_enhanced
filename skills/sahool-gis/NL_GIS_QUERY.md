# NL_GIS_QUERY — استعلام GIS باللغة الطبيعيّة (قراءة فقط)

تحويل طلب المستخدم العربيّ إلى **نيّة من قائمة مغلقة** ثمّ استدعاء **API قراءة موجود**
وعرض معاينة الحقول المطابقة على الخريطة/الجدول. **لا توليد SQL، لا LLM حُرّ، لا طبقة
بلا برهان من API.** هذه مهارة «الوكيل يفسّر، لا يكتب استعلاماً».

## API
- `POST /api/v1/nl-gis/query` (`routers/nl_gis.py`) — محروسة بعلم
  `FEATURE_NATURAL_LANGUAGE_GIS` (مُطفأة افتراضاً ⇒ `404`). صلاحيّة
  `RECOMMENDATION_VIEW`. تُصنّف النصّ عبر الطبقة النقيّة `parse_nl_intent`
  (`api/nl_gis_intent.py`) ثمّ تُرسِل لمصدر قراءة موجود بمعاملات مربوطة.
- المصادر القرائيّة الفعليّة المُستدعاة (لا نقاط جديدة، إعادة استخدام جداول قائمة):
  `alerts ⋈ fields` · `ndvi_timeseries` · `irrigation_schedules.last_run_at`.

## المدخلات (شكل)
- `{ "query": string }` — نصّ عربيّ حُرّ. لا مدخلات أخرى (tenant من JWT لا من النصّ).
- النيّات المدعومة (whitelist مغلقة — `SUPPORTED_INTENTS`):
  - `ndvi_drop` — خانات: `threshold_pct` (افتراضيّ 15، موسوم `threshold_is_default`)، `crop?`، `region?`.
  - `alert_filter` — خانات: `alert_type?` (heat_stress/low_moisture/heavy_rain/disease_risk/frost_risk)، `crop?`، `region?`.
  - `irrigation_gap` — خانات: `days` (افتراضيّ 5، موسوم `days_is_default`)، `crop?`، `region?`.

## المخرجات (شكل، من الموجِّه)
```jsonc
{ "read_only": true,
  "intent": "alert_filter",              // أو ndvi_drop | irrigation_gap | unsupported
  "supported": true,
  "status": "ok",                        // ok | needs_data | unsupported
  "slots": { "crop":"قمح","region":"الجوف","alert_type":"heat_stress" },
  "confidence": 0.84,
  "api_called": "alerts⋈fields",
  "items": [ { "field_id":"field_01","name":"…","crop":"…","gov":"…",
               "alert_type":"heat_stress","severity":"critical","title_ar":"…" } ],
  "count": 1,
  "note_ar": null,                       // سبب صريح عند فراغ/needs_data
  "tenant_id": "…" }
```
- شكل `items` يختلف بالنيّة (NDVI: `ndvi_latest/ndvi_prev/drop_pct/latest_date`؛ الريّ:
  `last_run_at`؛ التنبيهات: `alert_type/severity/title_ar`) — اعرض الأعمدة ديناميّاً.
- سقف صارم `LIMIT 200` (معاينة لا تفريغ كامل).

## empty/loading/error
- **unsupported:** `status:"unsupported"` + `reason_ar` ⇒ اعرض الرفض الصريح + أمثلة موجِّهة. لا تخمين.
- **needs_data:** `status:"needs_data"` + `note_ar` ⇒ المصدر غائب/تعذّر — **لا تعرض جدولاً فارغاً كأنّه نتيجة صفر حقيقيّة**.
- **empty حقيقيّ:** `status:"ok"` و`count:0` + `note_ar` «لا حقول تطابق» (نتيجة صادقة).
- **error:** `404` (الميزة مُطفأة) ⇒ إشعار تفعيل العلم؛ `503` (قاعدة) ⇒ حالة خطأ صادقة.

## tenant/RLS
- `tenant_id` من **JWT حصراً** (`user.tenant_id`) لا من نصّ المستخدم؛ كلّ قراءة عبر
  `tenant_connection` المعزولة بـRLS. RBAC `RECOMMENDATION_VIEW`. كلّ استعلام يُدوَّن في
  سجلّ التدقيق append-only `nl_gis_audit` (v85، RLS+FORCE) — النصّ/النيّة/الخانات/المصدر/الحالة.

## قاعدة عدم الاختلاق
- **لا SQL حُرّ:** الخانات (محصول/منطقة/نوع) من قائمة مفردات معروفة، وتُمرَّر دائماً
  كـ`$n` مربوطة — نصّ المستخدم لا يُدمَج في SQL إطلاقاً.
- **لا طبقة بلا API:** تعذّر المصدر ⇒ `needs_data`؛ لا تُرسَم نتائج مُختلقة.
- **النيّة المنخفضة الثقة/المجهولة ⇒ `unsupported`** لا تنفيذ ظنّيّ. الخانات الافتراضيّة
  (عتبة 15٪/فجوة 5 أيّام) **موسومة** `*_is_default` — اعرضها كافتراض لا كطلب صريح.

## ربط field_id الحقيقيّ
- كلّ عنصر يحمل `field_id` حقيقيّاً من الجداول — اربط النقر بالحقل النشط/الخريطة.
  ملاحظة: العناصر لا تحمل حاليّاً `lat/lon`، فلا تُرسَم علامات على الخريطة دون
  إحداثيّات حقيقيّة (لا تَفبرِك مواقع) — الجدول هو المخرَج الأساسيّ.

## مثال نداء
```ts
const r = await kongApi.post('/api/v1/nl-gis/query',
  { query: 'اعرض حقول القمح في الجوف التي لديها تنبيه حرارة' }).then(x => x.data);
// r.supported===false ⇒ اعرض r.reason_ar؛ r.status==='needs_data' ⇒ اعرض r.note_ar؛
// غير ذلك ارسم r.items في جدول (أعمدة من مفاتيح العنصر) واعرض r.slots كشرائح تفسير.
```

## اختبارات القبول
- علم مُطفأ ⇒ `404`. نيّة خارج القائمة ⇒ `unsupported` (لا استدعاء، لا SQL).
- مصدر غائب ⇒ `needs_data` لا جدول فارغ مُضلِّل. `tenant_id` من JWT فقط (لا من النصّ).
- كلّ استعلام (حتى المرفوض) يُدوَّن في `nl_gis_audit` بـ`read_only=TRUE`.
