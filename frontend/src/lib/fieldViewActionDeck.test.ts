import { describe, expect, it } from 'vitest';
import { buildFieldViewActionDeck, summarizeImageryFreshness } from './fieldViewActionDeck';

describe('fieldViewActionDeck', () => {
  it('flags missing imagery as a backfill action', () => {
    const cards = buildFieldViewActionDeck({ fieldId: 'f1', fieldName: 'الشمال', imageryDates: [] }, Date.parse('2026-07-04T00:00:00Z'));
    expect(cards[0].id).toBe('imagery-backfill');
    expect(cards[0].tone).toBe('warn');
  });

  it('summarizes ready low-cloud imagery', () => {
    const summary = summarizeImageryFreshness([
      { date: '2026-07-01', has_cog: true, cloud_pct: 12 },
      { date: '2026-06-20', has_cog: false, cloud_pct: 50 },
    ], Date.parse('2026-07-04T00:00:00Z'));
    expect(summary.readyCount).toBe(1);
    expect(summary.pendingCount).toBe(1);
    expect(summary.lowCloudCount).toBe(1);
    expect(summary.newestAgeDays).toBe(3);
  });

  it('adds governance card when decision sources are incomplete', () => {
    const cards = buildFieldViewActionDeck({ fieldId: 'f1', imageryDates: [], weatherReady: false });
    expect(cards.some((card) => card.id === 'fieldview-source-governance')).toBe(true);
  });

  it('adds context reconciliation card for stale route or stored field', () => {
    const cards = buildFieldViewActionDeck({
      fieldId: 'f2', fieldName: 'بديل', routeFieldIsInvalid: true, storedFieldIsInvalid: true, imageryDates: [],
    });
    expect(cards[0].id).toBe('field-context-reconciled');
  });
});
