import { describe, expect, it } from 'vitest';
import { buildBudgetPayload, buildOperationPayload, buildRevenuePayload } from './ledgerEntry';

describe('buildOperationPayload — strict local validation before POST', () => {
  const base = { operationDate: '2026-07-04', operationType: 'irrigation', costAmount: '1500', costCategory: 'water', fieldId: 'f1', seasonId: 's1' };
  it('builds a valid completed operation with cost', () => {
    const r = buildOperationPayload({ ...base, notes: ' ريّ تكميليّ ' });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload).toEqual({
        operation_date: '2026-07-04', operation_type: 'irrigation', field_id: 'f1',
        season_id: 's1', cost_amount: 1500, cost_category: 'water', status: 'completed', notes: 'ريّ تكميليّ',
      });
    }
  });
  it('rejects missing/invalid pieces with Arabic reasons', () => {
    expect(buildOperationPayload({ ...base, operationDate: 'garbage' })).toMatchObject({ ok: false });
    expect(buildOperationPayload({ ...base, fieldId: null })).toMatchObject({ ok: false, error: expect.stringContaining('حقل') });
    expect(buildOperationPayload({ ...base, costAmount: '0' })).toMatchObject({ ok: false, error: expect.stringContaining('موجب') });
    expect(buildOperationPayload({ ...base, costAmount: '-5' }).ok).toBe(false);
    expect(buildOperationPayload({ ...base, costCategory: '' }).ok).toBe(false);
  });
});

describe('buildBudgetPayload', () => {
  it('wraps a single manual whole-season line', () => {
    const r = buildBudgetPayload({ seasonId: 's1', category: 'fertilizer', plannedCost: 20000 });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload.lines).toHaveLength(1);
      expect(r.payload.lines[0]).toMatchObject({ season_id: 's1', stage: 'whole_season', category: 'fertilizer', planned_cost: 20000, source: 'manual' });
    }
  });
  it('rejects without season or positive amount', () => {
    expect(buildBudgetPayload({ seasonId: null, category: 'water', plannedCost: 1 }).ok).toBe(false);
    expect(buildBudgetPayload({ seasonId: 's1', category: 'water', plannedCost: 'nan' }).ok).toBe(false);
  });
});

describe('buildRevenuePayload — optional quantity validated when present', () => {
  const base = { seasonId: 's1', fieldId: 'f1', revenueDate: '2026-07-04', amount: '90000' };
  it('builds minimal and full revenue records', () => {
    const r = buildRevenuePayload({ ...base, productName: 'قمح', quantity: '12.5', unit: 'طن' });
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(r.payload).toMatchObject({ season_id: 's1', field_id: 'f1', amount: 90000, product_name: 'قمح', quantity: 12.5, unit: 'طن', source: 'manual' });
    }
    const minimal = buildRevenuePayload(base);
    expect(minimal.ok).toBe(true);
    if (minimal.ok) expect('quantity' in minimal.payload).toBe(false); // اختياريّ يسقط لا يُصفَّر
  });
  it('rejects bad quantity instead of silently dropping it', () => {
    expect(buildRevenuePayload({ ...base, quantity: '-1' }).ok).toBe(false);
  });
  it('rejects missing season/date/amount', () => {
    expect(buildRevenuePayload({ ...base, seasonId: null }).ok).toBe(false);
    expect(buildRevenuePayload({ ...base, revenueDate: '' }).ok).toBe(false);
    expect(buildRevenuePayload({ ...base, amount: '0' }).ok).toBe(false);
  });
});
