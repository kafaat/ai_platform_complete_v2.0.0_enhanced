// FieldView Recommendation Lifecycle — دورة حياة التوصية كآلة حالات صرفة:
// مسوّدة ⇒ دليل مُرفَق ⇒ موافقة المستخدم ⇒ مهمّة مُنشأة ⇒ تنفيذ ⇒ متابعة (صورة/مدّة) ⇒
// مُراجَعة ⇒ تحديث جودة التوصية. صدق: انتقالات صريحة فقط (لا قفز)، ولا تُنشأ توصية قابلة
// للتنفيذ قبل اكتمال الدليل (canAct من محرّك الأهداف)، ولا يُختلق أثر — الأثر يأتي من
// مراجعة حقيقيّة (تحسّن/ثبات/تراجع) يُدخِلها المستخدم أو الصورة القادمة.
import type { FieldObjectiveDef } from './fieldObjectiveEngine';

export type LifecycleStage =
  | 'draft' //        مسوّدة (هدف مُختار، لا دليل بعد)
  | 'evidence' //     الدليل مُرفَق ومكتمل
  | 'approved' //     وافق المستخدم على التوصية
  | 'task_created' // أُنشئت مهمّة قابلة للمتابعة
  | 'executing' //    قيد التنفيذ الميدانيّ
  | 'follow_up' //    بانتظار متابعة (صورة قادمة أو مدّة)
  | 'reviewed' //     رُوجِعت النتيجة (أثر حقيقيّ)
  | 'archived'; //    مؤرشفة (أُلغيت أو اكتملت بلا متابعة)

export type LifecycleEvent =
  | 'attach_evidence'
  | 'approve'
  | 'create_task'
  | 'start_execution'
  | 'schedule_follow_up'
  | 'record_outcome'
  | 'archive';

export type Outcome = 'improved' | 'stable' | 'declined' | 'completed' | 'unknown';

export interface FollowUp {
  kind: 'next_image' | 'days' | 'none';
  /** عدد الأيّام إذا kind='days'. */
  days?: number;
}

export interface LifecycleState {
  stage: LifecycleStage;
  /** الأثر المُراجَع — 'unknown' حتّى تُدخَل مراجعة حقيقيّة (لا اختلاق). */
  outcome: Outcome;
  followUp: FollowUp | null;
}

/** انتقالات مسموحة صريحة (المفتاح = الحالة، القيمة = الأحداث المقبولة ⇒ الحالة التالية). */
const TRANSITIONS: Record<LifecycleStage, Partial<Record<LifecycleEvent, LifecycleStage>>> = {
  draft: { attach_evidence: 'evidence', archive: 'archived' },
  evidence: { approve: 'approved', archive: 'archived' },
  // للأهداف التي لا تنتج مهمة ميدانية (VRA/ربحية/تقرير)، يمكن تسجيل المخرج مباشرة بعد الاعتماد.
  approved: { create_task: 'task_created', record_outcome: 'reviewed', archive: 'archived' },
  task_created: { start_execution: 'executing', archive: 'archived' },
  executing: { schedule_follow_up: 'follow_up', record_outcome: 'reviewed', archive: 'archived' },
  follow_up: { record_outcome: 'reviewed', archive: 'archived' },
  reviewed: { archive: 'archived' },
  archived: {},
};

export function initLifecycle(): LifecycleState {
  return { stage: 'draft', outcome: 'unknown', followUp: null };
}

/** يُشتقّ إعداد المتابعة من تعريف الهدف (لا أرقام مُختلَقة — من الكتالوج). */
export function followUpForObjective(objective: FieldObjectiveDef): FollowUp {
  if (objective.followUp === 'days') {
    // لا نُخرج متابعة زمنية ناقصة حتى لو استُدعيت الدالة مباشرة خارج advanceLifecycle.
    if (typeof objective.followUpDays !== 'number' || !Number.isFinite(objective.followUpDays) || objective.followUpDays <= 0) {
      return { kind: 'none' };
    }
    return { kind: 'days', days: objective.followUpDays };
  }
  if (objective.followUp === 'next_image') return { kind: 'next_image' };
  return { kind: 'none' };
}

export interface AdvanceInput {
  /** الهدف — يُستخدم لجدولة المتابعة ولمنع إنشاء مهمة لهدف لا ينتج مهمة. */
  objective?: FieldObjectiveDef | null;
  /** يجب أن يكون الدليل مكتملاً (canAct=true) قبل السماح بـattach_evidence. */
  canAct?: boolean;
  /** الأثر المُراجَع عند record_outcome (حقيقيّ من المستخدم/الصورة). */
  outcome?: Outcome;
}

export interface AdvanceResult {
  state: LifecycleState;
  changed: boolean;
  /** سبب رفض الانتقال (إن رُفِض) — للعرض الصادق لا للاختلاق. */
  blockedReason?: string;
}

/** آلة الحالات الصرفة: تُرجِع حالة جديدة أو ترفض الحدث بسبب صريح. لا تطفر أبداً. */
export function advanceLifecycle(
  state: LifecycleState,
  event: LifecycleEvent,
  input: AdvanceInput = {},
): AdvanceResult {
  const next = TRANSITIONS[state.stage]?.[event];
  if (!next) {
    return { state, changed: false, blockedReason: `الحدث «${event}» غير مسموح من «${state.stage}».` };
  }
  // بوّابة الدليل: لا تُرفَق أدلّة إلا بتصريح صريح canAct=true.
  // كان canAct غير الممرَّر يُعامَل ضمنياً كقبول، وهذا يسمح باستدعاء برمجي خاطئ
  // يتجاوز شرط اكتمال الدليل.
  if (event === 'attach_evidence' && input.canAct !== true) {
    return { state, changed: false, blockedReason: 'الدليل ناقص أو غير مؤكَّد — أكمِله قبل اعتماد التوصية.' };
  }

  // هدف لا ينتج مهمة لا يجوز أن يمر عبر create_task حتى لو أخفى المكوّن الزرّ؛
  // الحارس هنا داخل آلة الحالات نفسها حتى لا تعتمد السلامة على الواجهة فقط.
  if (event === 'create_task') {
    if (!input.objective) {
      return { state, changed: false, blockedReason: 'لا يمكن إنشاء مهمة دون تعريف الهدف.' };
    }
    if (!input.objective.producesTask) {
      return { state, changed: false, blockedReason: 'هذا الهدف ينتج مخرجاً لا مهمة ميدانية.' };
    }
  }

  // الاكتمال المباشر من approved مخصص فقط للأهداف غير الميدانية وبنتيجة completed.
  if (event === 'record_outcome' && state.stage === 'approved') {
    if (!input.objective) {
      return { state, changed: false, blockedReason: 'لا يمكن تسجيل المخرج دون تعريف الهدف.' };
    }
    if (input.objective.producesTask) {
      return { state, changed: false, blockedReason: 'هذا الهدف يحتاج مهمة ومتابعة قبل تسجيل الأثر.' };
    }
    if (input.outcome !== 'completed') {
      return { state, changed: false, blockedReason: 'الأهداف غير الميدانية تُغلق من هذه المرحلة كمخرج مكتمل فقط.' };
    }
  }

  if (event === 'schedule_follow_up') {
    if (!input.objective) {
      return { state, changed: false, blockedReason: 'لا يمكن جدولة متابعة دون تعريف الهدف.' };
    }
    if (input.objective.followUp === 'none') {
      return { state, changed: false, blockedReason: 'هذا الهدف لا يملك متابعة مجدولة.' };
    }
    if (input.objective.followUp === 'days' && (typeof input.objective.followUpDays !== 'number' || !Number.isFinite(input.objective.followUpDays) || input.objective.followUpDays <= 0)) {
      return { state, changed: false, blockedReason: 'تعريف الهدف يطلب متابعة زمنية بلا عدد أيام صالح.' };
    }
  }

  const newState: LifecycleState = { ...state, stage: next };

  if (event === 'schedule_follow_up' && input.objective) {
    newState.followUp = followUpForObjective(input.objective);
  }
  if (event === 'record_outcome') {
    newState.outcome = input.outcome ?? 'unknown';
  }

  return { state: newState, changed: true };
}

/** تسمية عربيّة للمرحلة (عرض). */
export function stageLabel(stage: LifecycleStage): string {
  const map: Record<LifecycleStage, string> = {
    draft: 'مسوّدة',
    evidence: 'الدليل مُرفَق',
    approved: 'مُعتمَدة',
    task_created: 'مهمّة مُنشأة',
    executing: 'قيد التنفيذ',
    follow_up: 'بانتظار المتابعة',
    reviewed: 'رُوجِعت',
    archived: 'مؤرشفة',
  };
  return map[stage];
}

/** تسمية عربيّة للأثر (عرض). */
export function outcomeLabel(outcome: Outcome): string {
  const map: Record<Outcome, string> = {
    improved: 'تحسّن',
    stable: 'ثابت',
    declined: 'تراجع',
    completed: 'مكتمل',
    unknown: 'غير معروف بعد',
  };
  return map[outcome];
}

/** جودة التوصية = هل أدّت لأثر إيجابيّ؟ 'unknown' حتّى تُراجَع (صدق). */
export function recommendationQuality(state: LifecycleState): 'good' | 'poor' | 'unknown' {
  if (state.stage !== 'reviewed') return 'unknown';
  if (state.outcome === 'improved' || state.outcome === 'stable' || state.outcome === 'completed') return 'good';
  if (state.outcome === 'declined') return 'poor';
  return 'unknown';
}
