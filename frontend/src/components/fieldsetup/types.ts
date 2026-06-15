// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/types.ts
// أنواع مشتركة لمعالج تهيئة الحقل المتسلسل (نمط Climate FieldView):
//   حقل → موسم → فحوص تربة (اختياريّة) → إنتاجيّة (اختياريّة) → workspace.
// قابل للتوسّع: الخطوات مُعرَّفة كمصفوفة مرتّبة في steps.ts، فإضافة خطوة
// FieldView جديدة لا تتطلّب إعادة توصيل المعالج.
// ═══════════════════════════════════════════════════════════════

// السياق الذي يحمله المعالج عبر الخطوات. field_id يُملأ فور إنشاء الحقل
// (الخطوة 1) ويُستخدم في كلّ النقاط اللاحقة (موسم/تربة/إنتاجيّة).
export interface WizardContext {
  fieldId: string;
  fieldName: string;
  // محصول الحقل المختار عند الإنشاء — يُستخدم كقيمة افتراضيّة في خطوة
  // الإنتاجيّة (تتطلّب crop) ويُعرَض في خطوة الموسم.
  crop: string;
  areaHa: number;
  centroidLat?: number;
  centroidLon?: number;
}

// واجهة موحّدة لكلّ خطوة بعد إنشاء الحقل. كلّ خطوة تتلقّى السياق وأزرار
// التنقّل (التالي/تخطّي/رجوع) ويُديرها الحاوي FieldSetupWizard.
export interface FieldSetupStepProps {
  ctx: WizardContext;
  // ينتقل للخطوة التالية (يُستدعى بعد نجاح النداء على النقطة الخلفيّة).
  onNext: () => void;
  // يتخطّى الخطوة دون نداء (للخطوات الاختياريّة فقط).
  onSkip: () => void;
  // يرجع للخطوة السابقة.
  onBack: () => void;
  // هل توجد خطوة سابقة (لإظهار/إخفاء زرّ الرجوع).
  canGoBack: boolean;
  // ترتيب الخطوة الحاليّة وإجماليّها (لمؤشّر التقدّم).
  stepIndex: number;
  stepTotal: number;
}

// تعريف خطوة في المصفوفة المرتّبة (steps.ts). إضافة خطوة = إضافة عنصر هنا.
export interface FieldSetupStepDef {
  id: string;
  title: string;
  optional: boolean;
  Component: React.ComponentType<FieldSetupStepProps>;
}
