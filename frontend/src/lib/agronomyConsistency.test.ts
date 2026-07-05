import { describe, expect, it } from 'vitest';
import {
  conflictRows,
  conflictSeverityBadge,
  executionModeBadge,
  fmtNum,
  freshnessWarningRows,
  geometryIssueBadge,
  geometryIssues,
  geometryValidationFacts,
  irrigationPolicyBadge,
  irrigationRecommendationFacts,
  parseMeasure,
  parsePctToFraction,
  pctFromFraction,
  portfolioFieldRows,
  portfolioStatusBadge,
  portfolioSummaryFacts,
  rotationRatingBadge,
  rotationReasons,
  supportedCropRows,
  unsupportedMessage,
  validityBadge,
  wofostKeyParams,
  wofostModelTypeRows,
} from './agronomyConsistency';

const NEUTRAL = '#64748b';

describe('formatters — null/غائب ⇒ «—» (لا تصفير)', () => {
  it('fmtNum passes numbers, dashes the missing', () => {
    expect(fmtNum(3.14159, 2)).toBe('3.14');
    expect(fmtNum(0)).toBe('0'); // صفر حقيقيّ ليس غياباً
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined)).toBe('—');
    expect(fmtNum(Number.NaN)).toBe('—');
  });
  it('pctFromFraction converts server fraction, dashes the missing', () => {
    expect(pctFromFraction(0.42)).toBe('42٪');
    expect(pctFromFraction(null)).toBe('—');
  });
  it('parseMeasure/parsePctToFraction — empty/non-numeric ⇒ null (no assumption)', () => {
    expect(parseMeasure('12.5')).toBe(12.5);
    expect(parseMeasure('  ')).toBeNull();
    expect(parseMeasure('abc')).toBeNull();
    expect(parsePctToFraction('50')).toBe(0.5);
    expect(parsePctToFraction('')).toBeNull();
  });
});

describe('badges — known values only, unknown/null neutral with server text', () => {
  it('conflict severity — block/warn/info known, else neutral', () => {
    expect(conflictSeverityBadge('block').color).toBe('#fca5a5');
    expect(conflictSeverityBadge('WARN').color).toBe('#fdba74'); // case-insensitive
    expect(conflictSeverityBadge('info').color).toBe('#7dd3fc');
    const unknown = conflictSeverityBadge('weird');
    expect(unknown.color).toBe(NEUTRAL);
    expect(unknown.label_ar).toBe('weird'); // نصّ الخادم يمرّ كما جاء
    expect(conflictSeverityBadge(null).label_ar).toBe('—');
  });
  it('validity — four states known, else neutral', () => {
    expect(validityBadge('valid').color).toBe('#86efac');
    expect(validityBadge('degraded').color).toBe('#fdba74');
    expect(validityBadge('conflicted').color).toBe('#fca5a5');
    expect(validityBadge('insufficient').color).toBe('#94a3b8');
    expect(validityBadge('nope').color).toBe(NEUTRAL);
  });
  it('execution mode — auto/human_review/blocked known', () => {
    expect(executionModeBadge('auto').color).toBe('#86efac');
    expect(executionModeBadge('human_review').color).toBe('#fdba74');
    expect(executionModeBadge('blocked').color).toBe('#fca5a5');
    expect(executionModeBadge(undefined).color).toBe(NEUTRAL);
  });
  it('rotation rating — good/acceptable/avoid known', () => {
    expect(rotationRatingBadge('good').color).toBe('#86efac');
    expect(rotationRatingBadge('acceptable').color).toBe('#7dd3fc');
    expect(rotationRatingBadge('avoid').color).toBe('#fca5a5');
    expect(rotationRatingBadge('x').color).toBe(NEUTRAL);
  });
  it('irrigation policy — four policies known', () => {
    expect(irrigationPolicyBadge('net_only').color).toBe('#7dd3fc');
    expect(irrigationPolicyBadge('salinity_adjusted').color).toBe('#fdba74');
    expect(irrigationPolicyBadge('salinity_with_leaching').color).toBe('#fdba74');
    expect(irrigationPolicyBadge('blocked_for_review').color).toBe('#fca5a5');
    expect(irrigationPolicyBadge('other').color).toBe(NEUTRAL);
  });
  it('geometry issue severity — ok/warning/error known', () => {
    expect(geometryIssueBadge('ok').color).toBe('#86efac');
    expect(geometryIssueBadge('warning').color).toBe('#fdba74');
    expect(geometryIssueBadge('error').color).toBe('#fca5a5');
    expect(geometryIssueBadge('').color).toBe(NEUTRAL);
  });
  it('portfolio status — full/partial/unmet known', () => {
    expect(portfolioStatusBadge('full').color).toBe('#86efac');
    expect(portfolioStatusBadge('partial').color).toBe('#fdba74');
    expect(portfolioStatusBadge('unmet').color).toBe('#fca5a5');
    expect(portfolioStatusBadge(null).color).toBe(NEUTRAL);
  });
});

describe('row/list extractors — missing ⇒ [] (honest empty, no fabrication)', () => {
  it('conflictRows/freshnessWarningRows keep server arrays, dash the missing', () => {
    expect(conflictRows({ conflicts: [{ rule_id: 'irrig_vs_rain', severity: 'block' }] })).toHaveLength(1);
    expect(conflictRows({})).toEqual([]);
    expect(conflictRows(null)).toEqual([]);
    expect(freshnessWarningRows({ freshness_warnings: [{ rule_id: 'stale_ndvi' }] })).toHaveLength(1);
    expect(freshnessWarningRows(null)).toEqual([]);
  });
  it('rotationReasons + supportedCropRows pass through / empty', () => {
    expect(rotationReasons({ reasons_ar: ['عائلتان مختلفتان'] })).toEqual(['عائلتان مختلفتان']);
    expect(rotationReasons({ supported: false })).toEqual([]);
    expect(supportedCropRows({ supported_crops: [{ crop: 'wheat', name_ar: 'القمح' }] })).toHaveLength(1);
    expect(supportedCropRows(null)).toEqual([]);
  });
  it('wofostKeyParams + wofostModelTypeRows keyed from dict', () => {
    expect(wofostKeyParams({ key_parameters: [{ param: 'RDMSOL' }] })).toHaveLength(1);
    expect(wofostKeyParams({})).toEqual([]);
    const rows = wofostModelTypeRows({
      model_types: { perennial_tree: { name_ar: 'شجرة معمّرة', change_pct: '40–60%' } },
    });
    expect(rows).toHaveLength(1);
    expect(rows[0].key).toBe('perennial_tree');
    expect(rows[0].name_ar).toBe('شجرة معمّرة');
    expect(wofostModelTypeRows(null)).toEqual([]);
  });
  it('portfolioFieldRows + geometryIssues honest empty', () => {
    expect(portfolioFieldRows({ fields: [{ field_id: 'f1', status: 'full' }] })).toHaveLength(1);
    expect(portfolioFieldRows({})).toEqual([]);
    expect(geometryIssues({ issues: [{ severity: 'error', code: 'invalid' }] })).toHaveLength(1);
    expect(geometryIssues(undefined)).toEqual([]);
  });
});

describe('unsupportedMessage — server supported=false passes its message', () => {
  it('returns message only when supported is explicitly false', () => {
    expect(unsupportedMessage({ supported: false, message_ar: 'المحصول غير معروف' })).toBe('المحصول غير معروف');
    expect(unsupportedMessage({ supported: true })).toBeNull();
    expect(unsupportedMessage(null)).toBeNull();
  });
});

describe('fact builders — server numbers as-is, missing drops (no zero-fill)', () => {
  it('irrigationRecommendationFacts drops zero/absent leaching, keeps real values', () => {
    const facts = irrigationRecommendationFacts({
      net_irrigation_mm: 8.4,
      salinity_leaching_mm: 0,
      gross_irrigation_mm: 9.9,
      irrigation_efficiency: 0.85,
      salinity_ks: 0.92,
    });
    const labels = facts.map((f) => f.label);
    expect(labels).toContain('الصافي');
    expect(labels).not.toContain('غسل الملوحة'); // صفر ⇒ يسقط (لا يُعرَض ماء بلا أساس)
    expect(labels).toContain('كفاءة الريّ');
    expect(irrigationRecommendationFacts(null)).toEqual([]);
  });
  it('portfolioSummaryFacts + geometryValidationFacts', () => {
    const p = portfolioSummaryFacts({ total_water_m3: 100, allocated_m3: 80, unallocated_m3: 20, total_expected_margin: 1234 });
    expect(p.map((f) => f.label)).toContain('الماء الكلّيّ');
    expect(portfolioSummaryFacts(undefined)).toEqual([]);
    const g = geometryValidationFacts({ computed_area_ha: 2.5, canonical_crs: 'EPSG:4326', computed_bbox: [1, 2, 3, 4] });
    expect(g.map((f) => f.label)).toEqual(['المساحة المحسوبة', 'النظام المرجعيّ', 'الإطار المحيط']);
    expect(geometryValidationFacts(null)).toEqual([]);
  });
});
