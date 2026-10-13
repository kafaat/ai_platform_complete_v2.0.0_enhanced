import { useState } from 'react';
import type { ManualExecutionRecord } from '../services/api/irrigationManualOperations';
import { compareIrrigationExecutions, type IrrigationScenarioComparison } from '../services/api/irrigationScenarioComparison';

function measurement(value: number | null): string {
  return value !== null && Number.isFinite(value)
    ? value.toLocaleString('ar-YE', { maximumFractionDigits: 4 })
    : 'غير مقاس';
}

interface Props {
  fieldId: string;
  seasonId?: string | null;
  executions: ManualExecutionRecord[];
}

function executionLabel(item: ManualExecutionRecord): string {
  const raw = item.stopped_at ?? item.created_at;
  const date = raw ? new Date(raw) : null;
  const label = date && Number.isFinite(date.getTime())
    ? date.toLocaleString('ar-YE', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' }) + ' UTC'
    : 'تاريخ غير مسجل';
  return `${item.system_id} · ${label} · ${item.execution_id}`;
}

export default function IrrigationScenarioComparisonPanel(props: Props) {
  return <ScopedComparison key={`${props.fieldId}:${props.seasonId ?? ''}`} {...props} />;
}

function ScopedComparison({ fieldId, seasonId, executions }: Props) {
  const [baselineId, setBaselineId] = useState('');
  const [candidateId, setCandidateId] = useState('');
  const [data, setData] = useState<IrrigationScenarioComparison>();
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const eligible = executions.filter(item => item.field_id === fieldId
    && (!seasonId || item.season_id === seasonId)
    && item.state === 'reconciled' && item.execution_mode === 'manual_measured'
    && item.ledger_eligible && ['measured_meter', 'measured_flow'].includes(item.as_applied?.quality ?? ''));
  const reset = () => { setData(undefined); setFailed(false); };
  const calculate = async () => {
    setPending(true); reset();
    try { setData(await compareIrrigationExecutions(fieldId, baselineId, candidateId)); }
    catch { setFailed(true); }
    finally { setPending(false); }
  };
  const ready = baselineId !== candidateId && eligible.some(item => item.execution_id === baselineId)
    && eligible.some(item => item.execution_id === candidateId);
  // A result belongs only to its submitted pair, including after the source list changes.
  const result = ready && data?.baseline_execution_id === baselineId
    && data?.candidate_execution_id === candidateId ? data : undefined;

  return <section aria-label="مقارنة تنفيذ الري" dir="rtl" className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5 space-y-3">
    <h3 className="font-bold text-slate-100">مقارنة تنفيذ الري مع خط الأساس</h3>
    <p className="text-sm text-slate-400">اختر تنفيذين مقاسين ومتحققاً منهما ومرحلين للدفتر. يفحص الخادم توافق الحقل والموسم والنظام والمساحة.</p>
    <p className="text-xs text-amber-200">الفرق وصفي؛ لا يثبت وفر المياه أو أثر التوصية. يلزم ضبط الطقس والتربة والمحصول قبل نسبة التحسن إليها.</p>
    {eligible.length < 2 ? <p role="status" className="text-sm text-slate-400">يلزم تنفيذان مؤهلان على الأقل؛ القياسات الناقصة لا تُعامل كصفر.</p> : <>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="text-sm text-slate-300">تنفيذ خط الأساس
          <select className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 p-2" value={baselineId} disabled={pending} onChange={event => {
            setBaselineId(event.target.value); if (candidateId === event.target.value) setCandidateId(''); reset();
          }}>
            <option value="">اختر خط الأساس</option>
            {eligible.map(item => <option key={item.execution_id} value={item.execution_id}>{executionLabel(item)}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-300">التنفيذ المقارن
          <select className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 p-2" value={candidateId} disabled={pending} onChange={event => { setCandidateId(event.target.value); reset(); }}>
            <option value="">اختر التنفيذ المقارن</option>
            {eligible.filter(item => item.execution_id !== baselineId).map(item => <option key={item.execution_id} value={item.execution_id}>{executionLabel(item)}</option>)}
          </select>
        </label>
      </div>
      <button type="button" disabled={!ready || pending} onClick={calculate} className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-100 disabled:opacity-50">
        {pending ? 'جارٍ حساب المقارنة…' : 'حساب المقارنة'}
      </button>
    </>}
    {failed && <p role="alert" className="text-sm text-red-300">تعذر حساب المقارنة. تحقق من صلاحيات القراءة والسجلات ثم أعد المحاولة؛ لم يُنشأ أمر ري.</p>}
    {result && <div role="status" aria-live="polite" className="space-y-3 text-sm text-slate-300">
      <p>{result.status === 'measured_comparison' ? 'مقارنة القياسات المسجلة' : 'الأدلة غير كافية للمقارنة'}</p>
      {result.status === 'measured_comparison' && <div className="overflow-x-auto"><table className="w-full text-right">
        <thead><tr><th scope="col">المقياس</th><th scope="col">خط الأساس</th><th scope="col">التنفيذ المقارن</th><th scope="col">الأساس ناقص المقارن</th></tr></thead>
        <tbody>
          <tr><th scope="row">المياه (م³)</th><td>{measurement(result.water.baseline_volume_m3)}</td><td>{measurement(result.water.candidate_volume_m3)}</td><td>{measurement(result.water.baseline_minus_candidate_m3)}</td></tr>
          <tr><th scope="row">عمق الري (مم)</th><td>{measurement(result.water.baseline_depth_mm)}</td><td>{measurement(result.water.candidate_depth_mm)}</td><td>{measurement(result.water.baseline_minus_candidate_mm)}</td></tr>
          <tr><th scope="row">مدة التشغيل (ساعة)</th><td>{measurement(result.runtime.baseline_hours)}</td><td>{measurement(result.runtime.candidate_hours)}</td><td>{measurement(result.runtime.baseline_minus_candidate_hours)}</td></tr>
        </tbody>
      </table></div>}
      <p>الطاقة: غير مقاسة · القيمة الاقتصادية: غير محسوبة · الأثر السببي: غير مثبت.</p>
      {result.warnings_ar.map((warning, index) => <p key={index} className="text-xs text-amber-200">{warning}</p>)}
    </div>}
  </section>;
}
