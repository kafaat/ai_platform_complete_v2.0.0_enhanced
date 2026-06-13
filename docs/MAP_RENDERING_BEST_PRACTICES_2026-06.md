# أفضل الممارسات العالميّة: عرض الخريطة · البلاطات · المؤشّرات · التلوين بالبكسل · الصور الفضائيّة

> بحثٌ ميدانيّ (يونيو ٢٠٢٦) في ممارسات أفضل المنصّات (Climate FieldView · Farmonaut ·
> EOS Crop Monitoring · Sentinel Hub/EO Browser · Development Seed/TiTiler) مع
> **إسقاطٍ على بنية SAHOOL الحاليّة** (raster-service + vegetation-analysis +
> indicators) — تأكيدُ ما هو متوائم، وتوصياتٌ دقيقة للتحسين. المصادر في الأسفل.

## خلاصة تنفيذيّة
بنية SAHOOL **متوائمة بقوّة** مع المعيار العالميّ: خادم بلاطات **COG ديناميكيّ
(TiTiler)** مع `colormap_name`/`rescale`، حفظ المؤشّرات كـ**COG محسّن** (ضغط +
بلاطات + أهرامات)، **قناع غيوم SCL**، إدخال **STAC** (تكديس COGs عبر VRT/`vsicurl`)،
`tilejson` + أصول لكلّ تاريخ، ومؤشّرات متعدّدة (NDVI/EVI/SAVI/NDWI/NDMI/GNDVI).
التحسينات أدناه **صقلٌ** لا إعادة بناء.

---

## ١) البلاطات الديناميكيّة من COG (Dynamic Tiling)
**المعيار:** بدل ما قبل‑التصيير (pre-render)، خادمٌ يقرأ COG الخام ويطبّق
(rescale + إعادة إسقاط + ترميز + colormap) **آنيّاً** لكلّ بلاطة (rio-tiler/TiTiler:
`/cog/tiles/{z}/{x}/{y}.png?url=...&rescale=...&colormap_name=...&expression=...`).
رياضة النطاقات (NDVI) تُمرَّر كـ`expression` فلا حاجة لتخزين كلّ مؤشّر مسبقاً.
**SAHOOL:** ✅ مُطبَّق — `raster-service` يُفوّض لـ`TITILER_URL/cog/tiles/...?colormap_name=...`
ويحفظ COG لكلّ مؤشّر/تاريخ ويُصدِر `tilejson` + `tile_url_template`.
**توصية:** أبقِ خيار `expression` لحساب المؤشّر آنيّاً من COG نطاقات خام (يقلّل التخزين)؛
واستخدم **WebP** لترميز البلاطات (أصغر من PNG ~30% بصريّاً مكافئ).

## ٢) بنية COG الصحيحة (التخزين)
**المعيار:** `BLOCKSIZE=512`، **أهرام داخليّ** (overviews) حتّى يصغر أكبر بُعد دون 512،
ومحاذاة شبكة **Web Mercator** كي تطابق بلاطات الويب. مثال:
`gdal_translate in.tif out.tif -of COG -co COMPRESS=DEFLATE -co BLOCKSIZE=512 -co OVERVIEWS=AUTO`.
**SAHOOL:** ✅ يحفظ COG «محسّن (ضغط + بلاطات + أهرامات)».
**توصية:** ثبّت `BLOCKSIZE=512` صراحةً + `-co OVERVIEW_RESAMPLING=AVERAGE` للمؤشّرات
المستمرّة؛ ولتخديم أسرع فكّر بـ`-co TILING_SCHEME=GoogleMapsCompatible` (محاذاة Mercator).

## ٣) التلوين بالبكسل (Colormaps) — أهمّ نقطة بصريّة
**المعيار:**
- النبات (NDVI): **RdYlGn** (أحمر→أصفر→أخضر) بديهيّ للزراعة.
- **عمى الألوان:** RdYlGn **ليس آمناً** لعمى الأحمر‑أخضر (الأشيع!). الأكثر أماناً
  **viridis/cividis** (موحّد إدراكيّاً، يُطبَع رماديّاً، صديق لعمى الألوان).
- **لا تستخدم rainbow/jet أبداً** (حدود زائفة + غير مقروء لعمى الألوان).
- خرائط الفرق (Δ NDVI بين تاريخين): **مُتباعِدة (diverging)** بمركز صفر (مثل RdBu).
**SAHOOL:** ✅ يستخدم `RdYlGn` (و`RdYlGn_r` للملوحة/الثلج) + `viridis` افتراضيّاً.
**توصية:** أضِف **مفتاح «وضع صديق لعمى الألوان»** يبدّل لـ`cividis`؛ وثبّت
**rescale لكلّ مؤشّر** (NDVI `0,1` أو `-0.2,0.9`؛ NDWI/NDMI `-1,1`) كي تكون الألوان
**قابلة للمقارنة عبر التواريخ** (مفتاح «تطوّر المحصول»)؛ واعرض **مفتاح ألوان (legend)**
دائم + **شريط شفافيّة (opacity)** فوق الأساس.

## ٤) عرض عدّة مؤشّرات (Multi-index UX)
**المعيار:** مبدّل مؤشّر واحد فعّال (NDVI/EVI/NDWI/NDMI/NDRE…)، كلٌّ بـ`colormap`+`rescale`
خاصّين، + شريط زمنيّ بالتاريخ + شفافيّة + legend. أفضل المنصّات (EOS/Sentinel Hub)
تفصل **اختيار المؤشّر** عن **اختيار التاريخ**.
**SAHOOL:** ✅ ٦ مؤشّرات (evalscript) + شريط زمنيّ (NDVI، تمّ بناؤه) + نقر‑التاريخ→طبقة.
**توصية:** عمّم الشريط الزمنيّ ليشمل أيّ مؤشّر مختار (لا NDVI فقط)؛ واجعل كلّ مؤشّر
يحمل `rescale`+`colormap`+`legend` من جدول إعداد واحد (قابل للتوسّع).

## ٥) قناع الغيوم (Cloud Masking) — جودة المؤشّر
**المعيار (Sentinel-2 L2A):**
- **SCL** أفضل طبقة جودة مدمجة لكنّها ليست القرار النهائيّ وحدها. أقنِع الأصناف
  **3 (ظلّ غيوم) · 8 (غيوم متوسّطة) · 9 (غيوم عالية) · 10 (سحب رقيقة/cirrus)**
  (و7/11 للثلج حسب الحاجة).
- **هجين أقوى:** احتمال غيوم (**s2cloudless** أو **Cloud Score+**) كإشارة جودة رئيسة
  + SCL للأصناف الواضحة (ظلّ/ثلج/cirrus).
- **تركيبات زمنيّة (composites):** للمناطق دائمة الغيوم، **أفضل‑بكسل** (أعلى NDVI)
  أو **وسيط (median)** عبر عدّة تواريخ — أفضل‑بكسل يحفظ الوفاء الطيفيّ.
- **درجة غيوم لكلّ تاريخ** (cloudy_pct) لترتيب/إخفاء الأيّام الغائمة في الشريط الزمنيّ.
**SAHOOL:** ✅ يطبّق قناع SCL؛ ✅ يُمرّر `cloudy_pct` لكلّ تاريخ (شريط «إخفاء الأيّام
الغائمة» تمّ بناؤه).
**توصية:** أضِف **Cloud Score+** (أو s2cloudless) فوق SCL كإشارة احتمال (هجين)؛
وادعم **تركيب أفضل‑بكسل/وسيط** أسبوعيّ/نصف‑شهريّ للحقول دائمة الغيوم (يملأ الفجوات).

## ٦) الجلب من مزوّدي الأقمار (Providers)
**المعيار:**
- **STAC** للاكتشاف (Catalog API): استعلم بـ bbox + نافذة زمنيّة + نسبة غيوم،
  واقرأ **أصول COG لكلّ نطاق** عبر `vsicurl`/HTTP بلا تنزيل كامل.
- **Statistical API** (Sentinel Hub/CDSE): احصل **متوسّطات الحقل** (mean/stdev/histogram)
  لمؤشّر دون تنزيل صور — أرخص وأدقّ من التقدير التركيبيّ لقيم الحقل.
- **Process API + evalscript** لتصيير مؤشّر مخصّص خادميّاً.
- **Batch API** للمناطق/المدد الكبيرة إلى تخزين كائنات.
- مصادر مجّانيّة: **CDSE** (Sentinel-2 L2A، STAC) · **Microsoft Planetary Computer**
  (STAC + signed COG) · **Element84 Earth Search**.
**SAHOOL:** ✅ يدمج Sentinel Hub + CDSE (ميتاداتا/قابليّة وصول) + إدخال STAC (VRT لـCOGs).
لكن `vegetation-analysis` يُرجِع قيم مؤشّر **تركيبيّة** (`real_data:false`) للحقل.
**توصية مهمّة (صدق + دقّة):** استبدِل القيم التركيبيّة لـ`vegetation-analysis` بـ
**Statistical API** (CDSE/SH) للحصول على **متوسّط NDVI حقيقيّ للحقل** بثمن زهيد دون
تنزيل صور — يرفع الشريط الزمنيّ من «تقدير» إلى «قياس». (مسار البكسل الحقيقيّ موجود
سلفاً في raster-service؛ هذا يكمّله لقيم القائمة/الشريط.)

## ٧) محرّك الخريطة والرسم (Engine)
**المعيار:** **MapLibre GL** (مفتوح، خلفًا لـMapbox) لبلاطات متّجهة/نقطيّة + تصيير GPU
+ تدوير/ميل؛ Leaflet كافٍ للنقطيّ البسيط. البلاطات (متّجهة ونقطيّة) تتبع **TileJSON**.
أدوات الرسم: مضلّع/دائرة بنصف قطر + تحرير رؤوس (FieldView نمط مرجعيّ).
**SAHOOL:** Leaflet (ويب) + flutter_map (موبايل) + Leaflet Draw + دائرة بنصف قطر (تمّ).
**توصية:** كافٍ حاليّاً؛ إن لزم تصيير NDVI لكلّ بكسل بسلاسة + طبقات كثيفة فكّر
بترقية الويب لـ**MapLibre GL** (تصيير GPU، انتقالات أنعم بين تواريخ المؤشّر).

---

## أولويّات التنفيذ (صقل، لا إعادة بناء)
| # | التحسين | الأثر | الجهد |
|---|---------|-------|------|
| ١ | `rescale` ثابت لكلّ مؤشّر + legend + opacity | مقارنة عبر التواريخ + وضوح | منخفض |
| ٢ | وضع colormap صديق لعمى الألوان (cividis) | وصوليّة | منخفض |
| ٣ | Statistical API لقيم الحقل الحقيقيّة (بدل التركيبيّة) | دقّة + صدق | متوسّط |
| ٤ | Cloud Score+/s2cloudless هجين فوق SCL | جودة المؤشّر | متوسّط |
| ٥ | تركيب أفضل‑بكسل/وسيط للحقول الغائمة | تغطية | متوسّط |
| ٦ | WebP للبلاطات + BLOCKSIZE=512 صريح | أداء/تكلفة | منخفض |
| ٧ | تعميم الشريط الزمنيّ لكلّ المؤشّرات + expression آنيّ | UX + تخزين أقلّ | متوسّط |

> ملاحظة صدق: SAHOOL متوائم بنيويّاً؛ هذه توصيات صقل. أهمّها (٣) — رفع قيم الحقل من
> «تقدير تركيبيّ» إلى «قياس حقيقيّ» عبر Statistical API دون كلفة تنزيل صور.

---

## المصادر
- TiTiler — Dynamic Tiling: https://developmentseed.org/titiler/user_guide/dynamic_tiling/
- rio-tiler (cogeotiff): https://cogeotiff.github.io/rio-tiler/latest/ · https://github.com/cogeotiff/rio-tiler
- COG Talk (Development Seed): https://developmentseed.org/blog/2021-02-02-cog-talk-part-5-rio-tiler/
- Dynamic map tiling with COGs (Kyle Barron): https://kylebarron.dev/blog/cog-mosaic/overview/
- GDAL COG driver: https://gdal.org/en/stable/drivers/raster/cog.html
- COG spec: https://github.com/cogeotiff/cog-spec/blob/master/spec.md
- Cloud-Native Geospatial Guide (COG details): https://guide.cloudnativegeo.org/cloud-optimized-geotiffs/cogs-details.html
- Colormaps لبيانات الأقمار (Off-Nadir Delta): https://offnadir-delta.com/blog/understanding-satellite-data-colormaps
- viridis/cividis لعمى الألوان: https://sjmgarnier.github.io/viridis/ · https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6070163/
- تصوّر NDVI palettes (OpenWeather): https://openweathermap.medium.com/visualisation-of-the-ndvi-index-on-satellite-maps-custom-palettes-for-agricultural-applications-f99b0652f991
- ArcGIS NDVI Colorized: https://pro.arcgis.com/en/pro-app/latest/help/analysis/raster-functions/ndvi-colorized-function.htm
- أقنعة غيوم Sentinel-2 (ClearSKY): https://clearsky.vision/knowledge/best-sentinel-2-cloud-mask-scl-vs-s2cloudless-vs-fmask
- تركيب خالٍ من الغيوم (ScienceDirect): https://www.sciencedirect.com/science/article/pii/S2352340920306314
- Sentinel Hub على CDSE (الوصول + Statistical/Catalog/Batch): https://dataspace.copernicus.eu/analyse/apis/sentinel-hub · https://documentation.dataspace.copernicus.eu/notebook-samples/sentinelhub/introduction_to_SH_APIs.html
- CDSE STAC (Sentinel-2 L2A): https://browser.stac.dataspace.copernicus.eu/collections/sentinel-2-l2a
- MapLibre Style Spec (Sources/TileJSON): https://maplibre.org/maplibre-style-spec/sources/
- EOS Crop Monitoring (صور زراعيّة): https://eos.com/products/crop-monitoring/satellite-images-for-agriculture/
- بلاطات الخرائط (Geoapify): https://www.geoapify.com/map-tiles/
