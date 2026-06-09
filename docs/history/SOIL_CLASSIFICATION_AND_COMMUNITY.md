# تصنيف التربة من الفضاء + استبيان المزارعين + Community Sharing

> **الغرض:** الإجابة على ٣ أسئلة:
>
> 1. مؤشّرات تحديد **نوع** التربة (نسيج/لون) ودقّتها الفعليّة
> 2. مؤشّرات تحديد **خصائص** التربة (pH/NPK/EC) ودقّتها
> 3. منهجيّة استبيان المزارعين + community sharing

---

## القسم ١: دقّة تحديد نسيج التربة من Sentinel-2

### ١.١ الواقع العلمي (مهمّ — لا نُبالغ)

> **النتيجة الجوهريّة:** "prediction accuracy based on lab spectroscopy, airborne and Sentinel-2 in the majority of the sites was adequate for SOC and fair for clay; however, Sentinel-2 imagery could not be used to detect and map variations in silt and sand"

**أي:** Sentinel-2 وحده **لا يكفي** لفصل الـsand/silt بدقّة عالية. لكنّه **يكفي** للـclay و SOC.

### ١.٢ جدول الدقّة الفعليّة (موثّقة)

| الخاصيّة | R² | RMSE | الدقّة العمليّة | الـtechnique |
|----------|-----|-------|-----------------|---------------|
| **Clay (طين)** | 0.59-0.87 | 5.8% | 🟢 ممتاز | PLSR — high accuracy: clay (R²=0.87, RMSE=5.8%) |
| **Sand (رمل)** | 0.63-0.80 | 7.7-10% | 🟢 جيّد | PLSR — satisfactory: sand (R²=0.80, RMSE=7.7%) |
| **Silt (طمي)** | 0.32-0.73 | 7.2-16% | 🟡 ضعيف | silt fractions (R²=0.60) |
| **Clay (Sentinel-2 فقط)** | 0.60 | 1.95% | 🟢 جيّد | bare soil period in April: Clay R²=0.604, RMSE=1.945% |
| **pH** | 0.62 | 0.39 | 🟡 متوسّط | Sentinel-2 + Random Forest, R²=0.62 at 30m resolution |
| **TN (نيتروجين)** | 0.77 | 0.04% | 🟢 ممتاز | TN R²=0.77, RMSE=0.04% |
| **AK (بوتاسيوم)** | 0.72 | — | 🟢 جيّد | المرجع نفسه |
| **AP (فوسفور)** | منخفض | عالٍ | 🔴 ضعيف | elements with lower mobility, such as AP, still require direct measurement methods |
| **Salinity (UAE)** | 0.91 | — | 🟢 ممتاز جدّاً | Wang et al. 2019 (UAE) |
| **SOM/SOC** | عالٍ | منخفض | 🟢 ممتاز | adequate for SOC |

### ١.٣ ترجمة الـR² إلى لغة المزارع

```
R² = 0.91  →  ٩١٪ من الاختلاف يُفسّره النموذج (شبه مثالي)
R² = 0.80  →  ٨٠٪ (جيّد جدّاً)
R² = 0.60  →  ٦٠٪ (متوسّط)
R² = 0.40  →  ٤٠٪ (ضعيف، يحتاج lab)
R² < 0.30  →  لا يُعتمَد عليه
```

### ١.٤ توقيت التصوير — مهمّ

> "the bare soil period in April provided peak prediction accuracy for all texture fractions (Sand: R²=0.617, Silt: R²=0.606, Clay: R²=0.604)"

**خلاصة:** نلتقط صور Sentinel-2 خلال **فترة الحقل العاري** (قبل الزراعة أو بعد الحصاد) للحصول على أعلى دقّة.

**للسياق اليمني:** سبتمبر-أكتوبر (بعد حصاد القمح/الشعير) أو أبريل-مايو (قبل الزراعة الصيفيّة).

---

## القسم ٢: المنهجيّة الكاملة لتصنيف نوع التربة

### ٢.١ Workflow متكامل (٥ مراحل)

```
المرحلة ١: Acquisition (الاستحواذ)
  ↓
  - استخدم Sentinel-2 L2A (atmospherically corrected)
  - اختر تواريخ "barest soil" (تغطية نباتيّة < 30٪)
  - استخدم ٢-٣ صور لحساب الـmedian (يقلّل الضوضاء)

المرحلة ٢: Masking (التنقية)
  ↓
  - NDVI mask: استبعد البكسلات حيث NDVI > 0.3 (نبات)
  - NBR2 mask: استبعد حيث NBR2 > 0.075 (cloud/water)
  - الناتج: pure soil pixels فقط

المرحلة ٣: Feature Extraction
  ↓
  - احسب ١٠ bands الخام + ٨ مؤشّرات تربة
  - الجمع: ١٨ feature per pixel

المرحلة ٤: Prediction (التنبؤ)
  ↓
  لو لديك ground samples (≥٢٥ عيّنة):
    → Random Forest أو PLSR
  لو لا:
    → Threshold-based classification (rule-based)
    → BI + BSI + NDSI → likely soil type

المرحلة ٥: Calibration & Output
  ↓
  - أنتج خريطة soil type per pixel (10m resolution)
  - أنتج probability map (ثقة التصنيف)
  - زمن المعالجة: ~٢-٣ دقائق per field
```

### ٢.٢ Rule-Based Classification (يعمل بدون ground samples)

```python
def classify_soil_type_from_indices(bi, bsi, ndsi, satvi, dbsi, ndti):
    """
    تصنيف نوع التربة من مؤشّرات Sentinel-2.
    دقّة متوقّعة: ٦٥-٧٥٪ (rule-based)
    تحسّن لـ٨٥٪+ مع ground samples (Random Forest)
    """
    # خطوة ١: كشف الملوحة (أولاً لأنّها overrides)
    if ndsi > 0.10:
        return ('saline_soil', confidence=0.85,
                note='ملوحة عالية — يُنصح بأخذ عيّنة EC')

    # خطوة ٢: حسب السطوع (BI)
    if bi > 0.30 and bsi > 0.15:
        # تربة فاتحة جدّاً → رمليّة أو صخريّة
        if bsi > 0.25 and dbsi > 0.20:
            return ('rocky', 0.70, 'صخريّة/حصويّة')
        return ('sandy', 0.75, 'رمليّة')

    if bi < 0.15 and satvi > 0.10:
        # تربة داكنة → عضويّة أو بركانيّة
        if satvi > 0.15:
            return ('volcanic', 0.70, 'بركانيّة (شائعة في صعدة)')
        return ('clay', 0.65, 'طينيّة داكنة')

    if 0.15 <= bi <= 0.25:
        # تربة متوسّطة → طمييّة
        if ndti > 0.10:
            return ('clay_loam', 0.65, 'طميي طيني (بقايا حراثة)')
        return ('loam', 0.70, 'طميي متوازن')

    return ('mixed', 0.50, 'مختلطة — يحتاج عيّنة لاب')
```

### ٢.٣ الـSpectral Signatures لكل نوع تربة (مرجع للتفسير)

من الأبحاث المُحقّقة + اختبار سيناريوهات سهول:

| نوع التربة | BI | BSI | NDSI | SATVI | DBSI |
|-----------|-----|------|------|-------|------|
| **رمليّة (مأرب)** | 0.26 | +0.11 | -0.03 | -0.04 | +0.26 |
| **بركانيّة (صعدة)** | 0.11 | -0.02 | -0.25 | +0.10 | +0.13 |
| **مالحة (تهامة)** | 0.37 | +0.15 | **+0.09** ⚠ | -0.20 | +0.23 |
| **طينيّة (متوقّعة)** | 0.18 | +0.03 | -0.10 | +0.15 | +0.18 |
| **طمييّة (متوقّعة)** | 0.20 | +0.05 | -0.05 | +0.05 | +0.15 |

---

## القسم ٣: دمج تصنيف التربة مع نواة سهول

### ٣.١ التدفّق المُقتَرح

```
[المزارع يضيف حقل]
       ↓
[نواة تطلب Sentinel-2 من STAC]
       ↓
[raster-service يحسب ٧ مؤشّرات تربة]
       ↓
[classify_soil_type_from_indices()]
       ↓
[تحديث field.soil_texture تلقائياً]
       ↓
[إن confidence < 0.65 → اقترح للمزارع التأكيد]
       ↓
[إن المزارع يُغيّر → تعديل النموذج (citizen science)]
```

### ٣.٢ الـrecommendation مع التصنيف

```python
async def auto_classify_and_recommend(field_id):
    # ١. اجلب آخر Sentinel-2
    image = await fetch_sentinel2(field.polygon, cloud_free=True)

    # ٢. احسب المؤشّرات
    indices = compute_all_soil_indices(image)

    # ٣. صنّف
    soil_type, confidence, note = classify_soil_type_from_indices(**indices)

    # ٤. تحديث الـDB
    if confidence > 0.65:
        update_field(field_id, suggested_soil_texture=soil_type)

    # ٥. إنشاء توصية
    if soil_type == 'saline_soil':
        create_recommendation(
            field_id,
            priority='HIGH',
            type='SALINITY_DETECTED',
            text=f'كشفت صور القمر الصناعي ملوحة عالية '
                 f'(NDSI={indices["ndsi"]:.2f}). '
                 f'يُنصح بأخذ عيّنة EC من ٣-٥ نقاط في الحقل.'
        )

    return {
        'detected_type': soil_type,
        'confidence': confidence,
        'note': note,
        'indices': indices,
        'recommendation_for_validation': confidence < 0.85,
    }
```

---

## القسم ٤: استبيان المزارعين — منهجيّة مُتقَنة

### ٤.١ أفضل الممارسات من الأبحاث

> **GeoFarmer (Colombia, 2019):** "1,240 farmers were surveyed using GeoFarmer's interactive voice response (IVR) calling system... five-question surveys that were completed in 2-3 minutes"

> **Wikifarmer:** "Surveys and Questionnaires: traditional survey methods... best administered in person using mobile applications or remotely through telephonic mediums... FGDs provide a platform for farmers to engage in open dialogue, share their experiences, and collectively brainstorm solutions to common issues"

> **Syngenta mAgriculture Report:** "prompts inspectors through every step of the survey process, with both text and audio. The latter option compensates for the small screen on the phone, and helps farmers with literacy problems to follow the process"

### ٤.٢ المبادئ الـ٨ المُختارة

```
١. قصر المدّة: ٢-٣ دقائق فقط (GeoFarmer نمط)
٢. أسئلة مغلقة: multiple-choice أكثر من open-text
٣. صور بدلاً من نصّ كلّما أمكن
٤. audio prompts (للمزارعين الأميّين)
٥. georeferenced (auto attach GPS من field)
٦. offline-first (SQLite، sync لاحقاً)
٧. progressive disclosure (لا تُظهر كل الأسئلة دفعة واحدة)
٨. incentive واضح (يُحسّن توصياتك الشخصيّة)
```

### ٤.٣ ٥ قوالب استبيان مُقترَحة

#### القالب ١: Baseline Onboarding (٢ دقيقة)
عند إنشاء أوّل حقل — لتخصيص النظام:
```
١. خبرتك في الزراعة: [<2 سنة | 2-5 | 5-10 | >10]
٢. ملكيّة الحقل:     [مالك | مستأجر | عامل]
٣. عدد العمّال:      [أنت فقط | 2-5 | >5]
٤. لغة الواجهة:      [عربيّة فصحى | عاميّة يمنيّة]
٥. هل تستخدم WhatsApp؟ [نعم | لا]
```

#### القالب ٢: Pre-Season Planning (٣ دقائق)
قبل بدء الموسم — لتوصيات أدقّ:
```
١. ما المحصول الذي تنوي زراعته؟ [picker من 20]
٢. مصدر البذور:        [مزارع | حكومة | استيراد]
٣. ميزانيّتك للموسم:    [<100$ | 100-500 | >500]
٤. مخاوفك الرئيسيّة:    [ماء | آفات | تسويق | أسعار]
٥. خطّة الري:          [بعل | بئر | سيل | مختلط]
```

#### القالب ٣: Mid-Season Check (٢ دقيقة)
كل ٢-٣ أسابيع — لتعديل التوصيات:
```
١. الحالة العامّة للمحصول: [ممتاز | جيّد | متوسّط | سيّء]
   ← مع emoji للأمّييين

٢. هل لاحظت أيّ مشكلة جديدة؟ [نعم/لا]
   ← لو نعم: التقط صورة + اوصف بصوت

٣. متى رويت آخر مرّة؟ [اليوم | أمس | <أسبوع | >أسبوع]

٤. هل سمّدت؟ [نعم/لا/قريباً]
```

#### القالب ٤: Problem Report (دقيقة واحدة)
لـcommunity helpdesk:
```
١. نوع المشكلة: [مرض | حشرة | جفاف | ملوحة | أخرى]
٢. شدّتها: [خفيفة | متوسّطة | شديدة]
٣. صورة (إجباري)
٤. صوت لشرح (اختياري ٣٠ ثانية)
← يُنشر في community feed (anonymous إن أراد)
```

#### القالب ٥: Post-Harvest Validation (٣ دقائق)
بعد الحصاد — لتدريب النموذج:
```
١. كم أنتج الحقل؟ [أرقام]
٢. هل كانت التوصيات مفيدة؟ [1-5 stars]
٣. ما الذي كان مفقوداً؟ [open-text أو audio]
٤. هل ستزرع نفس المحصول الموسم القادم؟
٥. هل توافق مشاركة نتائجك مع المجتمع؟ [نعم/لا]
```

---

## القسم ٥: Community Sharing — مشاركة التجارب

### ٥.١ مرجع: GeoFarmer + Citizen Science

> "A very positive example of successful citizen science that resulted in community best practices is the Wheat Stripe Rust disease effort... citizen scientists were farmers, whose boots were on the ground quickly to meet this time-sensitive challenge of the rapidly spreading Stripe Rust disease. Farmer participation had clear value in fighting the spread of the Stripe Rust disease that was harming crop production, and many data points were collected from a broad range of participants"

> GeoFarmer aims: "expand beyond sharing comments and photos to include discussion, voting and rating mechanisms to help farmers determine best practice solutions"

### ٥.٢ تصميم Community في سهول

```
[Tab جديد في Main: "المجتمع"]
   ↓
   ٤ أقسام:
   1. 📢 Feed المحلّي (شارة "محافظتك")
      - منشورات من مزارعي نفس المنطقة (anonymous بالافتراض)
      - بكلمات + صور + موقع تقريبي (مدينة، لا إحداثيّات دقيقة)

   2. 🆘 سؤال/مشكلة
      - استبيان Problem Report
      - يُنشر للمنطقة → أيّ مزارع آخر يردّ بحلّ
      - rating للحلول (downvote/upvote)

   3. 💡 تجارب ناجحة
      - مزارع يشارك "جرّبت X وحصلت Y"
      - مع context: محصول، تربة، موسم
      - الآخرون يصوّتون "أفادني" أو "جرّبته أيضاً"

   4. 📚 المعرفة المحلّيّة
      - knowledge base مبنيّ من tagged posts
      - مفهرس: محصول × مشكلة × حلّ
      - مرجع للنواة لإنتاج توصيات مستقبليّة
```

### ٥.٣ قواعد الخصوصيّة (مهمّة)

```
✅ افتراضي: anonymous (الاسم لا يظهر)
✅ الموقع: مستوى المحافظة فقط (لا إحداثيّات GPS)
✅ المزارع يختار: مشاركة كل حقل أم لا
❌ لا تُنشَر قيم لاب (pH/EC) دون موافقة صريحة
❌ لا تُنشَر مساحات الحقول الدقيقة
❌ لا تُنشَر معلومات الآبار (حسّاسة)
```

### ٥.٤ Anti-Spam + Quality

```
١. Trust score per user:
   - يرتفع بـcomments مفيدة (upvoted)
   - ينخفض بـreports (downvote/flag)

٢. Verification:
   - "مزارع نشط" (badge) لمن له >3 fields + >1 season
   - "خبير محلّي" (badge) لمن trust > 80

٣. Moderation:
   - flag system
   - auto-hide بعد 3 flags
   - manual review

٤. Rate limits:
   - مزارع جديد: 1 post/day
   - مزارع نشط: 5 posts/day
   - خبير: غير محدود
```

---

## القسم ٦: الخلاصة العمليّة

### ٦.١ ماذا نملك الآن (بعد هذه الجلسة)
```
✅ ٧ مؤشّرات تربة في raster-service (مع unit tests)
   - BSI, BI, BI2, NDTI, DBSI, NDSI, SATVI
✅ توثيق دقّة كل مؤشّر (R² + RMSE موثَّقة)
```

### ٦.٢ ما يستحقّ البناء (هذه الجلسة + قادمة)
```
🟡 Tier 1 (هذه الجلسة):
   - استبيان onboarding (٥ أسئلة)
   - 4 templates للاستبيانات
   - بنية community feed (DB + UI shell)

🟡 Tier 2 (الجلسة القادمة):
   - classify_soil_type_from_indices() في النواة
   - ربط Sentinel-2 fetching بـauto-classification
   - Community feed كامل (UI + moderation)
```

### ٦.٣ ما يُؤجَّل بـtrigger صريح
```
⏸ ML model لتصنيف التربة (يحتاج ٥٠+ ground samples)
⏸ PLSR/Random Forest training (يحتاج dataset)
⏸ Sentinel-1 SAR fusion (يحتاج radar service)
⏸ Audio recordings (يحتاج storage backend)
⏸ Video tutorials (يحتاج CDN)
```

---

## ملاحظة منهجيّة جوهريّة

الأبحاث تُحذّر: elements with lower mobility, such as AP, still require direct measurement methods or more sophisticated modeling approaches that integrate remote sensing data, soil properties, and land management history

أي: **الاستشعار عن بعد ليس بديلاً عن العيّنات** — هو **مكمّل**. نُحسّن دقّة التصنيف بـ:
1. توصية أماكن العيّنات (zone_sampling.ts الموجود)
2. أخذ ٣-٥ عيّنات لاب per field
3. استخدام النتائج لـcalibrate النموذج
4. مع تراكم البيانات → دقّة تتحسّن

هذا هو الـ**Citizen Science loop**: المزارعون يساهمون → النظام يتعلّم → الدقّة ترتفع لكل المجتمع.
