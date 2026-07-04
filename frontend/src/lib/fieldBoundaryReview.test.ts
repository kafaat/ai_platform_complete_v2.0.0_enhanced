import { describe, expect, it } from 'vitest';
import {
  confidencePct,
  reviewStatusLabel,
  summarizeClean,
  confidenceTone,
  summarizeNeighbors,
  topPenalties,
  type BoundaryScoreResult,
} from './fieldBoundaryReview';

describe('topPenalties — most negative deltas first, penalties only', () => {
  it('sorts by delta ascending and drops boosts/zeros', () => {
    const out = topPenalties([
      { name_ar: 'حلقات متعدّدة', delta: -0.1 },
      { name_ar: 'تعزيز زمنيّ', delta: 0.05 },
      { name_ar: 'هندسة غير صالحة', delta: -0.6 },
      { name_ar: 'بلا اتّفاق زمنيّ', delta: 0 },
      { name_ar: 'تقاطعات ذاتيّة', delta: -0.4 },
    ], 2);
    expect(out.map((f) => f.name_ar)).toEqual(['هندسة غير صالحة', 'تقاطعات ذاتيّة']);
  });
  it('returns [] for missing input', () => {
    expect(topPenalties(null)).toEqual([]);
  });
});

describe('confidenceTone — mirrors the server review verdict', () => {
  const base: BoundaryScoreResult = { confidence: 0.9, factors: [], review_recommended: false };
  it('is good only when the server did not recommend review', () => {
    expect(confidenceTone(base)).toBe('good');
    // حتّى لو بدت الثقة عالية، قرار المراجعة للخادم لا للواجهة
    expect(confidenceTone({ ...base, confidence: 0.9, review_recommended: true })).toBe('review');
  });
  it('is unknown for missing result', () => {
    expect(confidenceTone(null)).toBe('unknown');
  });
});

describe('summarizeNeighbors + confidencePct', () => {
  it('counts and slices neighbors honestly', () => {
    const s = summarizeNeighbors({
      field_id: 'f1',
      neighbors: [
        { neighbor_field_id: 'a', relation_type: 'adjacent', shared_edge_length_m: 120 },
        { neighbor_field_id: 'b', relation_type: 'adjacent', shared_edge_length_m: 45 },
      ],
    }, 1);
    expect(s.count).toBe(2);
    expect(s.top).toHaveLength(1);
    expect(summarizeNeighbors(null).count).toBe(0);
  });
  it('formats confidence or — honestly', () => {
    expect(confidencePct(0.873)).toBe('87٪');
    expect(confidencePct(null)).toBe('—');
    expect(confidencePct(Number.NaN)).toBe('—');
  });
});

describe('summarizeClean — server before/after numbers, no claimed improvement', () => {
  it('reports vertex change and validity from the server', () => {
    expect(summarizeClean({ field_id: 'f', vertex_count_before: 2400, vertex_count_after: 850, is_valid_before: false, is_valid_after: true, tolerance_m: 1 }))
      .toBe('الرؤوس 2400 ⇒ 850 · هندسة صالحة (سماحيّة 1 م)');
  });
  it('is honest when nothing changed or validity stayed broken', () => {
    expect(summarizeClean({ field_id: 'f', vertex_count_before: 100, vertex_count_after: 100, is_valid_before: true, is_valid_after: true, tolerance_m: 1 }))
      .toContain('الرؤوس ثابتة');
    expect(summarizeClean({ field_id: 'f', vertex_count_before: 100, vertex_count_after: 90, is_valid_before: false, is_valid_after: false, tolerance_m: 3 }))
      .toContain('ما زالت غير صالحة');
    expect(summarizeClean(null)).toBe('—');
  });
});

describe('reviewStatusLabel', () => {
  it('maps HIL statuses and passes unknown through', () => {
    expect(reviewStatusLabel('approved')).toBe('مُعتمَد');
    expect(reviewStatusLabel('needs_edit')).toBe('يحتاج تعديلاً');
    expect(reviewStatusLabel('odd')).toBe('odd');
    expect(reviewStatusLabel(null)).toBe('—');
  });
});
