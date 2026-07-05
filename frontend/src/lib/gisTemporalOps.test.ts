import { describe, expect, it } from 'vitest';
import {
  bufferFacts,
  coherenceFacts,
  countPositions,
  geometryLabel,
  geometrySummary,
  parseJsonObject,
  replayFacts,
  severityColor,
  splitFacts,
  stageCheckHazards,
  temporalCheckIssues,
  trialFacts,
  validateFacts,
  whatIfFacts,
} from './gisTemporalOps';

describe('parseJsonObject — honest guard, never throws', () => {
  it('empty text is a neutral (non-error) state', () => {
    expect(parseJsonObject('')).toEqual({ obj: null, error: null });
    expect(parseJsonObject('   ')).toEqual({ obj: null, error: null });
  });
  it('parses a valid object', () => {
    expect(parseJsonObject('{"type":"Polygon"}')).toEqual({ obj: { type: 'Polygon' }, error: null });
  });
  it('returns an Arabic error (not a throw) for invalid JSON', () => {
    const out = parseJsonObject('{not json');
    expect(out.obj).toBeNull();
    expect(out.error).toBe('JSON غير صالح — تحقّق من الصيغة.');
  });
  it('rejects non-object JSON (array / scalar) honestly', () => {
    expect(parseJsonObject('[1,2]').error).toBe('المُدخَل ليس كائن JSON (object).');
    expect(parseJsonObject('42').error).toBe('المُدخَل ليس كائن JSON (object).');
    expect(parseJsonObject('null').error).toBe('المُدخَل ليس كائن JSON (object).');
  });
});

describe('countPositions + geometrySummary — pure geometry counting', () => {
  it('counts positions across nesting depths', () => {
    expect(countPositions([1, 2])).toBe(1); // Point position
    expect(countPositions([[0, 0], [1, 1], [2, 2]])).toBe(3); // LineString
    expect(countPositions([[[0, 0], [1, 0], [1, 1], [0, 0]]])).toBe(4); // Polygon ring
  });
  it('summarizes a Polygon (type · vertices · single part)', () => {
    const geom = { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] };
    expect(geometrySummary(geom)).toEqual({ type: 'Polygon', vertices: 4, parts: 1 });
  });
  it('summarizes a GeometryCollection by member geometries', () => {
    const gc = {
      type: 'GeometryCollection',
      geometries: [
        { type: 'Point', coordinates: [0, 0] },
        { type: 'LineString', coordinates: [[0, 0], [1, 1]] },
      ],
    };
    expect(geometrySummary(gc)).toEqual({ type: 'GeometryCollection', vertices: 3, parts: 2 });
  });
  it('returns null for non-geometry input and «—» label', () => {
    expect(geometrySummary(null)).toBeNull();
    expect(geometrySummary({ foo: 1 })).toBeNull();
    expect(geometryLabel(null)).toBe('—');
    expect(geometryLabel({ type: 'Point', coordinates: [1, 2] })).toBe('Point · 1 رأس');
  });
});

describe('severityColor — known severities only', () => {
  it('colors known levels case-insensitively', () => {
    expect(severityColor('high')).toBe('#fdba74');
    expect(severityColor('LOW')).toBe('#86efac');
    expect(severityColor('critical')).toBe('#fca5a5');
  });
  it('is neutral for unknown/missing', () => {
    expect(severityColor('weird')).toBe('#64748b');
    expect(severityColor(null)).toBe('#64748b');
  });
});

describe('fact extractors — server values as-is, missing skipped', () => {
  it('validateFacts surfaces reason + repaired summary', () => {
    const facts = validateFacts({ is_valid: false, reason: 'Self-intersection', repaired: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } });
    expect(facts).toEqual([
      { label: 'السبب', value: 'Self-intersection' },
      { label: 'المُصلَّحة', value: 'Polygon · 4 رأس' },
    ]);
  });
  it('bufferFacts + splitFacts read server-computed distance/part_count', () => {
    expect(bufferFacts({ distance_m: 5, result: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } }))
      .toEqual([{ label: 'المسافة (م)', value: '5.0' }, { label: 'النتيجة', value: 'Polygon · 4 رأس' }]);
    expect(splitFacts({ part_count: 2, result: { type: 'GeometryCollection', geometries: [] } }))
      .toEqual([{ label: 'عدد الأجزاء', value: '2' }, { label: 'المجموعة', value: 'GeometryCollection · 0 رأس' }]);
  });
  it('temporalCheckIssues + stageCheckHazards default to empty arrays', () => {
    expect(temporalCheckIssues(undefined)).toEqual([]);
    expect(temporalCheckIssues({ valid: false, issues: [{ severity: 'high', code: 'STALE', message_ar: 'قديم' }] }))
      .toHaveLength(1);
    expect(stageCheckHazards({ supported: true })).toEqual([]);
  });
  it('coherenceFacts reads the unified temporal context', () => {
    expect(coherenceFacts({ context: { day_of_year: 120, days_since_planting: 40 } }))
      .toEqual([{ label: 'اليوم/السنة', value: '120' }, { label: 'أيّام منذ الزراعة', value: '40' }]);
  });
  it('whatIfFacts only when server says available', () => {
    expect(whatIfFacts({ available: false, note_ar: 'x' })).toEqual([]);
    const f = whatIfFacts({ available: true, baseline_yield_t_ha: 3, action_yield_t_ha: 4, water_saved_mm: 12.3 });
    expect(f).toHaveLength(3);
    expect(f[2]).toEqual({ label: 'توفير الماء (مم)', value: '12.3' });
  });
  it('replayFacts + trialFacts skip missing fields and honor disabled', () => {
    expect(replayFacts({ lifecycle_stage: 'GROWING', total_events: 7 }))
      .toEqual([{ label: 'الطور', value: 'GROWING' }, { label: 'إجماليّ الأحداث', value: '7' }]);
    expect(trialFacts({ disabled: true })).toEqual([]);
    const tf = trialFacts({ n_blocks: 4, p_value: 0.012, is_significant: true });
    expect(tf[0]).toEqual({ label: 'الكتل', value: '4' });
    expect(tf.find((x) => x.label === 'p')?.value).toBe('0.01200');
  });
});
