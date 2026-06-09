# FIELDVIEW_UI_INSIGHTS — أنماط نتبنّاها في سهول

> **المصادر:** Bayer FieldView (climate.com), FieldView Cab (App Store), دراسات UX
> agriculture (Gapsy, designstudiouiux, Medium). كل insight هنا له reference.

---

## ١. الأنماط المُجرَّبة من FieldView (تعمل ميدانياً منذ ٢٠١٠)

### ١.١ Side-by-Side Map Comparison

**ما يفعله FieldView:**
> "Tap on the Side-by-Side icon (top right). Using the drop-down menus, compare and
> analyze your map layers, such as comparing hybrid to yield."

شاشتان للخرائط بجانب بعض، كل واحدة layer مختلف (NDVI vs scouting، planting vs harvest).

**التطبيق في سهول:**
- شاشة FieldDetail تحتاج زرّ "مقارنة Layers"
- مفيد جدّاً لمزارع يمني يقارن: NDVI الأسبوع الماضي vs اليوم
- مقارنة pre-irrigation vs post-irrigation

### ١.٢ Three Imagery Methods (NDVI تُعرَض بـ٣ طرق)

**ما يفعله FieldView:**
> "field health imagery features NDVI imagery formatted in three different methods:
> scouting map, vegetation map, and true color"

- **Scouting map:** يُظهر المناطق الضعيفة بألوان فاضحة (للأخصّائي)
- **Vegetation map:** تدرّج مفصّل للـbiomass (للأبحاث)
- **True color:** صورة طبيعيّة (للتحقّق البصري)

**التطبيق في سهول:**
المزارع اليمني قد يحتاج فقط *true color* + *scouting* (أبسط). الـvegetation map يبقى للـadvisor.

### ١.٣ Pin Dropping للـbookmarks

**ما يفعله FieldView:**
> "dropping and saving pins is critical ... locate a specific spot that needs attention"

عند رؤية بقعة سيّئة في NDVI، المزارع يضع pin → يذهب فيزيائياً → يلتقط صورة → يربطها بالـpin.

**التطبيق في سهول:**
- نفس النمط للمشاكل: "اصفرار هنا" pin → صورة → ملاحظة → community post
- ممتاز للـoffline workflow

### ١.٤ Field Region Reports

**ما يفعله FieldView:**
> "field region report tool allows me to compare pass by pass, soil type, checks,
> populations, etc."

تقسيم الحقل إلى مناطق (zones) ومقارنة الإنتاج بينها.

**التطبيق في سهول:**
- مرتبط مباشرة بـ"Zone Sampling" الذي بنيناه
- ٥ zones × NDVI mean + موارد التربة + الإنتاج
- المزارع يكتشف: "النصف الشمالي ينتج ١٥٪ أكثر — لماذا؟"

### ١.٥ Real-time Alerts

**ما يفعله FieldView:**
> "Get real-time alerts ... critical data layers ... weather data on all of your
> mapped fields to help determine application timing"

تنبيهات: weather change، crop water usage، application timing.

**التطبيق في سهول:**
- موجود جزئياً (notification-agent)
- يحتاج: تنبيه قبل ساعتين من الـsunset (وقت ري مثالي)
- تنبيه عند توقّع رياح > 15 km/h (لا رشّ)

---

## ٢. أفضل الممارسات من أبحاث UX agriculture

### ٢.١ Sequential Information Architecture (لا "all-at-once")

**من Gapsy:**
> "We replace dense, 'all-at-once' dashboards with task-oriented flows. If a user
> is recording a soil sample, the interface should only show the fields relevant
> to that specific action."

**في سهول حالياً:** ✓ مُطبَّق — SoilFormScreen يعرض حقول التربة فقط، لا dashboard كامل.

### ٢.٢ Predictive Data Entry (pre-populate)

**من Gapsy:**
> "By leveraging GPS and historical records, our designs pre-populate as much data
> as possible. Reducing the number of taps required for a record directly increases
> data accuracy and user adoption."

**التطبيق في سهول:**
- موقع العيّنة → GPS تلقائياً
- محصول الموسم الجديد → اقتراح من تاريخ المزارع
- تربة الحقل → نسخ من حقل مجاور للمزارع نفسه

### ٢.٣ Confidence Score بدلاً من error codes

**من Gapsy:**
> "When data is fuzzy, cryptic error codes are replaced with a 'Confidence Score.'
> This empowers the farmer to decide when to trust the algorithm and when to drive
> out and check the soil themselves."

**التطبيق في سهول:**
- NDVI value → "ثقة: ٩٢٪ (يوم صافٍ)" أو "ثقة: ٤٥٪ (غيوم)"
- توصية الري → "بناءً على NDVI + سجلّ المنطقة، الثقة ٧٨٪"

### ٢.٤ Telescoping UI

**من Gapsy:**
> "We start users in essential mode, stripping the interface down to core metrics
> like yield and weather. As the operation scales, the UI simply unlocks new modules."

**التطبيق في سهول:**
- مزارع جديد: ٣ شاشات فقط (حقولي، الطقس، تنبيهات)
- بعد إنشاء ٣ حقول: يفتح "Insights"
- بعد موسم كامل: يفتح "Yield Analysis"
- بعد ٥ مزارع: يفتح "Portfolio Comparison"

### ٢.٥ Role-Based Context

**من Gapsy:**
> "An operations manager needs to see fleet fuel efficiency, while a field worker
> just needs a checklist."

**التطبيق في سهول:**
- المزارع: حقولي + توصيات + تنبيهات
- المهندس الزراعي: ٢٠ حقل لـ٢٠ مزارع + reports + comparisons
- مدير الجمعيّة: portfolio analysis + market prices + bulk ordering

### ٢.٦ Field-Optimized (sunlight + dust + outdoor)

**من المراجع المتعدّدة:**
> "Sunlight, dust, and physical movement dictate the visual requirements"
> "they prefer the dark colors and the hard colors for font, a slighter large font,
> high contrast, larger touch base to make click easy"

**التطبيق في سهول:**
- خطّ أكبر (16-18pt في الحقول الميدانيّة)
- contrast عالٍ (لا gray-on-gray)
- touch targets ≥ 48dp (FieldView نفسه يستخدم 56dp)
- ألوان "hard" (لا pastels)

### ٢.٧ Simplicity First, Rural First

**من designstudiouiux (GramRaj case study):**
> "User journeys were shortened. Three taps to all relevant content were now a
> mandatory rule. Our design process was guided by a principle of 'Simplicity
> First, Rural First.'"

**التطبيق في سهول:**
- إضافة حقل: tap → polygon → save (3 taps)
- إضافة عيّنة: tap field → tap "+ عيّنة" → fill (3 taps)
- ✓ مُحقَّق حالياً

### ٢.٨ Offline-First (الـ"غير قابل للتفاوض")

**من f1studioz:**
> "By allowing farmers to collect and store data offline, and then sync it when a
> connection is available, UX design ensures that users can still benefit from the
> technology even in areas with poor connectivity."

**التطبيق في سهول:** ✓ مُطبَّق — SQLite + offline_queue + syncEngine

### ٢.٩ Localization حقيقيّة (لا ترجمة فقط)

**من f1studioz:**
> "UX design incorporates localisation elements such as language options,
> region-specific data, and culturally relevant design features"

**التطبيق في سهول:**
- ✓ Arabic RTL
- ✓ خطّ Cairo + IBM Plex Sans Arabic
- ✓ أرقام عربيّة (٠١٢٣)
- ✓ تواريخ الهجريّة كـoption
- ⚠ يحتاج: dialect-aware (يمنيّ vs خليجي vs مصري)

---

## ٣. الفجوات بين تطبيقنا الحالي و FieldView

| الميزة | FieldView | سهول الآن | الأولويّة |
|--------|-----------|-----------|-----------|
| Side-by-Side Map | ✓ | ✗ | 🟡 مهمّ |
| Pin Dropping | ✓ | ✗ | 🟢 مفيد |
| 3 Imagery Methods | ✓ | جزئي (NDVI فقط) | 🟢 مفيد |
| Field Region Reports | ✓ | جزئي (zone sampling) | 🟡 مهمّ |
| Real-time Alerts | ✓ | جزئي (notif-agent) | 🟡 مهمّ |
| Offline | ✗ (محدود) | ✓✓ | — متفوّقون |
| Arabic + RTL | ✗ | ✓✓ | — متفوّقون |
| WOFOST simulation | ✗ | ✓ | — متفوّقون |
| Soil indices (BSI/BI/etc.) | ✗ | ✓ | — متفوّقون |

**الخلاصة:** سهول يتفوّق في الـAR/offline/scientific depth، ويحتاج إضافات في الـmap UX.

---

## ٤. ما سأطبّقه في الـpreview المُحدَّث

### الإضافات الجديدة:
1. **Side-by-Side Comparison** في FieldDetail
2. **Pin Dropping** على الخريطة (مع photo + note)
3. **Confidence Score** على كل NDVI/recommendation
4. **Telescoping UI badge** ("افتح ميزة جديدة!")
5. **Pre-populated forms** (GPS تلقائي + تاريخ المزارع)

### تحسينات بصريّة (FieldView-inspired):
- خطّ أكبر (16-18px للـbody)
- contrast أقوى
- touch targets أكبر (56dp بدلاً من 48dp)
