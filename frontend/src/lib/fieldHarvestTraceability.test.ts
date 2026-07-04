import { describe, expect, it } from 'vitest';
import {
  chainStatusLabel,
  inputLedgerFacts,
  summarizeLots,
  type HarvestLotSummary,
  type InputLedger,
} from './fieldHarvestTraceability';

const lot = (over: Partial<HarvestLotSummary> = {}): HarvestLotSummary => ({
  harvest_lot_id: 'hl1',
  field_id: 'f1',
  status: 'open',
  ...over,
});

describe('chainStatusLabel — mirrors server verdict, no re-judging', () => {
  it('labels a complete farm-to-market chain', () => {
    expect(chainStatusLabel({ event_count: 3, started_at_harvest: true, reached_market: true, complete: true }))
      .toBe('كاملة: من الحصاد إلى السوق');
  });
  it('labels partial chains honestly', () => {
    expect(chainStatusLabel({ event_count: 2, started_at_harvest: true, reached_market: false, complete: false }))
      .toContain('لم تبلغ السوق');
    expect(chainStatusLabel({ event_count: 1, started_at_harvest: false, reached_market: false, complete: false }))
      .toContain('بلا حدث حصاد');
    expect(chainStatusLabel({ event_count: 0, started_at_harvest: false, reached_market: false, complete: false }))
      .toBe('لا أحداث حيازة بعد');
    expect(chainStatusLabel(null)).toBe('—');
  });
});

describe('summarizeLots — sums only known quantities', () => {
  it('aggregates known quantities and keeps null when none known', () => {
    const s = summarizeLots([lot({ quantity_kg: 1200 }), lot({ harvest_lot_id: 'hl2', quantity_kg: null }), lot({ harvest_lot_id: 'hl3', quantity_kg: 800 })]);
    expect(s.count).toBe(3);
    expect(s.knownQuantityKg).toBe(2000);
    const none = summarizeLots([lot({ quantity_kg: null })]);
    expect(none.knownQuantityKg).toBeNull(); // لا صفر مُلفَّق
  });
  it('is honest for empty input', () => {
    expect(summarizeLots([])).toEqual({ count: 0, knownQuantityKg: null, latest: null });
    expect(summarizeLots(null).count).toBe(0);
  });
});

describe('inputLedgerFacts — declares cost coverage instead of fabricating', () => {
  const ledger: InputLedger = {
    field_id: 'f1',
    state: 'partial',
    by_input_type: {
      seed: { count: 1, cost: 5000, n_with_cost: 1 },
      fertilizer: { count: 3, cost: 12000, n_with_cost: 2 },
    },
    total_cost: 17000,
    cost_coverage: 0.75,
    cost_per_ha: 1416.7,
    cost_per_ton: null,
    harvest_yield_t_ha: null,
    area_ha: 12,
    currency: 'YER',
  };
  it('surfaces types, cost with explicit coverage, and per-ha', () => {
    const facts = inputLedgerFacts(ledger);
    const labels = facts.map((f) => f.label);
    expect(labels).toEqual(['مدخلات', 'كلفة المدخلات', 'كلفة/هـ']);
    expect(facts[0].value).toBe('بذار×1 · تسميد×3');
    expect(facts[1].value).toContain('(تغطية 75٪)');
  });
  it('returns [] for no_inputs or missing ledger', () => {
    expect(inputLedgerFacts({ ...ledger, state: 'no_inputs' })).toEqual([]);
    expect(inputLedgerFacts(null)).toEqual([]);
  });
});
