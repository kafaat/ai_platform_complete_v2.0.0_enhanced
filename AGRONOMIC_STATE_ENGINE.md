# طبقة الغراء: agronomic_state_engine (الحالة الزراعيّة الموحّدة)

بنيتُ **طبقة الغراء** التي شخّصتها المراجعتان — لا "عقل جديد" بل تأليف
(composition) يجمع اللبنات الموجودة في `CanonicalFieldState` واحد.

## المبدأ (من المراجعتين)
- الدمج يحدث **مرّة واحدة** هنا → حالة موحّدة
- decision_engine يصبح **policy-over-state** (لا يعيد تفسير الخام)
- يمنع double-interpretation bugs وparallel intelligence stacks

## ما يعيد استخدامه (لا ازدواج)
| اللبنة الموجودة | الاستخدام في الغراء |
|------------------|---------------------|
| `fuse_health` (engines/fusion.py) | دمج المؤشّرات الطيفيّة → crop_vigor + ثقة |
| `detect_trend` (time_series.py) | التحليل الزمني → slope/anomaly |
| `fuse_confidence` (knowledge_levels.py) | الثقة ≤ سقف أدنى مصدر |
| قواعد SAL-SOIL-* | عتبات حلّ تعارض الملوحة |

**صفر إعادة اختراع** — تحقّق آليّ يثبت استدعاء fuse_health + fuse_confidence.

## CanonicalFieldState (الغراء الحقيقي)
يجمع: field_id, operational_truths (crop_vigor/salinity_risk/ndvi_trend/
effective_status), confidence + reason, provenance (سلسلة أدلّة), contradictions,
missing_signals, + الإصدارات (schema_version, fusion_strategy_version للـreplay).

## حلّ التعارض (arbitration) — أسبقيّة صريحة لا IF عشوائيّة
**القاعدة الحاسمة المُختبَرة**: ملوحة حرجة (ECe>8) تتجاوز NDVI الإيجابي.
- المنطق: NDVI قد يتأخّر زمنيّاً؛ الملوحة انهيار بنيوي طويل الأمد
- النتيجة: effective_status = salinity_limited (لا vigor_led)
- مُسنَد لـSAL-SOIL-03
- تربة سليمة → vigor_led (المؤشّر الطيفي يقود)

## الثقة رياضيّة لا تجميليّة
- مُشتقّة من سقف المصدر: NDVI استقرائي → سقف medium (لا high مزيّف!)
- تنخفض بنقص المُدخلات + قِدَم البيانات (>14 يوماً)
- صدق: NDVI من القمر لا يدّعي ثقة "عالية" — هذا صحيح إبستمولوجيّاً

## الصدق
- المؤشّرات الغائبة تُعلَن صراحةً (missing_signals)
- لو فشلت لبنة، يُسجَّل في contradictions (لا اختراع قيمة)
- freshness SLA: بيانات >14 يوماً تخفض الثقة

## التحقّق
- 492/492 roadmap (+8) · 0 خطأ ترجمة
- 8 اختبارات: تعارض/زمني/ثقة/إسناد/صدق/إصدارات/لا-ازدواج

## ما تبقّى (الخطوة التالية المقترحة)
الطبقة جاهزة لكن **لم تُربط بعد بـdecision_engine** كـpolicy-over-state. الخطوة
التالية: تحويل decide_for_location ليستهلك CanonicalFieldState بدل المؤشّرات
الخام، وربط المخرَج بالبوّابة. تركتُها منفصلة الآن لتراجع التصميم أوّلاً.

## ملاحظة صدق
لم أبنِ ما هو مبنيّ (رفضتُ اقتراح النقد الأوّل ببناء fusion/confidence جديدين).
الغراء يستدعي اللبنات الفعليّة — تحقّق آليّ يثبت ذلك. صحّحتُ توقيعين أثناء
البناء (IndexReading.name/family، detect_trend يحتاج TimePoint) — وجدتهما
بقراءة الكود لا بالافتراض.
