# sahool-gis-skills — حزمة مهارات GIS الداخليّة لِسهول

توثيق **قدرات GIS القابلة للاستدعاء** على البنية الحاليّة لِسهول (بلا SDK جديد).
يستعملها وكيل (Codex/Claude) عند توليد أو تعديل **شاشات الخرائط** — بدل كتابة صفحة
خريطة من الصفر، يقرأ المهارة المناسبة فيعرف: أيّ API حقيقيّ يستعمل، شكل المدخلات
والمخرجات (من الموجِّه الفعليّ)، حالات empty/loading/error، قواعد tenant/RLS،
**قاعدة عدم الاختلاق**، وكيف يربط الخريطة بـ`field_id` حقيقيّ.

> مستلهَمة من نمط ClientX-skills لكن مُكيَّفة لِسهول والبنية القائمة. كلّ نقطة
> هنا **مُتحقَّق منها من الكود** في `services/sahool-platform/api/routers/` و
> `frontend/src/services/api.ts`. لا اختراع نقاط ولا أشكال.

---

## جدول المهارات

| المهارة | الملفّ | النقاط الأساسيّة | الطبقة |
|---|---|---|---|
| عارض الخريطة (react-leaflet 2D) | [MAP_VIEWER.md](MAP_VIEWER.md) | `GET /api/v1/fields` | أساس |
| حدود الحقل | [FIELD_BOUNDARY.md](FIELD_BOUNDARY.md) | `GET /fields`، `GET /fields/{id}`، `POST /fields/{id}/boundary/score\|clean` | متّجهات |
| طبقات الراستر (NDVI/NDRE/LAI) | [RASTER_LAYER.md](RASTER_LAYER.md) | `POST /fields/{id}/ndvi-analysis`، `GET /fields/{id}/water-stress-spectral`، `GET /indices/coverage-report` + خدمتا raster/vegetation | راستر |
| الخطّ الزمنيّ التاريخيّ | [NDVI_TIMELINE.md](NDVI_TIMELINE.md) | `GET /fields/{id}/unified-timeline\|history`، `POST /fields/{id}/timeline` | زمن |
| popup قيم pixel/field | [PIXEL_FIELD_POPUP.md](PIXEL_FIELD_POPUP.md) | `POST /fields/{id}/ndvi-analysis` | تفاعل |
| تقطيع المحوريّ/المناطق | [PIVOT_SEGMENTATION.md](PIVOT_SEGMENTATION.md) | `POST /fields/{id}/zones`، `POST /gis/{buffer,union,split,validate}` | متّجهات |
| التضاريس DEM | [TERRAIN_DEM.md](TERRAIN_DEM.md) | `GET /fields/{id}/terrain` | راستر/سياق |
| شبكة الريّ | [IRRIGATION_NETWORK.md](IRRIGATION_NETWORK.md) | `GET /irrigation/valves\|schedules` | overlay |
| المعدّات والأجهزة | [EQUIPMENT_OVERLAY.md](EQUIPMENT_OVERLAY.md) | `GET /equipment`، `GET /devices`، `GET /devices/{id}/telemetry` | overlay |
| تصدير لقطة وتقرير | [EXPORT_SNAPSHOT.md](EXPORT_SNAPSHOT.md) | canvas + `POST /fields/{id}/walk-plan/pdf` | تصدير |
| القرار الموحّد | [UNIFIED_DECISION.md](UNIFIED_DECISION.md) | `POST /crop-twin/decision`، `GET /fields/{id}/workspace` | قرار |
| GIS باللغة الطبيعيّة (قراءة فقط) | [NL_GIS_QUERY.md](NL_GIS_QUERY.md) | `POST /nl-gis/query` (نيّات مغلقة → `alerts⋈fields`/`ndvi_timeseries`/`irrigation_schedules`) | لغة→نيّة |

---

## عائلات المهارات (Skill Families)

الفكرة الجوهريّة المُستنبَطة من نمط ClientX-skills: **لا ننقل SDK، ننقل عقد المهارة** —
الوكيل لا يكتب شاشة من الصفر، بل **يركّبها من مهارات موثوقة مقيَّدة بالبيانات الحقيقيّة**.
كلّ مهارة تُحدّد ثمانية أقسام إلزاميّة: الغرض · API · المدخلات · المخرجات · empty/loading/
error · tenant/RLS · قاعدة عدم الاختلاق · ربط `field_id` · اختبارات القبول.

تنتظم المهارات في أربع عائلات:

| العائلة | المهارات | الغرض |
|---|---|---|
| **GIS Skills** | MAP_VIEWER · FIELD_BOUNDARY · RASTER_LAYER · NDVI_TIMELINE · PIXEL_FIELD_POPUP · PIVOT_SEGMENTATION · TERRAIN_DEM · IRRIGATION_NETWORK · EQUIPMENT_OVERLAY · EXPORT_SNAPSHOT | طبقات الخريطة وتفاعلها على Leaflet/PostGIS/TiTiler |
| **Crop-Decision Skills** | UNIFIED_DECISION · (مرجع: Portfolio Command · Scenario Compare · Decision Studio) | تحويل القرار الزراعيّ الموحّد إلى لوحة/مقارنة فوق الخريطة |
| **Evidence Skills** | (مُخطَّط: EVIDENCE_MAP · AGRONOMIC_REPLAY) | عرض **مستوى الدليل** (مؤكَّد/مدعوم/إرشاديّ/needs_data) لا النتيجة وحدها |
| **Operations-Wall Skills** | (مرجع: Operation Center Wall) · NL_GIS_QUERY | تلخيص تشغيليّ + استعلام لُغة-طبيعيّة قراءة فقط بنيّات مغلقة |

## خارطة الطريق (مُحاذاة المراجعة النهائيّة)

1. ✅ **SAHOOL GIS Skills Pack** — هذه الحزمة (عقد المهارة الثمانيّ).
2. ✅ **Field Workspace Map Card** — `FieldWorkspaceMapCard.tsx` فوق `assemble_workspace`.
3. ✅ **Natural Language GIS (read-only)** — `NL_GIS_QUERY` + `POST /nl-gis/query` خلف علم.
4. ⏳ **Evidence / Replay Map** — خريطة تعرض مستوى الدليل + إعادة تشغيل الموسم (NDVI/طقس/ريّ/قرار/نتيجة/دليل على خطّ زمنيّ واحد).
5. ⏸ **CesiumJS Field 3D Workbench** — **تطبيق مستقل** `apps/field-3d-workbench/` لاحقاً (terrain/DEM، حدود، شبكة ريّ، محاور، آبار، معدّات، NDVI مُسقَط، خطّ زمنيّ) — **بعد** تثبيت 3 و4، لا داخل الواجهة الرئيسيّة، ولا SuperMap/ClientX/Tianditu.

> **لا يُنقَل**: SuperMap ClientX / SuperMap3D / Tianditu (SDK مملوك، سياق صينيّ، تبعيّة
> ثقيلة، لا يخدم اليمن، يكسر بنية Leaflet/PostGIS/TiTiler/STAC). **يُنقَل**: *نمط*
> ClientX-Skills — واجهات وخرائط يركّبها الوكيل من مهارات موثوقة مقيَّدة بالبيانات الحقيقيّة.

---

## مبادئ عامّة (تُطبَّق على كلّ مهارة)

### 1) الصدق وقاعدة عدم الاختلاق (Anti-Fabrication)
- **لا تعرض طبقة إن لم يُرجِعها API.** إن غاب المصدر (لا صورة صافية، لا قيمة
  مخزّنة) فالطبقة **`missing` / `on_demand`** لا تلوين مفبرك. هذا منطق الخادم نفسه:
  `assemble_workspace` تُعلن لكلّ طبقة `available/status/note_ar`
  (`core/engines/field_workspace.py`).
- **لا قيمة بلا بيانات.** `analyze_ndvi_series` تُرجع `trend:"insufficient"` و
  `health_class:"unknown"` + `note_ar` عند نقص السلسلة — اعرض الحالة كما هي ولا
  تستبدلها بقيمة افتراضيّة.
- المؤشّرات الطيفيّة من `vegetation-analysis-service` **تقدير تركيبيّ موسوم**
  (`real_data=False`)؛ البكسل الحقيقيّ في `raster-service`. ميّزهما في الواجهة.

### 2) لا mock في الإنتاج
- بعض دوالّ `api.ts` تمرّر دالّة fallback ثانية (مثل `useCurrentNDVI`) — تلك
  **للتطوير المحلّيّ فقط** وتُحكَم بـ`VITE_MOCK_MODE`/`IS_LOCAL`. لا تُدخِل بيانات
  وهميّة جديدة في مسار الإنتاج. الفشل يُعرَض بصدق عبر `ErrorState`.
- المصفوفات الثابتة في أسفل `api.ts` (`field_01…`) بيانات عرض تجريبيّة — لا
  تستعملها كمصدر للخريطة الحقيقيّة.

### 3) tenant / RLS
- **كلّ كتابة** تمرّ عبر `tenant_connection(user)` المعزولة بـRLS — لا يُرى/يُكتَب
  إلّا سجلّ المستأجِر. **كلّ قراءة** تتطلّب توكناً (`Depends(require_permission(...))`
  أو `get_current_user`).
- الواجهة تُرفِق التوكن آليّاً عبر `kongApi` (interceptor في
  `frontend/src/services/api.ts`). نقاط `field-scoped` تتحقّق أنّ الحقل يخصّ
  المستأجِر وترفع `404` وإلّا.
- `403` = صلاحيّة ناقصة؛ `404` = الحقل ليس للمستأجِر (أو غير موجود)؛
  `503` = القاعدة غير متاحة (اعرضه صريحاً، لا بيانات بديلة).

### 4) عملاء الـAPI في الواجهة (من `frontend/src/services/api.ts`)
- `kongApi` (بوّابة Kong، `VITE_API_URL` / `:8000`) — لكلّ نقاط `/api/v1/*` للمنصّة.
- `vegetationApi` (`:8090`) — تقدير الغطاء التركيبيّ (`/v1/...`).
- `rasterApi` (`:8099`) — البكسل/البلاطات الحقيقيّة (`/tiles/...`, `/info/...`).
- التوكن يُحقَن في `makeClient` interceptor — لا تمرّره يدويّاً.

### 5) الخريطة الأساس
- المكدّس الحاليّ **react-leaflet** (انظر `FarmMapOverview.tsx`). الأساس صور أقمار
  Esri World Imagery. الحقل بهندسة ⇒ `<Polygon>`، وبلا هندسة ⇒ `<CircleMarker>`
  على `lat/lon`. استعمل مساعِدات `lib/geo` (`geomToPolygon`،
  `collectFieldBoundsPoints`، `fieldRepresentativePoint`) ومكوّنات `StateViews`
  (`LoadingState/EmptyState/ErrorState`).

---

## كيف يقرأ الوكيل مهارة
كلّ ملفّ مهارة يتبع القسم الموحّد:
**API** · **المدخلات (شكل)** · **المخرجات (شكل، من الموجِّه)** ·
**empty/loading/error** · **tenant/RLS** · **قاعدة عدم الاختلاق** ·
**ربط field_id الحقيقيّ** · **مثال نداء**.
