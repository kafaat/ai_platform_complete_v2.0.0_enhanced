// ═══════════════════════════════════════════════════════════════
// SAHOOL — PestEscalationPage (ربط حيّ بـ POST /api/v1/pest-escalation/run)
// يُبرِز تدفّق تصعيد الآفة الدائم (workflow) مع الموافقة البشريّة (HIL):
// تشغيل → يُعلَّق عند الموافقة → موافقة الخبير → يُستأنف فينفّذ. الاستئناف بنفس
// workflow_id. صدق: لا تنفيذ قبل موافقة معتمَدة (البوّابة من الخادم).
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from 'react';
import { Bug, PlayCircle, ShieldCheck, ShieldAlert, CheckCircle2, Clock } from 'lucide-react';
import { usePestEscalation, useGuardrailsValidate } from '../hooks/useApi';
import { ErrorState } from '../components/StateViews';

const RISK_COLOR: Record<string, string> = {
  LOW: '#16a34a', MEDIUM: '#f59e0b', HIGH: '#f97316', CRITICAL: '#dc2626',
};

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
  const [workflowId, setWorkflowId] = useState('');
  const mut = usePestEscalation();
  const guard = useGuardrailsValidate();

  const start = () => {
    const wid = `pest-${Date.now()}`;
    setWorkflowId(wid);
    guard.reset(); // إعادة التحقّق الأمنيّ لكلّ تشغيل جديد
    mut.mutate({ workflow_id: wid, pest_type: pestType, severity, field_id: fieldId || undefined });
  };
  const approve = () => {
    if (!workflowId) return;
    mut.mutate({ workflow_id: workflowId, approval_status: 'approved' });
  };

  const res = mut.data;
  const ctx = (res?.context ?? {}) as Record<string, unknown>;
  const status = res?.workflow.status ?? '';
  const st = STATUS_STYLE[status] ?? { ar: status || '—', color: '#94a3b8', bg: '#1e293b' };

  // تحقّق السلامة (Guardrails) قبل القرار الحرج: عند تعليق التدفّق بانتظار موافقة
  // الخبير وكان هناك إجراء فعليّ (رشّ/مكافحة)، نمرّره عبر حواجز السلامة الكيميائيّة/
  // البيئيّة/الاقتصاديّة. حاجز صارم (allowed=false) يمنع الموافقة.
  const actionType = String(ctx.action_type ?? '');
  const hasAction = !!actionType && actionType !== 'none';
  const needsSafety = status === 'suspended' && hasAction;
  // معرّف الـworkflow المُعلَّق كما ورد فعليّاً من الخادم — لا من حالة workflowId
  // المحلّيّة التي تتغيّر فور الضغط على «تشغيل» قبل وصول الاستجابة (سباق).
  const suspendedWfId = needsSafety ? (res?.workflow.workflow_id ?? '') : '';

  useEffect(() => {
    if (suspendedWfId && guard.isIdle) {
      guard.mutate({
        actionType: 'pesticide',
        actionData: {
          intervention: actionType,
          pest_type: ctx.pest_type,
          severity: ctx.severity,
          recommendation_ar: ctx.recommendation_ar,
        },
        farmContext: { field_id: fieldId || ctx.field_id },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [suspendedWfId]);

  const verdict = guard.data;
  // حظر صارم فقط للرفض القاطع (مادّة محظورة/تجاوز حدّ). حالة «يتطلّب موافقة بشريّة»
  // (HIGH/CRITICAL) ليست حظراً — هي موافقة الخبير نفسها، فحجبها يُجمّد التدفّق.
  const hardBlocked = !!verdict && verdict.allowed === false && !verdict.requires_human_approval;
  // لا نُتيح الموافقة قبل اكتمال الفحص (بوّابة فعليّة). لكن إن تعذّر الفحص نفسه لا
  // نُجمّد التدفّق — يبقى قرار الخبير (guardrails مُعطّل ≠ منع).
  const safetyBlocking = needsSafety && !verdict && !guard.isError;
  const riskColor = verdict ? (RISK_COLOR[verdict.overall_risk] ?? '#94a3b8') : '#94a3b8';

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
            <span className="text-xs text-slate-400">معرّف الحقل (اختياريّ)</span>
            <input value={fieldId} onChange={e => setFieldId(e.target.value)} placeholder="field_06"
              className="px-3 py-2 rounded-lg text-sm" style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }} />
          </label>
        </div>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-slate-400">شدّة الإصابة: <span className="text-slate-200 font-bold">{severity.toFixed(2)}</span></span>
          <input type="range" min={0} max={1} step={0.05} value={severity}
            onChange={e => setSeverity(Number(e.target.value))} className="accent-orange-500" />
          <span className="text-[10px] text-slate-600">≥ 0.40 يُؤكِّد التصعيد · ≥ 0.70 مكافحة عاجلة</span>
        </label>
        <div className="flex justify-end">
          <button onClick={start} disabled={mut.isPending}
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
              {res.workflow.completed_steps.map(s => (
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

          {/* Guardrails — تحقّق السلامة قبل القرار الحرج */}
          {needsSafety && (
            <div className="rounded-xl border p-4" style={{ background: '#0f1a16', borderColor: `${riskColor}44` }}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-sm text-slate-200">
                  <ShieldAlert className="w-4 h-4" style={{ color: riskColor }} />
                  حواجز السلامة (Guardrails)
                </div>
                {guard.isPending && <span className="text-xs text-slate-500">جارٍ الفحص…</span>}
                {verdict && (
                  <span className="text-xs px-2 py-0.5 rounded-full font-semibold" style={{ background: `${riskColor}22`, color: riskColor }}>
                    خطر: {verdict.overall_risk}
                  </span>
                )}
              </div>
              {guard.isError && <p className="text-xs text-slate-500">تعذّر فحص السلامة — الموافقة تبقى قرار الخبير.</p>}
              {verdict && (
                <>
                  <p className="text-sm text-slate-300">{verdict.arabic_explanation}</p>
                  <div className="flex flex-wrap gap-3 mt-2 text-[11px]">
                    <span style={{ color: hardBlocked ? '#f87171' : verdict.requires_human_approval ? '#f59e0b' : '#4ade80' }}>
                      {hardBlocked ? '✗ محجوب بحاجز صارم'
                        : verdict.requires_human_approval ? 'يتطلّب مراجعة الخبير'
                        : '✓ مسموح ضمن الحواجز'}
                    </span>
                  </div>
                  {/* صدق: الفحص أوّليّ — تدفّق الآفة لا يحمل مبيداً/جرعة محدّدين، فالتقييم
                      الكيميائيّ الدقيق يحتاجهما (وصفة الرشّ). يُعرَض كإرشاد لا كحُكم قاطع. */}
                  <p className="text-[10px] text-slate-500 mt-2">
                    فحص أوّليّ — التقييم الدقيق يتطلّب تحديد المبيد والجرعة (وصفة الرشّ).
                  </p>
                </>
              )}
            </div>
          )}

          {/* HIL approval */}
          {status === 'suspended' && (
            <div className="rounded-xl border p-4 flex items-center justify-between" style={{ background: '#1a1000', borderColor: '#f59e0b33' }}>
              <div className="text-sm text-amber-200">
                {hardBlocked
                  ? 'محجوب بحاجز السلامة — لا يمكن الموافقة على هذا الإجراء.'
                  : safetyBlocking
                    ? 'يجري فحص السلامة قبل إتاحة الموافقة…'
                    : 'التدفّق مُعلَّق بانتظار موافقة الخبير قبل التنفيذ.'}
              </div>
              <button onClick={approve} disabled={mut.isPending || hardBlocked || safetyBlocking}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white disabled:opacity-60"
                style={{ background: hardBlocked ? '#6b7280' : '#16a34a' }}>
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
      <span className="text-sm text-slate-400 flex-shrink-0">{label}</span>
      <span className="text-sm text-slate-200 text-left">{value}</span>
    </div>
  );
}
