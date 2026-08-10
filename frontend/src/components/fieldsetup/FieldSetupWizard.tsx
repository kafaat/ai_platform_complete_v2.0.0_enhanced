// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/FieldSetupWizard.tsx
// حاوي معالج تهيئة الحقل المتسلسل (نمط Climate FieldView):
//   ① إنشاء الحقل (AddFieldWithMap القائم — خريطة + مضلّع + مساحة geodesic)
//   ② موسم زراعي (إلزاميّ)
//   ③ فحوص تربة (اختياريّة — تُتخطّى)
//   ④ تقدير إنتاجيّة (اختياريّ — يُتخطّى)
//   ⑤ إنهاء → مساحة عمل الحقل (تفاصيل الحقل)
// السلسلة مبنيّة على نقاط API حقيقيّة (لا اختراع). الخطوات اللاحقة مُعرَّفة في
// steps.ts كمصفوفة مرتّبة ⇒ التوسّع بإضافة عنصر دون إعادة توصيل هذا الحاوي.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import AddFieldWithMap from '../AddFieldWithMap';
import { FIELD_SETUP_STEPS } from './steps';
import type { WizardContext } from './types';
import type { FieldImportInput } from '../../services/api';
import type { FieldData } from '../AddFieldWithMap';

interface Props {
  // إنشاء الحقل الحقيقيّ (POST /api/v1/fields) — يُمرَّر من الصفحة الحاوية.
  // يجب أن يُرجِع سجلّ الحقل المُنشأ (ردّ الخادم) كي يلتقط المعالج field_id.
  onSaveField: (data: FieldData) => Promise<Record<string, unknown>>;
  // استيراد حدّ حقل من ملفّ (POST /api/v1/fields/import) — اختياريّ، يُرجِع السجلّ كذلك.
  onImportField?: (payload: FieldImportInput) => Promise<Record<string, unknown>>;
  // إلغاء/إغلاق المعالج كلّه.
  onCancel: () => void;
  // اكتمال السلسلة (أو الوصول لمساحة العمل) — يتلقّى field_id للانتقال إليه.
  onComplete: (fieldId: string) => void;
}

// يستخرج معرّف الحقل من ردّ الخادم بأسماء بديلة (دفاعيّ — لا انهيار على شكل ناقص).
function extractFieldId(rec: Record<string, unknown> | null | undefined): string | null {
  if (!rec || typeof rec !== 'object') return null;
  const v = rec.field_id ?? rec.id;
  return v == null ? null : String(v);
}

function readNum(rec: Record<string, unknown> | null, ...keys: string[]): number {
  if (!rec) return 0;
  for (const k of keys) {
    const v = rec[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    const n = Number(v);
    if (Number.isFinite(n) && v != null && v !== '') return n;
  }
  return 0;
}

function readStr(rec: Record<string, unknown> | null, fallback: string, ...keys: string[]): string {
  if (!rec) return fallback;
  for (const k of keys) {
    const v = rec[k];
    if (v != null && v !== '') return String(v);
  }
  return fallback;
}

export default function FieldSetupWizard({ onSaveField, onImportField, onCancel, onComplete }: Props) {
  // -1 = خطوة إنشاء الحقل (AddFieldWithMap). 0..n = خطوات steps.ts اللاحقة.
  const [stepIdx, setStepIdx] = useState(-1);
  const [ctx, setCtx] = useState<WizardContext | null>(null);

  const steps = FIELD_SETUP_STEPS;
  // مؤشّر التقدّم يشمل خطوة الإنشاء (1) + الخطوات اللاحقة.
  const stepTotal = steps.length + 1;

  // يبني السياق من ردّ الخادم بعد الإنشاء/الاستيراد. لا يتقدّم بلا field_id صالح
  // (الصفحة الحاوية تكون قد عرضت toast خطأ عبر دالّة الحفظ نفسها).
  const buildCtxAndAdvance = (rec: Record<string, unknown>, fallbackName: string, fallbackCrop: string) => {
    const fieldId = extractFieldId(rec);
    if (!fieldId) return; // الحفظ فشل أو الردّ بلا معرّف — يبقى المعالج على خطوة الإنشاء
    setCtx({
      fieldId,
      fieldName: readStr(rec, fallbackName, 'name_ar', 'name', 'field_name'),
      crop: readStr(rec, fallbackCrop, 'crop', 'crop_ar'),
      areaHa: readNum(rec, 'area_ha', 'area'),
      centroidLat: readNum(rec, 'centroid_lat', 'lat') || undefined,
      centroidLon: readNum(rec, 'centroid_lon', 'lon') || undefined,
    });
    setStepIdx(0);
  };

  // غلاف حفظ الحقل: يستدعي الحفظ الحقيقيّ ثمّ يلتقط field_id ويتقدّم. يُعيد رمي
  // الخطأ كي يعرضه AddFieldWithMap في حقله الخاصّ (لا ابتلاع).
  const handleSave = async (data: FieldData) => {
    const rec = await onSaveField(data);
    buildCtxAndAdvance(rec || {}, data?.name ?? 'حقل', data?.crop ?? '—');
  };

  const handleImport = onImportField
    ? async (payload: FieldImportInput) => {
        const rec = await onImportField(payload);
        buildCtxAndAdvance(rec || {}, payload?.name ?? 'حقل', payload?.crop ?? '—');
      }
    : undefined;

  // ① خطوة إنشاء الحقل — نعيد استخدام AddFieldWithMap كما هو (لا إعادة بناء).
  if (stepIdx < 0 || !ctx) {
    return (
      <AddFieldWithMap
        onSave={handleSave}
        onImport={handleImport}
        onCancel={onCancel}
      />
    );
  }

  // التنقّل بين الخطوات اللاحقة. تجاوز آخر خطوة ⇒ اكتمال (مساحة العمل).
  const goNext = () => {
    if (stepIdx >= steps.length - 1) { onComplete(ctx.fieldId); return; }
    setStepIdx(i => i + 1);
  };
  const goBack = () => {
    // الرجوع من أوّل خطوة لاحقة لا يعود لإنشاء الحقل (الحقل أُنشئ فعلاً) — يُلغى المعالج
    // ويُترَك المستخدم على مساحة العمل عوضاً عن إعادة إنشاء حقل مكرّر.
    if (stepIdx <= 0) { onComplete(ctx.fieldId); return; }
    setStepIdx(i => i - 1);
  };

  const def = steps[stepIdx];
  const StepComponent = def.Component;
  // مؤشّر التقدّم: +1 لأنّ خطوة الإنشاء (0) قد اكتملت.
  return (
    <StepComponent
      ctx={ctx}
      onNext={goNext}
      onSkip={goNext}
      onBack={goBack}
      canGoBack={stepIdx > 0}
      stepIndex={stepIdx + 1}
      stepTotal={stepTotal}
    />
  );
}
