# فحص edge-inference الكامل

## الإصلاحات المطبّقة (مشاكل حقيقيّة وُجدت)

### 🟠 لا حدّ لحجم الملفّ المرفوع (DoS)
- /inference/pest-detect و /inference/yield-estimate كانا يقرآن
  `await file.read()` بلا حدّ → صورة ضخمة (GB) تستهلك الذاكرة وتُسقط الخدمة.
- الإصلاح: حدّ 10MB لكلّ صورة (413 لو تجاوز) + تحقّق content-type=image/* (415).

### 🟠 Image.open بلا معالجة أخطاء (500 → 400)
- predict يفتح الصورة بلا try → ملفّ تالف/ليس صورة = استثناء غير معالَج (500).
- الإصلاح: لفّ predict/extract_features بـtry → 400 واضح "صورة غير صالحة".

## ما كان سليماً بالفعل (لا إصلاح)
- sync_service: تصميم ممتاز —
  - queue_result: أسماء ملفّات بدقّة microsecond (لا تصادم)
  - sync_result: fallback نظيف للـqueue عند فشل المزامنة
  - process_queue: يحذف بعد 200 فقط (لا تكرار) + يتوقّف عند أوّل فشل (يحفظ
    الترتيب ولا يُرهق خادماً معطّلاً)
- create_task محفوظ على app.state (أُصلح سابقاً — لا GC)
- _periodic_sync: حلقة معزولة بـtry (خطأ لا يوقفها)
- /inference endpoints تحليليّة (مقبولة مكشوفة خلف العزل)
- /sync/trigger: يعالج OFFLINE_MODE بأمان
- كلّ الملفّات تُترجم (main, sync_service, download_models)

## التحقّق
- edge يُترجم · 314/314 · لا regressions

## ملاحظة صدق
- /sync/trigger ما زال بلا مصادقة صريحة — لكنّه يقرأ من queue محلّي ويزامن
  لـcloud بتوكن الخدمة (self.token)؛ مقبول خلف عزل الشبكة. إضافة Depends
  ممكنة لكن غير حرجة (لا يقبل مدخلات خارجيّة تُغيّر سلوكاً حسّاساً).
- حدّ 10MB افتراض معقول لصور المحاصيل — اضبطه إن لزمتك دقّة أعلى.
- pest_detector في وضع simulation (For MVP) — placeholder صادق لنموذج ONNX
  غير مُدرَّب بعد، ليس خطأً.
