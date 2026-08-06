# مؤشّرات استشعار التربة عن بعد — لتحديد نوع التربة وتصنيفها

> **الغرض:** الإجابة الكاملة على سؤال: "ما المؤشّرات الفضائيّة لتصنيف التربة؟"
>
> **النتيجة:** ١١ مؤشّر مُختبَر علميّاً، ٧ منها قابلة للتطبيق مباشرة من Sentinel-2
> (مجاني، ١٠م resolution، كلّ ٥ أيّام).

---

## القسم ١: المشكلة الجوهريّة

التربة ليست النباتات. مؤشّرات سهول الـ١٣ الحاليّة (NDVI/EVI/SAVI/NDWI/NDMI/GNDVI/LAI/FAPAR/VARI/GLI/TGI/NDRE/CI_REDEDGE/MCARI) **كلها نباتيّة** — تقيس صحّة الـcanopy، لا تقيس التربة.

**لتصنيف التربة** نحتاج مؤشّرات مختلفة جذريّاً، تستهدف:
- **الـreflectance خصائص التربة العارية** (Visible + NIR + SWIR)
- **سطوع التربة** ← مرتبط بمادة عضويّة (SOM)
- **الـtexture** (رمل/طمي/طين) ← يُستنتج من spectral signature
- **الـmoisture** ← يُؤثّر على البقيّة، يجب أخذه بالحسبان
- **الـsalinity** ← مهمّ جدّاً للسياق اليمني

---

## القسم ٢: المؤشّرات الـ١١ الجوهريّة

### ٢.١ BSI — Bare Soil Index

**الصيغة:**
```
BSI = ((SWIR2 + Red) - (NIR + Blue)) / ((SWIR2 + Red) + (NIR + Blue))
```

**Sentinel-2 bands:** B12 (SWIR2) + B4 (Red) − B8 (NIR) − B2 (Blue)

**الغرض:** فصل التربة العارية عن النباتات والمناطق المبنيّة.

**القيم:**
- `> 0.1`: تربة عارية واضحة
- `-0.1 إلى 0.1`: تربة جزئيّة (vegetation cover خفيف)
- `< -0.1`: غطاء نباتي كثيف

**الأهميّة:** الـ"دخول" لكل تحليل تربة لاحق — أولاً نُحدّد أين التربة العارية، ثمّ نطبّق المؤشّرات الأخرى.

**المرجع:** A study in Italy using Sentinel-2 combined NDVI and BSI and delivered good discrimination between bare soil and other land classes

---

### ٢.٢ BI — Brightness Index

**الصيغة:**
```
BI = sqrt((Red² + Green²) / 2)
```

**Sentinel-2 bands:** B4 (Red) + B3 (Green)

**الغرض:** قياس سطوع التربة. أعلى = تربة فاتحة، أدنى = تربة داكنة.

**العلاقة مع SOM:** "Soil Organic Matter (SOM) content was found to be significantly negatively correlated with the Brightness Index (BI)"

**التفسير:**
- تربة داكنة → سطوع منخفض → SOM عالٍ (مادة عضويّة كثيرة، خصبة)
- تربة فاتحة → سطوع عالٍ → SOM منخفض (فقيرة عضويّاً)

**الاستخدام في سهول:** تقدير أوّلي لـSOM دون تحليل لاب.

---

### ٢.٣ BI2 — Brightness Index 2

**الصيغة:**
```
BI2 = sqrt((Red² + Green² + NIR²) / 3)
```

**Sentinel-2 bands:** B4 + B3 + B8

**الفرق عن BI:** يستخدم NIR إضافي، أدقّ في فصل أنواع التربة المتشابهة.

---

### ٢.٤ HBSI — Hyperspectral Bare Soil Index

**الصيغة (مبسّطة لـSentinel-2):**
```
HBSI = ((SWIR2 + Green) - (Blue + NIR)) / ((SWIR2 + Green) + (Blue + NIR))
```

**Sentinel-2 bands:** B12 + B3 − B2 − B8

**الدقّة:** "the HBSI outperformed other existing bare-soil indices with over 91% accuracy for Sentinel-2 and AVIRIS-NG"

**عند الجمع مع NDVI:** الدقّة ترتفع إلى أكثر من ٩٢٪ مع Sentinel-2.

**الأفضليّة على BSI:** أكثر استقراراً عبر مناطق مختلفة.

---

### ٢.٥ MBI — Modified Bare Soil Index

**الصيغة (Landsat 8 الأصليّة):**
```
MBI = ((SWIR1 - SWIR2 - NIR) / (SWIR1 + SWIR2 + NIR)) + 0.5
```

**Sentinel-2 equivalent:** B11 − B12 − B8

**الغرض:** يعمل بشكل خاص في **agricultural fallow periods** (فترات راحة الأرض). مناسب للمواسم اليمنيّة التقليديّة.

**المرجع:** A Modified Bare Soil Index to Identify Bare Land Features during Agricultural Fallow-Period in Southeast Asia Using Landsat 8

---

### ٢.٦ NDTI — Normalized Difference Tillage Index

**الصيغة:**
```
NDTI = (SWIR1 - SWIR2) / (SWIR1 + SWIR2)
```

**Sentinel-2 bands:** B11 − B12

**الغرض:**
- كشف بقايا المحاصيل crop residue
- التمييز بين أرض محروثة وأرض غير محروثة
- تقدير **conservation tillage** (الزراعة الحافظة)

**القيم:**
- `> 0.1`: أرض غير محروثة، بقايا محاصيل كثيفة
- `< 0`: أرض محروثة حديثاً، تربة عارية

---

### ٢.٧ DBSI — Dry Bare Soil Index ⭐ **(مهمّ للسياق اليمني)**

**الصيغة:**
```
DBSI = ((SWIR1 - Green) / (SWIR1 + Green)) - NDVI
```

**Sentinel-2 bands:** B11 + B3 + NDVI

**الغرض:** صُمّم خصيصاً للمناطق **القاحلة وشبه القاحلة** — أي اليمن بالكامل.

**الميزة:** يفصل التربة الجافّة عن الرمل والمناطق الصخريّة بدقّة أعلى من BSI في الأقاليم الجافّة.

**المرجع:** Multi-Index Approach from Sentinel-2 Imagery uses NDTI for built-up, and both bare soil index (BSI) and dry bare-soil index (DBSI), which are related to bare soil

---

### ٢.٨ NBR2 — Normalized Burn Ratio 2

**الصيغة:**
```
NBR2 = (SWIR1 - SWIR2) / (SWIR1 + SWIR2)
```

**ملاحظة:** نفس صيغة NDTI، لكن استخدام مختلف.

**الغرض في تحليل التربة:** **soil masking** — استبعاد البكسلات التي ليست تربة (ماء، نبات، مبنى).

**القيم:** "over a NBR2 value of about 0.075, less restrictive NBR2 thresholds increased the soil coverage but decreased soil data quality"

**كيفيّة الاستخدام:**
- إن `NBR2 < 0.075` → بكسل تربة موثوق → احسب باقي المؤشّرات
- إن `NBR2 >= 0.075` → بكسل ملوّث (نبات/مبنى) → تجاهله

---

### ٢.٩ SATVI — Soil-Adjusted Total Vegetation Index

**الصيغة:**
```
SATVI = ((SWIR1 - Red) / (SWIR1 + Red + L)) × (1 + L) - (SWIR2 / 2)
```
حيث `L = 0.5` (soil brightness correction factor)

**Sentinel-2 bands:** B11 + B4 + B12

**العلاقة مع SOM:** "Though higher SATVI values indicate denser vegetation but it is also strongly correlated to SOM"

**الاستخدام:** تقدير SOM في مناطق بها غطاء نباتي خفيف (دون BI الذي يتطلّب تربة عارية تماماً).

---

### ٢.١٠ NDSI — Normalized Difference Salinity Index ⭐ **(مهمّ للسياق اليمني)**

**الصيغة:**
```
NDSI = (Red - NIR) / (Red + NIR)
```

**Sentinel-2 bands:** B4 + B8

**الغرض:** كشف الملوحة في التربة (salt affected soils).

**القيم:**
- `> 0.1`: تربة شديدة الملوحة (saline)
- `0 إلى 0.1`: ملوحة متوسّطة
- `< 0`: تربة غير متأثّرة بالملوحة

**أهميّة خاصة للسياق اليمني:** سواحل تهامة، حقول قرب البحر، مناطق غير مصرّفة جيّداً.

**تكميل:** يُقارَن مع نتائج EC من lab samples (في `lab_samples.readings_json`).

---

### ٢.١١ ENDBSI — Enhanced Normalized Difference Bare Soil Index

**الدقّة:** "the ENDBSI demonstrates excellent performance in bare soil identification across all 14 study areas, with an average spectral discrimination index between bare soil and non-bare soil exceeding 2.41 and an average identification accuracy of 94.33%"

**الميزة:** أعلى دقّة (٩٤.٣٣٪) من بين كل المؤشّرات المختبَرة في ١٤ منطقة دراسة مختلفة.

**التطبيق:** للحقول الكبيرة (>٥٠ هكتار) حيث يحتاج المُصنّف دقّة قصوى.

---

## القسم ٣: التطبيق العملي — Workflow لتصنيف التربة

```
┌─────────────────────────────────────────────────────────────┐
│  المدخلات:                                                    │
│   - Sentinel-2 image (B2, B3, B4, B8, B11, B12)             │
│   - حدود الحقل (field polygon)                                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  الخطوة ١: Masking — استبعد ما ليس تربة                       │
│   - احسب NBR2                                                 │
│   - استبعد البكسلات `NBR2 >= 0.075` (نبات/ماء/مبنى)           │
│   - احسب NDVI، استبعد `NDVI > 0.3` (نبات كثيف)                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  الخطوة ٢: كشف التربة العارية — أيّ بكسل تربة؟                  │
│   - احسب BSI                                                  │
│   - أو HBSI للدقّة الأعلى                                       │
│   - أو DBSI إن كانت المنطقة جافّة (يمن، صحراء)                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  الخطوة ٣: استخراج خصائص التربة لكل بكسل                       │
│   - BI → سطوع → تقدير SOM (سلبي: قليل OM = سطوع عالٍ)          │
│   - NDSI → ملوحة (للمناطق الساحليّة)                            │
│   - NDTI → بقايا حراثة                                          │
│   - SATVI → SOM في مناطق بنبات خفيف                            │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  الخطوة ٤: التصنيف — k-means clustering                       │
│   - أدخل ٥-٦ مؤشّرات كـfeatures                                │
│   - k-means → ٣-٦ classes                                     │
│   - كل class = منطقة تربة (zone) متجانسة                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  الخطوة ٥: المُعايرة (Calibration)                              │
│   - خذ ١-٢ عيّنة لاب من كل zone                                │
│   - استخدم النتائج لتسمية الـclasses (sandy/loamy/clay)        │
│   - نَموذج Regression: spectral → texture                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  المخرَجات:                                                    │
│   - خريطة Soil Type per pixel (10م resolution)                │
│   - تحديث field.soil_texture في الـDB                          │
│   - توصيات Zone Sampling بناءً على هذه الزونات الحقيقيّة         │
└─────────────────────────────────────────────────────────────┘
```

---

## القسم ٤: علاقة المؤشّرات بأنواع التربة (Spectral Signatures)

| نوع التربة | BI | BSI | NDSI | SATVI | الملاحظة |
|------------|-----|-----|------|-------|----------|
| **رمليّة (Sandy)** | عالٍ (>0.25) | عالٍ (>0.2) | منخفض | منخفض | فاتحة، عاكسة، قليلة OM |
| **طمييّة (Loamy)** | متوسّط (0.15-0.25) | متوسّط (0.05-0.2) | متفاوت | متوسّط | متوازنة |
| **طينيّة (Clay)** | منخفض (<0.15) | متفاوت | منخفض | عالٍ | داكنة، احتفاظ ماء عالٍ |
| **بركانيّة (Volcanic)** | منخفض جدّاً | متفاوت | منخفض | عالٍ | داكنة جدّاً، خصبة |
| **صخريّة (Rocky)** | عالٍ جدّاً | عالٍ جدّاً | منخفض | منخفض جدّاً | تشبه الرمل لكن أكثر سطوعاً |
| **مالحة (Saline)** | عالٍ | عالٍ | **عالٍ** | منخفض | **NDSI هو الـsignature** |

---

## القسم ٥: الـTriggers والمتطلّبات (ما نحتاج لبنائه)

### ٥.١ ما نملك ✅

- raster-service موجود مع ١٣ مؤشّر نباتي
- بنية تشغيل (FastAPI + xarray + numpy)
- Sentinel-2 STAC search
- bands: B2, B3, B4, B8, B11, B12 متاحة كلّها

### ٥.٢ ما يجب بناؤه (الجلسة الحاليّة) 🟡

```
١. compute_bsi(blue, red, nir, swir2)         → BSI
٢. compute_bi(red, green)                      → BI
٣. compute_bi2(red, green, nir)                → BI2
٤. compute_ndti(swir1, swir2)                  → NDTI
٥. compute_dbsi(green, swir1, ndvi)            → DBSI
٦. compute_ndsi(red, nir)                      → NDSI (salinity)
٧. compute_satvi(red, swir1, swir2)            → SATVI
```

### ٥.٣ ما يُؤجَّل بـtrigger صريح ⏸

```
⏸ k-means clustering للتصنيف:
   trigger: scikit-learn dependency + multiple soil zones per field

⏸ Calibration model (spectral → texture):
   trigger: ١٠٠+ عيّنة تربة بإحداثيّات من الميدان (dataset training)

⏸ HBSI + ENDBSI:
   trigger: hyperspectral data (يحتاج AVIRIS، ليس Sentinel فقط)
```

---

## القسم ٦: التكامل مع نواة سهول

### ٦.١ Soil Indices → Field Soil Texture (auto-classify)

```python
# في indicators-service:
async def auto_classify_field_soil(field_id: str):
    # ١. اجلب آخر Sentinel-2 image
    image = await fetch_sentinel2(field.polygon, date="latest")

    # ٢. احسب المؤشّرات
    bsi = compute_bsi(image.b2, image.b4, image.b8, image.b12)
    bi = compute_bi(image.b4, image.b3)
    ndsi = compute_ndsi(image.b4, image.b8)

    # ٣. صنّف بناءً على القيم
    if bi.mean() > 0.25 and bsi.mean() > 0.2:
        return "sandy"
    elif bi.mean() < 0.15 and satvi.mean() > 0.3:
        return "volcanic"  # شائع في صعدة/ذمار
    elif ndsi.mean() > 0.1:
        return "saline_soil_alert"
    # ... إلخ
```

### ٦.٢ Soil Indices → Zone Sampling Recommendations

```python
# مستقبلاً في zone_sampling.ts:
if has_recent_soil_indices(field):
    # استخدم بدلاً من spatial stratification
    zones = kmeans_cluster(bsi_map, bi_map, ndsi_map, n=4)
    sample_points = one_per_zone(zones)
else:
    # fallback إلى rule-based الحالي
    sample_points = spatial_stratified(field)
```

### ٦.٣ Soil Indices → Alerts

```python
# في recommendation engine:
if ndsi.mean() > 0.1:
    add_recommendation(
        priority="HIGH",
        type="SALINITY_ALERT",
        text="كشف ملوحة عالية من القمر الصناعي. ينصح بأخذ عيّنة EC.",
    )
```

---

## الخلاصة

**سؤال:** هل سهول يحوي مؤشّرات تربة فضائيّة؟ **الإجابة الصادقة:** لا، إلى الآن.

**ما سنبني الآن (Tier 1 — جوهري):**
- ✅ BSI، BI، BI2 (سطوع وكشف تربة عارية)
- ✅ NDTI (حراثة وبقايا محاصيل)
- ✅ DBSI (مناطق جافّة كاليمن)
- ✅ NDSI (ملوحة — مهم للسواحل والوديان)
- ✅ SATVI (SOM في مناطق نبات خفيف)

**ما نُؤجّل بـtrigger صريح:**
- ⏸ HBSI (يحتاج بيانات hyperspectral)
- ⏸ k-means classification (يحتاج scikit-learn)
- ⏸ training dataset لـregression (يحتاج ١٠٠+ عيّنة معايرة)

النضج هنا: نضيف ٧ مؤشّرات تربة جاهزة للحساب، نُؤجّل التصنيف الآلي حتى تتوفّر بيانات معايرة كافية.
