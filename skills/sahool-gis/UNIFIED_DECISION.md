# UNIFIED_DECISION — ملخّص القرار الموحّد ومساحة عمل الحقل

لوحة القرار فوق الخريطة: **القرار الزراعيّ الموحّد** للحقل + **مساحة عمل** تجمع
الحقل + التضاريس + الخطّ الزمنيّ في تجميع عرض واحد.

## API
- `POST /api/v1/crop-twin/decision` (`crop_twin.py:222`) — يُصدر قرار المحصول
  الموحّد (ريّ/تسميد/صحّة) ويُديمه تلقائيّاً في سلسلة النَّسَب إن فُعِّل العلم. توكن.
- `GET /api/v1/fields/{field_id}/workspace?timeline_limit=` (`fields.py:508`) —
  `assemble_workspace`: ملخّص الحقل + طبقات قابلة للتبديل + خطّ زمنيّ. صلاحيّة
  `FIELD_VIEW`.
- (واعٍ بالربح) `POST /api/v1/crop-twin/decision/profit-aware` (`crop_twin.py:349`).

## المدخلات (شكل)
- `decision` (`CropDecisionRequest`): `field_id`، `crop`، `forecast`
  (`[{et0_mm,kc?,rain_mm,runoff_mm}]`)، `management`، `policy`، حدود الريّ… (قرار
  نقيّ، حسابيّ). `profit-aware` يضيف مدخلات اقتصاديّة + `auto_policy`.
- `workspace`: query `timeline_limit` (افتراضيّ 50، يُقصّ [1..500]).

## المخرجات (شكل، من الموجِّه)
- `crop-twin/decision` (`crop_twin.py:214`): كائن `decision` فيه `field_id`،
  `dynamic_kc`، `irrigation_plan` (`plan.to_dict()`)، `decision_id`، `lineage`،
  و`persisted` (`true/false` — إدامة best-effort لا تكسر القرار)، إضافةً لمخرجات
  `unified_decision` (توصية/ثقة/حالة).
- `workspace` (`field_workspace.py:131`):
```jsonc
{ "field_id":"…","display_only":true,
  "field": { "name_ar":"…","crop":"…","area_ha":23.5,"soil_type":"…" },
  "layers": [ { "key":"ndvi","label_ar":"…","category":"vegetation",
                "available":false,"status":"on_demand|available|missing",
                "display_only":true,"note_ar":"…" }, … ],
  "timeline": [ { "occurred_at":"…","event_type":"…","op_ar":"…","category":"…","issue_tags":[] } ]
  /* + terrain من enrich_terrain */ }
```

## empty/loading/error
- **empty:** `layers[*].available=false` ⇒ اعرض الطبقة معطّلة بـ`note_ar` (لا تلوين).
  `timeline:[]` ⇒ «لا أحداث» (من أحداث مسجّلة فقط).
- **error:** `workspace`: `404` (الحقل ليس للمستأجِر)، `503` (قاعدة). `decision`
  حسابيّ بحت (`422` على مدخل غير صالح).

## tenant/RLS
- `workspace` عبر `tenant_connection` (RLS) بـ`FIELD_VIEW` — يقرأ الحقل + الأحداث
  المعزولة. `decision` بتوكن؛ إدامته (`persist_decision_if_enabled`) معزولة بالمستأجِر.

## قاعدة عدم الاختلاق
- `workspace` نفسها تُجسّد القاعدة: **كلّ طبقة تُعلن توفّرها** (`available/status/
  note_ar`) والخطّ الزمنيّ من **أحداث مسجّلة فقط**. اعرض هذا كما هو ولا تُفعّل طبقة
  «غير متوفّرة». `display_only:true` ⇒ تجميع عرض، **ليس قراراً** — القرار من
  `crop-twin/decision`. اعرض `persisted=false` بصدق (لم يُلتقَط في السلسلة).

## ربط field_id الحقيقيّ
- كلاهما `field-scoped` بـ`field_id` (الحقل النشط `useSelectedField`). `workspace`
  يجمع `field+terrain+events` لنفس الحقل؛ القرار يحمل `field_id` و`lineage`.

## مثال نداء
```ts
const ws = await kongApi.get(`/api/v1/fields/${fieldId}/workspace`,
  { params: { timeline_limit: 50 } }).then(r => r.data);
const dec = await kongApi.post('/api/v1/crop-twin/decision',
  { field_id: fieldId, crop, forecast, management, policy }).then(r => r.data);
// ارسم فقط الطبقات: ws.layers.filter(l => l.available)
```
