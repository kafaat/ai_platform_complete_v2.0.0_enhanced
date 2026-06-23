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

## خارطة الطريق (٤ حِزَم + R&D)
- **A — توحيد (الأولويّة القصوى):** إزالة التكرار — **H4 ✅ (#457)** · **H5 ✅ (#464، الملوحة اختياريّة
  + سياسة تفعيل تلقائيّ)** · المتبقّي: ET0 عبر-خدمات + مواءمة `crop_twin`. **شبه مكتمل.**
- **B — فجوات صغيرة عالية القيمة (Yemen-fit):** ✅ **CDSE افتراضيّ (#457)** · **دفتر مياه v98 (#458)** ·
  **Parquet (#458)** · **Water Twin v1/v2 (#459/#460)** · **Kc-NDVI + etc-dual (#461/#462)** ·
  **Open-Meteo + عمق جذور Zr + لوحة etc-dual (#463)** · Shapefile (#456) · **boundary confidence ✅
  (فرع `claude/bundle-b-boundary-confidence`، تصعيد ثقة الحدّ < 0.6 → human_review في الحالة القانونيّة،
  log (ر))**. المتبقّي الصغير: **ربط Zr بحساب الاستنزاف (TAW ديناميكيّ)** · **NDVI من COG الطازج** ·
  LULC (بيانات) · offline-first hardening (تخطيط).
- **D — FieldState Water Canonicalization (جديدة — بتوجيه المستخدم، 2026-06-23):** دمج
  **ETc-dual + Ks/Kc/ET0/الملوحة في `CanonicalFieldState`** (SSOT الفعليّ، `field_state.agronomic`/المسار
  القانونيّ). ⚠️ **يمسّ SSOT — مرحليّ، متأنٍّ.** **D1 ✅ منفَّذ (#466، إضافيّ محفوظ السلوك):** ET0 (عبر
  `core/engines/et0` الموحّد من الطقس المخزَّن) + `etc_mm`=Kc·ET0 + `etc_demand_class` في
  `operational_truths` — دون مسّ التحكيم (validity/execution_mode) ولا مخطّط القاعدة ولا المستهلكين.
  **D3 ✅ منفَّذ (#467، آمن لا يغيّر القرار):** قارئ كنسيّ `api/canonical_water.py` + كتلة `water` موحّدة
  على نموذج الحالة، ومستهلِك `diagnose` يقرؤها من **مصدر واحد** بدل تعدّد مصادر ET0/ETc (يُغلق فئة
  تناقضات). **D2a ✅ منفَّذ (فرع `claude/bundle-d2a-water-stress`، معلوماتيّ محفوظ السلوك):** كتلة
  `water_stress` كنسيّة (AWF + مستويات NORMAL/WATCH/CRITICAL، قرار المستخدم 2026-06-23) من
  `water_ledger`+TAW — بلا تصعيد. **D2b (التصعيد ESCALATE→`human_review`) مؤجَّل بإشارة:** المسند المُقَرّ
  `AWF≤0.2 ∧ depletion_confidence≥0.8 ∧ تأكيد طيفيّ` يتطلّب توصيل NDMI/MSI للحالة الكنسيّة (بقرار
  المستخدم: لا تصعيد بلا تأكيد طيفيّ) — [`decisions/water-stress-d2.md`](water-stress-d2.md). ثمرة
  Bundle A لكنّها أكبر من «إصلاح تكرار»: تجعل الحالة المصدرَ الوحيد لقيم المياه.
- **C — رهانات R&D (مسار منفصل، feature-flags، خارج المسار الحرج):** Field Embeddings · نماذج أساس
  (Prithvi/DINOv3) · SAM2 production (GPU) · Multi-engine Ensemble · Machine Integration (ISOXML).
  تُموَّل صراحةً وتُحقَّق ملاءمتها لليمن.

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
