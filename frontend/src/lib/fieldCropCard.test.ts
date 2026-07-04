import { describe, expect, it } from 'vitest';
import { matchCropId, summarizeCropCard, type CropCardDoc, type CropIndexEntry } from './fieldCropCard';

const crops: CropIndexEntry[] = [
  { crop_id: 'wheat', name_ar: 'القمح', name_en: 'Wheat', varieties: ['wheat_bohooth_10'] },
  { crop_id: 'faba_bean', name_ar: 'الفول', name_en: 'Faba bean', varieties: [] },
  { crop_id: 'barley', name_ar: 'الشعير', name_en: 'Barley', varieties: [] },
];

describe('matchCropId — explicit, no guessing', () => {
  it('matches exact Arabic name with/without ال التعريف', () => {
    expect(matchCropId('القمح', crops)).toBe('wheat');
    expect(matchCropId('قمح', crops)).toBe('wheat');
  });
  it('matches English case-insensitively and crop_id', () => {
    expect(matchCropId('WHEAT', crops)).toBe('wheat');
    expect(matchCropId('faba_bean', crops)).toBe('faba_bean');
  });
  it('matches containment only when unambiguous', () => {
    expect(matchCropId('قمح بلدي', crops)).toBe('wheat');
  });
  it('returns null honestly for unknown or empty labels', () => {
    expect(matchCropId('بنّ', crops)).toBeNull();
    expect(matchCropId('', crops)).toBeNull();
    expect(matchCropId(null, crops)).toBeNull();
    expect(matchCropId('قمح', null)).toBeNull();
  });
});

describe('summarizeCropCard — real facts only', () => {
  const card: CropCardDoc = {
    crop_id: 'faba_bean',
    name_ar: 'الفول',
    kc: { initial: 0.5, mid: 1.15, end: 0.3 },
    salinity: { threshold_ece_ds_m: 1.5, slope_pct_per_ds_m: 9.6 },
    thermal: { gdd_base_c: 0, gdd_to_maturity: 1500, flowering_safe_max_c: 27 },
    governing: { ph: { min: 6.0, max: 8.5 } },
    modifying: { nitrogen_kg_ha_required: 25, phosphorus_kg_ha_required: 50, potassium_kg_ha_required: 40 },
    pest_susceptibility: { pests: ['aphids', 'rust'] },
    phenology: { total_cycle_days: 90 },
  };

  it('extracts all present facts with correct formatting', () => {
    const facts = summarizeCropCard(card);
    const labels = facts.map((f) => f.label);
    expect(labels).toEqual([
      'Kc (بدء/وسط/نهاية)',
      'دورة النموّ',
      'GDD للنضج',
      'حدّ حرارة التزهير',
      'عتبة الملوحة ECe',
      'pH',
      'N-P-K (كغ/هـ)',
      'آفات مرصودة',
    ]);
    expect(facts.find((f) => f.label === 'عتبة الملوحة ECe')!.value).toBe('1.5 dS/m (−9.6٪/وحدة)');
    expect(facts.find((f) => f.label === 'N-P-K (كغ/هـ)')!.value).toBe('25-50-40');
  });

  it('omits missing sections instead of fabricating them', () => {
    const facts = summarizeCropCard({ crop_id: 'x', kc: { initial: 0.4 } }); // kc ناقص ⇒ يسقط
    expect(facts).toEqual([]);
    expect(summarizeCropCard(null)).toEqual([]);
  });
});
