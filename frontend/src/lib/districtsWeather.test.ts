import { describe, expect, it } from 'vitest';
import {
  activePestsList,
  lonLatToTile,
  tileSeriesRows,
  analysisFacts,
  answeredCount,
  buildSubmitPayload,
  districtLabel,
  districtOptions,
  geoRecommendFacts,
  isAnswered,
  isDisabled,
  missingRequiredIds,
  monthNameAr,
  monthOptions,
  operationRows,
  parseWeatherRecords,
  pestWindows,
  plantingMonths,
  plantingWindowColor,
  rangeText,
  requiredQuestionIds,
  riskMonthsText,
  serverMessage,
  severityColor,
  severityLabelAr,
  stringList,
  suitabilityColor,
  suitabilityLabelAr,
  weatherAlerts,
  type DistrictCard,
  type FieldWeatherSummaryResponse,
  type PestWindow,
  type QuestionnaireResponse,
} from './districtsWeather';

const win = (over: Partial<PestWindow> = {}): PestWindow => ({
  pest: 'aphids', pest_ar: 'المنّ', crops: ['wheat'], risk_months: [11, 12, 1],
  severity: 'medium', scouting_cue_ar: 'تجمّعات على القمم', source: 'FAO IPM', ...over,
});

describe('isDisabled — 404 «غير مُفعَّل» يُميَّز عن غيره', () => {
  it('true فقط عند disabled صريح', () => {
    expect(isDisabled({ disabled: true })).toBe(true);
    expect(isDisabled({ disabled: false })).toBe(false);
    expect(isDisabled({})).toBe(false);
    expect(isDisabled(null)).toBe(false);
  });
});

describe('serverMessage — unsupported دلاليّ فقط', () => {
  it('يمرّر message_ar عند supported=false، وإلّا null', () => {
    expect(serverMessage({ supported: false, message_ar: 'سجلّ فارغ' })).toBe('سجلّ فارغ');
    expect(serverMessage({ supported: true, message_ar: 'x' })).toBeNull();
    expect(serverMessage(null)).toBeNull();
  });
});

describe('rangeText — مجال صادق أو «—»', () => {
  it('يعرض [min,max] بوحدة، ويرفض الناقص/غير الرقميّ', () => {
    expect(rangeText([10, 20], '°م')).toBe('10–20 °م');
    expect(rangeText([5, 8])).toBe('5–8');
    expect(rangeText([1])).toBe('—');
    expect(rangeText(null)).toBe('—');
  });
});

describe('districtOptions + districtLabel', () => {
  it('يُصفّي بلا district_id ويسقط المصفوفة الغائبة', () => {
    const opts = districtOptions({
      districts: [
        { district_id: 'central_highlands', name_ar: 'المرتفعات الوسطى' },
        { district_id: '', name_ar: 'سيّئ' } as never,
      ],
    });
    expect(opts).toHaveLength(1);
    expect(opts[0].district_id).toBe('central_highlands');
    expect(districtOptions(null)).toEqual([]);
    expect(districtOptions({})).toEqual([]);
  });
  it('التسمية: الاسم ثمّ المعرّف ثمّ «—»', () => {
    expect(districtLabel({ district_id: 'x', name_ar: 'المرتفعات' })).toBe('المرتفعات');
    expect(districtLabel({ district_id: 'x' })).toBe('x');
    expect(districtLabel(null)).toBe('—');
  });
});

describe('severity — عقد الخادم معروف، الغريب محايد/كما جاء', () => {
  it('اللون للمعروف فقط، والغريب محايد', () => {
    expect(severityColor('high')).toBe('#fca5a5');
    expect(severityColor('MEDIUM')).toBe('#fdba74');
    expect(severityColor('low')).toBe('#86efac');
    expect(severityColor('weird')).toBe('#64748b');
    expect(severityColor(null)).toBe('#64748b');
  });
  it('التسمية العربيّة للمعروف، والغريب يُعرَض كما جاء', () => {
    expect(severityLabelAr('high')).toBe('عالية');
    expect(severityLabelAr('weird')).toBe('weird');
    expect(severityLabelAr(null)).toBe('—');
  });
});

describe('monthNameAr + monthOptions — حرس النطاق 1..12', () => {
  it('يسمّي الأشهر الصالحة ويرفض خارج النطاق', () => {
    expect(monthNameAr(1)).toBe('يناير');
    expect(monthNameAr(12)).toBe('ديسمبر');
    expect(monthNameAr(0)).toBe('—');
    expect(monthNameAr(13)).toBe('—');
    expect(monthNameAr(6.5)).toBe('—');
    expect(monthNameAr(null)).toBe('—');
  });
  it('اثنا عشر خياراً مرتّباً', () => {
    const opts = monthOptions();
    expect(opts).toHaveLength(12);
    expect(opts[0]).toEqual({ value: 1, label_ar: 'يناير' });
    expect(opts[11].value).toBe(12);
  });
});

describe('pestWindows + activePestsList + riskMonthsText', () => {
  it('يُرجع النوافذ أو [] صادقة', () => {
    const card: DistrictCard = { district_id: 'x', pest_windows: [win()] };
    expect(pestWindows(card)).toHaveLength(1);
    expect(pestWindows({ district_id: 'x' })).toEqual([]);
    expect(pestWindows(null)).toEqual([]);
    expect(activePestsList({ active_pests: [win(), win()] })).toHaveLength(2);
    expect(activePestsList({ active_pest_count: 0, active_pests: [] })).toEqual([]);
    expect(activePestsList(null)).toEqual([]);
  });
  it('أشهر الخطر بالعربيّة، وتُصفّي خارج النطاق', () => {
    expect(riskMonthsText(win({ risk_months: [11, 12, 1] }))).toBe('نوفمبر، ديسمبر، يناير');
    expect(riskMonthsText(win({ risk_months: [] }))).toBe('—');
    expect(riskMonthsText(win({ risk_months: [13] }))).toBe('—');
    expect(riskMonthsText(null)).toBe('—');
  });
});

describe('geoRecommendFacts + stringList', () => {
  it('يُسقِط الغائب ولا يُصفّر المجالات، unsupported ⇒ []', () => {
    const facts = geoRecommendFacts({
      supported: true, governorate_ar: 'ذمار', zone_name_ar: 'مرتفعات',
      climate_ar: 'معتدل', temp_range_c: [10, 25], annual_rain_mm: [300, 600],
    });
    const labels = facts.map((f) => f.label);
    expect(labels).toContain('المحافظة');
    expect(labels).toContain('الحرارة');
    expect(facts.find((f) => f.label === 'المطر السنويّ')?.value).toBe('300–600 مم');
    expect(labels).not.toContain('الرطوبة'); // humidity غائبة ⇒ تسقط
    expect(geoRecommendFacts({ supported: false })).toEqual([]);
    expect(geoRecommendFacts(null)).toEqual([]);
  });
  it('stringList يُصفّي الفراغ ويسقط غير المصفوفة', () => {
    expect(stringList(['قمح', '', 'شعير'])).toEqual(['قمح', 'شعير']);
    expect(stringList(null)).toEqual([]);
  });
});

describe('field-weather-summary — operationRows/suitability/alerts', () => {
  const resp: FieldWeatherSummaryResponse = {
    operations: {
      spraying: { operation: 'spraying', score: 0.9, suitability: 'optimal', limiting_factors: [] },
      irrigation: { operation: 'irrigation', score: 0.3, suitability: 'unsafe', limiting_factors: ['rain_reduces_irrigation_need'] },
    },
    alerts_ar: ['رياح مرتفعة'],
  };
  it('يحوّل خريطة العمليّات إلى صفوف، بلا خريطة ⇒ []', () => {
    expect(operationRows(resp)).toHaveLength(2);
    expect(operationRows({})).toEqual([]);
    expect(operationRows(null)).toEqual([]);
  });
  it('ألوان/تسميات الصلاحيّة بعقد الخادم', () => {
    expect(suitabilityColor('optimal')).toBe('#86efac');
    expect(suitabilityColor('unsafe')).toBe('#fca5a5');
    expect(suitabilityColor('???')).toBe('#64748b');
    expect(suitabilityLabelAr('acceptable')).toBe('مقبول');
    expect(suitabilityLabelAr('poor')).toBe('ضعيف');
  });
  it('تنبيهات الطقس كما صاغها الخادم، بلا مصفوفة ⇒ []', () => {
    expect(weatherAlerts(resp)).toEqual(['رياح مرتفعة']);
    expect(weatherAlerts({})).toEqual([]);
  });
});

describe('weather-analytics — analysisFacts + plantingMonths', () => {
  it('حقائق التحليل تُسقِط الغائب، unsupported ⇒ []', () => {
    const facts = analysisFacts({
      supported: true, days_analyzed: 365, annual_rainfall_mm: 80.4,
      annual_water_deficit_mm: 1900.2,
    });
    const labels = facts.map((f) => f.label);
    expect(labels).toContain('أيّام محلَّلة');
    expect(facts.find((f) => f.label === 'العجز المائيّ')?.value).toBe('1900.2 مم/سنة');
    expect(labels).not.toContain('ET₀ (سنويّاً)'); // غائبة ⇒ تسقط
    expect(analysisFacts({ supported: false })).toEqual([]);
  });
  it('أشهر الدليل، وألوان النوافذ بعقد الخادم', () => {
    const months = plantingMonths({
      supported: true,
      months: [{ month: 1, month_ar: 'يناير', avg_tmax_c: 24, window: 'optimal', window_ar: 'أمثل' }],
    });
    expect(months).toHaveLength(1);
    expect(plantingMonths({ supported: false })).toEqual([]);
    expect(plantingWindowColor('optimal')).toBe('#86efac');
    expect(plantingWindowColor('heat_stress')).toBe('#fca5a5');
    expect(plantingWindowColor('x')).toBe('#64748b');
  });
});

describe('parseWeatherRecords — صدق بلا تخمين', () => {
  it('فارغ ⇒ لا سجلّ ولا خطأ (حالة أوّليّة)', () => {
    expect(parseWeatherRecords('')).toEqual({ records: null, error_ar: null });
    expect(parseWeatherRecords('   ')).toEqual({ records: null, error_ar: null });
  });
  it('JSON تالف ⇒ خطأ صادق', () => {
    expect(parseWeatherRecords('{bad').error_ar).toMatch(/JSON/);
  });
  it('غير مصفوفة ⇒ خطأ', () => {
    expect(parseWeatherRecords('{"a":1}').error_ar).toMatch(/مصفوفة/);
  });
  it('مصفوفة فارغة ⇒ خطأ سجلّ فارغ', () => {
    expect(parseWeatherRecords('[]').error_ar).toMatch(/فارغ/);
  });
  it('سجلّ ينقصه الحرارة ⇒ خطأ يشير للرقم', () => {
    const r = parseWeatherRecords('[{"date":"2025-01-01","temp_max_c":30}]');
    expect(r.records).toBeNull();
    expect(r.error_ar).toMatch(/temp_max_c\/temp_min_c/);
  });
  it('سجلّ صالح ⇒ يُطبَّع مع الاختياريّات فقط عند وجودها', () => {
    const r = parseWeatherRecords(
      '[{"date":"2025-01-01","temp_max_c":"30","temp_min_c":15,"precipitation_mm":2}]',
    );
    expect(r.error_ar).toBeNull();
    expect(r.records).toEqual([
      { date: '2025-01-01', temp_max_c: 30, temp_min_c: 15, precipitation_mm: 2 },
    ]);
    expect(r.records?.[0]).not.toHaveProperty('wind_speed_kmh');
  });
});

describe('onboarding — required/answered/payload يطابق validate_response', () => {
  const q: QuestionnaireResponse = {
    sections: [
      {
        id: 'identity', title_ar: 'التعريف', phase: 1,
        questions: [
          { id: 'farmer_name', label_ar: 'الاسم', type: 'text', required: true },
          { id: 'variety', label_ar: 'الصنف', type: 'text' },
        ],
      },
      {
        id: 'agronomic', title_ar: 'المحصول', phase: 1,
        questions: [{ id: 'crop', label_ar: 'المحصول', type: 'select', required: true }],
      },
    ],
  };
  it('requiredQuestionIds عبر الأقسام', () => {
    expect(requiredQuestionIds(q)).toEqual(['farmer_name', 'crop']);
    expect(requiredQuestionIds(null)).toEqual([]);
  });
  it('isAnswered يطابق عقد الخادم (None/""/[] ⇒ false)', () => {
    expect(isAnswered('قمح')).toBe(true);
    expect(isAnswered('')).toBe(false);
    expect(isAnswered('  ')).toBe(false);
    expect(isAnswered([])).toBe(false);
    expect(isAnswered(['x'])).toBe(true);
    expect(isAnswered(null)).toBe(false);
    expect(isAnswered(0)).toBe(true);
  });
  it('missingRequiredIds معاينة عميل تطابق الخادم', () => {
    expect(missingRequiredIds(q, { farmer_name: 'علي' })).toEqual(['crop']);
    expect(missingRequiredIds(q, { farmer_name: 'علي', crop: 'قمح' })).toEqual([]);
    expect(missingRequiredIds(q, {})).toEqual(['farmer_name', 'crop']);
  });
  it('answeredCount يعدّ غير الفارغ فقط', () => {
    expect(answeredCount({ a: 'x', b: '', c: [], d: ['y'] })).toBe(2);
    expect(answeredCount(null)).toBe(0);
  });
  it('buildSubmitPayload يُسقِط الفارغ ويُطبِّع field_id إلى null', () => {
    expect(buildSubmitPayload('field-1', { crop: 'قمح', variety: '' })).toEqual({
      field_id: 'field-1', answers: { crop: 'قمح' },
    });
    expect(buildSubmitPayload('', { crop: 'قمح' })).toEqual({
      field_id: null, answers: { crop: 'قمح' },
    });
    expect(buildSubmitPayload(null, {})).toEqual({ field_id: null, answers: {} });
  });
});

describe('lonLatToTile — slippy-tile قياسيّ', () => {
  it('صنعاء (~15.35,44.2) عند z=9 تقع في بلاطة صالحة', () => {
    const t = lonLatToTile(44.2, 15.35, 9);
    expect(t.z).toBe(9);
    expect(t.x).toBeGreaterThanOrEqual(0);
    expect(t.x).toBeLessThan(2 ** 9);
    expect(t.y).toBeGreaterThanOrEqual(0);
    expect(t.y).toBeLessThan(2 ** 9);
  });
  it('يقيّد القيم القصوى ضمن نطاق البلاطات', () => {
    const t = lonLatToTile(179.9, 85, 3);
    expect(t.x).toBeLessThan(8);
    expect(t.y).toBeLessThan(8);
    expect(t.y).toBeGreaterThanOrEqual(0);
  });
});

describe('tileSeriesRows — القيمة null ⇒ «—» لا صفر', () => {
  it('يحوّل الإطارات إلى صفوف عرض', () => {
    const rows = tileSeriesRows({ frames: [
      { hour_offset: 0, time: 't0', value: 2.5 },
      { hour_offset: 3, time: 't3', value: null },
    ] });
    expect(rows).toEqual([
      { hour: 0, label: '+0س', value: '2.5' },
      { hour: 3, label: '+3س', value: '—' },
    ]);
  });
  it('غياب الإطارات ⇒ قائمة فارغة', () => {
    expect(tileSeriesRows(undefined)).toEqual([]);
    expect(tileSeriesRows({})).toEqual([]);
  });
});
