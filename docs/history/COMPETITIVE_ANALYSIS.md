# التحليل التنافسي وخارطة الميزات — سهول

> **الغرض:** استخلاص الأفكار من تطبيقات الزراعة الدقيقة الرائدة + تطبيقات
> إدارة الآبار، ومطابقتها مع نواة سهول لتحديد ما يستحقّ البناء.
>
> **المبدأ الحاكم:** كل ميزة جديدة تُضاف فقط إذا كان لها trigger واضح
> (بيانات/معدّات موجودة)، وكانت ترتبط ربطاً معنوياً بـnucleus القرار.

---

## القسم ١: التطبيقات المرجعيّة

### ١.١ OneSoil (سويسري، مجاني للأساسي)

**الفلسفة:** "ما يحدث في كلّ حقل، فهماً بصرياً سريعاً"

| الميزة | الوصف | الـtrigger |
|--------|-------|------------|
| Auto field boundary detection | يكتشف حدود الحقول تلقائياً من Sentinel-2 (٥٧ دولة) | فيه نموذج segmentation مُدرَّب |
| NDVI كل ٣-٥ أيّام | تحديث آلي، contrasted NDVI للجوّال | Sentinel-2 cloud-free |
| Moisture layers | طبقة رطوبة من Sentinel-1 SAR | SAR data API |
| Field cards | بطاقات حقول بـcrop/yield/dates | إدخال يدوي |
| Scouting notes + photos | ملاحظات داخل الحقل مع GPS | mobile GPS |
| Field history | مقارنة NDVI بين تواريخ | تخزين tile time-series |
| **VRA prescription maps** (PRO) | خرائط معدّل متغيّر للبذر/التسميد/الرش | NDVI + productivity zones |
| **Productivity zones** | تقسيم الحقل لمناطق إنتاجيّة | clustering على تاريخ NDVI |
| Soil sampling map | شبكة عيّنات تربة محسوبة | grid generation |
| John Deere Operations Center | استيراد yield maps، تصدير AB lines | API integration |
| Spraying window | توقيت رش حسب الطقس | hyperlocal forecast 4h |
| Field grouping | تجميع الحقول (clients/farms) | tagging |
| 6+ indices in 2025 update | NDVI, MSAVI, NDRE, NDMI، إلخ | band-ratio calculations |

### ١.٢ Climate FieldView (Bayer/Climate Corp)

**الفلسفة:** "البيانات تتدفّق من الجرّار للقرار"

| الميزة | الوصف | الـtrigger |
|--------|-------|------------|
| Field data collection | جمع آلي من المعدّات (planter, combine) | Bluetooth/cellular adapter |
| Yield analysis | خرائط yield من الـcombine | yield monitor data |
| Fertility planning | خطط تسميد مخصّصة per-field | productivity zones + soil tests |
| Seeding plans | معدّلات بذر متغيّرة | hybrid response curves |
| Performance benchmarking | مقارنة مع farmers مجاورين (anonymized) | dataset مجمَّع |

### ١.٣ xarvio Field Manager / Scouting (BASF)

**الفلسفة:** "ذكاء اصطناعي للأمراض والتغذية"

| الميزة | الوصف | الـtrigger |
|--------|-------|------------|
| **Disease recognition AI** | يتعرّف على ١٣٩ مرض في ٣٧ محصولاً من صورة | CNN trained on millions of images |
| Weed identification | ٢٥٠+ نوع حشيش | image recognition |
| Insect counting (yellow pan) | يعدّ الحشرات في طبق أصفر | computer vision |
| Nitrogen status | يحدّد نسبة النيتروجين من صورة | leaf color analysis |
| Leaf damage quantification | يقدّر ٪ الضرر | pixel segmentation |
| Disease/pest risk forecast | تنبؤ مخاطر حسب الطقس + المرحلة | agronomic modelling |
| Optimal spray timing | توقيت رش أمثل | forecast + crop stage |
| VRA fungicide/fertilizer maps | خرائط تطبيق متغيّر | NDVI + recommendations |
| Wireless transfer to machinery | إرسال خرائط لاسلكياً | ISO-XML, John Deere |

### ١.٤ FarmHQ (إدارة الري والمضخّات)

**الفلسفة:** "مضخّتك في جيبك"

| الميزة | الوصف | الـtrigger |
|--------|-------|------------|
| **Remote pump control** | تشغيل/إيقاف من الجوّال | cellular IoT device |
| Pressure + flow monitoring | متابعة الضغط ومعدّل التدفّق آنياً | pressure sensor |
| Auto-shutdown on anomaly | إيقاف تلقائي عند خروج عن النطاق | sensor + cloud rules |
| Flow rate analysis | تحليل آنيّ من pulse-output flow meter | pulse counter |
| Pivot tracking | موقع وسرعة واتجاه الـcenter pivot | GPS on pivot |
| Scheduling | جدولة الري (timer/schedule) | cloud scheduler |
| Water usage records | تتبّع استهلاك دقيق per-field | flow × runtime |
| **Alerts** (text/email) | تنبيهات فوريّة عند عطل | rule engine |

### ١.٥ Aqvify (إدارة الآبار)

**الفلسفة:** "بئرك بصمت من الصمت"

| الميزة | الوصف | الـtrigger |
|--------|-------|------------|
| Static water level | منسوب الماء الساكن (لا ضخّ) | pressure sensor in well |
| Dynamic water level | منسوب أثناء الضخّ | pressure sensor |
| **Drawdown rate** | معدّل هبوط أثناء الضخّ | level/time differential |
| Inflow rate | معدّل ملء البئر | recovery curve |
| Volume available | ليترات بين الحدّ الأدنى والمنسوب الحالي | well geometry + level |
| Level alarms | تنبيه عند هبوط حرج | threshold rules |
| Historical comparison | ٧ أيّام مقارنة | time-series |
| Multi-user sharing | مشاركة access مع شركاء | tenant model |

### ١.٦ AgriLynk (مراقبة آبار زراعيّة)

| الميزة | الوصف |
|--------|-------|
| Static + dynamic level (pressure) | استشعار ضغطي داخل البئر |
| Pump status detection | يكشف عطل المضخّة من غياب التدفّق |
| Off-grid operation | يعمل بلا شبكة كهرباء |
| Integration with VFD | يعمل مع inverter للحفاظ على البئر |

### ١.٧ MU Crop Water Use / WISE / KanSched (أكاديميّة)

**الفلسفة:** "ميزانيّة الماء — checkbook method"

| الميزة | الوصف |
|--------|-------|
| ET-based water balance | حساب التبخّر-نتح اليومي |
| Soil layer + root depth | نموذج تربة طبقي |
| Maximum allowed deficit | عتبة الإجهاد المائي |
| Rainfall discount | خصم المطر من الـbalance |
| Crop growth stage tracking | تتبّع المراحل BBCH |

---

## القسم ٢: المطابقة مع نواة سهول

### ٢.١ ما نملكه فعلاً ✅

| العنصر | في النواة | في الموبايل |
|--------|-----------|-------------|
| Field boundary | FieldSchema (GeoJSON) | ✅ ٥ أوضاع رسم |
| NDVI + indices | `vegetation-analysis-service` (٧ مؤشّرات NIR) + ٣ red-edge | عرض في FieldHealth |
| Crop seasons | CropSeasonSchema | ✅ SeasonForm |
| Observations | ObservationSchema (EAV) | جزئي |
| Recommendations | RecommendationSchema | RecommendationsScreen |
| WOFOST yield model | `indicators-service` (RUE + GDD) | يُستهلَك في UI |
| VRA | `VRAScreen` (UI placeholder) | يحتاج النموذج backend |
| Source of truth | `source_of_truth.py` | يُحترَم في Samples |
| Crop portfolio | `crop_portfolio.py` (Renard & Tilman 2019) | لا UI بعد |
| Farm ledger | `farm_ledger.py` (cost/revenue) | لا UI بعد |

### ٢.٢ ما يوجد في النواة بلا UI ⚠

| العنصر | الموقع | السبب |
|--------|--------|-------|
| `farm_ledger.py` | core | لا screen يعرض cost/revenue |
| `crop_portfolio.py` | core | لا screen للـ portfolio analysis |
| ٣ مؤشّرات red-edge (NDRE/CI/MCARI) | raster-service | جاهزة، تحتاج عرض |
| WOFOST seasons table | DB | تظهر في HybridIndex فقط |

### ٢.٣ الفجوات الحقيقيّة 🟥

| الفجوة | الـtrigger | الأولويّة |
|--------|------------|----------|
| **wells (الآبار)** | السياق اليمني = الزراعة المروّية من بئر | 🔴 عالية |
| **pump_runs** (سجلّ تشغيل المضخّات) | هكتارات الري الفعليّة | 🔴 عالية |
| **irrigation_events** (سجلّ ريّات) | حسبة water balance الميدانيّة | 🟡 متوسّطة |
| **scouting_observations** (مع صور) | اكتشاف الإجهاد المبكّر | 🟡 متوسّطة |
| **tasks** (مهامّ + تذكيرات BBCH) | متابعة الموسم | 🟢 منخفضة |
| Disease recognition AI | يحتاج dataset عربي + on-device ML | ⏸ مؤجَّلة (trigger: dataset) |
| Auto field boundary | يحتاج Sentinel API + model | ⏸ مؤجَّلة (trigger: ML model) |

---

## القسم ٣: الميزات المُختارة للبناء (Top 3)

> اختياري المنهج: **١. wells, ٢. pump_runs, ٣. irrigation_events**.
> هذه ٣ ميزات تتكامل مع الموجود وتعالج فجوة السياق اليمني.

### ٣.١ Wells (الآبار) — تصميم الـschema

```sql
CREATE TABLE wells (
  well_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  farm_id TEXT NOT NULL,
  name_ar TEXT NOT NULL,
  well_type TEXT,        -- 'drilled' | 'dug' | 'spring' | 'borehole'
  location_lat REAL,
  location_lng REAL,
  total_depth_m REAL,
  casing_diameter_cm REAL,
  static_water_level_m REAL,     -- منسوب ساكن (متّ من فتحة البئر)
  dynamic_water_level_m REAL,    -- أثناء الضخّ
  drawdown_m REAL,                -- الفرق = static - dynamic
  pump_type TEXT,                 -- 'submersible' | 'centrifugal' | 'manual'
  pump_capacity_lpm REAL,         -- liters per minute
  pump_power_kw REAL,
  energy_source TEXT,             -- 'electric' | 'diesel' | 'solar' | 'mixed'
  water_ec_dsm REAL,              -- ملوحة (مرجع سريع)
  drilling_date TEXT,
  last_inspection_date TEXT,
  notes TEXT,
  created_by_user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  synced INTEGER NOT NULL DEFAULT 0
);
```

**الـ٧ نقاط محتفظ بها:**
- موقع GPS (شائع في تطبيقات الآبار)
- العمق الإجمالي
- الـstatic + dynamic + drawdown (من Aqvify + AgriLynk)
- بيانات المضخّة (capacity, power)
- ملوحة الماء (لربط مع نموذج FAO-56)
- تاريخ الحفر + آخر فحص

### ٣.٢ Pump Runs (تشغيل المضخّات)

```sql
CREATE TABLE pump_runs (
  run_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  well_id TEXT NOT NULL,
  field_id TEXT,                 -- اختياري: حقل مُروى
  started_at TEXT NOT NULL,
  ended_at TEXT,                 -- null = ما زالت تعمل
  duration_minutes REAL,         -- محسوبة
  flow_rate_lpm REAL,            -- معدّل تدفّق (إن أُدخل)
  volume_pumped_l REAL,          -- = flow × duration
  energy_consumed_kwh REAL,      -- اختياري
  fuel_consumed_l REAL,          -- لمضخّات الديزل
  pump_pressure_bar REAL,        -- اختياري
  notes TEXT,
  created_by_user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  synced INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (well_id) REFERENCES wells(well_id),
  FOREIGN KEY (field_id) REFERENCES fields(field_id)
);
```

### ٣.٣ Irrigation Events (سجلّ ريّات)

```sql
CREATE TABLE irrigation_events (
  event_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  field_id TEXT NOT NULL,
  season_id TEXT,                -- ربط بالموسم النشط
  irrigated_at TEXT NOT NULL,
  duration_hours REAL,
  amount_mm REAL,                -- ملم/هكتار (= حجم/مساحة)
  total_volume_l REAL,
  water_source TEXT,             -- 'well_X' | 'rain' | 'spate' | ...
  source_id TEXT,                -- well_id إن من بئر
  method TEXT,                   -- pivot / drip / flood / ...
  observed_yield_response TEXT,  -- ملاحظة عن استجابة المحصول
  notes TEXT,
  created_by_user_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  synced INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (field_id) REFERENCES fields(field_id),
  FOREIGN KEY (season_id) REFERENCES crop_seasons(season_id)
);
```

---

## القسم ٤: ربط مع نواة القرار

### ٤.١ التدفّق الكامل (well → irrigation → yield)

```
[Mobile UI]
    ↓
[Wells repo] → SQLite (offline-first)
    ↓ على pump_run جديد
[PumpRuns repo] → SQLite
    ↓ يحسب volume_pumped
[Irrigation events] → ربط مع field + season
    ↓ يُزامن للـbackend عبر offline_queue
[NATS JetStream] → تنبيه النواة
    ↓
[indicators-service] → يحسب كم ملم تلقّاها الحقل
    ↓
[WOFOST simulation] → يستخدم irrigation_mm كـinput
    ↓
[yield prediction] → تقدير الإنتاج المتأثّر بالري الفعلي
    ↓
[recommendation engine] → "الموسم القادم، الحقل يحتاج X ملم"
    ↓
[Mobile UI] → عرض التوصية للمستخدم
```

### ٤.٢ ٣ نقاط ربط جوهريّة

#### ربط ١: `irrigation_events.amount_mm` → `WOFOST.water_input`

```python
# في indicators-service:
seasonal_irrigation_mm = sum(
    event.amount_mm for event in irrigation_events
    if event.season_id == active_season.season_id
)
wofost_inputs.water = (
    seasonal_irrigation_mm + seasonal_rainfall_mm
)
```

#### ربط ٢: `wells.water_ec_dsm` → `crop_water_tolerance` (FAO-56)

```python
# في recommendation engine:
if well.water_ec_dsm > crop_tolerance[season.crop_id]:
    add_recommendation(
        type='WATER_QUALITY',
        priority='HIGH',
        text=f'ملوحة ماء البئر {well.water_ec_dsm} dS/m '
             f'تتجاوز تحمّل {crop_name} ({tolerance} dS/m)'
    )
```

#### ربط ٣: `pump_runs.drawdown_trend` → `groundwater_alert`

```python
# في انذار البئر:
# لو الـstatic level ينخفض > X ملم/شهر → تنبيه نضوب
recent_drawdowns = [r.drawdown_m for r in last_30_days_runs]
if mean(recent_drawdowns) > threshold:
    add_alert('بئر %s: علامات نضوب — راجع جدول الضخّ' % well.name_ar)
```

---

## القسم ٥: ما لا نبنيه الآن (مؤجَّل بـtrigger صريح)

| الميزة | السبب | الـtrigger المطلوب |
|--------|------|---------------------|
| Disease AI recognition | لا dataset عربي | ١٠،٠٠٠+ صورة من مزارع يمنيّة |
| Auto field boundary detection | يحتاج ML model | Sentinel-2 segmentation model |
| Wireless pump control | يحتاج hardware IoT | partnership + cellular device |
| Productivity zones (VRA) | يحتاج 2+ موسم NDVI | الجلسة السابقة (موسمَين Sentinel-2) |
| Benchmarking مع المجاورين | يحتاج dataset جماعي | ٢٠+ مزارع نشطين في نفس المنطقة |
| Wireless transfer للمعدّات | لا معدّات ذكيّة عند المزارعين | جرّارات معايرة |

---

## القسم ٦: الخطّة المُقترَحة (التنفيذ في هذه الجلسة)

```
الأولويّة ١ (يُبنى الآن):
   ✅ Migration v8: wells + pump_runs + irrigation_events
   ✅ wellRepo.ts + pumpRunRepo.ts + irrigationEventRepo.ts
   ✅ شاشة WellsListScreen
   ✅ شاشة AddWellScreen (map + form)
   ✅ شاشة WellDetailScreen (water levels + pump runs history)
   ✅ شاشة AddPumpRunScreen (start/stop quickly)
   ✅ شاشة AddIrrigationEventScreen
   ✅ ربط من FieldDetail "إدارة الري"

الأولويّة ٢ (مُؤجَّل لجلسة قادمة):
   ⏸ النموذج backend: water_balance.py في النواة
   ⏸ المؤشّر الجديد: drawdown_trend
   ⏸ recommendation: water_quality_check
```

---

## الخلاصة الموضوعيّة

```
✓ سهول يملك نواة قويّة لـ٧٠٪ من ميزات OneSoil/FieldView الأساسيّة
✓ الفجوة الحقيقيّة: إدارة الآبار + سجلّ الري (٧٠٪ من السياق اليمني)
✓ الفجوة الثانية: scouting AI (مؤجَّل بانتظار dataset)
✓ المرحلة التالية: ٣ entities + ٤ شاشات يكفي لمكاملة الميزة
✓ التكامل مع النواة: ٣ نقاط ربط معماريّة محدّدة (irrigation → WOFOST،
   ec → tolerance، drawdown → alert)
```

النضج هنا أنّا لم نُحاول استنساخ كلّ ميزات FieldView بل اخترنا ما يحلّ مشكلة
حقيقيّة في السياق اليمني (الآبار + الري) ويربط معنوياً مع ما نملكه فعلاً.
