import { describe, expect, it } from 'vitest';
import {
  formatMoney,
  formatPercent,
  rankCostBreakdown,
  summarizeProfitability,
  topVariances,
  type ProfitabilityResponse,
  type VarianceLine,
} from './fieldProfitability';

describe('summarizeProfitability — honest states', () => {
  it('reports feature-disabled honestly (no fabricated zero)', () => {
    const v = summarizeProfitability({ season_id: 's1', profitability: null, disabled: true });
    expect(v.available).toBe(false);
    expect(v.reason).toContain('غير مفعّل');
    expect(v.revenue).toBeNull();
    expect(v.grossMargin).toBeNull();
    expect(v.profitable).toBeNull();
  });

  it('reports empty ledger with the server note, not a zero profit', () => {
    const v = summarizeProfitability({ season_id: 's1', profitability: null, note_ar: 'القاعدة غير مفعلة' });
    expect(v.available).toBe(false);
    expect(v.reason).toBe('القاعدة غير مفعلة');
    expect(v.totalCost).toBeNull();
  });

  it('surfaces real numbers and flags a profitable season', () => {
    const resp: ProfitabilityResponse = {
      season_id: 's1',
      profitability: {
        season_id: 's1',
        revenue: 100000,
        total_cost: 60000,
        gross_margin: 40000,
        margin_percent: 40,
        yield_quantity: 12.5,
        unit: 't',
        cost_per_unit: 4800,
        revenue_per_unit: 8000,
        currency: 'YER',
      },
    };
    const v = summarizeProfitability(resp);
    expect(v.available).toBe(true);
    expect(v.grossMargin).toBe(40000);
    expect(v.marginPercent).toBe(40);
    expect(v.profitable).toBe(true);
  });

  it('flags a loss-making season (negative margin)', () => {
    const v = summarizeProfitability({
      season_id: 's1',
      profitability: {
        season_id: 's1', revenue: 20000, total_cost: 50000, gross_margin: -30000,
        margin_percent: -150, yield_quantity: null, unit: null, cost_per_unit: null,
        revenue_per_unit: null, currency: 'YER',
      },
    });
    expect(v.profitable).toBe(false);
    expect(v.grossMargin).toBe(-30000);
    // الغلّة غير معروفة ⇒ تبقى null لا صفر
    expect(v.costPerUnit).toBeNull();
  });

  it('is honest for null/undefined input', () => {
    expect(summarizeProfitability(null).available).toBe(false);
    expect(summarizeProfitability(undefined).revenue).toBeNull();
  });
});

describe('rankCostBreakdown', () => {
  it('sorts categories by amount desc and drops zero/negative', () => {
    const slices = rankCostBreakdown({ labor: 3000, water: 500, seed: 0, overhead: -10, fertilizer: 1200 });
    expect(slices.map((s) => s.category)).toEqual(['labor', 'fertilizer', 'water']);
    expect(slices[0].amount).toBe(3000);
  });
  it('returns [] for missing breakdown', () => {
    expect(rankCostBreakdown(null)).toEqual([]);
    expect(rankCostBreakdown(undefined)).toEqual([]);
  });
});

describe('topVariances', () => {
  it('ranks by absolute variance amount (biggest impact first)', () => {
    const lines: VarianceLine[] = [
      { season_id: 's', category: 'water', stage: 'x', planned_cost: 100, actual_cost: 120, variance_amount: 20, variance_percent: 20, severity: 'info', explanation: '' },
      { season_id: 's', category: 'labor', stage: 'x', planned_cost: 100, actual_cost: 40, variance_amount: -60, variance_percent: -60, severity: 'warn', explanation: '' },
      { season_id: 's', category: 'seed', stage: 'x', planned_cost: 100, actual_cost: 105, variance_amount: 5, variance_percent: 5, severity: 'info', explanation: '' },
    ];
    expect(topVariances(lines, 2).map((v) => v.category)).toEqual(['labor', 'water']);
  });
  it('returns [] for non-array', () => {
    expect(topVariances(null)).toEqual([]);
  });
});

describe('formatters — never fabricate a zero for missing data', () => {
  it('formatMoney renders — for null and a localized number otherwise', () => {
    expect(formatMoney(null)).toBe('—');
    expect(formatMoney(undefined, 'YER')).toBe('—');
    expect(formatMoney(1234567, 'YER')).toBe('1,234,567 YER');
    expect(formatMoney(0, 'YER')).toBe('0 YER'); // صفر حقيقيّ يُعرَض، null لا
  });
  it('formatPercent renders — for null and one decimal otherwise', () => {
    expect(formatPercent(null)).toBe('—');
    expect(formatPercent(42.37)).toBe('42.4٪');
  });
});
