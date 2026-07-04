import { useEffect, useMemo, useState } from 'react';
import { Target, Search, Brain, Play, CheckCircle2, Lock, ListChecks } from 'lucide-react';
import {
  FIELD_OBJECTIVES,
  buildObjectivePlan,
  type EvidenceAvailability,
  type EvidenceSource,
  type FieldObjectiveId,
  type ObjectiveStepKind,
} from '../../lib/fieldObjectiveEngine';
import {
  advanceLifecycle,
  initLifecycle,
  outcomeLabel,
  recommendationQuality,
  stageLabel,
  type LifecycleState,
  type Outcome,
} from '../../lib/fieldActionLifecycle';
import { useEvaluateDispatch } from '../../hooks/useApi';
import { dispatchStateColor, dispatchStateLabel } from '../../lib/decisionRuntime';
import { T } from '../ds';

const SOURCE_LABEL: Record<EvidenceSource, string> = {
  imagery: 'صور',
  weather: 'طقس',
  alerts: 'تنبيهات',
  tasks: 'مهامّ',
  records: 'سجلّات',
  zones: 'مناطق',
  moisture: 'رطوبة',
  season: 'موسم',
};

const STEP_ICON: Record<ObjectiveStepKind, typeof Search> = {
  inspect: Search,
  reason: Brain,
  act: Play,
  review: CheckCircle2,
};

const STEP_TONE: Record<ObjectiveStepKind, string> = {
  inspect: '#38bdf8',
  reason: '#a78bfa',
  act: '#86efac',
  review: '#fbbf24',
};

export interface FieldObjectivePanelProps {
  /** مفتاح السياق الحيّ (fieldId/seasonId). تغييره يعيد دورة الحياة حتى لا تنتقل توصية حقل إلى آخر. */
  contextKey?: string | null;
  /** توفّر الأدلّة الحقيقيّ محسوباً من استعلامات FieldView الحيّة. */
  availability: EvidenceAvailability;
  /** يُنشئ مهمّة قابلة للمتابعة من التوصية (backend حقيقيّ). يُستدعى فقط بعد اكتمال الدليل. */
  onCreateTask?: (objectiveId: FieldObjectiveId, label: string) => boolean | Promise<boolean>;
}

/** لوحة الأهداف: نيّة المستخدم ⇒ خطّة (فحص→تفسير→إجراء→مراجعة) مربوطة بأدلّة حقيقيّة،
 *  تمنع الإجراء حتّى اكتمال الدليل، وتحوّل التوصية إلى مهمّة قابلة للمتابعة بدورة حياة صريحة. */
export default function FieldObjectivePanel({ contextKey, availability, onCreateTask }: FieldObjectivePanelProps) {
  const [selectedId, setSelectedId] = useState<FieldObjectiveId>('diagnose_field_stress');
  const [lifecycle, setLifecycle] = useState<LifecycleState>(initLifecycle());
  const [blockedMessage, setBlockedMessage] = useState<string | null>(null);
  const [creatingTask, setCreatingTask] = useState(false);
  // حكم الحوكمة الخلفيّة (dry-run عند الاعتماد) — إثراء معلوماتيّ لا بوّابة محليّة:
  // الميزة قد تكون مُطفأة (404) فتُعرَض ملاحظة صادقة ولا تُعطَّل دورة الحياة.
  const dispatchEval = useEvaluateDispatch();

  const plan = useMemo(() => buildObjectivePlan(selectedId, availability), [selectedId, availability]);

  const pick = (id: FieldObjectiveId) => {
    setSelectedId(id);
    setLifecycle(initLifecycle()); // هدف جديد ⇒ دورة حياة جديدة (لا خلط أدلّة)
    setBlockedMessage(null);
    dispatchEval.reset();
  };

  useEffect(() => {
    // تغيير الحقل/الموسم يعني سياق دليل جديد؛ لا ننقل دورة حياة توصية من حقل إلى آخر.
    setLifecycle(initLifecycle());
    setBlockedMessage(null);
    setCreatingTask(false);
    dispatchEval.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contextKey]);

  useEffect(() => {
    // إذا تغيّرت البيانات الحيّة وأصبح الدليل ناقصاً قبل الوصول إلى مراجعة نهائية،
    // نرجع لمسودة بدل إبقاء توصية معتمدة على أدلة لم تعد متاحة.
    if (!plan?.canAct && ['evidence', 'approved', 'task_created', 'executing', 'follow_up'].includes(lifecycle.stage)) {
      setLifecycle(initLifecycle());
    }
  }, [plan?.canAct, lifecycle.stage]);

  const attachAndApprove = () => {
    if (!plan?.canAct) return;
    setBlockedMessage(null);
    // مسوّدة ⇒ دليل ⇒ مُعتمَدة (انتقالات صريحة، بوّابة الدليل مطبَّقة)
    const evidence = advanceLifecycle(lifecycle, 'attach_evidence', { canAct: plan.canAct });
    if (!evidence.changed) { setBlockedMessage(evidence.blockedReason ?? 'تعذّر إرفاق الدليل.'); return; }
    const approved = advanceLifecycle(evidence.state, 'approve');
    if (!approved.changed) { setBlockedMessage(approved.blockedReason ?? 'تعذّر اعتماد التوصية.'); return; }
    setLifecycle(approved.state);
    // جسر الحوكمة: معاينة القرار في الموزِّع الخلفيّ (dry-run، لا تنفيذ) — الدليل
    // مكتمل هنا بالتعريف (canAct)، فيُمرَّر has_governing_data=true بصدق.
    const d = plan.objective.dispatch;
    if (d) {
      dispatchEval.mutate({
        recommendation_id: `objective:${plan.objective.id}`,
        action_type: d.actionType,
        risk_level: d.riskLevel,
        field_id: contextKey ?? null,
        has_governing_data: true,
      });
    }
  };

  const createTask = async () => {
    if (!plan?.canAct || creatingTask) return;
    setBlockedMessage(null);
    // لا نسمح بتقدّم دورة الحياة بمجرد عدم وجود callback؛
    // الهدف المنتج لمهمة يحتاج قبولاً صريحاً من طبقة تنفيذ حية.
    if (!onCreateTask) { setBlockedMessage('لا يوجد مسار تنفيذ حيّ لإنشاء المهمة.'); return; }
    const r = advanceLifecycle(lifecycle, 'create_task', { objective: plan.objective });
    if (!r.changed) { setBlockedMessage(r.blockedReason ?? 'تعذّر إنشاء المهمة.'); return; }
    setCreatingTask(true);
    try {
      const accepted = await onCreateTask(plan.objective.id, plan.objective.label);
      // يجب أن ترجع الطبقة المضيفة true صراحة بعد إنشاء/فتح مسار تنفيذ حقيقي.
      if (accepted !== true) { setBlockedMessage('لا يوجد مسار تنفيذ فعلي لهذا الهدف داخل هذه الشاشة.'); return; }
      setLifecycle(r.state);
    } catch {
      // رفض/فشل backend أو المسار المضيف لا يغيّر الحالة؛ لا نكذب بأن مهمة أُنشئت.
      setBlockedMessage('فشل إنشاء المهمة؛ لم تتغير دورة الحياة.');
      return;
    } finally {
      setCreatingTask(false);
    }
  };

  const scheduleFollowUp = () => {
    if (!plan?.canAct) return;
    setBlockedMessage(null);
    const started = advanceLifecycle(lifecycle, 'start_execution');
    if (!started.changed) { setBlockedMessage(started.blockedReason ?? 'تعذّر بدء التنفيذ.'); return; }
    const scheduled = advanceLifecycle(started.state, 'schedule_follow_up', { objective: plan.objective });
    if (!scheduled.changed) { setBlockedMessage(scheduled.blockedReason ?? 'تعذّرت جدولة المتابعة.'); return; }
    setLifecycle(scheduled.state);
  };

  const recordOutcome = (outcome: Outcome) => {
    if (!plan) return;
    setBlockedMessage(null);
    const r = advanceLifecycle(lifecycle, 'record_outcome', { objective: plan.objective, outcome });
    if (r.changed) setLifecycle(r.state);
    else setBlockedMessage(r.blockedReason ?? 'تعذّر تسجيل الأثر.');
  };

  if (!plan) return null;

  const quality = recommendationQuality(lifecycle);

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="field-objective"
      aria-label="لوحة الأهداف"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Target className="w-4 h-4 text-emerald-300" aria-hidden="true" /> ماذا تريد أن تحقّق في هذا الحقل؟
        </span>
        <span className="text-[11px]" style={{ color: T.faint }}>
          {stageLabel(lifecycle.stage)}
        </span>
      </div>

      {/* منتقي الهدف */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {FIELD_OBJECTIVES.map((o) => {
          const active = o.id === selectedId;
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => pick(o.id)}
              className="text-[11px] px-2.5 py-1 rounded-full font-semibold"
              style={{
                border: `1px solid ${active ? '#14532d' : T.line}`,
                color: active ? '#86efac' : T.muted,
                background: active ? 'rgba(20,83,45,.25)' : 'rgba(15,23,42,.45)',
              }}
            >
              {o.label}
            </button>
          );
        })}
      </div>

      {/* جاهزيّة الدليل */}
      <div
        className="flex items-center gap-2 mb-2 rounded-xl px-2.5 py-1.5 text-[11px]"
        style={{
          border: `1px solid ${plan.ready ? '#14532d' : '#7c2d12'}`,
          color: plan.ready ? '#86efac' : '#fdba74',
          background: 'rgba(15,23,42,.35)',
        }}
      >
        {plan.ready ? (
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        ) : (
          <Lock className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        )}
        <span>{plan.summary}</span>
      </div>

      {/* المصادر المطلوبة */}
      <div className="flex flex-wrap gap-1.5 mb-3">
        {plan.objective.requiredSources.map((s) => {
          const ok = !plan.missingSources.includes(s);
          return (
            <span
              key={s}
              className="text-[10px] px-2 py-0.5 rounded-full font-semibold"
              style={{
                border: `1px solid ${ok ? '#14532d' : T.line}`,
                color: ok ? '#86efac' : T.faint,
                background: 'rgba(15,23,42,.45)',
              }}
            >
              {ok ? '✓' : '○'} {SOURCE_LABEL[s]}
            </span>
          );
        })}
      </div>

      {/* خطوات الحلقة: فحص ⇒ تفسير ⇒ إجراء ⇒ مراجعة */}
      <ol className="flex flex-col gap-1.5 mb-3">
        {plan.steps.map((step, i) => {
          const Icon = STEP_ICON[step.kind];
          return (
            <li key={i} className="flex items-center gap-2 text-[11px]" style={{ color: T.muted }}>
              <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: STEP_TONE[step.kind] }} aria-hidden="true" />
              <span style={{ color: T.ink }}>{step.label}</span>
              {step.source && (
                <span className="text-[10px]" style={{ color: T.faint }}>· {SOURCE_LABEL[step.source]}</span>
              )}
            </li>
          );
        })}
      </ol>

      {/* حكم الحوكمة الخلفيّة (dry-run) — معلوماتيّ: يعرض حالة الموزِّع كما حكم الخادم */}
      {dispatchEval.data && (
        <div className="flex flex-wrap items-center gap-1.5 mb-2 text-[11px]" role="status">
          <span className="px-2 py-0.5 rounded-full font-semibold" style={{ border: `1px solid ${T.line}`, color: dispatchStateColor(String(dispatchEval.data.state ?? '')) }}>
            حوكمة الموزِّع: {dispatchStateLabel(String(dispatchEval.data.state ?? ''))}
          </span>
          {typeof dispatchEval.data.required_approvals === 'number' && dispatchEval.data.required_approvals > 0 && (
            <span style={{ color: T.faint }}>موافقات مطلوبة: {dispatchEval.data.required_approvals}</span>
          )}
          {typeof dispatchEval.data.reason_ar === 'string' && dispatchEval.data.reason_ar && (
            <span style={{ color: T.muted }}>— {dispatchEval.data.reason_ar}</span>
          )}
          <span className="text-[10px]" style={{ color: T.faint }}>(معاينة — لا تنفيذ)</span>
        </div>
      )}
      {dispatchEval.isError && (
        <div className="mb-2 text-[10px]" style={{ color: T.faint }}>
          موزِّع القرار الخلفيّ غير متاح في هذه البيئة — دورة الحياة محليّة فقط.
        </div>
      )}

      {/* الإجراءات المُدارة بدورة الحياة */}
      <div className="flex flex-wrap items-center gap-1.5">
        {lifecycle.stage === 'draft' && (
          <button
            type="button"
            onClick={attachAndApprove}
            disabled={!plan.canAct}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
          >
            <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" /> اعتمِد التوصية
          </button>
        )}

        {lifecycle.stage === 'approved' && plan.objective.producesTask && (
          <button
            type="button"
            onClick={createTask}
            disabled={creatingTask}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
          >
            <ListChecks className="w-3.5 h-3.5" aria-hidden="true" /> {creatingTask ? 'جارٍ إنشاء المهمة…' : 'حوِّل إلى مهمّة'}
          </button>
        )}

        {lifecycle.stage === 'approved' && !plan.objective.producesTask && (
          <button
            type="button"
            onClick={() => recordOutcome('completed')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold"
            style={{ border: `1px solid ${T.line}`, color: T.ink, background: 'rgba(15,23,42,.45)' }}
          >
            <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" /> سجّل المخرج كمكتمل
          </button>
        )}

        {lifecycle.stage === 'task_created' && (
          <button
            type="button"
            onClick={scheduleFollowUp}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold"
            style={{ border: `1px solid ${T.line}`, color: T.ink, background: 'rgba(15,23,42,.45)' }}
          >
            <Play className="w-3.5 h-3.5" aria-hidden="true" /> ابدأ التنفيذ وجدوِل المتابعة
          </button>
        )}

        {lifecycle.stage === 'follow_up' && (
          <div className="flex items-center gap-1.5">
            <span className="text-[11px]" style={{ color: T.faint }}>
              المتابعة:{' '}
              {lifecycle.followUp?.kind === 'next_image'
                ? 'عند الصورة القادمة'
                : lifecycle.followUp?.kind === 'days'
                  ? `بعد ${lifecycle.followUp.days} يوم`
                  : '—'}{' '}
              · النتيجة؟
            </span>
            {(['improved', 'stable', 'declined'] as const).map((o) => (
              <button
                key={o}
                type="button"
                onClick={() => recordOutcome(o)}
                className="px-2 py-0.5 rounded-lg text-[10px] font-semibold"
                style={{ border: `1px solid ${T.line}`, color: T.muted, background: 'rgba(15,23,42,.45)' }}
              >
                {outcomeLabel(o)}
              </button>
            ))}
          </div>
        )}



        {blockedMessage && (
          <span
            className="inline-flex items-center gap-1 text-[11px] font-semibold"
            style={{ color: '#fdba74' }}
            role="status"
          >
            <Lock className="w-3.5 h-3.5" aria-hidden="true" />
            {blockedMessage}
          </span>
        )}

        {lifecycle.stage === 'reviewed' && (
          <span
            className="inline-flex items-center gap-1 text-[11px] font-semibold"
            style={{ color: quality === 'good' ? '#86efac' : quality === 'poor' ? '#fca5a5' : T.muted }}
          >
            <CheckCircle2 className="w-3.5 h-3.5" aria-hidden="true" />
            رُوجِعت · الأثر: {outcomeLabel(lifecycle.outcome)}
            {quality !== 'unknown' && ` · جودة التوصية: ${quality === 'good' ? 'جيّدة' : 'ضعيفة'}`}
          </span>
        )}
      </div>
    </section>
  );
}
