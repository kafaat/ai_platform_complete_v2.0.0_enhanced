import { describe, expect, it } from 'vitest';
import { buildComparePresets } from './layerComparePresets';

describe('buildComparePresets', () => {
  it('returns only presets whose both layers exist in the catalog', () => {
    const presets = buildComparePresets(['truecolor', 'ndvi', 'ndmi', 'ndwi', 'salinity', 'msi']);
    const ids = presets.map((p) => p.id);
    expect(ids).toContain('cover-moisture');
    expect(ids).toContain('cover-salinity');
    expect(ids).toContain('moisture-water');
    expect(ids).toContain('cover-stress');
    expect(ids).toContain('image-cover');
    // كلّ مقارنة تحمل تفسيراً وطبقتين
    presets.forEach((p) => {
      expect(p.why.length).toBeGreaterThan(0);
      expect(p.left).not.toEqual(p.right);
    });
  });

  it('drops presets when a required layer is missing', () => {
    const presets = buildComparePresets(['ndvi', 'ndmi']); // لا salinity/ndwi/msi/truecolor
    expect(presets.map((p) => p.id)).toEqual(['cover-moisture']);
  });

  it('returns nothing when the catalog is empty', () => {
    expect(buildComparePresets([])).toEqual([]);
  });
});
