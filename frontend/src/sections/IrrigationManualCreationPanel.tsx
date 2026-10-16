import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  approveManualCandidate, createManualExecutionFromPlan, createManualPlan,
  loadManualCandidates, manualPlanSource, submitIrrigationCandidate, validatedReview,
  type ApprovedIrrigationReview, type ManualWorkflowCandidate, type ManualIrrigationIntent,
} from '../services/api/irrigationManualCreation';

const buttonClass = 'rounded-lg border border-slate-700 px-3 py-2 text-sm disabled:opacity-50';
function errorText(error: unknown): string {
  const value = error as { response?: { data?: { detail?: unknown } }; message?: string };
  if (value.response?.data?.detail === 'execution_plan_already_exists') return 'توجد خطة أنشئت من مسار آخر؛ لا يمكن استئنافها هنا أو إنشاء نسخة مكررة. راجع سجل الخطة الأصلي.';
  return typeof value.response?.data?.detail === 'string' ? value.response.data.detail : value.message ?? 'تعذر إتمام الطلب.';
}

function WorkflowCard({ candidate, fieldId, seasonId, onCreated, refresh }: {
  candidate: ManualWorkflowCandidate; fieldId: string; seasonId: string; onCreated: () => void; refresh: () => void;
}) {
  const [localReview, setLocalReview] = useState<ApprovedIrrigationReview | null>(null);
  const [localPlan, setLocalPlan] = useState<string | null>(null);
  const [created, setCreated] = useState(false);
  const source = manualPlanSource(candidate, fieldId, seasonId);
  const proof = validatedReview(candidate, candidate.review) ? candidate.review : localReview;
  const saved = candidate.execution_plan;
  const savedPlan = proof && saved?.plan_state === 'planned' && saved.decision_id === candidate.decision_id
    && saved.review_id === proof.review_id && saved.decision_value_digest === proof.decision_value_digest
    && saved.candidate_lineage_id === proof.candidate_lineage_id ? saved.execution_plan_id : null;
  const planId = savedPlan ?? localPlan;
  const review = useMutation({ mutationFn: () => approveManualCandidate(candidate), onSuccess: result => { setLocalReview(result); refresh(); } });
  const ensurePlan = async () => {
    if (!proof) throw new Error('يلزم اعتماد موثق أولاً.');
    return createManualPlan(candidate, proof, fieldId, seasonId);
  };
  const plan = useMutation({ mutationFn: ensurePlan, onSuccess: id => { setLocalPlan(id); refresh(); } });
  const create = useMutation({ mutationFn: async () => {
    // Replaying plan creation repairs a prior DS-success / platform-source-write failure.
    const id = await ensurePlan();
    return createManualExecutionFromPlan(id);
  }, onSuccess: () => { setCreated(true); onCreated(); refresh(); } });
  const busy = review.isPending || plan.isPending || create.isPending;
  const error = review.error || plan.error || create.error;
  return <article className="space-y-2 rounded-xl border border-slate-700 p-3">
    <p>مرشح الري: {candidate.decision_id}</p>
    {source ? <>
      <p>الصافي: {source.net_depth_mm} مم · الإجمالي: {source.target_depth_mm} مم · الحجم: {source.target_volume_m3} م³</p>
      <p>النظام: {source.system_id} · المساحة: {source.irrigated_area_ha} هكتار · كفاءة التطبيق: {source.application_efficiency}</p>
      <p className="text-amber-200">بيانات النظام مُعلنة من المستخدم وليست قياسًا متحققًا: {source.specification.source_reference} · {source.specification.observed_at}</p>
      <p className="text-xs">دفتر الماء: {source.water_truth.canonical.ledger_date} · الماء المضاف مسجل · الفترة: {source.valid_from} — {source.valid_until}</p>
    </> : <p className="text-amber-200">مصدر خطة التنفيذ غير مكتمل أو منتهي الصلاحية. أعد تقديم توصية ببيانات صريحة وماء حالي قبل الاعتماد.</p>}
    {!proof && <button className={buttonClass} disabled={busy || !source || candidate.review_state !== 'pending_approval'} onClick={() => review.mutate()}>اعتماد هذه النسخة من التوصية</button>}
    {proof && <>
      <p>اعتمد الخادم هذه النسخة من القرار.</p>
      {!planId && <button className={buttonClass} disabled={busy || !source} onClick={() => plan.mutate()}>إنشاء خطة الري</button>}
      {planId && <><p>الخطة محفوظة: {planId}</p><button className={buttonClass} disabled={busy || !source || created} onClick={() => create.mutate()}>إنشاء سجل تنفيذ ري يدوي</button></>}
      {created && <p role="status">حُفظ سجل التنفيذ أو استعيد السجل السابق؛ لم يبدأ الري بهذا الإجراء.</p>}
    </>}
    {error && <p role="alert">{errorText(error)}</p>}
  </article>;
}

/** Separate explicit actions; persisted review/plan proof is restored from the server. */
export default function IrrigationManualCreationPanel({ fieldId, seasonId, onCreated }: {
  fieldId: string; seasonId: string; onCreated: () => void;
}) {
  const candidates = useQuery({ queryKey: ['manual-candidates', fieldId, seasonId],
    queryFn: () => loadManualCandidates(fieldId, seasonId), retry: false });
  const [form, setForm] = useState<Record<string, string>>({});
  const fields = [
    ['system_id', 'معرف نظام الري', 'text'], ['irrigated_area_ha', 'المساحة المروية بالهكتار', 'number'],
    ['application_efficiency', 'كفاءة التطبيق من صفر إلى واحد', 'number'], ['source_reference', 'مرجع بيانات النظام والكفاءة', 'text'],
    ['observed_at', 'وقت توثيق البيانات', 'datetime-local'], ['valid_from', 'بداية فترة التشغيل', 'datetime-local'], ['valid_until', 'نهاية فترة التشغيل', 'datetime-local'],
  ];
  const complete = fields.every(([key]) => !!form[key]?.trim());
  const submit = useMutation({ mutationFn: () => {
    const intent: ManualIrrigationIntent = { season_id: seasonId, system_id: form.system_id, irrigated_area_ha: Number(form.irrigated_area_ha),
      application_efficiency: Number(form.application_efficiency), source_reference: form.source_reference,
      observed_at: new Date(form.observed_at).toISOString(), valid_from: new Date(form.valid_from).toISOString(), valid_until: new Date(form.valid_until).toISOString() };
    return submitIrrigationCandidate(fieldId, intent);
  }, onSuccess: () => candidates.refetch() });
  return <section className="space-y-3 rounded-2xl border border-slate-800 bg-slate-950 p-4 text-slate-200" aria-label="إنشاء ري يدوي">
    <h3 className="font-semibold">من التوصية إلى سجل الري اليدوي</h3>
    <p className="text-xs text-slate-400">أدخل بيانات النظام ومصدرها صراحةً. تُحفظ كإقرار مستخدم للمراجعة؛ يقرأ الخادم الماء والطقس الحاليين. الاعتماد والخطة والسجل خطوات منفصلة، ولا يبدأ الري تلقائيًا.</p>
    <form className="grid gap-2 sm:grid-cols-2" onSubmit={event => { event.preventDefault(); if (complete) submit.mutate(); }}>
      {fields.map(([name, label, type]) => <label key={name} className="text-xs">{label}<input required name={name} type={type} step="any" value={form[name] ?? ''} onChange={event => setForm(value => ({ ...value, [name]: event.target.value }))} className="mt-1 w-full rounded border border-slate-700 bg-slate-900 p-2" /></label>)}
      <button type="submit" className={buttonClass} disabled={!complete || submit.isPending}>تقديم توصية الري للمراجعة</button>
    </form>
    <button className={buttonClass} disabled={candidates.isFetching} onClick={() => candidates.refetch()}>تحديث القرارات</button>
    {submit.data && <p role="status">{submit.data.status === 'recommendation_ready' ? `حالة التقديم: ${submit.data.approval_state ?? 'غير مؤكدة'}` : 'لم تتوفر توصية قابلة للتقديم؛ راجع بيانات الماء والطقس.'}</p>}
    {submit.data?.limitations?.map(reason => <p key={reason} className="text-xs text-amber-200">{reason}</p>)}
    {submit.error && <p role="alert">{errorText(submit.error)}</p>}
    {candidates.isLoading && <p>جارٍ قراءة القرارات…</p>}
    {candidates.isError && <p role="alert">تعذر قراءة حالة القرارات أو لا تتوفر صلاحية المراجعة.</p>}
    {candidates.data?.map(candidate => <WorkflowCard key={`${candidate.decision_id}:${candidate.decision_value_digest}`} candidate={candidate} fieldId={fieldId} seasonId={seasonId} onCreated={onCreated} refresh={() => { void candidates.refetch(); }} />)}
    {candidates.data?.length === 0 && <p>لا توجد توصية ري لهذا الحقل والموسم.</p>}
  </section>;
}
