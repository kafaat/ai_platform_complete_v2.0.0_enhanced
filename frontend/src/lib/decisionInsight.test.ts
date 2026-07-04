import { describe, expect, it } from 'vitest';
import {
  dash,
  decisionTypeLabel,
  explanationSteps,
  outcomeSuccessColor,
  outcomeSuccessLabel,
  percentLabel,
  suggestionKindColor,
  suggestionKindLabel,
  type DecisionExplanation,
} from './decisionInsight';

const explanation = (over: Partial<DecisionExplanation> = {}): DecisionExplanation => ({
  crop: 'wheat',
  crop_known: true,
  decision_id: 'd1',
  field_id: 'f1',
  confidence: { value: 0.72, data_quality: null, present: true },
  signals: {
    water: { present: true, needs_irrigation: true, depletion_mm: 12, deficit_mm: 8 },
    nutrient: { present: false, stage: null, remaining_need_kg_ha: null },
    phenology: { present: true, stage: 'tillering', past_maturity: false },
    risks: [],
    stress_flags: [{ code: 'water_deficit', label_ar: 'عجز مائيّ' }],
  },
  policy: { present: true, resolved: 'balanced', applied: 'deficit', auto: true, reasons_ar: [] },
  constraints: {
    max_application_mm: 25,
    season_budget_mm: 300,
    budget_exhausted: false,
    active_risks: [{ key: 'frost', label_ar: 'صقيع', level_ar: 'مرتفع' }],
    economic_status: null,
  },
  final: {
    present: true,
    recommended_action: 'ريّ خلال 48 ساعة',
    next_event_mm: 18,
    total_irrigation_mm: 120,
    next_event_day: 2,
    dynamic_kc: null,
    fertilization: { present: false, due: null, action_ar: null },
  },
  calibrated: false,
  has_decision_value: true,
  ...over,
});

describe('dash — null becomes «—», zero is a real value', () => {
  it('maps null/undefined/empty to the dash and keeps zero', () => {
    expect(dash(null)).toBe('—');
    expect(dash(undefined)).toBe('—');
    expect(dash('')).toBe('—');
    expect(dash(0)).toBe('0');
    expect(dash('ready')).toBe('ready');
  });
});

describe('percentLabel — server ratio passes through, missing never fabricated', () => {
  it('renders [0,1] ratios and refuses non-numbers', () => {
    expect(percentLabel(0.72)).toBe('72٪');
    expect(percentLabel(0)).toBe('0٪');
    expect(percentLabel(null)).toBe('—');
    expect(percentLabel(undefined)).toBe('—');
    expect(percentLabel(Number.NaN)).toBe('—');
  });
});

describe('decisionTypeLabel — known types localized, unknown pass through', () => {
  it('maps persisted decision_type vocabulary', () => {
    expect(decisionTypeLabel('crop_twin')).toBe('توأم المحصول');
    expect(decisionTypeLabel('irrigation_plan')).toBe('خطّة الريّ');
    expect(decisionTypeLabel('profit_aware')).toBe('قرار واعٍ بالربح');
    expect(decisionTypeLabel('mystery_type')).toBe('mystery_type');
    expect(decisionTypeLabel(null)).toBe('—');
  });
});

describe('suggestionKind label/color — server kinds as-is, unknown neutral', () => {
  it('maps the four learning kinds and passes unknown through', () => {
    expect(suggestionKindLabel('raise_approvals')).toBe('رفع الموافقات');
    expect(suggestionKindLabel('relax_friction')).toBe('تخفيف الاحتكاك');
    expect(suggestionKindLabel('weird_kind')).toBe('weird_kind');
    expect(suggestionKindColor('relax_friction')).toBe('#86efac');
    expect(suggestionKindColor('raise_approvals')).toBe('#fdba74');
    expect(suggestionKindColor('weird_kind')).toBe('#64748b');
  });
});

describe('explanationSteps — ordered chain, absent blocks dropped not fabricated', () => {
  it('builds the full chain in server order (confidence→signals→policy→constraints→final)', () => {
    const steps = explanationSteps(explanation());
    expect(steps.map((s) => s.key)).toEqual(['confidence', 'signals', 'policy', 'constraints', 'final']);
    expect(steps[0].detail_ar).toBe('72٪');
    expect(steps[1].detail_ar).toContain('الماء: يحتاج ريّاً');
    expect(steps[2].detail_ar).toBe('deficit'); // applied wins over resolved
    expect(steps[3].detail_ar).toContain('مخاطر فاعلة: 1');
    expect(steps[4].detail_ar).toContain('ريّ خلال 48 ساعة');
  });

  it('drops absent blocks entirely (present=false ⇒ no invented step)', () => {
    const steps = explanationSteps(explanation({
      confidence: { value: null, data_quality: null, present: false },
      signals: {
        water: { present: false, needs_irrigation: null, depletion_mm: null, deficit_mm: null },
        nutrient: { present: false, stage: null, remaining_need_kg_ha: null },
        phenology: { present: false, stage: null, past_maturity: null },
        risks: [],
        stress_flags: [],
      },
      policy: { present: false, resolved: null, applied: null, auto: false, reasons_ar: [] },
      constraints: {
        max_application_mm: null, season_budget_mm: null, budget_exhausted: null,
        active_risks: [], economic_status: null,
      },
    }));
    expect(steps.map((s) => s.key)).toEqual(['final']);
  });

  it('returns an empty chain for a missing explanation (no crash, no fabrication)', () => {
    expect(explanationSteps(null)).toEqual([]);
    expect(explanationSteps(undefined)).toEqual([]);
  });
});

describe('outcomeSuccess — NULL is an honest «no verdict», not a failure', () => {
  it('labels and colors the tri-state verdict', () => {
    expect(outcomeSuccessLabel(true)).toBe('نجح');
    expect(outcomeSuccessLabel(false)).toBe('انحرف');
    expect(outcomeSuccessLabel(null)).toBe('بلا حكم');
    expect(outcomeSuccessColor(true)).toBe('#86efac');
    expect(outcomeSuccessColor(false)).toBe('#fca5a5');
    expect(outcomeSuccessColor(null)).toBe('#64748b');
  });
});
