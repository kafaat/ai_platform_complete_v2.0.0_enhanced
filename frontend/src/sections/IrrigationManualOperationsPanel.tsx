import { useMemo, useState, type ReactNode } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, CircleStop, Droplets, Play, ShieldCheck, WalletCards, XCircle } from 'lucide-react';
import { EmptyState, ErrorState, LoadingState } from '../components/StateViews';
import {
  confirmManualExecution,
  listManualExecutions,
  reconcileManualExecution,
  transitionManualExecution,
  verifyManualExecution,
  type ManualExecutionRecord,
  type ManualExecutionState,
} from '../services/api/irrigationManualOperations';
import { STORAGE_KEYS } from '../lib/authStorage';

const STATE_AR: Record<ManualExecutionState, string> = {
  recommended: 'موصى به', approved: 'معتمد', started: 'قيد الري', stopped: 'متوقف',
  confirmed: 'مؤكد', verified: 'متحقق منه', reconciled: 'مرحل للدفتر', cancelled: 'ملغى',
};

function currentUserId(): string {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEYS.user);
    if (!raw) return 'unknown-reviewer';
    const parsed = JSON.parse(raw) as { id?: string; user_id?: string };
    return parsed.user_id ?? parsed.id ?? 'unknown-reviewer';
  } catch {
    return 'unknown-reviewer';
  }
}

function toLocalInput(value?: string | null): string {
  const date = value ? new Date(value) : new Date();
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
}

function ActionButton({ children, onClick, disabled = false }: { children: ReactNode; onClick: () => void; disabled?: boolean }) {
  return <button type="button" disabled={disabled} onClick={onClick} className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-slate-100 hover:border-emerald-500 disabled:cursor-not-allowed disabled:opacity-50">{children}</button>;
}

export default function IrrigationManualOperationsPanel({ fieldId, seasonId }: { fieldId: string; seasonId?: string | null }) {
  const qc = useQueryClient();
  const key = ['field-workspace', fieldId, seasonId, 'manual-irrigation-executions'];
  const executionsQ = useQuery({ queryKey: key, queryFn: () => listManualExecutions(fieldId, seasonId), enabled: Boolean(fieldId), staleTime: 15_000 });
  const [selected, setSelected] = useState<ManualExecutionRecord | null>(null);
  const [mode, setMode] = useState<'confirm' | 'verify' | null>(null);
  const [form, setForm] = useState<Record<string, string>>({});

  const refresh = async () => { await qc.invalidateQueries({ queryKey: key }); setSelected(null); setMode(null); };
  const mutation = useMutation({
    mutationFn: async ({ execution, action }: { execution: ManualExecutionRecord; action: string }) => {
      if (action === 'approve') return transitionManualExecution(execution.execution_id, 'approved');
      if (action === 'start') return transitionManualExecution(execution.execution_id, 'started');
      if (action === 'stop') return transitionManualExecution(execution.execution_id, 'stopped');
      if (action === 'cancel') return transitionManualExecution(execution.execution_id, 'cancelled');
      if (action === 'reconcile') return reconcileManualExecution(execution.execution_id);
      if (action === 'confirm') {
        return confirmManualExecution(execution.execution_id, {
          started_at: new Date(form.started_at).toISOString(), stopped_at: new Date(form.stopped_at).toISOString(),
          completion_ratio: Number(form.completion_ratio || 1),
          meter_start_m3: form.meter_start_m3 ? Number(form.meter_start_m3) : undefined,
          meter_end_m3: form.meter_end_m3 ? Number(form.meter_end_m3) : undefined,
          measured_flow_m3_h: form.measured_flow_m3_h ? Number(form.measured_flow_m3_h) : undefined,
          manual_volume_m3: form.manual_volume_m3 ? Number(form.manual_volume_m3) : undefined,
          estimated_flow_m3_h: form.estimated_flow_m3_h ? Number(form.estimated_flow_m3_h) : undefined,
          interruptions_minutes: Number(form.interruptions_minutes || 0),
          pressure_bar: form.pressure_bar ? Number(form.pressure_bar) : undefined,
          evidence_digests: form.evidence_digests ? form.evidence_digests.split(',').map(v => v.trim()).filter(Boolean) : [],
          notes: form.notes || undefined,
        });
      }
      if (action === 'verify') {
        const asAppliedDigest = String(execution.as_applied_digest ?? '');
        return verifyManualExecution(execution.execution_id, {
          as_applied_digest: asAppliedDigest,
          reviewer_id: currentUserId(),
          reviewed_at: new Date().toISOString(),
          evidence_digests: form.evidence_digests ? form.evidence_digests.split(',').map(v => v.trim()).filter(Boolean) : [],
          volume_verified: form.volume_verified === 'true',
          timing_verified: form.timing_verified === 'true',
          field_verified: form.field_verified === 'true',
          notes: form.notes || undefined,
        });
      }
      throw new Error('unsupported action');
    },
    onSuccess: refresh,
  });

  const active = useMemo(() => (executionsQ.data ?? []).filter(item => !['cancelled', 'reconciled'].includes(item.state)), [executionsQ.data]);

  if (executionsQ.isLoading) return <LoadingState message="جارٍ تحميل دورة التنفيذ اليدوي…" />;
  if (executionsQ.isError) return <ErrorState title="تعذر تحميل عمليات الري اليدوية" detail="لا يتم إنشاء سجل بديل داخل الواجهة." onRetry={() => executionsQ.refetch()} />;

  return (
    <section className="space-y-4" aria-label="التشغيل اليدوي للري" dir="rtl">
      <header className="rounded-2xl border border-slate-800 bg-slate-950/70 p-5">
        <div className="flex items-center gap-2"><Droplets className="h-5 w-5 text-emerald-300"/><h2 className="font-bold text-slate-100">دورة التشغيل اليدوي</h2></div>
        <p className="mt-1 text-sm text-slate-400">موصى به ≠ معتمد ≠ بدأ ≠ اكتمل ≠ تحقق ≠ رُحّل إلى دفتر المياه.</p>
      </header>
      {(executionsQ.data ?? []).length === 0 ? <EmptyState title="لا توجد عملية ري يدوية" hint="تظهر هنا العمليات المنشأة من توصية ري قانونية؛ لا تولّد الواجهة توصيات أو قيماً مصطنعة." /> : (
        <div className="space-y-3">
          {(executionsQ.data ?? []).map((item) => (
            <article key={item.execution_id} className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div><p className="font-semibold text-slate-100">{item.system_id}</p><p className="text-xs text-slate-500">{item.execution_id}</p></div>
                <span className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-300">{STATE_AR[item.state]}</span>
              </div>
              <div className="mt-3 grid gap-2 text-sm text-slate-300 sm:grid-cols-4">
                <span>العمق: {item.target_depth_mm} مم</span><span>الحجم: {item.target_volume_m3} م³</span><span>الوضع: {item.execution_mode}</span><span>Ledger: {item.ledger_eligible ? 'مؤهل' : 'غير مؤهل'}</span>
              </div>
              {item.as_applied && <div className="mt-3 rounded-xl border border-slate-800 bg-slate-900/50 p-3 text-xs text-slate-300">المطبق: {item.as_applied.actual_volume_m3 ?? '—'} م³ · {item.as_applied.actual_depth_mm ?? '—'} مم · {item.as_applied.quality ?? '—'}</div>}
              <div className="mt-4 flex flex-wrap gap-2">
                {item.state === 'recommended' && <><ActionButton onClick={() => mutation.mutate({ execution: item, action: 'approve' })}><CheckCircle2 className="h-4 w-4"/>اعتماد</ActionButton><ActionButton onClick={() => mutation.mutate({ execution: item, action: 'cancel' })}><XCircle className="h-4 w-4"/>إلغاء</ActionButton></>}
                {item.state === 'approved' && <ActionButton onClick={() => mutation.mutate({ execution: item, action: 'start' })}><Play className="h-4 w-4"/>بدء الري</ActionButton>}
                {item.state === 'started' && <ActionButton onClick={() => mutation.mutate({ execution: item, action: 'stop' })}><CircleStop className="h-4 w-4"/>إيقاف الري</ActionButton>}
                {item.state === 'stopped' && <ActionButton onClick={() => { setSelected(item); setMode('confirm'); setForm({ started_at: toLocalInput(item.started_at), stopped_at: toLocalInput(item.stopped_at), completion_ratio: '1', interruptions_minutes: '0' }); }}>تأكيد التنفيذ</ActionButton>}
                {item.state === 'confirmed' && item.execution_mode === 'manual_measured' && <ActionButton onClick={() => { setSelected(item); setMode('verify'); setForm({ volume_verified: 'true', timing_verified: 'true', field_verified: 'true' }); }}><ShieldCheck className="h-4 w-4"/>تحقق مستقل</ActionButton>}
                {item.state === 'verified' && <ActionButton onClick={() => mutation.mutate({ execution: item, action: 'reconcile' })}><WalletCards className="h-4 w-4"/>ترحيل للدفتر</ActionButton>}
              </div>
            </article>
          ))}
          {active.length === 0 && <p className="text-xs text-slate-500">لا توجد عمليات نشطة حالياً.</p>}
        </div>
      )}
      {selected && mode && <div className="rounded-2xl border border-emerald-800/50 bg-slate-950 p-4">
        <h3 className="font-semibold text-slate-100">{mode === 'confirm' ? 'تأكيد التنفيذ الميداني' : 'التحقق المستقل'}</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {(mode === 'confirm' ? ['started_at','stopped_at','completion_ratio','meter_start_m3','meter_end_m3','measured_flow_m3_h','manual_volume_m3','estimated_flow_m3_h','interruptions_minutes','pressure_bar','evidence_digests','notes'] : ['volume_verified','timing_verified','field_verified','evidence_digests','notes']).map(name => <label key={name} className="text-xs text-slate-400">{name}<input type={name.includes('_at') ? 'datetime-local' : name.endsWith('_verified') ? 'checkbox' : name === 'notes' || name === 'evidence_digests' ? 'text' : 'number'} step="any" value={name.endsWith('_verified') ? undefined : (form[name] ?? '')} checked={name.endsWith('_verified') ? form[name] === 'true' : undefined} onChange={e => setForm(v => ({ ...v, [name]: name.endsWith('_verified') ? String(e.target.checked) : e.target.value }))} className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100"/></label>)}
        </div>
        {mutation.isError && <p className="mt-3 text-sm text-red-300">فشل الطلب؛ لم تتغير حالة التنفيذ.</p>}
        <div className="mt-4 flex gap-2"><ActionButton disabled={mutation.isPending} onClick={() => mutation.mutate({ execution: selected, action: mode })}>حفظ</ActionButton><ActionButton onClick={() => { setSelected(null); setMode(null); }}>إغلاق</ActionButton></div>
      </div>}
    </section>
  );
}
