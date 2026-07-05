import { describe, expect, it } from 'vitest';
import {
  EXECUTE_CONFIRM_PHRASE,
  buildForLocationParams,
  buildUnifiedRequest,
  executeConfirmed,
  executionStatusColor,
  executionStatusLabel,
  explainSourceLabel,
  hasLocationInput,
  httpStatusOf,
  isFeatureDisabled404,
  moneyLabel,
  numFromText,
  numLabel,
  parseDecisionValue,
  percentLabel,
  unifiedStateColor,
  unifiedStateLabel,
  urgencyLabel,
} from './decisionDeep';

describe('numLabel / moneyLabel / percentLabel — الغائب «—» لا صفر مُختلق', () => {
  it('renders dash for null/undefined/NaN', () => {
    expect(numLabel(null)).toBe('—');
    expect(numLabel(undefined)).toBe('—');
    expect(numLabel(Number.NaN)).toBe('—');
    expect(moneyLabel(null, 'YER')).toBe('—');
    expect(percentLabel(null)).toBe('—');
  });
  it('rounds to two decimals and keeps server currency', () => {
    expect(numLabel(3.14159)).toBe('3.14');
    expect(numLabel(0)).toBe('0'); // صفر حقيقيّ من الخادم يُعرَض — لا يُخفى
    expect(moneyLabel(1234.567, 'YER')).toBe('1234.57 YER');
  });
  it('percent maps [0,1] to Arabic percent', () => {
    expect(percentLabel(0.756)).toBe('76٪');
    expect(percentLabel(0)).toBe('0٪');
  });
});

describe('unified state — known values only, neutral fallback', () => {
  it('labels/colors ready and blocked', () => {
    expect(unifiedStateLabel('ready')).toBe('جاهز');
    expect(unifiedStateLabel('blocked')).toBe('محجوب');
    expect(unifiedStateColor('ready')).toBe('#86efac');
    expect(unifiedStateColor('blocked')).toBe('#fca5a5');
  });
  it('passes unknown state through with neutral color (no invented verdict)', () => {
    expect(unifiedStateLabel('weird')).toBe('weird');
    expect(unifiedStateLabel(null)).toBe('—');
    expect(unifiedStateColor('weird')).toBe('#64748b');
  });
});

describe('execution status — queued/not_executed only', () => {
  it('labels the two server statuses', () => {
    expect(executionStatusLabel('queued')).toBe('أُدرِج في الطابور');
    expect(executionStatusLabel('not_executed')).toBe('لم يُنفَّذ (سُجِّل فقط)');
  });
  it('neutral for unknown/missing', () => {
    expect(executionStatusLabel('other')).toBe('other');
    expect(executionStatusLabel(null)).toBe('—');
    expect(executionStatusColor('queued')).toBe('#86efac');
    expect(executionStatusColor('not_executed')).toBe('#fdba74');
    expect(executionStatusColor('other')).toBe('#64748b');
  });
});

describe('urgencyLabel / explainSourceLabel — server vocabulary as-is', () => {
  it('translates known urgencies and passes unknown through', () => {
    expect(urgencyLabel('critical')).toBe('حرج');
    expect(urgencyLabel('none')).toBe('بلا إلحاح');
    expect(urgencyLabel('odd')).toBe('odd');
    expect(urgencyLabel(null)).toBe('—');
  });
  it('labels the two explanation sources', () => {
    expect(explainSourceLabel('ai')).toContain('القرار من القواعد');
    expect(explainSourceLabel('rule_based_offline')).toContain('دون إنترنت');
    expect(explainSourceLabel('x')).toBe('x');
  });
});

describe('numFromText — empty stays absent, never zero', () => {
  it('parses numbers and rejects blanks/garbage', () => {
    expect(numFromText('12.5')).toBe(12.5);
    expect(numFromText(' 0 ')).toBe(0);
    expect(numFromText('')).toBeUndefined();
    expect(numFromText('   ')).toBeUndefined();
    expect(numFromText('abc')).toBeUndefined();
    expect(numFromText(undefined)).toBeUndefined();
  });
});

describe('buildForLocationParams + hasLocationInput', () => {
  it('sends only what the user entered', () => {
    const p = buildForLocationParams({ location: ' الجوف ', soilPh: '8.2', lat: '', areaHa: 'x' });
    expect(p).toEqual({ location: 'الجوف', soil_ph: 8.2 });
  });
  it('requires a name or a full lat/lon pair (server contract)', () => {
    expect(hasLocationInput({ location: 'مأرب' })).toBe(true);
    expect(hasLocationInput({ lat: 15.1, lon: 45.3 })).toBe(true);
    expect(hasLocationInput({ lat: 15.1 })).toBe(false);
    expect(hasLocationInput({})).toBe(false);
  });
});

describe('buildUnifiedRequest — optional water numbers omitted when blank', () => {
  const sig = {
    domain: 'irrigation', action: 'irrigate', urgency: 'high',
    params: { water_mm: 20 }, halt: false, reason_ar: 'عجز رطوبة', confidence: 0.9,
  };
  it('trims field id and keeps signals untouched', () => {
    const req = buildUnifiedRequest({ fieldId: ' f1 ', signals: [sig], minMmForYield: '', waterBudgetMm: '' });
    expect(req).toEqual({ field_id: 'f1', signals: [sig] });
  });
  it('includes optimization inputs only when provided', () => {
    const req = buildUnifiedRequest({ fieldId: 'f1', signals: [sig], minMmForYield: '15', waterBudgetMm: '30' });
    expect(req.min_mm_for_yield).toBe(15);
    expect(req.water_budget_mm).toBe(30);
  });
});

describe('parseDecisionValue — honest JSON gate (dict only)', () => {
  it('accepts an object payload', () => {
    const r = parseDecisionValue('{"action":"irrigate","water_mm":20}');
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.action).toBe('irrigate');
  });
  it('rejects empty, arrays, scalars and broken JSON with Arabic reasons', () => {
    expect(parseDecisionValue('')).toEqual({ ok: false, error_ar: expect.stringContaining('فارغة') });
    expect(parseDecisionValue('[1,2]').ok).toBe(false);
    expect(parseDecisionValue('42').ok).toBe(false);
    expect(parseDecisionValue('{broken').ok).toBe(false);
  });
});

describe('executeConfirmed — literal typed confirmation', () => {
  it('matches the exact phrase only', () => {
    expect(executeConfirmed(EXECUTE_CONFIRM_PHRASE)).toBe(true);
    expect(executeConfirmed(` ${EXECUTE_CONFIRM_PHRASE} `)).toBe(true); // فراغ حواشٍ فقط
    expect(executeConfirmed('نفذ')).toBe(false); // بلا شدّة — لا مطابقة تقريبيّة
    expect(executeConfirmed('')).toBe(false);
    expect(executeConfirmed(null)).toBe(false);
  });
});

describe('httpStatusOf / isFeatureDisabled404', () => {
  it('reads axios-shaped errors and treats 404 as feature-off', () => {
    expect(httpStatusOf({ response: { status: 404 } })).toBe(404);
    expect(httpStatusOf({ response: { status: 503 } })).toBe(503);
    expect(httpStatusOf(new Error('net'))).toBeNull();
    expect(isFeatureDisabled404({ response: { status: 404 } })).toBe(true);
    expect(isFeatureDisabled404({ response: { status: 403 } })).toBe(false);
    expect(isFeatureDisabled404(undefined)).toBe(false);
  });
});
