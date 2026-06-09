# تحليل وثيقة بحث Remote Sensing — تصنيف صارم بدون بناء

> **التاريخ:** 2026-05-29 (نفس يوم تحليل المرفقات السابقة)
> **المصدر:** بحث ميتا في ٢٤+ مجلّة Remote Sensing مع توصيات لـ"منصة سهول"
> **القاعدة الذهبية المُتَّبَعة:** الجلسة السابقة قرّرت "إيقاف البناء" — هذا الالتزام يُحترَم.

---

## النتيجة الموضوعية الأولى — تصنيف الوثيقة

هذه الوثيقة **ليست مراجعة لكود سهول الحالي**. لا تذكر:
- أيّ ملفّ من ٦٧ ملفّ في النواة
- recommendation_engine، fao56، source_of_truth، أيّ وحدة قائمة
- ٧٧٧ اختبار، ١١ مراجعة سابقة، الإصلاحات المُنجَزة

هي **بحث ميتا في توجّهات أدبيات Remote Sensing** يصف منصّة افتراضية "مثالية" بناءً على أفضل ممارسات ٢٤+ مجلّة. تستخدم اسم "السهول الزراعية" كمسمّى عامّ لنظام Remote Sensing شامل.

**هذا تمييز جوهري:** الوثيقة لا تكشف فجوات في سهول الحالي، بل تصف "ما يجب أن يكون عليه نظام Remote Sensing مثالي".

---

## التدقيق الآلي — ٢٣ توصية محدّدة

```
✅ متطابق فعلاً (7/23):
   NDVI، EVI، LAI، NDWI، NDMI، SAVI، CWSI (٧ مؤشرات)
   WOFOST، Penman-Monteith (نماذج فيزيائية)
   Random Forest، XGBoost، Transformer/LSTM في model_selector
   Conformal prediction في yield_interval
   
❌ غائب فعلاً (8/23) — هل فجوة أم رفض واعٍ؟
   GEE، Sentinel Hub، xarray، SNAP (سحابي ثقيل)
   FAPAR، LST، GNDVI (مؤشرات إضافية)
   DSSAT/APSIM (بدائل لـWOFOST)
   ARIMA/Prophet (لا anomaly detection بنماذج ML)
   Digital Twin
   ERA5 (TB/year)
   GNSS/GPS tractor + Edge computing
   
🟡 جزئياً مغطّى (8/23):
   R²/RMSE، Field-level Yield Error
   Transferability testing
   Phenological Metrics
   Place & Time engine
   Data Assimilation
   Field calibration with TDR
   IoT/sensor station integration
   Place comparison (neighbor fields)
```

---

## الفلسفتان مختلفتان جذرياً

الوثيقة تصف **Remote Sensing-centric platform**:
```
Satellite/Cloud → GEE processing → Cloud Models → Dashboard
                  (24/7 connectivity, TB/day data)
```

سهول هو **decision-system للسياق اليمني**:
```
Lab + Manual + Sensor (offline-first) → Local Decision Engine 
→ Human-in-the-Loop Execution (vrt_manual_maps)
```

### لماذا الـ٨ الغائبة ليست فجوات

| المُرفقات تقترح | لماذا الغياب مبرّر |
|---------------|-------------------|
| GEE/Sentinel Hub/xarray | يتطلّبون 24/7 cloud connectivity — يكسر offline-first الجوهري |
| SNAP | معالجة ثقيلة سحابية — سهول يستخدم Copernicus connector بدلاً |
| FAPAR، LST | يحتاجون thermal/radiation bands — لا تتوفّر في spot readings الميدانية |
| DSSAT/APSIM | بدائل لـWOFOST، ليست تحسيناً — رفض الازدواجية |
| ARIMA/Prophet | يحتاجون ML pipeline — رفض ML سحرية، الـtime_series الحالي شفّاف |
| Digital Twin | farm_memory يحلّ نفس الحاجة بـComposition لا Simulation |
| ERA5 | TB/year — Open-Meteo connector يكفي للسياق |
| GNSS/Edge/Tractor | لا machinery في الميدان اليمني — vrt_manual_maps يحلّ بشرياً |

**كل غياب مبرّر بنفس مبدأ "أخذ المبدأ، رفض الهندسة" الذي اعتمدناه عبر ١١ مراجعة.**

---

## الـ٤ توصيات التي تستحقّ التأمّل الجدّي

### 🟡 (١) R²/RMSE كـmetric أساسي لـyield_interval

**الوثيقة:** "الإبلاغ عن R² و RMSE وليس فقط الدقة الكلية"

**الحالة في سهول:**
- `yield_interval` فيه coverage%، n_calibration، PENDING status
- ينقصه: RMSE تاريخي + error per zone

**لماذا التأجيل:** **لا بيانات حصاد فعلية لحساب RMSE الآن!** هذا نفس مبرّر `feedback_closure` المُؤجَّل. لا فرق منطقي بين الاثنين.

**متى يُفعَّل:** عند الوصول لـ٥٠+ outcome مكتمل، يُبنى `yield_metrics.py` يحسب RMSE/R² لكل tenant/zone.

### 🟡 (٢) Place & Time benchmarking — neighbor field comparison

**الوثيقة:** "مقارنة الحقل الحالي مع السنوات الماضية ومع الحقول المجاورة"

**الحالة في سهول:**
- `cross_reference_finder`: حالات مشابهة عبر النظام ✓
- `multi_season_analytics`: مقارنة المواسم ✓
- `farm_memory`: timeline تاريخي ✓
- **ما يُفقَد:** "neighbor field comparison" (مكاني، لا زمني)

**لماذا التأجيل:** يحتاج multi-field deployment في نفس tenant. سهول الآن يدعم tenant→farm→field لكن لا يستخدم relationships مكانية بعد.

**متى يُفعَّل:** عند tenant واحد بـ٥+ حقول في نفس المنطقة + بيانات حقيقية. يصبح زمنه `neighbor_comparison.py` (~٧٠ سطر).

### 🟡 (٣) Data Assimilation (LAI satellite → WOFOST state)

**الوثيقة:** "دمج LAI المستشعرة في النموذج الميكانيكي لإنتاج توقعات غلّة فيزيائية دقيقة"

**الحالة في سهول:**
- WOFOST موجود (RUE-based)
- LAI من satellite يدخل كـinput منفصل
- **ما يُفقَد:** assimilation feedback loop (LAI observation → WOFOST internal state)

**لماذا التأجيل:** يتطلّب:
- LAI dataset كثيف (سنتي 5-10 يوماً)
- معايرة WOFOST لكل tenant
- بيانات حصاد لـvalidate

سهول الحالي عنده spot readings، لا time-series LAI كثيف.

**متى يُفعَّل:** بعد ١٢-١٨ شهراً من النشر (موسمان كاملان من LAI Sentinel-2).

### 🟡 (٤) Field calibration with TDR/met stations

**الوثيقة:** "ربط المؤشرات المستخلصة بقراءات حقيقية من TDR ومحطات الأرصاد"

**الحالة في سهول:**
- `source_of_truth` يفصل بين LAB/MANUAL/SENSOR
- `calibration_loop` معدّ لكن غير مفعّل
- **ما يُفقَد:** workflow صريح لـ"calibration campaign"

**لماذا التأجيل:** هذا workflow operational، لا code gap. يتطلّب:
- توفّر أجهزة TDR ميدانياً
- جدولة قياسات
- protocol معايرة

**متى يُفعَّل:** عند وجود مهندس زراعي مع TDR في الميدان. سيستخدم `calibration_loop` الموجود مباشرةً.

---

## ❌ التوصيات المرفوضة بمبرّر نهائي (٣)

### Phenological Metrics للـcrop classification

**الوثيقة:** "بصمة طيفية-زمانية" لتصنيف المحاصيل آلياً

**لماذا الرفض:** سهول **لا يصنّف المحاصيل**. يقبل `crop_id` كـinput من المزارع/المهندس. هذا اختيار معماري واعٍ:
- لا حاجة لتصنيف ما يعرفه المستخدم
- يحفظ Computational budget للقرارات الفعلية
- يتجنّب false classifications

التصنيف الآلي مفيد في "Remote Sensing-centric platforms" حيث المستخدم لا يعرف ما زُرع. في سهول، المستخدم **هو من زرع**.

### Digital Twin

**الوثيقة:** "نموذج رقمي حي للحقل"

**لماذا الرفض النهائي:** وُثّق ٤ مرّات في الجلسات السابقة. `farm_memory` يحلّ نفس الحاجة بنمط مختلف:
- Twin = simulation + prediction مستمرّ
- Memory = composition + retrieval

سهول يحتاج "ماذا حدث" لا "ماذا سيحدث".

### GEE + Sentinel Hub + 24/7 cloud

**الوثيقة:** "Google Earth Engine هو المعيار الذهبي"

**لماذا الرفض النهائي:** يكسر offline-first الذي أصلحناه قبل ٤٨ ساعة. سهول الميداني يعمل لأيام بلا اتصال. GEE يتطلّب اتصال مستمرّ.

البديل المعتمد: `Copernicus`، `Farmonaut` connectors تُستدعى batch حين الاتصال يعود، تُخزّن النتائج محلياً.

---

## النقطة المنهجية الأعمق

هذه أصعب وثيقة في السلسلة لأنّها **ليست خاطئة**. كل توصية في الوثيقة:
- مبنيّة على بحث منشور
- مدعومة بمجلّات Q1
- صحيحة لسياق "Remote Sensing-centric platform"

**لكنّ سهول ليس Remote Sensing platform.** هو decision-system زراعي للسياق اليمني. الفرق:

| Remote Sensing platform | Decision-system زراعي |
|------------------------|----------------------|
| يكتشف ما يحدث في الحقل | يقترح ما يجب أن يحدث |
| Satellite-first | Lab + Manual first |
| Cloud-streaming | Offline-batch |
| Classification + Monitoring | Decision + Execution support |
| Researchers + Government | Farmers + Agronomists |

**سهول يستهلك Remote Sensing**، هو لا "منصّة Remote Sensing". هذا الفرق يفسّر لماذا ٨/٢٣ غائبة بمبرّر.

---

## السؤال المنهجي: متى تصبح هذه الوثيقة مفيدة؟

عند بناء "**SAHOOL Remote Sensing Layer**" منفصل عن النواة، الوثيقة تصبح **خارطة طريق ممتازة**:
- تختار مؤشرات إضافية (FAPAR، LST)
- تختار خوارزميات (Transformer للـtime-series)
- تختار infrastructure (GEE-based pipeline)

لكنّ هذا **service خارجي** يُغذّي سهول، **ليس داخل سهول النواة**:
```
SAHOOL Remote Sensing Layer (cloud, GEE-based)
  ↓ NDVI/LAI/ETa as batch readings
SAHOOL Core (offline-first, decision-system)
  ↓ recommendations
Human-in-the-loop execution
```

هذه المعمارية تحفظ:
- ✅ مبدأ offline-first في النواة
- ✅ استفادة من Remote Sensing best practices
- ✅ separation of concerns

**هذا "Layer 2 architecture" يستحقّ نقاشاً معمارياً مستقلّاً عند الحاجة، لا بناءً الآن.**

---

## الحكم النهائي

**صفر بناء جديد.** هذا الالتزام مُؤكَّد من جلستين سابقتين:
1. الجلسة قبل ٤٨ ساعة: "إيقاف البناء" بعد المراجعة العاشرة
2. الجلسة قبل ٢٤ ساعة: ٤ أفكار من مرفقات IoT — رُفضت كلّها بنزاهة
3. هذه الجلسة: ٢٣ توصية من Remote Sensing meta-review — نفس النتيجة

**نمط واضح:** كل وثيقة قادمة تصف "نظاماً مثالياً" مختلفاً عن سهول. كل واحدة تحوي أفكاراً جيّدة. **بناء كل فكرة جيّدة = أن أصبح ٥ منصّات في واحدة، لا منصّة واحدة ناضجة**.

النضج الحقيقي:
- معرفة هويّة المشروع الواضحة (decision-system، offline-first، human-in-loop)
- رفض الانجراف نحو "إضافة كل ميزة جيّدة"
- التركيز على ما يخدم المستخدم اليمني، لا على ما يُمتدَح في الأدبيات

النواة تنتظر **بيانات حقيقية ومستخدمين فعليّين**، لا مراجعة أخرى تصف منصّة مختلفة.

---

## للجلسات القادمة — متى نعود لهذه الوثيقة؟

- **عند بناء Remote Sensing Layer منفصل**: الوثيقة خارطة طريق ممتازة
- **عند انتقال للـcloud deployment**: GEE-based approach يستحقّ النظر
- **عند الحاجة لـmulti-spectral analysis**: FAPAR/LST تستحقّ الإضافة
- **عند ١٠٠+ tenant**: ERA5 ربّما يصبح ذا قيمة

حتى ذلك الحين، هذه الوثيقة **محفوظة، غير مُطبَّقة**.
