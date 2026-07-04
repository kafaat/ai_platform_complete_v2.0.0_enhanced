// FieldView Objective Engine — يحوّل FieldView من «أداة تعرض بيانات» إلى «متعاون
// يحقّق هدفاً زراعيّاً»: نيّة المستخدم ⇒ خطّة (فحص → تفسير → إجراء → مراجعة) مربوطة
// بمصادر أدلّة حقيقيّة. صدق: المحرّك يخطّط ويتحقّق من توفّر الأدلّة ويمنع الإجراء عند
// نقصها — لا يختلق التشخيص (التشخيص يأتي من محرّكات الحوكمة/الصحّة/الماء والوكيل الزراعيّ).
export type FieldObjectiveId =
  | 'diagnose_field_stress'
  | 'plan_irrigation_week'
  | 'prepare_spray_window'
  | 'create_vra_prescription'
  | 'review_season_profitability'
  | 'generate_field_report';

export type EvidenceSource = 'imagery' | 'weather' | 'alerts' | 'tasks' | 'records' | 'zones' | 'moisture' | 'season';
export type ObjectiveStepKind = 'inspect' | 'reason' | 'act' | 'review';

export interface ObjectiveStep {
  kind: ObjectiveStepKind;
  label: string;
  source?: EvidenceSource;
}

export interface FieldObjectiveDef {
  id: FieldObjectiveId;
  label: string;
  /** المصادر التي يجب توفّرها قبل السماح بالإجراء/التوصية. */
  requiredSources: EvidenceSource[];
  steps: ObjectiveStep[];
  /** هل ينتج عن الإجراء مهمّة قابلة للمتابعة؟ */
  producesTask: boolean;
  followUp: 'next_image' | 'days' | 'none';
  followUpDays?: number;
}

export const FIELD_OBJECTIVES: FieldObjectiveDef[] = [
  {
    id: 'diagnose_field_stress',
    label: 'اكتشف سبب الإجهاد',
    requiredSources: ['imagery', 'weather', 'moisture'],
    producesTask: true,
    followUp: 'next_image',
    steps: [
      { kind: 'inspect', label: 'قارن NDVI بين آخر صورتين', source: 'imagery' },
      { kind: 'inspect', label: 'افحص NDMI/الرطوبة', source: 'moisture' },
      { kind: 'inspect', label: 'افحص طقس آخر ٧ أيّام', source: 'weather' },
      { kind: 'inspect', label: 'افحص التنبيهات المفتوحة', source: 'alerts' },
      { kind: 'reason', label: 'حدّد المناطق الأضعف والسبب المرجَّح' },
      { kind: 'act', label: 'أنشئ مهمّة كشف ميدانيّ' },
      { kind: 'review', label: 'راجِع التحسّن عند الصورة القادمة' },
    ],
  },
  {
    id: 'plan_irrigation_week',
    label: 'خطّة ريّ الأسبوع',
    requiredSources: ['moisture', 'weather'],
    producesTask: true,
    followUp: 'days',
    followUpDays: 7,
    steps: [
      { kind: 'inspect', label: 'اقرأ رطوبة التربة الحاليّة', source: 'moisture' },
      { kind: 'inspect', label: 'اقرأ تنبّؤ المطر/الحرارة', source: 'weather' },
      { kind: 'reason', label: 'احسب قرار الريّ (اسقِ/أجّل) بثقة' },
      { kind: 'act', label: 'جدوِل الريّ للأسبوع' },
      { kind: 'review', label: 'راجِع بعد ٧ أيّام' },
    ],
  },
  {
    id: 'prepare_spray_window',
    label: 'جاهزيّة نافذة الرشّ',
    requiredSources: ['weather'],
    producesTask: true,
    followUp: 'days',
    followUpDays: 2,
    steps: [
      { kind: 'inspect', label: 'افحص الرياح/المطر/الحرارة القادمة', source: 'weather' },
      { kind: 'reason', label: 'حدّد النافذة الآمنة للرشّ' },
      { kind: 'act', label: 'أنشئ مهمّة رشّ ضمن النافذة' },
      { kind: 'review', label: 'أكّد التنفيذ ضمن الظروف' },
    ],
  },
  {
    id: 'create_vra_prescription',
    label: 'وصفة تطبيق متغيّر',
    requiredSources: ['imagery', 'zones'],
    producesTask: false,
    followUp: 'none',
    steps: [
      { kind: 'inspect', label: 'تأكّد من صور جاهزة للعنقدة', source: 'imagery' },
      { kind: 'reason', label: 'ابنِ المناطق الإنتاجيّة', source: 'zones' },
      { kind: 'act', label: 'أنشئ وصفة تسميد/ريّ متغيّرة وصدّرها' },
      { kind: 'review', label: 'قارن الأثر بعد التطبيق' },
    ],
  },
  {
    id: 'review_season_profitability',
    label: 'ربحيّة الموسم',
    requiredSources: ['records', 'season'],
    producesTask: false,
    followUp: 'none',
    steps: [
      { kind: 'inspect', label: 'اجمع التكاليف والماء المُطبَّق', source: 'records' },
      { kind: 'inspect', label: 'اقرأ مرحلة/موسم الحقل', source: 'season' },
      { kind: 'reason', label: 'احسب التكلفة/هكتار والصافي' },
      { kind: 'review', label: 'صدِّر تقرير ربحيّة الموسم' },
    ],
  },
  {
    id: 'generate_field_report',
    label: 'تقرير الحقل',
    requiredSources: ['imagery', 'season'],
    producesTask: false,
    followUp: 'none',
    steps: [
      { kind: 'inspect', label: 'اجمع الصور والموسم والعمليّات', source: 'season' },
      { kind: 'reason', label: 'لخّص الحالة والأدلّة' },
      { kind: 'review', label: 'صدِّر سجلّ الحقل القابل للمشاركة' },
    ],
  },
];

export interface EvidenceAvailability {
  imagery?: boolean;
  weather?: boolean;
  alerts?: boolean;
  tasks?: boolean;
  records?: boolean;
  zones?: boolean;
  moisture?: boolean;
  season?: boolean;
}

export interface ObjectivePlan {
  objective: FieldObjectiveDef;
  steps: ObjectiveStep[];
  missingSources: EvidenceSource[];
  /** كلّ المصادر المطلوبة متاحة. */
  ready: boolean;
  /** يُسمَح بالإجراء/التوصية فقط حين تكتمل الأدلّة (منع التوصية على دليل ناقص). */
  canAct: boolean;
  summary: string;
}

export function getObjective(id: FieldObjectiveId): FieldObjectiveDef | null {
  return FIELD_OBJECTIVES.find((o) => o.id === id) ?? null;
}

export function buildObjectivePlan(id: FieldObjectiveId, availability: EvidenceAvailability): ObjectivePlan | null {
  const objective = getObjective(id);
  if (!objective) return null;
  const missingSources = objective.requiredSources.filter((s) => availability[s] !== true);
  const ready = missingSources.length === 0;
  return {
    objective,
    steps: objective.steps,
    missingSources,
    ready,
    canAct: ready,
    summary: ready
      ? `الأدلّة مكتملة — يمكن تنفيذ «${objective.label}».`
      : `أدلّة ناقصة (${missingSources.join('، ')}) — أكمِلها قبل الإجراء لتفادي توصية بلا دليل.`,
  };
}
