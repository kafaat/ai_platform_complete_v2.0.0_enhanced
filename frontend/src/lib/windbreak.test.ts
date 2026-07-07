// تحقّق V73-UI — مساعِدات عرض الرياح السائدة/المصدّ (منطق نقيّ، بلا React).
// صدق: المحسوب بقيمته، المتعذّر بسببه؛ بلا ارتفاع لا رقم متر مُختلَق.

import { describe, it, expect } from 'vitest';
import {
  protectionSummaryAr,
  topRoseSectors,
  windMissingReasonAr,
  type WindbreakRec,
} from './windbreak';

describe('windbreak helpers', () => {
  it('topRoseSectors ranks sectors descending and limits', () => {
    const rose = { NW: 40, N: 12, W: 25, NE: 3 };
    const top = topRoseSectors(rose, 2);
    expect(top).toEqual([
      { key: 'NW', count: 40 },
      { key: 'W', count: 25 },
    ]);
    expect(topRoseSectors(undefined)).toEqual([]);
  });

  it('windMissingReasonAr surfaces source failure and passes unknown through', () => {
    expect(windMissingReasonAr('nasa_power_wind_unavailable')).toContain('NASA POWER');
    expect(windMissingReasonAr('insufficient_observations')).toContain('غير كافٍ');
    expect(windMissingReasonAr('some_future')).toBe('some_future');
    expect(windMissingReasonAr(undefined)).toBe('غير متاح');
  });

  it('protectionSummaryAr shows metres only when tree height known (no fabrication)', () => {
    expect(protectionSummaryAr({ protected_downwind_m: 40 } as WindbreakRec)).toContain('40م');
    // بلا ارتفاع ⇒ يطلب الارتفاع لا يخترع رقماً.
    expect(protectionSummaryAr({ protection_basis: 'needs_tree_height' } as WindbreakRec)).toContain(
      'ارتفاع',
    );
    expect(protectionSummaryAr(undefined)).toBe('—');
  });
});
