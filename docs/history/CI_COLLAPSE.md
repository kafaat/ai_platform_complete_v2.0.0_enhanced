# إغلاق الحلقة — مدخل CI واحد + evidence (مراجعة 14/15)

## القرار: Collapse لا Expand (يتّفق مع تحذيري السابق)
المراجعة 14 صحّحت المسار: توقّف عن بناء طبقات تحقّق، اقفلها في مسار واحد،
انتقل لـevidence تشغيلي. **نفّذتُ الـcollapse** بدل مزيد من التجريد.

## ما نُفّذ
### مدخل CI واحد (make ci)
بدل gates متعدّدة → 3 أنواع حقيقة فقط:
- static (py_compile) · domain (roadmap 376 + chaos 12) · system (RLS حيّ)
`make ci` ينتج **build/evidence.json** — مصدر الحقيقة الوحيد.

### evidence.json (الناتج الوحيد المهمّ)
- overall: pass/fail
- static + domain (مُنفَّذة offline)
- invariants flags (7 بنيويّة ✓ + 2 يُعلَّمان requires_live بصدق)
- sha256 (حماية من التعديل الصامت — مُختبَر: يكشف التلاعب)

### أدوات التوقيع (اختياريّة — إنتاجيّة)
tools/sign_evidence.py + verify_evidence.py — تعيد استخدام مفتاح RS256.
الـhash كافٍ للحماية الأساسيّة؛ التوقيع يُثبت المصدر (لـCI الإنتاجي).

## إعادة التصنيف (تقليل، لا إضافة)
- invariants.yaml → **توثيق** (لا محرّك منفصل)
- verify_invariants.py → diagnostic (ليس gate إلزاميّاً)
المدخل الواحد make ci هو البوّابة؛ البقيّة diagnostics.

## ما رفضتُ (over-engineering صريح)
- ❌ DSL engine منفصل · ❌ self-healing runtime · ❌ AST verifier وهمي
- ❌ drift detector (لا AST verifier حقيقي ليُقارَن)
- التوقيع الكامل بـhash-chain: نفّذتُ hash + sign اختياري؛ لم أبنِ سلسلة
  hash معقّدة (مبالغة لمرحلة المشروع).

## التحقّق
- 376/376 · 12 chaos · evidence.json نظيف (overall=pass)
- hash يكشف التلاعب (مُختبَر both ways)

## الاستخدام
- make ci → static + domain + evidence (offline)
- make verify → الحلقة الحيّة الكاملة (postgres، جهازك)
- python tools/verify_evidence.py → تحقّق نزاهة evidence

## ملاحظة صدق ختاميّة
هذه المراجعة (14) أصابت: نظام التحقّق كان يكبر أكثر من المنتج. الـcollapse
هو القرار الصحيح. **build/ artifact مؤقّت — لا يُحزَم** (يُولَّد عند make ci).
system truth الحقيقي (RLS تحت تزامن، temporal تحت حدث متأخّر) لا يُثبَت إلّا
على postgres حيّ — evidence.json يعلّمه requires_live بصدق، لا يدّعيه.
