# قرار استراتيجيّ: التوحيد قبل التوسّع + مُلاءمة اليمن (Capstone)

> خلاصة استراتيجيّة تحكم اتّجاهات الجلسة الأربع (GeoLibre · CultiWise · IrriPro · Agribound).
> الحالة: `accepted` (توافق مستخدم↔وكيل، 2026-06-23). تربط:
> [`gis-direction`](gis-direction.md) · [`precision-ag-direction`](precision-ag-direction.md) ·
> [`water-intelligence-direction`](water-intelligence-direction.md) · [`field-intelligence-direction`](field-intelligence-direction.md).

## السياق
ثمانية مشاريع إلهام نُوقشت اليوم تتقارب نحو **«نظام تشغيل زراعيّ دقيق»** (توأم حقل + قرار مُفسَّر +
تنفيذ + تعلّم). مراجعة كلٍّ منها مقابل **حالة SAHOOL الفعليّة (مُتحقَّقة)** كشفت نمطاً ثابتاً:
**SAHOOL يملك ~٧٠-٨٠٪ من الرؤية أصلاً** (field_state · water kernel FAO-56 · phenology · scenario ·
explainability · prescriptions · boundary/SAM2 · decision/outcome ledger · الدماغ · supervisor-agent).

## المبدأ الحاكم (مُتّفَق عليه)
1. **المشكلة = التشظّي لا نقص الطبقات.** سجلّ الفجوات يوثّق: **H4 ET0 مُكرّر ×4** (Ra متضاربة) · **H5 ريّ
   بصيغتين** · توصيات/حسابات طقس مُكرّرة ([`../gaps/registry.md`](../gaps/registry.md)). إضافة خدمات
   كبرى (WaterServiceV2…) **تُفاقم** المشكلة. «Architecture astronautics» خطر حقيقيّ.
2. **`CanonicalFieldState` هو مصدر الحقيقة الوحيد** المسموح له بحمل (ET0/Kc/ETc/رطوبة/فينولوجيا/إجهاد).
   لا تُحسَب في أربعة أماكن.
3. **«الطبقات الـ15» = نموذج ذهنيّ / North Star، لا backlog** — لتفادي تحسينات محلّيّة تُضيّع الرؤية البعيدة.
4. **مُلاءمة اليمن (Yemenization) قبل استيراد خرائط الغرب.** مزارع الجوف/صعدة يملك هاتفاً/بئراً/مضخّة/
   إنترنت ضعيفاً — لا John Deere/Trimble/variable-rate seeder. فالأولويّة: **offline-first + ريّ/محصول
   مُفسَّر + عمليّات بسيطة**، لا الأتمتة الآليّة. (لذا أُوقِف ISOXML بصدق؛ Shapefile كافٍ #456.)

## خارطة الطريق (٣ حِزَم)
- **A — توحيد (الأولويّة القصوى، ~٤-٨ أسابيع):** إزالة التكرار — H4 (ET0 → `core/engines/et0.py`)، H5
  (الريّ)، التوصيات/الطقس المُكرّرة. الناتج: `CanonicalFieldState` = SSOT فعليّ.
- **B — فجوات صغيرة عالية القيمة (Yemen-fit، ~١-٣ أشهر):** offline-first hardening · دفتر مياه يوميّ ·
  Dual Kc · عمق جذور ديناميكيّ · تصفية LULC · boundary confidence (موجود — تشغيل) · **GeoParquet**
  (يربط ورشة SQL #451) · **Shapefile للوصفة (✅ #456)**.
- **C — رهانات R&D (مسار منفصل، feature-flags):** Field Embeddings · Foundation Models (Prithvi/DINOv3) ·
  SAM2 deployment (GPU) · Multi-engine Ensemble · Machine Integration (ISOXML/John Deere). **ليست في
  المسار الحرج**؛ تُموَّل صراحةً وتُحقَّق ملاءمتها لليمن.

## المراحل (تسلسل)
1. **Unify** (أصلح H4/H5 وكلّ مصادر الحقيقة). 2. **Explain + Offline** (أفضل تجربة ريّ/محصول مُفسَّرة دون
اتّصال). 3. **Operational Excellence** (موثوقيّة/مراقبة/اختبارات/صلابة). 4. **Precision Agriculture** (وصفات/
مناطق/خرائط). 5. **Automation & R&D** (آلات/نماذج أساس/وكلاء).

## الميزة التنافسيّة الحقيقيّة (لا «عدد الخدمات/الوكلاء»)
**صدق التوصية · قابليّة التفسير · العمل دون إنترنت · التكيّف مع الواقع الزراعيّ اليمنيّ.** هذه أصلاً أقوى
نقاط SAHOOL — إذا وُحِّدت وشُغِّلت صحيحاً. (والصدق الذي تعيشه المنصّة — honest-503، TODOs مُعلَنة، لا
تلفيق — ميزة لا طبقة تُضاف.)

## الخطوة التالية الموصى بها
**A1: توحيد ET0 (H4)** إلى `core/engines/et0.py` — أساس CanonicalFieldState + إصلاح خطأ صحّة موثَّق.
ثمّ **GeoParquet** (B). تُخطَّط بمسارها.
