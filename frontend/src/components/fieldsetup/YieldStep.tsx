// ═══════════════════════════════════════════════════════════════
// SAHOOL — fieldsetup/YieldStep.tsx  (الخطوة 4 من معالج تهيئة الحقل)
// تقدير الإنتاجيّة (اختياريّة — تُتخطّى). تُشغّل تقديراً نموذجيّاً ثمّ تعرض النتيجة،
// والمستخدم ينهي المعالج للوصول إلى مساحة عمل الحقل.
// النقطة الخلفيّة الحقيقيّة:
//   POST /api/v1/fields/{field_id}/yield-estimate
//   body: { field_id, crop, days_in_growing?, avg_ndvi_growing? }  → يُرجِع تقديراً.
// النتيجة تُعرَض «كما عادت» (لا تلفيق): إن غابت حقول من الردّ تُعرَض «—».
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { TrendingUp, Loader2 } from 'lucide-react';
import { kongApi, apiErrorMessage } from '../../services/api';
import StepShell from './StepShell';
import type { FieldSetupStepProps } from './types';

function numOrUndef(v: string): number | undefined {
  if (v.trim() === '') return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

// يقرأ رقماً من ردّ غير معروف الشكل بأمان (دفاعيّ — لا انهيار على شكل ناقص).
function readNum(obj: Record<string, unknown> | null, ...keys: string[]): number | null {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'number' && Number.isFinite(v)) return v;
  }
  return null;
}

export default function YieldStep({
  ctx, onNext, onSkip, onBack, canGoBack, stepIndex, stepTotal,
}: FieldSetupStepProps) {
  const [crop, setCrop] = useState(ctx.crop && ctx.crop !== '—' ? ctx.crop : '');
  const [days, setDays] = useState('');
  const [ndvi, setNdvi] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  // الردّ الخام للتقدير (object غير معروف الشكل بدقّة — نقرأ منه دفاعيّاً).
  const [result, setResult] = useState<Record<string, unknown> | null>(null);

  const runEstimate = async () => {
    if (!crop.trim()) { setError('أدخِل المحصول لتقدير الإنتاجيّة'); return; }
    setSaving(true); setError('');
    try {
      const r = await kongApi.post(`/api/v1/fields/${ctx.fieldId}/yield-estimate`, {
        field_id: ctx.fieldId,
        crop: crop.trim(),
        days_in_growing: numOrUndef(days),
        avg_ndvi_growing: numOrUndef(ndvi),
      });
      // حارس شكل: نقبل كائناً فقط؛ غير ذلك ⇒ نعامله كغياب نتيجة (لا انهيار).
      setResult(r?.data && typeof r.data === 'object' ? (r.data as Record<string, unknown>) : null);
    } catch (e: any) {
      setError(apiErrorMessage(e, 'تعذّر تقدير الإنتاجيّة — تحقّق من القاعدة/الطقس/الصلاحيّة.'));
    } finally {
      setSaving(false);
    }
  };

  // قيم العرض المُستخرَجة دفاعيّاً من الردّ (أسماء بديلة شائعة).
  const yieldEst = readNum(result, 'yield_kg_ha', 'estimated_yield_kg_ha', 'yield');
  const yieldLow = readNum(result, 'yield_low_kg_ha', 'low');
  const yieldHigh = readNum(result, 'yield_high_kg_ha', 'high');
  const confidence = readNum(result, 'confidence');
  const fmt = (n: number | null) => (n == null ? '—' : Math.round(n).toLocaleString('ar'));

  return (
    <StepShell
      title="تقدير الإنتاجيّة"
      subtitle={`${ctx.fieldName} · اختياريّة`}
      icon={<TrendingUp className="w-5 h-5" />}
      stepIndex={stepIndex}
      stepTotal={stepTotal}
      optional
      canGoBack={canGoBack}
      onBack={onBack}
      onSkip={onSkip}
      // بعد ظهور نتيجة، زرّ «التالي» يُنهي المعالج؛ قبلها يُشغّل التقدير.
      onNext={result ? onNext : runEstimate}
      nextLabel={result ? 'إنهاء والذهاب لمساحة العمل' : 'تشغيل التقدير'}
      saving={saving}
      error={error}
    >
      <p className="text-xs text-slate-400 leading-relaxed">
        تقدير إنتاجيّة نموذجيّ مبكّر للحقل. النتائج <strong className="text-amber-400">تقديرات نموذجيّة</strong> لا قياسات
        ميدانيّة. هذه الخطوة <strong className="text-amber-400">اختياريّة</strong> — يمكنك تخطّيها والوصول مباشرةً لمساحة العمل.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-slate-400 mb-1">المحصول *</label>
          <input value={crop} onChange={e => setCrop(e.target.value)}
            placeholder="مثال: قمح صلب"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">أيّام النموّ (اختياري)</label>
          <input type="number" value={days} onChange={e => setDays(e.target.value)}
            placeholder="مثال: 90"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
        <div>
          <label className="block text-xs text-slate-400 mb-1">متوسّط NDVI (اختياري)</label>
          <input type="number" step="0.01" value={ndvi} onChange={e => setNdvi(e.target.value)}
            placeholder="0–1"
            className="w-full px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
        </div>
      </div>

      {saving && !result && (
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" /> جارٍ حساب التقدير…
        </div>
      )}

      {/* النتيجة (تُعرَض كما عادت، بنطاق وثقة حين توفّرا) */}
      {result && (
        <div className="rounded-xl p-3 space-y-2" style={{ background: '#0f172a', border: '1px solid #1e3a1e' }}>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg p-2" style={{ background: '#0f1117' }}>
              <div className="text-[10px] text-slate-400">الإنتاجيّة المُقدَّرة (كجم/هـ)</div>
              <div className="text-sm font-semibold text-emerald-300 mt-0.5">{fmt(yieldEst)}</div>
              {(yieldLow != null || yieldHigh != null) && (
                <div className="text-[10px] text-slate-500 mt-0.5">النطاق: {fmt(yieldLow)} – {fmt(yieldHigh)}</div>
              )}
            </div>
            <div className="rounded-lg p-2" style={{ background: '#0f1117' }}>
              <div className="text-[10px] text-slate-400">الثقة</div>
              <div className="text-sm font-semibold text-slate-100 mt-0.5">
                {confidence == null ? '—' : `${Math.round(confidence * 100)}٪`}
              </div>
            </div>
          </div>
          <p className="text-[11px] text-slate-500">تقدير نموذجيّ مبكّر — يُنقَّح لاحقاً ببيانات الموسم والأقمار.</p>
        </div>
      )}
    </StepShell>
  );
}
