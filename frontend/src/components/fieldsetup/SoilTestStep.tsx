// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/SoilTestStep.tsx  (الخطوة 3 من معالج تهيئة الحقل)
// فحوص التربة المخبريّة: pH / المادّة العضويّة / CEC. اختياريّة — تُتخطّى.
// النقطة الخلفيّة الحقيقيّة:
//   POST /api/v1/fields/{field_id}/soil-lab-tests  → 201
//   body: { lab_name?, sampled_on?, notes_ar?, result?: { ph?, organic_matter?, cec? } }
// مهمّ: pH/OM/CEC تُرسَل داخل result (لا في الجذر) — مطابقة العقد بدقّة.
// إن لم يُدخِل المستخدم أيّ قيمة قابلة للقياس نتخطّى النداء (لا إرسال جسم فارغ).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { FlaskConical } from 'lucide-react';
import { kongApi, apiErrorMessage } from '../../services/api';
import StepShell from './StepShell';
import type { FieldSetupStepProps } from './types';

// يحوّل نصّ مدخل إلى رقم أو undefined (فارغ/غير صالح ⇒ undefined، لا يُرسَل).
function numOrUndef(v: string): number | undefined {
  if (v.trim() === '') return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

export default function SoilTestStep({
  ctx, onNext, onSkip, onBack, canGoBack, stepIndex, stepTotal,
}: FieldSetupStepProps) {
  const [labName, setLabName] = useState('');
  const [sampledOn, setSampledOn] = useState('');
  const [ph, setPh] = useState('');
  const [om, setOm] = useState('');
  const [cec, setCec] = useState('');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleNext = async () => {
    const phN = numOrUndef(ph);
    const omN = numOrUndef(om);
    const cecN = numOrUndef(cec);
    // لا قيم مخبريّة ولا بيانات وصفيّة ⇒ لا داعي لنداء (نعامله كتخطٍّ صريح).
    const hasResult = phN != null || omN != null || cecN != null;
    if (!hasResult && !labName.trim() && !sampledOn && !notes.trim()) {
      onSkip();
      return;
    }
    if (phN != null && (phN < 0 || phN > 14)) {
      setError('قيمة الحموضة pH يجب أن تكون بين 0 و14'); return;
    }
    setSaving(true); setError('');
    try {
      // عقد الخلفيّة: pH/OM/CEC داخل result حصراً.
      await kongApi.post(`/api/v1/fields/${ctx.fieldId}/soil-lab-tests`, {
        lab_name: labName.trim() || undefined,
        sampled_on: sampledOn || undefined,
        notes_ar: notes.trim() || undefined,
        ...(hasResult
          ? { result: { ph: phN, organic_matter: omN, cec: cecN } }
          : {}),
      });
      onNext();
    } catch (e: any) {
      setError(apiErrorMessage(e, 'تعذّر حفظ فحص التربة — تحقّق من القاعدة/الصلاحيّة.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <StepShell
      title="فحوص التربة المخبريّة"
      subtitle={`${ctx.fieldName} · اختياريّة`}
      icon={<FlaskConical className="w-5 h-5" />}
      stepIndex={stepIndex}
      stepTotal={stepTotal}
      optional
      canGoBack={canGoBack}
      onBack={onBack}
      onSkip={onSkip}
      onNext={handleNext}
      nextLabel="حفظ ومتابعة"
      saving={saving}
      error={error}
    >
      <p className="text-xs text-slate-400 leading-relaxed">
        أدخِل نتائج فحص التربة إن توفّرت (مختبر معتمد). هذه الخطوة <strong className="text-amber-400">اختياريّة</strong> —
        يمكنك تخطّيها وإضافتها لاحقاً من تفاصيل الحقل.
      </p>

      {/* القيم المخبريّة: pH / المادّة العضويّة / CEC (داخل result خلفيّاً) */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">الحموضة pH</label>
          <input type="number" step="0.1" value={ph} onChange={e => setPh(e.target.value)}
            placeholder="0–14"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">المادّة العضويّة %</label>
          <input type="number" step="0.1" value={om} onChange={e => setOm(e.target.value)}
            placeholder="مثال: 1.8"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">السعة التبادليّة CEC (meq/100g)</label>
          <input type="number" step="0.1" value={cec} onChange={e => setCec(e.target.value)}
            placeholder="مثال: 12"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
      </div>

      {/* بيانات وصفيّة: المختبر + تاريخ العيّنة + ملاحظات */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">اسم المختبر (اختياري)</label>
          <input value={labName} onChange={e => setLabName(e.target.value)}
            placeholder="مثال: مختبر التربة المركزي"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">تاريخ أخذ العيّنة (اختياري)</label>
          <input type="date" value={sampledOn} onChange={e => setSampledOn(e.target.value)}
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
      </div>

      <div>
        <label className="block text-xs text-slate-400 mb-1">ملاحظات (اختياري)</label>
        <textarea value={notes} onChange={e => setNotes(e.target.value)}
          rows={2}
          placeholder="ملاحظات حول العيّنة أو طريقة الفحص"
          className="w-full px-3 py-2 rounded-lg text-sm resize-none"
          style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
      </div>
    </StepShell>
  );
}
