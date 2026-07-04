import { describe, expect, it } from 'vitest';
import {
  fmtNum,
  guideBenefits,
  irrigationProfiles,
  methodPills,
  potentialFacts,
  profileFacts,
  serverMessage,
  type HarvestPotentialResponse,
  type IrrigationMethodProfile,
} from './waterHarvesting';

// شكل نجاح حقيقيّ كما يعيده api/water_harvesting.py::harvest_potential
const realPotential: HarvestPotentialResponse = {
  supported: true,
  catchment_area_m2: 200,
  annual_rain_mm: 300,
  surface: 'roof',
  runoff_coefficient: 0.85,
  harvestable_liters: 51000,
  harvestable_m3: 51.0,
  advice_ar: 'يمكن حصاد ~51.0 م³ (51000 لتر) سنويّاً…',
  note_ar: 'تقدير إرشادي — الكميّة الفعليّة تقلّ بالتبخّر والتسرّب.',
};

// شكل ملامح حقيقيّ كما يعيده api/irrigation_method.py::method_profile («تقطير»)
const dripProfile: IrrigationMethodProfile = {
  method: 'drip',
  method_ar: 'تقطير',
  known: true,
  application_efficiency: 0.9,
  wetted_fraction: 0.4,
  ke_factor: 0.7,
  typical_max_application_mm: 8.0,
  pressurized: true,
  calibrated: false,
  warnings_ar: ['كفاءات FAO عامّة غير معايَرة لكلّ نظام/منطقة'],
};

describe('potentialFacts — real backend shape', () => {
  it('extracts harvest facts from the real success shape', () => {
    const facts = potentialFacts(realPotential);
    expect(facts.map((f) => f.label)).toEqual(['القابل للحصاد', 'باللتر', 'معامل الجريان']);
    expect(facts[0].value).toBe('51.0 م³/سنة');
    expect(facts[2].value).toBe('0.85');
  });
  it('is honestly empty for unsupported/missing, and drops absent fields instead of zeroing', () => {
    expect(potentialFacts({ supported: false, message_ar: 'أدخل مساحة ومطراً صحيحين.' })).toEqual([]);
    expect(potentialFacts(null)).toEqual([]);
    const partial = potentialFacts({ supported: true, harvestable_m3: 12.3 });
    expect(partial).toEqual([{ label: 'القابل للحصاد', value: '12.3 م³/سنة' }]);
  });
});

describe('serverMessage — verdict passthrough', () => {
  it('passes the server message_ar through untouched on unsupported, null otherwise', () => {
    expect(serverMessage({ supported: false, message_ar: 'أدخل مساحة ومطراً صحيحين.' })).toBe(
      'أدخل مساحة ومطراً صحيحين.',
    );
    expect(serverMessage(realPotential)).toBeNull();
    expect(serverMessage(null)).toBeNull();
  });
});

describe('methodPills + guideBenefits — server lists as-is', () => {
  it('returns the server methods list and [] when absent', () => {
    const pills = methodPills({
      methods: [{ method: 'terraces', name_ar: 'المدرّجات الجبليّة', what_ar: 'مصاطب…', best_for_ar: 'المرتفعات' }],
      yemen_note_ar: 'اليمن غنيّ بتراث حصاد المياه…',
    });
    expect(pills).toHaveLength(1);
    expect(pills[0].name_ar).toBe('المدرّجات الجبليّة');
    expect(methodPills(null)).toEqual([]);
    expect(methodPills({})).toEqual([]);
  });
  it('passes guide benefits through and is empty for unsupported guides', () => {
    expect(
      guideBenefits({ supported: true, benefits_ar: ['تحجز المطر', 'تمنع الانجراف'] }),
    ).toEqual(['تحجز المطر', 'تمنع الانجراف']);
    expect(guideBenefits({ supported: false, message_ar: 'لا دليل لـ«x»' })).toEqual([]);
    expect(guideBenefits(null)).toEqual([]);
  });
});

describe('profileFacts + irrigationProfiles — FAO profile passthrough', () => {
  it('renders the real drip profile facts from server numbers', () => {
    const facts = profileFacts(dripProfile);
    expect(facts).toEqual([
      { label: 'كفاءة التطبيق', value: '90٪' },
      { label: 'نسبة البلل', value: '0.40' },
      { label: 'معامل التبخّر Ke', value: '0.70' },
      { label: 'سقف الدفعة', value: '8 مم' },
      { label: 'الطاقة', value: 'مضغوط (يحتاج ضخّاً)' },
    ]);
  });
  it('drops missing profile fields instead of inventing zeros', () => {
    const facts = profileFacts({ method: 'flood', method_ar: 'غمر', known: true, pressurized: false });
    expect(facts).toEqual([{ label: 'الطاقة', value: 'جاذبيّ' }]);
    expect(profileFacts(null)).toEqual([]);
  });
  it('reads the server methods array and is [] when absent', () => {
    expect(irrigationProfiles({ methods: [dripProfile] })).toHaveLength(1);
    expect(irrigationProfiles(null)).toEqual([]);
    expect(irrigationProfiles({})).toEqual([]);
  });
});

describe('fmtNum — honest nulls', () => {
  it('renders «—» for null/undefined/NaN, formats finite numbers', () => {
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined)).toBe('—');
    expect(fmtNum(Number.NaN)).toBe('—');
    expect(fmtNum(51, 1)).toBe('51.0');
  });
});
