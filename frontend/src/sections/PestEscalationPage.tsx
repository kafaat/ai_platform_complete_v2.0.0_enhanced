// ═══════════════════════════════════════════════════════════════
// SAHOOL — PestEscalationPage (ربط حيّ بـ POST /api/v1/pest-escalation/run)
// يُبرِز تدفّق تصعيد الآفة الدائم (workflow) مع الموافقة البشريّة (HIL):
// تشغيل → يُعلَّق عند الموافقة → موافقة الخبير → يُستأنف فينفّذ. الاستئناف بنفس
// workflow_id. صدق: لا تنفيذ قبل موافقة معتمَدة (البوّابة من الخادم).
// W0-01: فحص السلامة الكيميائيّة (guardrails) يجري على الخادم عند التنفيذ، لا من
// المتصفّح. الواجهة تعرض حكمه فقط (step_results.execute.guardrails) ولا تقرّره.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import { Bug, PlayCircle, ShieldCheck, ShieldAlert, CheckCircle2, Clock } from 'lucide-react';
import { usePestEscalation } from '../hooks/useApi';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { ErrorState } from '../components/StateViews';
import { useSelectedField } from '../hooks/useSelectedField';

const RISK_COLOR: Record<string, string> = {
  LOW: '#16a34a', MEDIUM: '#f59e0b', HIGH: '#f97316', CRITICAL: '#dc2626',
};

// حكم السلامة الكيميائيّة كما يعيده الخادم في step_results.execute.guardrails.
interface ServerGuardrailsVerdict {
  allowed?: unknown;
  status?: string;
  reason_ar?: string;
  overall_risk?: string;
}

const PESTS = ['صدأ القمح', 'المنّ', 'دودة الحشد', 'الذبابة البيضاء', 'التربس', 'العنكبوت الأحمر'];

const STEP_AR: Record<string, string> = {
  detect: 'الرصد', confirm: 'التأكيد', recommend: 'التوصية',
  await_approval: 'انتظار الموافقة', execute: 'التنفيذ', follow_up: 'المتابعة',
};

const STATUS_STYLE: Record<string, { ar: string; color: string; bg: string }> = {
  running:     { ar: 'قيد التشغيل', color: '#38bdf8', bg: '#00101a' },
  suspended:   { ar: 'مُعلَّق (بانتظار موافقة)', color: '#f59e0b', bg: '#1a1000' },
  completed:   { ar: 'مكتمل', color: '#16a34a', bg: '#04140a' },
  failed:      { ar: 'فشل', color: '#dc2626', bg: '#1a0000' },
  compensated: { ar: 'مُعوَّض (تراجع)', color: '#dc2626', bg: '#1a0000' },
};

export default function PestEscalationPage() {
  const [pestType, setPestType] = useState(PESTS[0]);
  const [severity, setSeverity] = useState(0.7);
  const [fieldId, setFieldId] = useState('');
  const { options: fieldOptions, isLoading: fieldsLoading, isError: fieldsError, fieldId: activeFieldId } = useSelectedField();
  useEffect(() => {
    if (!fieldId && activeFieldId) setFieldId(activeFieldId);
  }, [activeFieldId, fieldId]);
  const [workflowId, setWorkflowId] = useState('');
  const mut = usePestEscalation();
  const role = useAuthStore(s => s.user?.role);
  const mutateAllowed = canMutate(role);

  const start = () => {
    const wid = `pest-${Date.now()}`;
    setWorkflowId(wid);
    mut.mutate({ workflow_id: wid, pest_type: pestType, severity, field_id: fieldId || undefined });
  };
  const approve = () => {
    if (!workflowId || !mutateAllowed) return;
    mut.mutate({ workflow_id: workflowId, approval_status: 'approved' });
  };

  const res = mut.data;
  const ctx = (res?.context ?? {}) as Record<string, unknown>;
  const status = res?.workflow?.status ?? '';
  const st = STATUS_STYLE[status] ?? { ar: status || '—', color: '#94a3b8', bg: '#1e293b' };

  // حكم السلامة من الخادم (W0-01): يُقرأ فقط. التنفيذ مسموح حين allowed === true حرفيّاً؛
  // غير ذلك (رفض، 401، مهلة، أدلّة ناقصة) محجوب على الخادم مهما كانت موافقة الخبير.
  const execResult = (res?.step_results?.execute ?? {}) as Record<string, unknown>;
  const verdict = (execResult.guardrails ?? null) as ServerGuardrailsVerdict | null;
  const safetyAllowed = !!verdict && verdict.allowed === true;
  const safetyBlocked = execResult.blocked_by === 'guardrails' || (!!verdict && !safetyAllowed);
  const riskColor = safetyBlocked
    ? '#dc2626'
    : verdict?.overall_risk
      ? (RISK_COLOR[verdict.overall_risk] ?? '#94a3b8')
      : '#94a3b8';

  return (
    <div className="space-y-5 max-w-3xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Bug className="w-5 h-5 text-orange-400" />
        <h2 className="text-xl font-bold text-slate-100">تصعيد الآفة</h2>
      </div>
      <p className="text-sm text-slate-400">
        تدفّق قرار دائم مع موافقة بشريّة: يُرصَد ويُؤكَّد ويُوصى، ثمّ يُعلَّق بانتظار
        موافقة الخبير قبل التنفيذ (لا تنفيذ بلا موافقة). الموافقة تستأنف التدفّق.
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1e293b', borderColor: '#334155' }}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">نوع الآفة</span>
            <select value={pestType} onChange={e => setPestType(e.target.value)}
              className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}>
              {PESTS.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">الحقل</span>
            <select
              value={fieldId}
              onChange={(e) => setFieldId(e.target.value)}
              disabled={fieldsLoading || fieldsError || fieldOptions.length === 0}
              className="px-3 py-2 rounded-lg text-sm disabled:opacity-60"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
            >
              <option value="">اختر الحقل</option>
              {fieldOptions.map((f) => <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}</option>)}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">شدّة الإصابة: <span className="text-slate-200 font-bold">{severity.toFixed(2)}</span></span>
          <input type="range" min={0} max={1} step={0.05} value={severity}
            onChange={e => setSeverity(Number(e.target.value))} className="accent-orange-500" />
          <span className="text-[10px] text-slate-600">≥ 0.40 يُؤكِّد التصعيد · ≥ 0.70 مكافحة عاجلة</span>
        </label>
        <div className="flex justify-end">
          <button onClick={start} disabled={mut.isPending || !fieldId}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#ea580c' }}>
            <PlayCircle className="w-4 h-4" />
            {mut.isPending ? 'جارٍ التشغيل…' : 'تشغيل التدفّق'}
          </button>
        </div>
      </div>

      {mut.isError && <ErrorState title="تعذّر تشغيل التدفّق" onRetry={start} />}

      {/* Result */}
      {res && (
        <div className="space-y-4">
          {/* Status + steps */}
          <div className="rounded-xl border p-4" style={{ background: st.bg, borderColor: `${st.color}33` }}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm text-slate-300">حالة التدفّق</span>
              <span className="text-xs px-2 py-0.5 rounded-full font-semibold" style={{ background: `${st.color}22`, color: st.color }}>{st.ar}</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {(res.workflow?.completed_steps ?? []).map(s => (
                <span key={s} className="text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1"
                  style={{ background: '#16a34a18', color: '#4ade80' }}>
                  <CheckCircle2 className="w-3 h-3" />{STEP_AR[s] ?? s}
                </span>
              ))}
              {res.workflow.current_step && status === 'suspended' && (
                <span className="text-[11px] px-2 py-0.5 rounded-full flex items-center gap-1"
                  style={{ background: '#f59e0b22', color: '#f59e0b' }}>
                  <Clock className="w-3 h-3" />{STEP_AR[res.workflow.current_step] ?? res.workflow.current_step}
                </span>
              )}
            </div>
          </div>

          {/* Recommendation / outcome from accumulated context */}
          <div className="rounded-xl border p-4 space-y-2" style={{ background: '#1e293b', borderColor: '#334155' }}>
            {ctx.alert_level != null && (
              <Row label="مستوى الإنذار" value={String(ctx.alert_level)} />
            )}
            {ctx.recommendation_ar != null && (
              <Row label="التوصية" value={String(ctx.recommendation_ar)} />
            )}
            {ctx.executed != null && (
              <Row label="نُفِّذ؟" value={ctx.executed ? 'نعم' : 'لا'} />
            )}
            {ctx.note_ar != null && <Row label="ملاحظة" value={String(ctx.note_ar)} />}
            {ctx.follow_up_note_ar != null && (
              <Row label="المتابعة" value={String(ctx.follow_up_note_ar)} />
            )}
            {res.workflow.error && <Row label="خطأ" value={res.workflow.error} />}
          </div>

          {/* Guardrails — حكم الخادم بعد الموافقة (لا فحص من المتصفّح) */}
          {verdict && (
            <div className="rounded-xl border p-4" style={{ background: '#0f1a16', borderColor: `${riskColor}44` }}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-sm text-slate-200">
                  <ShieldAlert className="w-4 h-4" style={{ color: riskColor }} />
                  حواجز السلامة (Guardrails)
                </div>
                <span className="text-xs px-2 py-0.5 rounded-full font-semibold" style={{ background: `${riskColor}22`, color: riskColor }}>
                  {safetyAllowed ? '✓ سمح الفحص' : '✗ محجوب'}
                </span>
              </div>
              {verdict.reason_ar && <p className="text-sm text-slate-300">{verdict.reason_ar}</p>}
              {safetyBlocked && (
                <p className="text-xs text-red-300 mt-2">
                  لم يُنفَّذ الإجراء: فحص السلامة الكيميائيّة على الخادم لم يسمح به
                  {verdict.status ? ` (${verdict.status})` : ''}.
                </p>
              )}
            </div>
          )}

          {/* HIL approval */}
          {status === 'suspended' && (
            <div className="rounded-xl border p-4 flex items-center justify-between" style={{ background: '#1a1000', borderColor: '#f59e0b33' }}>
              <div className="text-sm text-amber-200">
                {!mutateAllowed
                  ? 'دورك لا يملك صلاحيّة الاعتماد.'
                  : 'التدفّق مُعلَّق بانتظار موافقة الخبير. عند الموافقة يفحص الخادم السلامة الكيميائيّة، ولا يُنفَّذ إلّا إذا سمح الفحص.'}
              </div>
              <button onClick={approve} disabled={mut.isPending || !mutateAllowed}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
                style={{ background: '#16a34a' }}>
                <ShieldCheck className="w-4 h-4" />
                {mut.isPending ? 'جارٍ…' : 'موافقة الخبير'}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b last:border-0" style={{ borderColor: '#334155' }}>
      <span className="text-sm text-slate-400 shrink-0">{label}</span>
      <span className="text-sm text-slate-200 text-left">{value}</span>
    </div>
  );
}
