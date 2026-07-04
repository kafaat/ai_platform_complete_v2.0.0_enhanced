import { describe, expect, it } from 'vitest';
import { computeFieldEconomics, irrigationVolumeM3, estimateIrrigationCost } from './fieldEconomics';

describe('irrigationVolumeM3 / estimateIrrigationCost', () => {
  it('converts applied mm × area to m³ (1mm/ha = 10 m³)', () => {
    expect(irrigationVolumeM3(120, 10)).toBe(12000);
    expect(irrigationVolumeM3(0, 10)).toBe(0);
  });
  it('returns null without valid mm/area (no fabrication)', () => {
    expect(irrigationVolumeM3(null, 10)).toBeNull();
    expect(irrigationVolumeM3(120, 0)).toBeNull();
    expect(irrigationVolumeM3(-5, 10)).toBeNull();
  });
  it('estimates irrigation cost = real volume × user price', () => {
    expect(estimateIrrigationCost(120, 10, 0.5)).toBe(6000); // 12000 m³ × 0.5
    expect(estimateIrrigationCost(120, 10, null)).toBeNull();
    expect(estimateIrrigationCost(null, 10, 0.5)).toBeNull();
  });
});

describe('computeFieldEconomics', () => {
  it('returns nulls (no fabricated numbers) when nothing is entered', () => {
    const e = computeFieldEconomics({ areaHa: 10 });
    expect(e.hasAnyCost).toBe(false);
    expect(e.totalCost).toBe(0);
    expect(e.costPerHa).toBeNull();
    expect(e.revenue).toBeNull();
    expect(e.netProfit).toBeNull();
    expect(e.marginPct).toBeNull();
  });

  it('sums entered costs and computes cost/ha', () => {
    const e = computeFieldEconomics({ areaHa: 10, irrigationCost: 4000, laborCost: 2000, inputsCost: 4000 });
    expect(e.hasAnyCost).toBe(true);
    expect(e.totalCost).toBe(10000);
    expect(e.costPerHa).toBe(1000);
    expect(e.revenue).toBeNull(); // لا إنتاج/سعر ⇒ لا إيراد مُختلَق
    expect(e.breakdown.map((b) => b.label)).toEqual(['الريّ', 'العمالة', 'المدخلات']);
  });

  it('computes revenue, net profit and margin only with yield + price + area', () => {
    const e = computeFieldEconomics({
      areaHa: 10,
      irrigationCost: 5000,
      inputsCost: 5000,
      yieldTPerHa: 4,
      pricePerT: 500,
    });
    expect(e.revenue).toBe(20000); // 4 t/ha × 10 ha × 500
    expect(e.netProfit).toBe(10000); // 20000 − 10000
    expect(e.marginPct).toBe(50);
  });

  it('does not compute cost/ha without a positive area', () => {
    expect(computeFieldEconomics({ areaHa: 0, laborCost: 1000 }).costPerHa).toBeNull();
    expect(computeFieldEconomics({ areaHa: null, laborCost: 1000 }).costPerHa).toBeNull();
  });
});
