import { describe, expect, it } from 'vitest';
import {
  betterBadge,
  buildSeasonMetrics,
  cropRiskRows,
  escalationBadge,
  feedbackDirectionBadge,
  fmtNum,
  kcCompareStages,
  kcSeriesRows,
  lineageDecisionRows,
  outcomeCount,
  parseMeasure,
  parsePctToFraction,
  pctFromFraction,
  priorityAr,
  psfFacts,
  riskTypeAr,
  rotationFacts,
  scoreOutOf100,
  seasonMetricRows,
  severityBadge,
  shortDate,
  trendArrow,
} from './agroAnalytics';

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
  it('scoreOutOf100 formats [0,100] scores, dashes the missing', () => {
    expect(scoreOutOf100(73)).toBe('73/100');
    expect(scoreOutOf100(undefined)).toBe('—');
  });
  it('shortDate slices ISO, dashes the missing/invalid', () => {
    expect(shortDate('2026-07-04T12:00:00')).toBe('2026-07-04');
    expect(shortDate(null)).toBe('—');
    expect(shortDate('bad')).toBe('—');
  });
});

describe('input parsers — فارغ/غير رقميّ ⇒ null (لا افتراض)', () => {
  it('parseMeasure', () => {
    expect(parseMeasure('12.5')).toBe(12.5);
    expect(parseMeasure('  ')).toBeNull();
    expect(parseMeasure('abc')).toBeNull();
  });
  it('parsePctToFraction converts to server fraction', () => {
    expect(parsePctToFraction('40')).toBe(0.4);
    expect(parsePctToFraction('')).toBeNull();
  });
});

describe('known-value maps — neutral fallback for unknown/missing', () => {
  it('severityBadge: known levels, neutral unknown', () => {
    expect(severityBadge('high').color).toBe('#fca5a5');
    expect(severityBadge('MODERATE').label_ar).toBe('متوسّطة');
    expect(severityBadge('weird')).toEqual({ label_ar: 'weird', color: NEUTRAL });
    expect(severityBadge(null)).toEqual({ label_ar: '—', color: NEUTRAL });
  });
  it('feedbackDirectionBadge: known directions, neutral unknown', () => {
    expect(feedbackDirectionBadge('positive').color).toBe('#86efac');
    expect(feedbackDirectionBadge('negative').label_ar).toBe('سالبة');
    expect(feedbackDirectionBadge('xyz').color).toBe(NEUTRAL);
    expect(feedbackDirectionBadge(undefined).label_ar).toBe('—');
  });
  it('escalationBadge: known levels, neutral unknown', () => {
    expect(escalationBadge('none').color).toBe('#86efac');
    expect(escalationBadge('blocked').label_ar).toBe('محجوب (تصعيد حاكم)');
    expect(escalationBadge('other').color).toBe(NEUTRAL);
    expect(escalationBadge(null).label_ar).toBe('—');
  });
  it('betterBadge: server flag only, neutral for null', () => {
    expect(betterBadge(true).label_ar).toBe('تحسّن');
    expect(betterBadge(false).color).toBe('#fca5a5');
    expect(betterBadge(null)).toEqual({ label_ar: '—', color: NEUTRAL });
  });
  it('riskTypeAr / priorityAr / trendArrow map known, passthrough/dash unknown', () => {
    expect(riskTypeAr('fungal_disease')).toBe('مرض فطريّ');
    expect(riskTypeAr('novel_risk')).toBe('novel_risk');
    expect(riskTypeAr(null)).toBe('—');
    expect(priorityAr('high')).toBe('عالية');
    expect(priorityAr(undefined)).toBe('—');
    expect(trendArrow('up')).toBe('▲');
    expect(trendArrow('flat')).toBe('▬');
    expect(trendArrow('sideways')).toBe('—');
    expect(trendArrow(null)).toBe('—');
  });
});

describe('row/fact extractors — missing arrays ⇒ [] بصدق', () => {
  it('cropRiskRows / kcSeriesRows / lineageDecisionRows guard non-arrays', () => {
    expect(cropRiskRows(null)).toEqual([]);
    expect(cropRiskRows({ risks: undefined })).toEqual([]);
    expect(cropRiskRows({ risks: [{ risk_type: 'heat_stress' }] })).toHaveLength(1);
    expect(kcSeriesRows({ series: [{ season_id: 's1' }] })).toHaveLength(1);
    expect(kcSeriesRows(undefined)).toEqual([]);
    expect(lineageDecisionRows({ decisions: [{ decision_id: 'd1' }] })).toHaveLength(1);
    expect(lineageDecisionRows(null)).toEqual([]);
  });
  it('rotationFacts drops missing fields (no zero-filling)', () => {
    const facts = rotationFacts({ rotation_score: 62, legume_ratio: 0.25 });
    const labels = facts.map((f) => f.label);
    expect(labels).toContain('درجة التناوب');
    expect(labels).toContain('نسبة البقوليّات');
    expect(labels).not.toContain('مؤشّر التنوّع'); // غائب ⇒ يسقط
    expect(rotationFacts(null)).toEqual([]);
  });
  it('psfFacts formats [0,100] scores + confidence fraction', () => {
    const facts = psfFacts({ positive_feedback_score: 70, confidence: 0.6 });
    const map = Object.fromEntries(facts.map((f) => [f.label, f.value]));
    expect(map['تغذية موجبة']).toBe('70/100');
    expect(map['الثقة']).toBe('60٪');
  });
  it('kcCompareStages orders ini/mid/end and surfaces extras', () => {
    const rows = kcCompareStages({
      stages: {
        kc_end: { current: 0.6, direction: 'down' },
        kc_ini: { current: 0.3, direction: 'up' },
        kc_mid: { current: 1.1, direction: 'flat' },
        kc_odd: { current: 0.1 },
      },
    });
    expect(rows.map((r) => r.stage)).toEqual(['kc_ini', 'kc_mid', 'kc_end', 'kc_odd']);
    expect(kcCompareStages(null)).toEqual([]);
  });
  it('seasonMetricRows labels known metrics, passes unknown key through', () => {
    const rows = seasonMetricRows({
      metrics: {
        yield_t_ha: { current: 5, previous: 4, direction: 'up', better: true },
        unknown_metric: { current: 1, previous: 1, direction: 'flat', better: null },
      },
    });
    const byKey = Object.fromEntries(rows.map((r) => [r.metric, r.label_ar]));
    expect(byKey['yield_t_ha']).toBe('الغلّة (طن/هـ)');
    expect(byKey['unknown_metric']).toBe('unknown_metric');
    expect(seasonMetricRows(undefined)).toEqual([]);
  });
  it('outcomeCount counts honestly (no guessing)', () => {
    expect(outcomeCount({ outcomes: [{}, {}] })).toBe(2);
    expect(outcomeCount({ outcomes: undefined })).toBe(0);
    expect(outcomeCount(null)).toBe(0);
  });
});

describe('buildSeasonMetrics — empty inputs stay absent (no zero-filling)', () => {
  it('includes only measured metrics, keeps identifiers', () => {
    const out = buildSeasonMetrics('2026', 'wheat', {
      yield_t_ha: '5.2',
      water_used_m3: '',
      ndvi_peak: 'abc',
    });
    expect(out.season_id).toBe('2026');
    expect(out.crop_id).toBe('wheat');
    expect(out.yield_t_ha).toBe(5.2);
    expect(out.water_used_m3).toBeUndefined(); // فارغ ⇒ غائب لا صفر
    expect(out.ndvi_peak).toBeUndefined(); // غير رقميّ ⇒ غائب
  });
});
