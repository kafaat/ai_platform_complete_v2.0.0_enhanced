// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/steps.ts
// مصفوفة الخطوات المرتّبة لمعالج تهيئة الحقل (بعد إنشاء الحقل). نقطة التوسّع
// الوحيدة: لإضافة خطوة FieldView جديدة (مثل: حدود الإدارة، الأجهزة، أوّل تنبيه)
// أضِف عنصراً هنا — الحاوي FieldSetupWizard يقرأ هذه المصفوفة ولا يحتاج إعادة
// توصيل. الترتيب في المصفوفة هو ترتيب الظهور.
// ═══════════════════════════════════════════════════════════════
import SeasonStep from './SeasonStep';
import SoilTestStep from './SoilTestStep';
import YieldStep from './YieldStep';
import type { FieldSetupStepDef } from './types';

// الخطوة 1 (إنشاء الحقل عبر AddFieldWithMap) ليست هنا — هي مدخل المعالج. هذه
// المصفوفة هي الخطوات اللاحقة المُتسلسلة: موسم (إلزاميّ) → تربة (اختياريّ) →
// إنتاجيّة (اختياريّ) → إنهاء (مساحة العمل).
export const FIELD_SETUP_STEPS: FieldSetupStepDef[] = [
  { id: 'season',    title: 'موسم زراعي',          optional: false, Component: SeasonStep },
  { id: 'soil-test', title: 'فحوص التربة',         optional: true,  Component: SoilTestStep },
  { id: 'yield',     title: 'تقدير الإنتاجيّة',     optional: true,  Component: YieldStep },
];
