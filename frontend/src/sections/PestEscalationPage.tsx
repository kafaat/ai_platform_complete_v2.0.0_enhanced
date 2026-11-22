// ═══════════════════════════════════════════════════════════════
// SAHOOL — PestEscalationPage (ربط حيّ بـ POST /api/v1/pest-escalation/run)
// يُبرِز تدفّق تصعيد الآفة الدائم (workflow) مع الموافقة البشريّة (HIL):
// تشغيل → يُعلَّق عند الموافقة → موافقة الخبير → يُستأنف فينفّذ. الاستئناف بنفس
// workflow_id. صدق: لا تنفيذ قبل موافقة معتمَدة (البوّابة من الخادم).
// W0-01: فحص السلامة الكيميائيّة (guardrails) يجري على الخادم عند التنفيذ، لا من
// المتصفّح. الواجهة تعرض حكمه فقط (step_results.execute.guardrails) ولا تقرّره.
// W3-07: التصعيد يبدأ من دبّوس استطلاع أعاده الخادم ومن سياق دليل صورته (لا قائمة آفات
// حرّة)، والموافقة محجوبة ما لم يُثبت الخادم سلسلة المبيد في context.chemical_lineage_audit،
// ونتيجة التنفيذ تُعرَض كما أعادها الخادم (مرجع تنفيذ أو executed=false مع السبب).
// المنطق النقيّ في lib/pestEscalationLineage.ts.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useState } from 'react';
import { Bug, PlayCircle, ShieldCheck, ShieldAlert, CheckCircle2, Clock, Link2, Ban } from 'lucide-react';
import { usePestEscalation, useIpmPlan } from '../hooks/useApi';
import { useScoutingPins, useScoutPhotoContext } from '../hooks/useScouting';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { ErrorState } from '../components/StateViews';
import { useSelectedField } from '../hooks/useSelectedField';
import type { PestEscalationInput } from '../services/api';
import {
  LINEAGE_REF_AR,
  LINEAGE_REF_KEYS,
  evaluateApprovalLineage,
  lineageRefsFromContext,
  pestWorkflowIdForPin,
  readPestExecutionOutcome,
  refsFromPin,
} from '../lib/pestEscalationLineage';

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

const PIN_SEVERITY_AR: Record<string, string> = { low: 'منخفضة', medium: 'متوسّطة', high: 'عالية' };

function httpStatus(err: unknown): number | undefined {
  return (err as { response?: { status?: number } } | null)?.response?.status;
}

/** رفض الخادم للسلسلة (422 CHEMICAL_LINEAGE_REQUIRED في وضع enforce) بكلماته. */
function escalationErrorDetail(err: unknown): string | undefined {
  const detail = (err as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  if (detail && typeof detail === 'object' && (detail as { code?: unknown }).code === 'CHEMICAL_LINEAGE_REQUIRED') {
    const v = (detail as { violations?: unknown }).violations;
    const list = Array.isArray(v) ? v.filter((x) => typeof x === 'string').join('، ') : '';
    return `رفض الخادم: يلزم ربط تشخيص ودليل للحقل والموسم قبل أيّ مسار مبيدات${list ? ` (${list})` : ''}.`;
  }
  return undefined;
}

export default function PestEscalationPage() {
  const [severity, setSeverity] = useState(0.7);
  const [fieldId, setFieldId] = useState('');
  const [pinId, setPinId] = useState('');
  const { options: fieldOptions, isLoading: fieldsLoading, isError: fieldsError, fieldId: activeFieldId } = useSelectedField();
  useEffect(() => {
    if (!fieldId && activeFieldId) setFieldId(activeFieldId);
  }, [activeFieldId, fieldId]);
  const pinsQ = useScoutingPins(fieldId || undefined);
  const pins = useMemo(() => pinsQ.data?.pins ?? [], [pinsQ.data]);
  const pin = pins.find((p) => p.pin_id === pinId) ?? null;
  const photoQ = useScoutPhotoContext(pin?.field_id, pin?.pin_id);
  const refs = pin ? refsFromPin(pin, photoQ.data ?? null) : null;
  const ipmQ = useIpmPlan(refs?.pest_type);

  const [lastPayload, setLastPayload] = useState<PestEscalationInput | null>(null);
  const mut = usePestEscalation();
  const role = useAuthStore(s => s.user?.role);
  const mutateAllowed = canMutate(role);

  const send = (payload: PestEscalationInput) => {
    setLastPayload(payload);
    mut.mutate(payload);
  };

  const start = () => {
    if (!pin || !refs) return;
    const wid = pestWorkflowIdForPin(pin.pin_id, Date.now().toString(36));
    send({
      workflow_id: wid,
      field_id: refs.field_id,
      season_id: refs.season_id,
      diagnosis_ref: refs.diagnosis_ref,
      evidence_ref: refs.evidence_ref,
      pest_type: refs.pest_type,
      severity,
    });
  };

  const res = mut.data;
  const ctx = (res?.context ?? {}) as Record<string, unknown>;
  const status = res?.workflow?.status ?? '';
  const st = STATUS_STYLE[status] ?? { ar: status || '—', color: 'rgb(var(--sahool-muted))', bg: '#1e293b' };
  const lineage = evaluateApprovalLineage(res ? ctx : null);
  const outcome = readPestExecutionOutcome(res?.step_results, res?.execution, ctx.action_type);
  const approveDisabled = mut.isPending || !mutateAllowed || !lineage.allowed;

  const approve = () => {
    // حارس ثانٍ: لا موافقة بلا سلسلة أثبتها الخادم، ولو استُدعيت الدالّة مباشرة.
    // الاستئناف بمعرّف التدفّق الذي أعاده الخادم، لا بنسخة الواجهة.
    const workflowId = res?.workflow?.workflow_id;
    if (!workflowId || !mutateAllowed || !lineage.allowed) return;
    send({ workflow_id: workflowId, approval_status: 'approved', ...lineageRefsFromContext(ctx) });
  };

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

  const photoStatus = httpStatus(photoQ.error);
  const photoErrorAr = photoQ.isError
    ? photoStatus === 404
      ? 'لا دليل صورة لهذا الدبّوس على الخادم (أو خدمة الوسائط غير مفعّلة).'
      : photoStatus === 403
        ? 'دورك أو منحتك على الحقل لا تسمح بقراءة سياق دليل الصورة.'
        : 'تعذّر جلب سياق دليل الصورة من الخادم.'
    : null;

  return (
    <div className="space-y-5 max-w-3xl mx-auto" dir="rtl">
      <div className="flex items-center gap-2">
        <Bug className="w-5 h-5 text-ops-warning" />
        <h2 className="text-xl font-bold text-sahool-text">تصعيد الآفة</h2>
      </div>
      <p className="text-sm text-sahool-muted">
        يبدأ التصعيد من مشاهدة استطلاع محفوظة على الخادم ودليل صورتها: يُرصَد ويُؤكَّد ويُوصى،
        ثمّ يُعلَّق بانتظار موافقة الخبير. لا موافقة ما لم يُثبت الخادم سلسلة التشخيص والدليل.
      </p>

      {/* Form */}
      <div className="rounded-xl border p-4 space-y-3" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-sahool-muted">الحقل</span>
            <select
              value={fieldId}
              onChange={(e) => { setFieldId(e.target.value); setPinId(''); }}
              disabled={fieldsLoading || fieldsError || fieldOptions.length === 0}
              className="px-3 py-2 rounded-lg text-sm disabled:opacity-60"
              style={{ background: 'rgb(var(--sahool-surface-2))', border: '1px solid rgb(var(--sahool-border))', color: 'rgb(var(--sahool-text))' }}
            >
              <option value="">اختر الحقل</option>
              {fieldOptions.map((f) => <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}</option>)}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-xs text-sahool-muted">مشاهدة الاستطلاع (دبّوس محفوظ)</span>
            <select
              aria-label="مشاهدة الاستطلاع"
              value={pinId}
              onChange={(e) => setPinId(e.target.value)}
              disabled={!fieldId || pinsQ.isLoading || pinsQ.isError || pins.length === 0}
              className="px-3 py-2 rounded-lg text-sm disabled:opacity-60"
              style={{ background: 'rgb(var(--sahool-surface-2))', border: '1px solid rgb(var(--sahool-border))', color: 'rgb(var(--sahool-text))' }}
            >
              <option value="">اختر مشاهدة</option>
              {pins.map((p) => (
                <option key={p.pin_id} value={p.pin_id}>
                  {(p.issue_code ?? p.issue_category)} · {PIN_SEVERITY_AR[p.severity] ?? p.severity} · {p.created_at.slice(0, 10)}
                </option>
              ))}
            </select>
            {fieldId && pinsQ.isError && <span className="text-[11px] text-ops-danger">تعذّر جلب مشاهدات الحقل من الخادم.</span>}
            {fieldId && !pinsQ.isLoading && !pinsQ.isError && pins.length === 0 && (
              <span className="text-[11px] text-ops-warning">
                لا مشاهدات محفوظة لهذا الحقل{pinsQ.data?.note_ar ? ` — ${pinsQ.data.note_ar}` : ''}. سجّل مشاهدة من الاستطلاع أوّلاً.
              </span>
            )}
          </label>
        </div>

        {pin && refs && (
          <div className="rounded-lg border p-3 space-y-1.5" style={{ background: 'rgb(var(--sahool-surface-2))', borderColor: 'rgb(var(--sahool-border))' }} data-testid="escalation-refs">
            <div className="flex items-center gap-2 text-xs text-sahool-text">
              <Link2 className="w-3.5 h-3.5" /> مراجع السلسلة من الخادم
            </div>
            <Row label="الدبّوس" value={pin.pin_id} />
            <Row label="الآفة/التشخيص" value={refs.pest_type ?? '—'} />
            {photoQ.isLoading && <p className="text-[11px] text-sahool-muted">جارٍ جلب سياق دليل الصورة…</p>}
            {photoErrorAr && <p className="text-[11px] text-ops-danger">{photoErrorAr}</p>}
            {LINEAGE_REF_KEYS.map((k) => (
              <Row key={k} label={LINEAGE_REF_AR[k]} value={refs[k] ?? `غائب — ${refs.missing[k] ?? 'لم يُعِده الخادم'}`} />
            ))}
            {ipmQ.data && (
              <Row
                label="خطّة IPM"
                value={ipmQ.data.supported
                  ? `${ipmQ.data.name_ar ?? refs.pest_type} · ${(ipmQ.data.ipm_ladder ?? []).map((s) => s.stage_ar).join(' ← ')}`
                  : (ipmQ.data.message_ar ?? 'لا خطّة IPM لهذا الكود')}
              />
            )}
          </div>
        )}

        <label className="flex flex-col gap-1">
          <span className="text-xs text-sahool-muted">
            تقدير شدّة الإصابة: <span className="text-sahool-text font-bold">{severity.toFixed(2)}</span>
            {pin && <span className="text-sahool-muted"> · تقدير الكشّاف المسجَّل: {PIN_SEVERITY_AR[pin.severity] ?? pin.severity}</span>}
          </span>
          <input type="range" min={0} max={1} step={0.05} value={severity}
            onChange={e => setSeverity(Number(e.target.value))} className="accent-orange-500" />
          <span className="text-[10px] text-sahool-muted">≥ 0.40 يُؤكِّد التصعيد · ≥ 0.70 مكافحة عاجلة</span>
        </label>
        <div className="flex justify-end">
          <button onClick={start} disabled={mut.isPending || !pin || photoQ.isLoading}
            className="flex items-center gap-2 px-5 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
            style={{ background: '#ea580c' }}>
            <PlayCircle className="w-4 h-4" />
            {mut.isPending ? 'جارٍ التشغيل…' : 'تشغيل التدفّق من المشاهدة'}
          </button>
        </div>
      </div>

      {mut.isError && (
        <ErrorState
          title="تعذّر تشغيل التدفّق"
          detail={escalationErrorDetail(mut.error)}
          onRetry={lastPayload ? () => mut.mutate(lastPayload) : undefined}
        />
      )}

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

          {/* Recommendation from accumulated context */}
          <div className="rounded-xl border p-4 space-y-2" style={{ background: 'rgb(var(--sahool-surface))', borderColor: 'rgb(var(--sahool-border))' }}>
            {ctx.alert_level != null && (
              <Row label="مستوى الإنذار" value={String(ctx.alert_level)} />
            )}
            {ctx.recommendation_ar != null && (
              <Row label="التوصية" value={String(ctx.recommendation_ar)} />
            )}
            {ctx.follow_up_note_ar != null && (
              <Row label="المتابعة" value={String(ctx.follow_up_note_ar)} />
            )}
            {res.workflow.error && <Row label="خطأ" value={res.workflow.error} />}
          </div>

          {/* Execution outcome — كما أعاده الخادم، بلا نجاح متفائل */}
          {outcome.state !== 'pending' && (
            <div
              data-testid="execution-outcome"
              className="rounded-xl border p-4 space-y-1"
              style={{
                background: outcome.state === 'executed' ? '#04140a' : '#1a0000',
                borderColor: outcome.state === 'executed' ? '#16a34a44' : '#dc262644',
              }}
            >
              {outcome.state === 'executed' ? (
                <>
                  <p className="text-sm font-semibold text-green-300">نُفِّذ بحسب الخادم</p>
                  <Row label="مرجع التنفيذ (من الخادم)" value={outcome.executionRef} />
                </>
              ) : (
                <>
                  <p className="text-sm font-semibold text-red-300 flex items-center gap-1.5">
                    <Ban className="w-4 h-4" />
                    {outcome.state === 'unconfirmed' ? 'تنفيذ غير مؤكَّد' : 'لم يُنفَّذ (executed=false)'}
                  </p>
                  {outcome.reasons.map((r) => <p key={r} className="text-xs text-red-200">{r}</p>)}
                </>
              )}
            </div>
          )}

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

          {/* HIL approval — محجوبة بلا سلسلة أثبتها الخادم */}
          {status === 'suspended' && (
            <div className="rounded-xl border p-4 space-y-3" style={{ background: '#1a1000', borderColor: '#f59e0b33' }}>
              <div className="flex items-center justify-between gap-3">
                <div className="text-sm text-amber-200">
                  {!mutateAllowed
                    ? 'دورك لا يملك صلاحيّة الاعتماد.'
                    : lineage.allowed
                      ? 'التدفّق مُعلَّق بانتظار موافقة الخبير. عند الموافقة يفحص الخادم السلامة الكيميائيّة، ولا يُنفَّذ إلّا إذا سمح الفحص.'
                      : 'الموافقة محجوبة: الخادم لم يُثبت سلسلة التشخيص والدليل لهذا التدفّق.'}
                </div>
                <button onClick={approve} disabled={approveDisabled}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60 shrink-0"
                  style={{ background: '#16a34a' }}>
                  <ShieldCheck className="w-4 h-4" />
                  {mut.isPending ? 'جارٍ…' : 'موافقة الخبير'}
                </button>
              </div>
              {!lineage.allowed && (
                <ul data-testid="lineage-block-reasons" className="text-xs text-amber-100 list-disc pr-5 space-y-0.5">
                  {lineage.reasons.map((r) => <li key={r}>{r}</li>)}
                </ul>
              )}
              {lineage.allowed && !lineage.validated && (
                <p className="text-[11px] text-slate-400">
                  المراجع حاضرة ومتوافقة الشكل في تدقيق الخادم؛ التحقّق من التشخيص لدى مالكه غير موصول بعد
                  (validated=false)، فيُعاد التدقيق عند التنفيذ.
                </p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 py-1.5 border-b last:border-0" style={{ borderColor: 'rgb(var(--sahool-border))' }}>
      <span className="text-sm text-sahool-muted shrink-0">{label}</span>
      <span className="text-sm text-sahool-text text-left break-all">{value}</span>
    </div>
  );
}
