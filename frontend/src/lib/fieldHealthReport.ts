// FieldView Field Health Report — يترجم حالة الحقل النشط إلى تقرير يجيب عن خمسة أسئلة
// (مستوحى من Farmonaut Field Health Report + إطار القرار في John Deere/CropX/xarvio):
//   1) ما حالة هذا الحقل الآن؟   (state)
//   2) ما السبب؟                 (reasons — مدعومة بالأدلّة)
//   3) ما الإجراء التالي؟        (nextAction)
//   4) ما الدليل؟                (evidence — قيم حقيقيّة)
//   5) ما الأثر؟                 (impact — تشغيليّ نوعيّ الآن؛ الأثر الماليّ لطبقة الأعمال P4)
//
// صدق المصدر: لا بيانات ملفَّقة — كلّ رقم مشتقّ من الحوكمة (evaluateFieldViewGovernance)
// و/أو مشاهد الصور و/أو سجلّ الحقل الممرَّر من الشاشة. لا نداء شبكة هنا؛ منطق نقيّ مُختبَر.
import type { FieldViewActionDeckInput } from './fieldViewActionDeck';
import { buildFieldViewActionDeck, summarizeImageryFreshness } from './fieldViewActionDeck';
import { evaluateFieldViewGovernance, type FieldViewGovernanceSeverity } from './fieldViewGovernance';

export type FieldHealthSeverity = FieldViewGovernanceSeverity;

export interface FieldHealthEvidence {
  label: string;
  value: string;
}

export interface FieldHealthReport {
  fieldId: string | null;
  fieldLabel: string;
  /** ثقة مصادر القرار 0-100 (من الحوكمة). */
  confidence: number;
  /** ما حالة الحقل الآن؟ */
  state: { severity: FieldHealthSeverity; label: string; headline: string };
  /** ما السبب؟ — أسباب مدعومة بأدلّة من المصادر الضعيفة. */
  reasons: string[];
  /** ما الإجراء التالي؟ — أعلى بطاقة قابلة للتنفيذ (بلا بطاقة الحوكمة/السياق). */
  nextAction: { title: string; cta: string } | null;
  /** ما الدليل؟ — قيم حقيقيّة موجزة. */
  evidence: FieldHealthEvidence[];
  /** ما الأثر؟ — تشغيليّ نوعيّ (لا رقم ماليّ ملفَّق؛ الربحيّة في طبقة الأعمال P4). */
  impact: string;
}

const SEVERITY_LABEL: Record<FieldHealthSeverity, string> = {
  ok: 'سليم',
  info: 'متابعة',
  warn: 'انتباه',
  critical: 'حرج',
};

export function buildFieldHealthReport(input: FieldViewActionDeckInput, nowMs = Date.now()): FieldHealthReport {
  const fieldLabel = input.fieldName || 'الحقل النشط';

  if (!input.fieldId) {
    return {
      fieldId: null,
      fieldLabel,
      confidence: 0,
      state: { severity: 'warn', label: SEVERITY_LABEL.warn, headline: 'اختر حقلاً لعرض تقرير الحالة' },
      reasons: ['لا يوجد حقل نشط في FieldView.'],
      nextAction: { title: 'اختر حقلاً', cta: 'افتح قائمة الحقول' },
      evidence: [{ label: 'الحقل', value: 'غير محدَّد' }],
      impact: 'لا يمكن اتخاذ قرار حقليّ قبل اختيار حقل.',
    };
  }

  const gov = evaluateFieldViewGovernance(input, nowMs);
  const imagery = summarizeImageryFreshness(input.imageryDates ?? [], nowMs);
  const cards = buildFieldViewActionDeck(input, nowMs);

  // السبب: المصادر الضعيفة (warn/critical) هي ما يخفض ثقة القرار.
  const weak = gov.sources.filter((s) => s.severity === 'critical' || s.severity === 'warn');
  const reasons = weak.length
    ? weak.map((s) => `${s.label}: ${s.evidence}`)
    : ['كلّ مصادر القرار الأساسيّة متناسقة.'];

  // الإجراء التالي: أعلى بطاقة قابلة للتنفيذ ليست بطاقة حوكمة/سياق (فهي شرح لا فعل).
  const actionable = cards.find((c) => c.kind !== 'governance' && c.kind !== 'context') ?? cards[0] ?? null;
  const nextAction = actionable ? { title: actionable.title, cta: actionable.cta } : null;

  // الدليل: قيم حقيقيّة موجزة من المصادر.
  const evidence: FieldHealthEvidence[] = [
    { label: 'المحصول/المساحة', value: `${input.crop ?? '—'} · ${input.areaHa != null ? `${Number(input.areaHa).toFixed(1)} هـ` : '—'}` },
    {
      label: 'الصور',
      value: imagery.total === 0 ? 'لا مشاهد' : `أحدث ${imagery.newestDate} · جاهز ${imagery.readyCount}/${imagery.total}`,
    },
    { label: 'الطقس', value: input.weatherReady ? 'محدَّث' : 'قيد التحديث/احتياطيّ' },
    { label: 'التنبيهات', value: `${input.activeAlertsCount ?? 0} نشط` },
    { label: 'المهام', value: `${input.openTasksCount ?? 0} مفتوحة` },
    { label: 'ثقة المصادر', value: `${gov.score}%` },
  ];

  // الأثر: نوعيّ تشغيليّ مشتقّ من أضعف مصدر — بلا رقم ماليّ ملفَّق.
  const impact = weak.length
    ? `الأثر التشغيليّ: ${weak[0].action ?? weak[0].label} — القرار أقلّ موثوقيّة حتى تُعالَج. (الأثر الماليّ يُحسب في طبقة أعمال الحقل.)`
    : 'الأثر التشغيليّ: المصادر جاهزة — القرار الحاليّ مدعوم بالأدلّة.';

  return {
    fieldId: input.fieldId,
    fieldLabel,
    confidence: gov.score,
    state: {
      severity: gov.severity,
      label: SEVERITY_LABEL[gov.severity],
      headline: `حالة ${fieldLabel}: ${SEVERITY_LABEL[gov.severity]} · ثقة ${gov.score}%`,
    },
    reasons,
    nextAction,
    evidence,
    impact,
  };
}
