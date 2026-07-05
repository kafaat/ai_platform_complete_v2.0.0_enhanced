import { describe, expect, it } from 'vitest';
import {
  activationBadge,
  activationFacts,
  biasBadge,
  blendFacts,
  blendReady,
  calibrationFacts,
  coverageEntries,
  escalationBadge,
  fmtNum,
  gateBadge,
  mapLayers,
  observationReady,
  overrideEntries,
  parseMeasure,
  pctFromFraction,
  suggestionBadge,
  thresholdSuggestionRows,
  tierBadge,
} from './learningEvidence';
import type { ObservationInput } from './learningEvidence';

describe('formatting helpers — honest «—» for missing, no zero-fill', () => {
  it('fmtNum drops null/undefined/non-finite', () => {
    expect(fmtNum(1.234, 2)).toBe('1.23');
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined)).toBe('—');
    expect(fmtNum(Number.NaN)).toBe('—');
  });
  it('pctFromFraction converts [0,1] fraction to percent', () => {
    expect(pctFromFraction(0.7)).toBe('70٪');
    expect(pctFromFraction(0.125, 1)).toBe('12.5٪');
    expect(pctFromFraction(null)).toBe('—');
  });
  it('parseMeasure returns null for empty/non-numeric (no assumption)', () => {
    expect(parseMeasure('12.5')).toBe(12.5);
    expect(parseMeasure('  ')).toBeNull();
    expect(parseMeasure('abc')).toBeNull();
  });
});

describe('badges — known values coloured, unknown/missing neutral & passthrough', () => {
  it('activationBadge maps gate states', () => {
    expect(activationBadge('ready').color).toBe('#86efac');
    expect(activationBadge('accumulating').color).toBe('#fdba74');
    expect(activationBadge('dormant').color).toBe('#64748b');
    expect(activationBadge('weird')).toEqual({ label_ar: 'weird', color: '#64748b' });
    expect(activationBadge(null)).toEqual({ label_ar: '—', color: '#64748b' });
  });
  it('biasBadge maps calibration bias types', () => {
    expect(biasBadge('unbiased').color).toBe('#86efac');
    expect(biasBadge('overprediction').label_ar).toBe('إفراط في التقدير');
    expect(biasBadge('insufficient').color).toBe('#64748b');
  });
  it('suggestionBadge maps policy suggestions', () => {
    expect(suggestionBadge('loosen').color).toBe('#fdba74');
    expect(suggestionBadge('tighten').color).toBe('#7dd3fc');
    expect(suggestionBadge('keep').color).toBe('#86efac');
  });
  it('tierBadge maps corroboration tiers', () => {
    expect(tierBadge('confirmed').color).toBe('#86efac');
    expect(tierBadge('corroborated').color).toBe('#7dd3fc');
    expect(tierBadge('indicative').color).toBe('#64748b');
  });
  it('gateBadge maps confidence-gate decisions', () => {
    expect(gateBadge('confident').color).toBe('#86efac');
    expect(gateBadge('review').color).toBe('#fdba74');
    expect(gateBadge('blocked').color).toBe('#fca5a5');
  });
  it('escalationBadge maps escalation levels', () => {
    expect(escalationBadge('none').color).toBe('#86efac');
    expect(escalationBadge('blocked').label_ar).toBe('محجوب (تصعيد حاكم)');
  });
});

describe('activationFacts — drops missing fields', () => {
  it('builds only present facts', () => {
    const facts = activationFacts({ completed_outcomes: 12, threshold: 50, progress_pct: 24, acceptance_rate: 0.8 });
    expect(facts).toContainEqual({ label: 'نتائج مكتملة', value: '12/50' });
    expect(facts).toContainEqual({ label: 'التقدّم', value: '24.0٪' });
    expect(facts).toContainEqual({ label: 'القبول', value: '80٪' });
    // lag_compliance غائب ⇒ لا صفّ (لا تصفير)
    expect(facts.find((f) => f.label === 'النضج الزمنيّ')).toBeUndefined();
  });
  it('empty for null', () => {
    expect(activationFacts(null)).toEqual([]);
  });
});

describe('blend — readiness gate + facts', () => {
  it('blendReady requires at least one evidence input', () => {
    expect(blendReady({ external_prior: 3.2, local_estimate: null, n_local: 0, crop_grown_in_yemen: true, external_credibility: 0.5 })).toBe(true);
    expect(blendReady({ external_prior: null, local_estimate: 4.1, n_local: 5, crop_grown_in_yemen: true, external_credibility: 0.5 })).toBe(true);
    // تقدير محلّيّ بلا عيّنة ⇒ ليس جاهزاً
    expect(blendReady({ external_prior: null, local_estimate: 4.1, n_local: 0, crop_grown_in_yemen: true, external_credibility: 0.5 })).toBe(false);
    expect(blendReady({ external_prior: null, local_estimate: null, n_local: 0, crop_grown_in_yemen: false, external_credibility: 0.5 })).toBe(false);
    expect(blendReady(null)).toBe(false);
  });
  it('blendFacts empty when not applicable or no estimate', () => {
    expect(blendFacts({ applicable: false, blended_estimate: null })).toEqual([]);
    expect(blendFacts({ applicable: true, blended_estimate: null })).toEqual([]);
  });
  it('blendFacts builds weights and confidence honestly', () => {
    const facts = blendFacts({ applicable: true, blended_estimate: 3.456, local_weight: 0.25, external_weight: 0.75, output_confidence: 0.62, n_local: 10 });
    expect(facts[0]).toEqual({ label: 'التقدير الممزوج', value: '3.456' });
    expect(facts).toContainEqual({ label: 'ثقة المخرَج', value: '62٪' });
    expect(facts).toContainEqual({ label: 'عيّنات محلّيّة', value: '10' });
  });
});

describe('calibrationFacts — correction factor passthrough', () => {
  it('renders pairs, farms and factor', () => {
    const facts = calibrationFacts({ n_pairs: 8, n_farms: 3, mean_signed_bias: 0.12, confidence_weight: 0.21, correction_factor: 0.98 });
    expect(facts).toContainEqual({ label: 'أزواج', value: '8' });
    expect(facts).toContainEqual({ label: 'معامل التصحيح', value: '×0.980' });
  });
});

describe('thresholdSuggestionRows + overrideEntries — flatten dict to stable sorted rows', () => {
  it('sorts per_type by alert_type and carries fields', () => {
    const rows = thresholdSuggestionRows({
      per_type: {
        low_moisture: { n: 6, suggestion: 'loosen', suggested_overrides: { LOW_MOISTURE_SOIL_PCT: 25.5 } },
        heat_stress: { n: 4, suggestion: 'keep' },
      },
    });
    expect(rows.map((r) => r.alert_type)).toEqual(['heat_stress', 'low_moisture']);
    expect(rows[1].suggestion).toBe('loosen');
  });
  it('is empty for missing per_type', () => {
    expect(thresholdSuggestionRows(null)).toEqual([]);
    expect(thresholdSuggestionRows({})).toEqual([]);
  });
  it('overrideEntries flattens and sorts KEY→value', () => {
    expect(overrideEntries({ HEAVY_RAIN_MM: 23, LOW_MOISTURE_SOIL_PCT: 25.5 })).toEqual([
      { key: 'HEAVY_RAIN_MM', value: 23 },
      { key: 'LOW_MOISTURE_SOIL_PCT', value: 25.5 },
    ]);
    expect(overrideEntries(null)).toEqual([]);
  });
});

describe('coverageEntries — flatten index→description', () => {
  it('sorts by index key', () => {
    expect(coverageEntries({ ndvi: 'صحّة عامّة', bsi: 'تربة عارية' })).toEqual([
      { index: 'bsi', desc: 'تربة عارية' },
      { index: 'ndvi', desc: 'صحّة عامّة' },
    ]);
    expect(coverageEntries(undefined)).toEqual([]);
  });
});

describe('mapLayers — server order preserved, empty when absent', () => {
  it('returns layers as-is', () => {
    const layers = [{ id: 'ndvi' }, { id: 'ndre' }];
    expect(mapLayers({ layers })).toBe(layers);
    expect(mapLayers({})).toEqual([]);
    expect(mapLayers(null)).toEqual([]);
  });
});

describe('observationReady — no submit without a real measurement', () => {
  const base: ObservationInput = {
    tenant_id: 't1', farm_id: null, field_id: null, observable_id: 'soil_ph',
    value: 6.8, unit: '', source: 'manual', confidence: 'medium', measured_at: '2026-07-01T00:00:00Z', method: null,
  };
  it('true when tenant, observable, value and time present', () => {
    expect(observationReady(base)).toBe(true);
  });
  it('false when value missing or observable/time blank', () => {
    expect(observationReady({ ...base, value: null })).toBe(false);
    expect(observationReady({ ...base, observable_id: '  ' })).toBe(false);
    expect(observationReady({ ...base, measured_at: '' })).toBe(false);
    expect(observationReady(null)).toBe(false);
  });
});
