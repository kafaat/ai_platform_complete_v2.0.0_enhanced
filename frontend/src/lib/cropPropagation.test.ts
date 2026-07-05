import { describe, expect, it } from 'vitest';
import {
  comparedCrops,
  composeFacts,
  composeStressFlags,
  droughtComponentFacts,
  droughtRiskColor,
  fmtNum,
  methodGuideTypes,
  practiceBenefits,
  practicesList,
  propagationMethods,
  qualityColor,
  rankedCrops,
  rootstockStresses,
  samplingDepths,
  samplingFacts,
  samplingMethodBadge,
  seedAcceptableColor,
  seedFlags,
  serverMessage,
  suitabilityRatingColor,
} from './cropPropagation';

const NEUTRAL = '#64748b';

describe('fmtNum — صادق للغائب (لا تصفير)', () => {
  it('يُنسّق الأرقام ويعيد «—» للغائب/غير المنتهي', () => {
    expect(fmtNum(1.234, 2)).toBe('1.23');
    expect(fmtNum(0)).toBe('0');
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined)).toBe('—');
    expect(fmtNum(Infinity)).toBe('—');
  });
});

describe('serverMessage — supported=false ⇒ message_ar، غيره ⇒ null', () => {
  it('يمرّر رسالة الخادم للاستجابة غير المدعومة فقط', () => {
    expect(serverMessage({ supported: false, message_ar: 'لا دليل' })).toBe('لا دليل');
    expect(serverMessage({ supported: true, message_ar: 'x' })).toBeNull();
    expect(serverMessage(null)).toBeNull();
    expect(serverMessage({ supported: false })).toBeNull();
  });
});

describe('suitabilityRatingColor — قيم معروفة فقط، المجهول محايد', () => {
  it('يلوّن التقييمات الأربعة الحرفيّة من الخادم', () => {
    expect(suitabilityRatingColor('ممتاز')).toBe('#86efac');
    expect(suitabilityRatingColor('جيّد')).toBe('#7dd3fc');
    expect(suitabilityRatingColor('حدّي')).toBe('#fdba74');
    expect(suitabilityRatingColor('غير مناسب')).toBe('#fca5a5');
  });
  it('محايد للمجهول/الغائب', () => {
    expect(suitabilityRatingColor('غريب')).toBe(NEUTRAL);
    expect(suitabilityRatingColor(null)).toBe(NEUTRAL);
    expect(suitabilityRatingColor(undefined)).toBe(NEUTRAL);
  });
});

describe('rankedCrops — مصفوفة الخادم كما هي، الغائب ⇒ []', () => {
  it('يعيد الترتيب أو مصفوفة فارغة بصدق', () => {
    const ranked = [{ crop: 'wheat', rating_ar: 'جيّد' }];
    expect(rankedCrops({ ranked })).toEqual(ranked);
    expect(rankedCrops({})).toEqual([]);
    expect(rankedCrops(null)).toEqual([]);
  });
});

describe('composeStressFlags + composeFacts + qualityColor', () => {
  it('أعلام الإجهاد كما هي، الغائب ⇒ []', () => {
    const flags = [{ code: 'water_deficit', label_ar: 'عجز مائيّ' }];
    expect(composeStressFlags({ stress_flags: flags })).toEqual(flags);
    expect(composeStressFlags({})).toEqual([]);
    expect(composeStressFlags(null)).toEqual([]);
  });
  it('حقائق Kc تُسقِط الغائب لا تُصفّره', () => {
    expect(composeFacts({ dynamic_kc: 0.9, kc_fapar: 0.812 })).toEqual([
      { label: 'Kc الديناميكيّ', value: '0.900' },
      { label: 'Kc عبر fAPAR', value: '0.812' },
    ]);
    // kc_fapar=null يسقط (لا يُصفَّر)
    expect(composeFacts({ dynamic_kc: 0.5, kc_fapar: null })).toEqual([
      { label: 'Kc الديناميكيّ', value: '0.500' },
    ]);
    expect(composeFacts(null)).toEqual([]);
  });
  it('تلوين الجودة معروف فقط، المجهول محايد', () => {
    expect(qualityColor('high')).toBe('#86efac');
    expect(qualityColor('medium')).toBe('#fdba74');
    expect(qualityColor('low')).toBe('#fca5a5');
    expect(qualityColor('xx')).toBe(NEUTRAL);
    expect(qualityColor(null)).toBe(NEUTRAL);
  });
});

describe('propagation helpers — الغائب ⇒ []', () => {
  it('propagationMethods', () => {
    const methods = [{ method: 'cuttings', name_ar: 'العُقَل' }];
    expect(propagationMethods({ methods })).toEqual(methods);
    expect(propagationMethods({})).toEqual([]);
    expect(propagationMethods(null)).toEqual([]);
  });
  it('methodGuideTypes — supported فقط', () => {
    expect(methodGuideTypes({ supported: true, types_ar: ['a', 'b'] })).toEqual(['a', 'b']);
    expect(methodGuideTypes({ supported: false, message_ar: 'x' })).toEqual([]);
    expect(methodGuideTypes({ supported: true })).toEqual([]);
    expect(methodGuideTypes(null)).toEqual([]);
  });
  it('rootstockStresses', () => {
    const all = [{ stress: 'salinity', label_ar: 'الملوحة' }];
    expect(rootstockStresses({ all_stresses_ar: all })).toEqual(all);
    expect(rootstockStresses({})).toEqual([]);
    expect(rootstockStresses(null)).toEqual([]);
  });
});

describe('practices helpers — الغائب ⇒ []', () => {
  it('practicesList', () => {
    const practices = [{ practice: 'terracing', name_ar: 'المدرّجات' }];
    expect(practicesList({ practices })).toEqual(practices);
    expect(practicesList({})).toEqual([]);
    expect(practicesList(null)).toEqual([]);
  });
  it('practiceBenefits — supported فقط', () => {
    expect(practiceBenefits({ supported: true, benefits_ar: ['x'] })).toEqual(['x']);
    expect(practiceBenefits({ supported: false })).toEqual([]);
    expect(practiceBenefits(null)).toEqual([]);
  });
});

describe('droughtRiskColor — قيم معروفة، المجهول محايد', () => {
  it('يلوّن مستويات التحمّل الحرفيّة', () => {
    expect(droughtRiskColor('تحمّل عالٍ')).toBe('#86efac');
    expect(droughtRiskColor('تحمّل متوسّط')).toBe('#7dd3fc');
    expect(droughtRiskColor('تحمّل محدود')).toBe('#fdba74');
    expect(droughtRiskColor('حسّاس للجفاف')).toBe('#fca5a5');
  });
  it('محايد للمجهول/الغائب', () => {
    expect(droughtRiskColor('؟')).toBe(NEUTRAL);
    expect(droughtRiskColor(null)).toBe(NEUTRAL);
  });
});

describe('droughtComponentFacts — الغائب/null يسقط', () => {
  it('يبني الحقائق المتوفّرة فقط', () => {
    expect(
      droughtComponentFacts({
        components: { root_depth_m: 1.5, threshold_ece: 8, flowering_safe_max_c: 30, heat_headroom_c: -2 },
      }),
    ).toEqual([
      { label: 'عمق الجذور', value: '1.5 م' },
      { label: 'عتبة الملوحة ECe', value: '8.0' },
      { label: 'حدّ حرارة الإزهار', value: '30°م' },
      { label: 'هامش الحرارة', value: '-2.0°م' },
    ]);
    // null يسقط (heat_headroom غائب حين لا حرارة متوقّعة)
    expect(droughtComponentFacts({ components: { root_depth_m: 1.2, heat_headroom_c: null } })).toEqual([
      { label: 'عمق الجذور', value: '1.2 م' },
    ]);
    expect(droughtComponentFacts({})).toEqual([]);
    expect(droughtComponentFacts(null)).toEqual([]);
  });
});

describe('comparedCrops — الغائب ⇒ []', () => {
  it('يعيد الترتيب بالصمود', () => {
    const ranked = [{ crop_id: 'sorghum', resilience_score: 0.8 }];
    expect(comparedCrops({ ranked_by_resilience: ranked })).toEqual(ranked);
    expect(comparedCrops({})).toEqual([]);
    expect(comparedCrops(null)).toEqual([]);
  });
});

describe('seed helpers — حكم الخادم كما هو', () => {
  it('seedAcceptableColor منطقيّ لا يُعاد حكمه', () => {
    expect(seedAcceptableColor(true)).toBe('#86efac');
    expect(seedAcceptableColor(false)).toBe('#fca5a5');
    expect(seedAcceptableColor(null)).toBe(NEUTRAL);
    expect(seedAcceptableColor(undefined)).toBe(NEUTRAL);
  });
  it('seedFlags تمرّ حرفيّاً، الغائب ⇒ []', () => {
    expect(seedFlags({ flags_ar: ['✓ معتمد', '⚠ نقاوة منخفضة'] })).toEqual(['✓ معتمد', '⚠ نقاوة منخفضة']);
    expect(seedFlags({})).toEqual([]);
    expect(seedFlags(null)).toEqual([]);
  });
});

describe('sampling helpers', () => {
  it('samplingMethodBadge — معروف مُسمّى، المجهول محايد بمفتاحه', () => {
    expect(samplingMethodBadge('zone')).toEqual({ label_ar: 'مناطق إدارة (zone)', color: '#86efac' });
    expect(samplingMethodBadge('grid')).toEqual({ label_ar: 'شبكة (grid)', color: '#fdba74' });
    expect(samplingMethodBadge('grid_coarse')).toEqual({ label_ar: 'شبكة خشنة', color: '#7dd3fc' });
    expect(samplingMethodBadge('weird')).toEqual({ label_ar: 'weird', color: NEUTRAL });
    expect(samplingMethodBadge(null)).toEqual({ label_ar: '—', color: NEUTRAL });
  });
  it('samplingFacts — الغائب/null يسقط', () => {
    expect(
      samplingFacts({ recommended_zones: 4, recommended_samples: 4, cores_per_composite: 8 }),
    ).toEqual([
      { label: 'المناطق', value: '4' },
      { label: 'العيّنات المخبريّة', value: '4' },
      { label: 'cores لكلّ عيّنة', value: '8' },
    ]);
    // grid: recommended_zones=null يسقط
    expect(samplingFacts({ recommended_zones: null, recommended_samples: 12, cores_per_composite: 1 })).toEqual([
      { label: 'العيّنات المخبريّة', value: '12' },
      { label: 'cores لكلّ عيّنة', value: '1' },
    ]);
    expect(samplingFacts(null)).toEqual([]);
  });
  it('samplingDepths — بلا مصفوفة ⇒ []', () => {
    expect(samplingDepths({ depth_advice: { depths_cm: ['0-30 سم', '30-60 سم'] } })).toEqual(['0-30 سم', '30-60 سم']);
    expect(samplingDepths({ depth_advice: {} })).toEqual([]);
    expect(samplingDepths({})).toEqual([]);
    expect(samplingDepths(null)).toEqual([]);
  });
});
