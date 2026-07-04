# FieldView Agent-Inspired Governance Upgrade — 2026-07-04

## الهدف
تحويل Smart Deck من قائمة إجراءات فقط إلى طبقة قرار قابلة للتفسير، مستوحاة من أنماط:

- Capability routing / health checks: شبيه بفكرة Agent-Reach كطبقة قدرات فوق الأدوات.
- Knowledge graph: شبيه بفكرة Understand-Anything وcodebase-memory-mcp في جعل العلاقات مفهومة لا مجرد ملفات أو أزرار.
- Skill governance: شبيه بفكرة SkillSpector في فحص المخاطر قبل الثقة بالمهارة/الأداة.

## ما أضيف

### frontend/src/lib/fieldViewGovernance.ts
- يحسب درجة ثقة FieldView من مصادر القرار:
  - الحقل النشط
  - Sentinel/Timeline
  - الطقس
  - التنبيهات
  - المهام
  - سجل الحقل
  - سياق الوكيل الزراعي
  - سلامة route/stored context
- ينتج graph صغيراً من nodes/edges للعلاقات بين المصادر.
- يخرج score/severity/source evidence/action.

### frontend/src/components/fieldview/FieldViewInsightStrip.tsx
- أضيف مؤشر ثقة المصادر في رأس Smart Deck.
- أضيف نوع card جديد: governance.

### frontend/src/lib/fieldViewActionDeck.ts
- يضيف بطاقة "حوكمة مصادر القرار" عندما تكون المصادر ناقصة أو متدهورة.
- لا يغير قاعدة اختيار الحقل ولا يخطف create-form inputs.

### frontend/src/sections/MapHub.tsx
- يمرر weatherReady و agentContextReady إلى Smart Deck.

### اختبارات
- frontend/src/lib/fieldViewGovernance.test.ts
- توسيع frontend/src/lib/fieldViewActionDeck.test.ts

## القيمة العملية
- لا يكتفي FieldView بعرض الحقل؛ يشرح لماذا الإجراء التالي موثوق أو ناقص.
- يساعد على منع توصيات من سياق ناقص: صور قديمة، سجل ناقص، أو field_id غير صالح.
- يعطي أساساً لاحقاً لبناء لوحة "Field Decision Trace" أو "AI Evidence Pack".
