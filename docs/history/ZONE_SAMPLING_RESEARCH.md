# توصيات أماكن العيّنات + الاستفادة من Valley Irrigation

> **الغرض:** الإجابة على سؤالَين عمليّين:
>
> 1. هل سهول يُوصي بأماكن أخذ العيّنات بناء على imagery؟ (الإجابة: لا، نبنيه الآن)
> 2. ما يستحقّ من أفكار Valley Irrigation؟ (الإجابة: ٣ أفكار قابلة للتنفيذ، الباقي مؤجَّل)

---

## القسم ١: أفضل ممارسة Zone Sampling (مُستخلَص من البحث)

### ١.١ الفرق الجوهري: Grid vs Zone vs Random

| الطريقة | متى تُستخدم | المراجع |
|---------|-------------|---------|
| **Random** | حقول صغيرة (<٢ هكتار) متجانسة | بسيطة لكن قد تفوّت heterogeneity |
| **Grid** (٢-٤ acres/cell) | "حقول لا تعرف تاريخها — نتائج معايرة" | Grid sampling should be used when there is little information available about the variation in nutrient levels across a field |
| **Zone (Management Zones)** | "حقول معروف tarihha + variability واضح" | Management zones are a better choice than grids when the operator has a long history of working with the field, topography varies and can be used to define zones |

**النصيحة المُتقدّمة:** الجمع بينهما — grid مرّة كل ٣-٥ سنوات (calibration)، وzone-based كل موسم.

### ١.٢ ميزة Zone Sampling (لماذا هي الأفضل للحقول الكبيرة)

Cell sizes of about 4 acres failed to describe the high variability occurring in the fields (mainly of available P, K, and pH), and currently a cell size of about 2.5 acres is used. As a consequence, 20 to 30 samples are collected from typical Iowa fields where seldom more than five or six samples were collected before.

أي: grid sampling في حقل ٥٠ هكتار = ٤٠-٦٠ عيّنة (مكلف جدّاً).
zone sampling في نفس الحقل = ٣-٦ مناطق × عيّنة composite = ٣-٦ تحليل لاب فقط.

### ١.٣ الخوارزميّة العمليّة (٦ خطوات GeoPard + Iowa State + OSU)

```
الخطوة ١: Pre-sampling Analysis
  - اجمع: NDVI تاريخي + soil_texture + topography (إن وُجد)
  - حدّد ما هو "متوفّر"

الخطوة ٢: تقسيم المناطق (Stratification)
  ١. لو NDVI تاريخي موجود (موسم سابق):
     → quantile-based: high/medium/low NDVI
     → 3-6 zones عبر k-means clustering

  ٢. لو NDVI غير موجود (الحالة الشائعة في سهول):
     → spatial stratification:
       - قسّم الحقل لـ٤ quadrants (NE, NW, SE, SW)
     → إن كان soil_texture متغيّراً:
       - منطقة per soil type
     → الحدّ الأدنى: ٣ مناطق

الخطوة ٣: عدد العيّنات لكل منطقة
  → الأقلّ ١٠-١٥ cores → composite واحد
  → الموبايل لا يطلب cores فرديّة، فقط نقطة المركز

الخطوة ٤: نمط أخذ العيّنات داخل المنطقة
  → "زيج-زاج" (شكل M أو W) داخل المنطقة
  → يضمن coverage كاملاً بلا overlap

الخطوة ٥: GPS لكل نقطة
  → لإعادة الزيارة (longitudinal tracking)
  → التحقّق من النتائج عبر المواسم

الخطوة ٦: Calibration
  → بعد لاب results، قارن مع NDVI
  → إن لم يتطابقا → أعد تعريف الزونات
```

### ١.٤ التطبيق العملي على الحقول اليمنيّة

**سيناريو شائع:** مزارع يملك ٥ هكتارات قمح، لا NDVI، عرف من العين أنّ شمال الحقل أفضل.

```
المنطقة | السبب          | عدد العيّنات
─────────┼───────────────┼──────────────
شمال    | بصرياً أفضل    | ١
جنوب    | بصرياً أضعف    | ١
مركز    | الـcontrol     | ١
─────────┴───────────────┴──────────────
المجموع: ٣ عيّنات composite (٣ تحاليل لاب)
```

**التكلفة:** ٣ × ٥٠$ = ١٥٠$ بدلاً من ٢٠ × ٥٠$ = ١٠٠٠$ (grid).

---

## القسم ٢: استخلاص من Valley Irrigation

### ٢.١ المنصّة الكاملة (AgSense 365)

Valley Irrigation intends to merge its four market-leading irrigation management platforms – AgSense, Valley 365, PrecisionKing and PivoTrac – into a unified next-evolution app: AgSense 365

**ما يفعله Valley 365:**
- إدارة المحاور (center pivots) من الجوّال
- AgSense للتحكّم في المضخّات
- Valley Scheduling (٧-day forecast)
- VRI (Variable Rate Irrigation)
- Valley Insights (تحليل صور satellite)
- Valley Aqua Trac (probes رطوبة + ملوحة)

### ٢.٢ VRI — الفكرة المركزيّة

Valley VRI allows you to customize water application based on topography information, soil data maps, yield data, and other user-defined information. Based on your VRI Prescription, you're applying water only where it needs to be. So, you are not applying water to unnecessary areas in your field, such as: ditches, canals, buildings, and boggy areas.

**٣ مستويات تحكّم:**

```
١. Speed Control (الأبسط)
   → يغيّر سرعة دوران المحور
   → بطيء = ماء أكثر، سريع = ماء أقلّ
   → نفس المعدّل عبر كل span في اللحظة

٢. Zone Control (متوسّط)
   → يقسّم الـ360° لقطاعات (كل ٢° = قطاع)
   → كل قطاع له معدّل تطبيق مستقلّ
   → إجمالي: ١٨٠ قطاع ممكن

٣. Individual Sprinkler Control (الأقصى)
   → كل مرشّ على حدة
   → دقّة قصوى، تكلفة قصوى
```

### ٢.٣ ما يستحقّ التبنّي في سهول

#### ✅ الفكرة ١: Pivot Sectors Manager (موجود فعلاً!)

سهول يدعم **pivot_sectors** و**pivot_towers** كأوضاع رسم منذ بداية الموبايل. هذا يُطابق Valley Zone Control. **ما ينقص:** ربط كل قطاع بـirrigation rate مستقلّ.

#### ✅ الفكرة ٢: ٧-day Irrigation Forecast (مُؤجَّل بـtrigger)

Plus, get a 7-day irrigation forecast through Valley Scheduling

نواة سهول تحوي WOFOST لحساب water demand. التنبؤ ٧ أيّام:
```python
for day in next_7_days:
    eto_mm = penman_monteith(weather_forecast[day])
    kc = crop_kc[crop_id][growth_stage]
    etc_mm = eto_mm × kc
    soil_water_balance -= etc_mm
    if balance < threshold:
        recommendation[day] = 'IRRIGATE'
```

**الـtrigger:** يحتاج weather forecast API يومي (٧ أيّام). نواة سهول لا تستهلكه بعد.

#### ✅ الفكرة ٣: Soil Moisture Probes Integration

Valley Aqua Trac connects to soil moisture probes and sensors to determine the soil moisture content, temperature and salinity of the soil

سهول يدعم `soil_moisture` في `MEASURABLE_PARAMS` (وحدة %VWC). يمكن:
- إدخال يدوي من handheld probe
- مستقبلاً: ربط IoT (TDR/capacitive sensors)

#### ⏸ مُؤجَّل: Autonomous Pivot

The ultimate goal is the autonomous pivot. We're in the early stages, but we're progressing quickly. This would allow a grower to use that pivot in the field for other things than water. That autonomous pivot could act as a field monitor, checking for disease or crop stress, pull in fungicide or fertilizer to be precision-applied

غير قابل في سياق سهول الحالي (يحتاج معدّات Valley + AI).

---

## القسم ٣: تصميم الميزة المُختارة للبناء

### ٣.١ Zone Sampling Recommendation Engine

**Input:**
- `field.polygon_coords` (الحدود)
- `field.area_ha`
- `field.soil_texture` (اختياري)
- `field.shape_type` (polygon أو pivot)
- *مستقبلاً:* NDVI tile time-series

**Output:**
- ٣-٧ نقاط (lat, lng) داخل الحقل
- لكل نقطة: label (شمال/جنوب/مركز/...)
- ترتيب اقتراحي للزيارة
- ملاحظة per-point (مثلاً: "خذ ١٠ cores بشكل M حول هذه النقطة")

### ٣.٢ الخوارزميّة (بسيطة، rule-based)

```typescript
function recommendSamplePoints(field: FieldRecord): SamplePoint[] {
  const area = field.area_ha;
  const center = centroid(field.polygon_coords);
  const bbox = boundingBox(field.polygon_coords);

  // عدد المناطق حسب المساحة
  const nZones =
    area < 2  ? 3 :
    area < 10 ? 4 :
    area < 30 ? 5 : 7;

  // إن كان polygon (حقل تقليدي):
  if (field.shape_type === 'polygon') {
    return spatialStratification(field, nZones);
  }

  // إن كان pivot:
  if (field.shape_type === 'pivot_full') {
    return pivotRingStratification(field, nZones);
  }

  // إن كان sectors/towers:
  return perFeatureSampling(field);
}
```

### ٣.٣ Spatial Stratification (للحقول polygon)

```
الفكرة:
  ١. أوجد الـcentroid C
  ٢. أوجد الـbounding box
  ٣. نقطة المركز = C
  ٤. النقاط الـn-1 المتبقّية:
     - شمال C (lat + delta)
     - جنوب C (lat - delta)
     - شرق C (lng + delta)
     - غرب C (lng - delta)
     - (للـ7 zones): NE, NW
  ٥. كل نقطة في الحدّ الأقصى ٧٠٪ بُعد عن الـboundary (داخل الحقل بأمان)
  ٦. تحقّق pointInPolygon — إن خرجت، اسحبها نحو centroid
```

### ٣.٤ Pivot Ring Stratification (للمحاور)

```
الفكرة (مستوحاة من Valley Sectors):
  ١. للـcenter pivot: قسّم لـ٣ حلقات (inner/middle/outer)
  ٢. ولـ٤ قطاعات (N/S/E/W)
  ٣. نقطة عند تقاطع كل (ring, sector)
  ٤. عيّنة composite per ring × sector

المنطقي: الـouter ring يستهلك ماء أكثر، يحتاج fertility أكثر.
```

---

## القسم ٤: الفرق بين سهول والمنافسين

| الميزة | OneSoil PRO | GeoPard | Valley 365 | **سهول** |
|--------|-------------|---------|------------|----------|
| Auto field boundary | ✓ AI | ✓ AI | ✗ | ⏸ مؤجَّل |
| NDVI history | ✓ | ✓ | ✓ Insights | ✓ |
| Zone sampling recommendations | ✓ PRO | ✓ AI | ✗ | 🆕 **يُبنى الآن** |
| Grid sampling | ✓ | ✓ | ✗ | ⏸ مؤجَّل (بـtrigger) |
| VRI prescriptions | ✓ | ✓ | ✓✓ | جزئي (pivot_sectors) |
| Pivot integration | ✗ | ✗ | ✓✓✓ | جزئي (drawing only) |
| Pump remote control | ✗ | ✗ | ✓ | ✗ (يحتاج hardware) |
| Offline-first | ⚠ partial | ✗ | ✗ | ✓✓ |
| Arabic native | ✗ | ✗ | ✗ | ✓✓ |
| Yemeni soils (rocky/volcanic) | ✗ | ✗ | ✗ | ✓ |

---

## القسم ٥: قرارات معماريّة قبل البناء

### ٥.١ ما نبنيه الآن (الجلسة الحاليّة)

```
✅ Module: src/utils/zone_sampling.ts
   - recommendSamplePoints(field) → SamplePoint[]
   - spatialStratification (polygon)
   - pivotRingStratification (pivot)
   - perFeatureSampling (sectors/towers)
   - 3 helper functions: pointInPolygon, projectInside, distanceMeters

✅ Screen: SampleRecommendationsScreen
   - يظهر من SamplesList → زرّ "💡 توصيات أماكن العيّنات"
   - خريطة الحقل + markers بأرقام (١-٥)
   - قائمة بكل نقطة + سبب + ملاحظات
   - زرّ "أضف عيّنة من هذه النقطة" → AddSampleScreen مع lat/lng مُعبَّأ

✅ ربط من SamplesListScreen
```

### ٥.٢ ما نُؤجّله (بـtrigger صريح)

```
⏸ NDVI-based clustering:
   - يحتاج: موسم Sentinel-2 من نفس الحقل
   - الـcode موجود في raster-service (vegetation-analysis)
   - الربط للموبايل يحتاج: tile fetch + clustering library

⏸ VRI Prescription Maps:
   - يحتاج: معدّات Valley/Reinke/Zimmatic فعليّة
   - مزارع يمني نادراً ما يملكها

⏸ ٧-day irrigation forecast:
   - يحتاج: weather forecast API (OpenWeather أو AccuWeather)
   - نواة سهول لا تستهلكه بعد
```

---

## القسم ٦: لماذا هذه الميزة قبل غيرها؟

```
١. ترفع جودة قرارات النواة:
   → عيّنات مأخوذة في أماكن صحيحة = lab results صحيحة
   → lab results صحيحة = recommendations دقيقة

٢. تقلّل تكلفة التحاليل ٨٠٪:
   → ٣-٦ عيّنات composite بدلاً من ٢٠-٣٠ grid
   → كل تحليل ~٢٠-٥٠$، التوفير ١٠٠٠$ + لكل حقل

٣. ميزة فريدة في السوق العربي:
   → OneSoil/Geopard بالإنجليزيّة فقط
   → Valley لا يقدّم zone sampling (يقدّم VRI فقط)

٤. لا تحتاج trigger خارجي:
   → الكود pure logic (geometry + spatial)
   → لا backend جديد، لا hardware، لا API خارجي

٥. تتكامل مع ما بُني:
   → يستخدم field.polygon_coords الموجود
   → يُولِّد عيّنات تذهب إلى SamplesList الموجود
```

---

## الخلاصة

تطبيقات Valley Irrigation تستهدف **معدّات** (pivots, pumps, probes) — السوق الأمريكي/الأوروبي. **سهول** يستهدف **القرار** — السوق اليمني. لذا الاستلهام يكون من الـworkflows لا من الـhardware integration.

ما يستحقّ البناء **الآن**:
- ✅ Zone Sampling Recommendation Engine (rule-based، يعمل دون NDVI)
- ✅ Screen تفاعليّة في الموبايل
- ✅ ربط مع AddSampleScreen الموجود

ما يُؤجَّل بـtrigger صريح:
- ⏸ NDVI clustering (موسم Sentinel-2)
- ⏸ VRI prescriptions (معدّات Valley)
- ⏸ Forecast integration (weather API)
