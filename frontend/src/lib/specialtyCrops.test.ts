import { describe, expect, it } from 'vitest';
import {
  aromaticEntries,
  calendarStars,
  cropEntries,
  culturalNotes,
  economicsStages,
  fieldFitFacts,
  fodderEntries,
  highValueTiers,
  introductionRequirementRows,
  nicheEntries,
  orchardBlocks,
  orchardTimeline,
  ratingColor,
  regionalEntries,
  riskColorAr,
  serverUnsupportedMessage,
  textOrDash,
  usdRange,
} from './specialtyCrops';

describe('textOrDash + usdRange — honest formatting, no fabrication', () => {
  it('dashes null/empty/whitespace text', () => {
    expect(textOrDash('مورينجا')).toBe('مورينجا');
    expect(textOrDash('')).toBe('—');
    expect(textOrDash('   ')).toBe('—');
    expect(textOrDash(null)).toBe('—');
    expect(textOrDash(undefined)).toBe('—');
  });
  it('formats [lo,hi] ranges as-is, dashes malformed', () => {
    expect(usdRange([4000, 8000])).toBe('4000–8000 $');
    expect(usdRange([0, 500])).toBe('0–500 $');
    expect(usdRange([100])).toBe('—');
    expect(usdRange(null)).toBe('—');
    expect(usdRange(['a', 'b'] as any)).toBe('—');
  });
});

describe('ratingColor + riskColorAr — known Arabic verdicts only, unknown neutral', () => {
  it('colors the four suitability ratings', () => {
    expect(ratingColor('ممتاز')).toBe('#4ade80');
    expect(ratingColor('جيّد')).toBe('#86efac');
    expect(ratingColor('حدّي')).toBe('#fdba74');
    expect(ratingColor('غير مناسب')).toBe('#fca5a5');
  });
  it('colors the three orchard risk levels', () => {
    expect(riskColorAr('منخفضة')).toBe('#86efac');
    expect(riskColorAr('متوسّطة')).toBe('#fdba74');
    expect(riskColorAr('عالية')).toBe('#fca5a5');
  });
  it('is neutral #64748b for unknown/missing', () => {
    expect(ratingColor('weird')).toBe('#64748b');
    expect(ratingColor(null)).toBe('#64748b');
    expect(riskColorAr(undefined)).toBe('#64748b');
    expect(riskColorAr('')).toBe('#64748b');
  });
});

describe('cropEntries — server map → rows, string values become reason_ar', () => {
  const labels: [string, string][] = [
    ['type_ar', 'النوع'],
    ['water_ar', 'الماء'],
  ];
  it('maps object values to labelled rows and lifts caution_ar out', () => {
    const out = cropEntries(
      { 'الجوجوبا': { type_ar: 'شجيرة', water_ar: 'منخفض', caution_ar: 'بطيء النموّ' } },
      labels,
    );
    expect(out).toHaveLength(1);
    expect(out[0].name).toBe('الجوجوبا');
    expect(out[0].rows).toEqual([
      { key: 'type_ar', label: 'النوع', value: 'شجيرة' },
      { key: 'water_ar', label: 'الماء', value: 'منخفض' },
    ]);
    expect(out[0].caution_ar).toBe('بطيء النموّ');
    expect(out[0].reason_ar).toBeNull();
  });
  it('treats string values as reason_ar (not_suited tier)', () => {
    const out = cropEntries({ 'الكاجو': 'استوائي يحتاج رطوبة' }, labels);
    expect(out[0].reason_ar).toBe('استوائي يحتاج رطوبة');
    expect(out[0].rows).toEqual([]);
    expect(out[0].caution_ar).toBeNull();
  });
  it('drops absent fields (no zero-filling) and empty caution', () => {
    const out = cropEntries({ 'x': { type_ar: 'ت', caution_ar: '  ' } }, labels);
    expect(out[0].rows).toEqual([{ key: 'type_ar', label: 'النوع', value: 'ت' }]);
    expect(out[0].caution_ar).toBeNull();
  });
  it('is empty for missing/non-object map', () => {
    expect(cropEntries(null, labels)).toEqual([]);
    expect(cropEntries(undefined, labels)).toEqual([]);
  });
});

describe('highValueTiers — three honesty tiers in order, absent tier drops', () => {
  it('orders proven → conditional → not_suited and normalizes each', () => {
    const tiers = highValueTiers({
      proven_desert_ar: { intro_ar: 'مثبتة:', crops: { 'الجوجوبا': { type_ar: 'شجيرة' } } },
      not_suited_ar: { intro_ar: 'غير مناسبة:', crops: { 'الكاجو': 'استوائي رطب' } },
    });
    expect(tiers.map((t) => t.key)).toEqual(['proven', 'not_suited']);
    expect(tiers[0].intro_ar).toBe('مثبتة:');
    expect(tiers[0].entries[0].name).toBe('الجوجوبا');
    expect(tiers[1].entries[0].reason_ar).toBe('استوائي رطب');
  });
  it('is empty for missing response', () => {
    expect(highValueTiers(null)).toEqual([]);
  });
});

describe('niche/aromatic/fodder entries — read server map, empty when absent', () => {
  it('extracts niche crops with niche labels', () => {
    const out = nicheEntries({ crops: { 'الصمغ العربي': { category_ar: 'صمغ صناعي', market_ar: 'مليار$' } } });
    expect(out[0].rows).toEqual([
      { key: 'category_ar', label: 'الفئة', value: 'صمغ صناعي' },
      { key: 'market_ar', label: 'السوق', value: 'مليار$' },
    ]);
  });
  it('extracts aromatic + fodder crops', () => {
    expect(aromaticEntries({ crops: { 'اللافندر': { product_ar: 'زيت' } } })[0].rows[0].value).toBe('زيت');
    expect(fodderEntries({ crops: { 'السورغم': { advantage_ar: 'متحمّل' } } })[0].rows[0].label).toBe('الميزة');
  });
  it('is empty for missing crops map', () => {
    expect(nicheEntries({})).toEqual([]);
    expect(aromaticEntries(null)).toEqual([]);
    expect(fodderEntries(undefined)).toEqual([]);
  });
});

describe('introductionRequirementRows + fieldFitFacts — supported/scored gating', () => {
  it('reads requirements only when supported', () => {
    const rows = introductionRequirementRows({
      supported: true,
      requirements_ar: { climate: 'حارّ', water: 'متوسّط', soil: 'خصبة' },
    });
    expect(rows.map((r) => r.value)).toEqual(['حارّ', 'متوسّط', 'خصبة']);
    expect(introductionRequirementRows({ supported: false, message_ar: 'لا بطاقة' })).toEqual([]);
  });
  it('facts only when scored=true; score→٪, rating passed through', () => {
    const facts = fieldFitFacts({ supported: true, scored: true, score: 0.723, rating_ar: 'جيّد' });
    expect(facts).toEqual([
      { label: 'الدرجة', value: '72٪' },
      { label: 'التقييم', value: 'جيّد' },
    ]);
    expect(fieldFitFacts({ supported: true, scored: false, message_ar: 'بلا نطاقات' })).toEqual([]);
    expect(fieldFitFacts(null)).toEqual([]);
  });
});

describe('orchard + timing extractors — supported/matched gating, arrays honest', () => {
  it('blocks/timeline/stages require supported=true and an array', () => {
    expect(orchardBlocks({ supported: true, blocks: [{ crop_ar: 'اللوز' }] })).toHaveLength(1);
    expect(orchardBlocks({ supported: false, message_ar: 'أدخل مساحة موجبة' })).toEqual([]);
    expect(orchardTimeline({ supported: true, cash_flow_timeline_ar: [{ year: 4 }] })).toHaveLength(1);
    expect(economicsStages({ supported: true, annual_income_stages_ar: [{ years: '1-3' }] })).toHaveLength(1);
    expect(economicsStages({ supported: true })).toEqual([]);
  });
  it('stars/notes read arrays; regional entries need matched=true', () => {
    expect(calendarStars({ stars: [{ name_ar: 'سهيل' }] })).toHaveLength(1);
    expect(culturalNotes({ notes: [{ name_ar: 'سهيل' }] })).toHaveLength(1);
    expect(regionalEntries({ matched: true, entries: [{ period_name_ar: 'الصرفة' }] })).toHaveLength(1);
    expect(regionalEntries({ matched: false, message_ar: 'لا تقويم', available: ['himyarite'] })).toEqual([]);
  });
});

describe('serverUnsupportedMessage — passes message only when supported===false', () => {
  it('returns message on unsupported, null otherwise', () => {
    expect(serverUnsupportedMessage({ supported: false, message_ar: 'لا بطاقة لـ«س»' })).toBe('لا بطاقة لـ«س»');
    expect(serverUnsupportedMessage({ supported: true })).toBeNull();
    expect(serverUnsupportedMessage(null)).toBeNull();
    expect(serverUnsupportedMessage({ supported: false })).toBeNull();
  });
});
