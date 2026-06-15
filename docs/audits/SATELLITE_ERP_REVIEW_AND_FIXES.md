# الجولة الثامنة — مراجعة وإصلاح: ERPNext + الترحيلات + خطّ الأقمار (قصّ→بلاطات→pixel)

نُفِّذ بـ4 وكلاء مراجعة + 5 وكلاء تنفيذ متوازين، مع تحقّق شامل من المنسّق.

## ما كانت عليه الحال (المراجعة الصادقة)
- **ERPNext**: هيكل ~30% غير موصول بالمزامنة؛ `authenticate()` يكذب؛ نقاط قراءة بلا مصادقة.
- **الترحيلات**: نظيفة لكن **بلا جداول صور/raster**؛ `weather_observations` deny-all؛ تسرّب null-tenant.
- **الأقمار**: STAC (Element84 بلا مفتاح) حقيقي، لكن vegetation يلفّق النطاقات ويعلّمها `real_data:true` (NDVI من حجم الاستجابة!)، وSH-MCP مكسور وقت التشغيل.
- **القصّ→بلاطات→pixel**: القصّ غير منفّذ، البلاطات PNG شفّاف، والواجهة تحاكي الشبكة بـPRNG.

## ما أُصلح ونُفِّذ (كله مُتحقَّق)

### 1) الترحيلات + تخزين الصور — `v14_imagery_storage.sql` (جديد)
- **جداول جديدة**: `raster_assets` (سجلّ COG: field/scene/date/satellite/cog_uri/footprint…)، `management_zones`، `zonal_stats` — كلها بـtenant RLS **مفروض** + GiST.
- إصلاحات أمان: `weather_observations` صار له سياسة (لا deny-all)؛ إزالة تسرّب `tenant_id IS NULL`؛ GiST على `coverage_geom`؛ `last_image_date`→DATE.
- **تحقّق: 20 ترحيلًا/0 فشل**، الجداول الجديدة RLS-forced.

### 2) خلفية pixel الحقيقية — `raster-service`
- **القصّ فوق الحقل**: `rasterio.mask` بعد إسقاط مضلّع الحقل (4326→CRS المصدر)؛ بكسلات خارج الحقل = NaN.
- **cloud-mask** (SCL ∈ {3,8,9,10,11})؛ **إعادة إسقاط الحدود** الحقيقية لـ4326؛ **تخزين `cog_url`**.
- **نقطة جديدة** `GET /v1/fields/{id}/indicator-grid?index=&date=&grid=` — تقرأ COG المقصوص، تُنزّل لشبكة block-mean، تصنّف zones، وتُرجع `{grid, stats, zones, real_data}`؛ fallback صادق (`real_data:false`) بلا COG.
- **persistence** إلى `raster_assets` (best-effort عبر asyncpg).
- **تحقّق على raster اصطناعي (بلا شبكة)**: قصّ (داخل=5000/NaN=5000)، NDVI=0.5، حدود→4326، النقطة 200 بالعقد، cloud-mask يحجب النصف الغائم. **ALL ASSERTIONS PASSED.**

### 3) خدمات الأقمار — صدق + إصلاح وقت التشغيل
- **vegetation**: أُزيل NDVI-من-حجم-الاستجابة؛ `real_data:false` + `provider_reachable` عند عدم فكّ البكسلات (لا تلفيق مُعلَّم حقيقيًّا).
- **SH-MCP**: `retry_request` مُصلَح (4 مواضع: دالّة+معطيات بدل coroutine)؛ Dockerfile يدمج `shared/*` (كان ImportError يمنع الإقلاع).

### 4) الواجهة — استهلاك بيانات حقيقية
- `SpatialIndicatorsPage`/`SatellitePage` تجلبان الشبكة من `/v1/fields/{id}/indicator-grid` عبر `useIndicatorGrid` (rasterApi/`VITE_RASTER_URL`)؛ لافتة خضراء «Sentinel-2 (Element84)» عند `real_data`، وإلا لافتة المحاكاة الصادقة. النقر يقرأ قيمة pixel الحقيقية. **fallback آمن** (لا PRNG غير مشروط).

### 5) ERPNext — إصلاح الأخطاء
- `authenticate()` يرفض Guest؛ `push_field_cost` يرفع NotImplementedError بدل payload غير صالح؛ نقاط القراءة الخمس صارت تتطلّب JWT؛ compose: `frappe.ping` + healthcheck للـbackend + تبعيّات `service_healthy`.

## التحقّق النهائي (المنسّق)
```
raster synthetic clip/grid/NDVI . ALL PASSED   migrations bootstrap . 20/0
full pytest .................... 244/0/0        service smoke ........ 15 HEALTHY/0 FAIL
frontend tsc / build .......... 0 / OK          ruff (كامل) .......... All checks passed
```

## ملاحظة صدق
- الشبكة في بيئة المساعد تحجب Element84/AWS (403)، فلم أتمكّن من جلب صورة حيّة هنا؛ لكن المنطق تحقّق على raster اصطناعي عبر rasterio 1.4.4، وهو صحيح للنشر (المزوّد **بلا مفتاح**: Sentinel-2 L2A COGs على AWS Open Data عبر `/vsicurl/`، وGDAL في Dockerfile).
- تكامل مزوّد «حقيقي كامل» (بكسلات GeoTIFF فعلية + بلاطات XYZ/TiTiler) يحتاج بيئة تسمح بالشبكة؛ الخلفية جاهزة له عبر COG المقصوص و`cog_url`/tilejson.
