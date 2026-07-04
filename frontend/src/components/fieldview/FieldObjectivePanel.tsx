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
  /** توفّر الأدلّة الحقيقيّ محسوباً من استعلامات FieldView الحيّة. */
  availability: EvidenceAvailability;
  /** يُنشئ مهمّة قابلة للمتابعة من التوصية (backend حقيقيّ). يُستدعى فقط بعد اكتمال الدليل. */
  onCreateTask?: (objectiveId: FieldObjectiveId, label: string) => boolean | Promise<boolean>;
}

/** لوحة الأهداف: نيّة المستخدم ⇒ خطّة (فحص→تفسير→إجراء→مراجعة) مربوطة بأدلّة حقيقيّة،
 *  تمنع الإجراء حتّى اكتمال الدليل، وتحوّل التوصية إلى مهمّة قابلة للمتابعة بدورة حياة صريحة. */
export default function FieldObjectivePanel({ availability, onCreateTask }: FieldObjectivePanelProps) {
  const [selectedId, setSelectedId] = useState<FieldObjectiveId>('diagnose_field_stress');
  const [lifecycle, setLifecycle] = useState<LifecycleState>(initLifecycle());

  const plan = useMemo(() => buildObjectivePlan(selectedId, availability), [selectedId, availability]);

  const pick = (id: FieldObjectiveId) => {
    setSelectedId(id);
    setLifecycle(initLifecycle()); // هدف جديد ⇒ دورة حياة جديدة (لا خلط أدلّة)
  };

  useEffect(() => {
    // إذا تغيّرت البيانات الحيّة وأصبح الدليل ناقصاً قبل الوصول إلى مراجعة نهائية،
    // نرجع لمسودة بدل إبقاء توصية معتمدة على أدلة لم تعد متاحة.
    if (!plan?.canAct && ['evidence', 'approved', 'task_created', 'executing', 'follow_up'].includes(lifecycle.stage)) {
      setLifecycle(initLifecycle());
    }
  }, [plan?.canAct, lifecycle.stage]);

  const attachAndApprove = () => {
    if (!plan?.canAct) return;
    // مسوّدة ⇒ دليل ⇒ مُعتمَدة (انتقالات صريحة، بوّابة الدليل مطبَّقة)
    const evidence = advanceLifecycle(lifecycle, 'attach_evidence', { canAct: plan.canAct });
    if (!evidence.changed) return;
    const approved = advanceLifecycle(evidence.state, 'approve');
    if (!approved.changed) return;
    setLifecycle(approved.state);
  };

  const createTask = async () => {
    if (!plan?.canAct) return;
    // لا نسمح بتقدّم دورة الحياة بمجرد عدم وجود callback؛
    // الهدف المنتج لمهمة يحتاج قبولاً صريحاً من طبقة تنفيذ حية.
    if (!onCreateTask) return;
    const r = advanceLifecycle(lifecycle, 'create_task', { objective: plan.objective });
    if (!r.changed) return;
    try {
      const accepted = await onCreateTask(plan.objective.id, plan.objective.label);
      // يجب أن ترجع الطبقة المضيفة true صراحة بعد إنشاء/فتح مسار تنفيذ حقيقي.
      if (accepted !== true) return;
      setLifecycle(r.state);
    } catch {
      // رفض/فشل backend أو المسار المضيف لا يغيّر الحالة؛ لا نكذب بأن مهمة أُنشئت.
      return;
    }
  };

  const scheduleFollowUp = () => {
    if (!plan?.canAct) return;
    const started = advanceLifecycle(lifecycle, 'start_execution');
    if (!started.changed) return;
    const scheduled = advanceLifecycle(started.state, 'schedule_follow_up', { objective: plan.objective });
    if (!scheduled.changed) return;
    setLifecycle(scheduled.state);
  };

  const recordOutcome = (outcome: Outcome) => {
    if (!plan) return;
    const r = advanceLifecycle(lifecycle, 'record_outcome', { objective: plan.objective, outcome });
    if (r.changed) setLifecycle(r.state);
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
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold"
            style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
          >
            <ListChecks className="w-3.5 h-3.5" aria-hidden="true" /> حوِّل إلى مهمّة
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
