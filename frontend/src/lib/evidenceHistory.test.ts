import { describe, it, expect } from 'vitest';
import {
  gapTrend,
  evidenceTrend,
  hasHistory,
  type EvidenceTimelineSnapshot,
} from './evidenceHistory';

function snap(over: Partial<EvidenceTimelineSnapshot>): EvidenceTimelineSnapshot {
  return {
    generated_at: '2026-01-01T00:00:00Z',
    recommendation_hash: 'h',
    confidence_score: 0.5,
    evidence_count: 3,
    gap_count: 1,
    ...over,
  };
}

describe('evidenceHistory trends', () => {
  it('gapTrend: fewer gaps than previous = improving (latest is first)', () => {
    // أحدث-أوّلاً: 1 فجوة الآن، 3 سابقاً ⇒ نقصت ⇒ تحسّن.
    expect(gapTrend([snap({ gap_count: 1 }), snap({ gap_count: 3 })])).toBe('improving');
    expect(gapTrend([snap({ gap_count: 4 }), snap({ gap_count: 2 })])).toBe('worsening');
    expect(gapTrend([snap({ gap_count: 2 }), snap({ gap_count: 2 })])).toBe('stable');
  });

  it('evidenceTrend: more evidence than previous = improving', () => {
    expect(evidenceTrend([snap({ evidence_count: 5 }), snap({ evidence_count: 2 })])).toBe('improving');
    expect(evidenceTrend([snap({ evidence_count: 1 }), snap({ evidence_count: 4 })])).toBe('worsening');
  });

  it('unknown with fewer than two snapshots or non-numeric (no fabricated trend)', () => {
    expect(gapTrend([snap({ gap_count: 1 })])).toBe('unknown');
    expect(gapTrend([])).toBe('unknown');
    expect(gapTrend(null)).toBe('unknown');
    expect(gapTrend([snap({ gap_count: null }), snap({ gap_count: 2 })])).toBe('unknown');
  });

  it('hasHistory reflects presence of snapshots honestly', () => {
    expect(hasHistory({ field_id: 'f', snapshots: [snap({})] })).toBe(true);
    expect(hasHistory({ field_id: 'f', snapshots: [] })).toBe(false);
    expect(hasHistory(null)).toBe(false);
  });
});
