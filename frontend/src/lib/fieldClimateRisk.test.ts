import { describe, expect, it } from 'vitest';
import {
  analogRows,
  chillCropFit,
  chillFacts,
  hazardRows,
  sensitivityLabelAr,
  sensitivityTone,
  severityTone,
  waterCalendarFacts,
  waterStageRows,
  type ChillHoursResponse,
  type ClimateAnalogsListResponse,
  type SeasonalRiskCalendarResponse,
  type WaterCalendarResponse,
} from './fieldClimateRisk';

// ثوابت من بنية الخادم الفعليّة (crop_water_sensitivity.water_calendar("wheat"))
const wheat: WaterCalendarResponse = {
  supported: true,
  crop: 'wheat',
  crop_ar: 'القمح',
  season_total_mm: '350-600',
  season_ar: 'شتوي (يُزرع خريفاً، يُحصد أواخر الربيع)',
  drought_tolerance_ar: 'متوسّط',
  critical_window_ar: 'من الاستطالة حتى الإزهار = ~70% من الاحتياج',
  irrigation_frequency_ar: '4-6 ريّات؛ كل 12-18 يوماً في الأراضي الجافة المرويّة',
  yemen_context_ar: 'الجوف والهضاب، ريّ محوري من المياه الجوفيّة الشحيحة.',
  moderate_stress_threshold_ar: 'يبدأ الإجهاد المعتدل عند نضوب التربة فوق 70%',
  stages: [
    {
      stage_key: 'germination', name_ar: 'الإنبات', sensitivity: 'high',
      water_share_pct: 10, note_ar: 'نقص الماء قد يُفشل المحصول.', is_critical_window: true,
    },
    {
      stage_key: 'stem_elongation', name_ar: 'الاستطالة (الصعود)', sensitivity: 'critical',
      water_share_pct: 25, note_ar: '⚠ التشبّع المائي هنا كارثي.', is_critical_window: true,
    },
    {
      stage_key: 'maturity', name_ar: 'النضج', sensitivity: 'low',
      water_share_pct: 10, note_ar: 'أوقف الريّ تدريجيّاً قبل الحصاد.', is_critical_window: false,
    },
  ],
  disclaimer_ar: 'قيم إرشاديّة من مراجع عالميّة (FAO-56). تحتاج معايرة محلّيّة.',
};

describe('waterStageRows + waterCalendarFacts — استخراج البنية الفعليّة', () => {
  it('extracts real wheat calendar rows with server sensitivity passthrough', () => {
    const rows = waterStageRows(wheat);
    expect(rows.map((r) => r.key)).toEqual(['germination', 'stem_elongation', 'maturity']);
    expect(rows[1]).toMatchObject({
      name_ar: 'الاستطالة (الصعود)',
      sensitivity: 'critical',           // قيمة الخادم كما هي
      label_ar: 'حرجة',
      tone: 'critical',
      share_pct: 25,
      is_critical_window: true,
    });
    expect(rows[1].note_ar).toContain('التشبّع المائي');
    const facts = waterCalendarFacts(wheat);
    expect(facts.map((f) => f.label)).toEqual([
      'الموسم', 'الاحتياج الموسمي', 'تحمّل الجفاف', 'النافذة الحرجة', 'وتيرة الريّ',
    ]);
    expect(facts[1].value).toBe('350-600 مم');
  });

  it('is empty for unsupported crop (server message passes through, nothing fabricated)', () => {
    const unsupported: WaterCalendarResponse = {
      supported: false,
      message_ar: 'لا بيانات حساسيّة مائيّة لـ«البنّ». المدعوم: القمح، الذرة الشاميّة…',
    };
    expect(waterStageRows(unsupported)).toEqual([]);
    expect(waterCalendarFacts(unsupported)).toEqual([]);
    expect(waterStageRows(null)).toEqual([]);
    expect(waterCalendarFacts(undefined)).toEqual([]);
  });

  it('drops nameless stages and nulls unknown values instead of zero-filling', () => {
    const rows = waterStageRows({
      supported: true,
      stages: [
        { stage_key: 'x', name_ar: null, sensitivity: 'high' },              // بلا اسم ⇒ تُسقَط
        { stage_key: 'y', name_ar: 'مرحلة تجريبيّة', sensitivity: 'extreme' }, // قيمة مجهولة
      ],
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      sensitivity: 'extreme',   // تمرّ حرفيّاً — لا يُعاد الحكم
      label_ar: null,           // لا ترجمة مخترعة ⇒ «—»
      tone: 'unknown',
      share_pct: null,
      note_ar: null,
    });
    // تمرير الأحكام: القيم المعروفة فقط تُترجَم/تُلوَّن — المجهول null/unknown
    expect(sensitivityLabelAr('critical')).toBe('حرجة');
    expect(sensitivityLabelAr('SEVERE')).toBeNull();
    expect(sensitivityLabelAr(null)).toBeNull();
    expect(sensitivityTone('moderate')).toBe('moderate');
    expect(sensitivityTone('???')).toBe('unknown');
    expect(severityTone('medium')).toBe('medium');
    expect(severityTone(undefined)).toBe('unknown');
  });
});

describe('hazardRows — نوافذ المخاطر الموسميّة', () => {
  it('passes real tihama-shaped hazards through with server severity', () => {
    const resp: SeasonalRiskCalendarResponse = {
      supported: true,
      zone: 'tihama',
      zone_name_ar: 'سهل تهامة الساحلي (البحر الأحمر)',
      hazards: [
        { hazard_ar: 'موجات حرّ شديدة', season_ar: 'الصيف (يونيو-سبتمبر)', risk_to_ar: 'الإزهار وعقد الثمار', severity: 'high' },
        { hazard_ar: 'رطوبة بحريّة عالية', season_ar: 'على مدار السنة', risk_to_ar: 'أمراض فطريّة', severity: 'medium' },
      ],
      high_severity_count: 1,
      disclaimer_ar: 'تقدير إرشادي من أنماط الإقليم العامّة، لا تنبّؤ جوّي يومي.',
    };
    const rows = hazardRows(resp);
    expect(rows).toHaveLength(2);
    expect(rows[0]).toEqual({
      hazard_ar: 'موجات حرّ شديدة',
      season_ar: 'الصيف (يونيو-سبتمبر)',
      risk_to_ar: 'الإزهار وعقد الثمار',
      severity: 'high',
      tone: 'high',
    });
  });

  it('is empty for unsupported zone response', () => {
    expect(hazardRows({ supported: false, message_ar: 'لا بيانات مخاطر لإقليم «x».' })).toEqual([]);
    expect(hazardRows(null)).toEqual([]);
  });
});

describe('chillFacts + chillCropFit — ساعات البرودة بحكم الخادم', () => {
  const chill: ChillHoursResponse = {
    supported: true,
    zone: 'tihama',
    zone_name_ar: 'سهل تهامة الساحلي (البحر الأحمر)',
    estimated_chill_hours: 0,     // صفر حقيقيّ (سهول حارّة) — يُعرَض لا يُسقَط
    min_temp_c: 22,
    max_altitude_m: 300,
    crops_chill_requirement: { 'التفاح': 800, 'العنب': 100 },
    can_satisfy: { 'التفاح': false, 'العنب': false },
    verdict_ar: '⚠ لا برودة كافية — الأشجار المتساقطة المحتاجة للبرودة (تفاح) لن تزهر جيّداً.',
    disclaimer_ar: 'تقدير تقريبي من حرارة وارتفاع الإقليم.',
  };

  it('keeps a real zero and pairs requirement with server verdict only', () => {
    const facts = chillFacts(chill);
    expect(facts[0]).toEqual({ label: 'ساعات البرودة المقدّرة', value: '~0 ساعة' });
    const fit = chillCropFit(chill);
    expect(fit).toEqual([
      { crop_ar: 'التفاح', need_hours: 800, satisfied: false },
      { crop_ar: 'العنب', need_hours: 100, satisfied: false },
    ]);
  });

  it('drops crops without a server verdict and is empty when sections are missing', () => {
    const partial = { ...chill, can_satisfy: { 'العنب': true } };
    expect(chillCropFit(partial)).toEqual([{ crop_ar: 'العنب', need_hours: 100, satisfied: true }]);
    expect(chillCropFit({ supported: true })).toEqual([]);
    expect(chillCropFit({ supported: false, message_ar: 'لا إقليم «x».' })).toEqual([]);
    expect(chillFacts({ supported: true })).toEqual([]);
  });
});

describe('analogRows — ترتيب الخادم يُحفَظ والغائب null', () => {
  it('preserves server order and nulls missing similarity', () => {
    const resp: ClimateAnalogsListResponse = {
      regions: [
        {
          region_ar: 'الجوف السعوديّة', country_ar: 'السعوديّة', similarity_pct: 95,
          relevance_ar: 'الأعلى صلةً — نموذج مباشر يُحتذى للحزم',
          biggest_problem_ar: 'المياه (الاستدامة تعتمد عليها)',
          proven_crops_ar: ['الزيتون', 'النخيل (تمور)', 'القمح'],
        },
        { region_ar: 'صحراء النقب', country_ar: null, relevance_ar: null, proven_crops_ar: [] },
      ],
      count: 2,
      principle_ar: 'الاستلهام من نجاح موثّق في مناخ مطابق أصدق من التخمين.',
      disclaimer_ar: 'توجيه للتجربة المدروسة لا ضمان.',
    };
    const rows = analogRows(resp);
    expect(rows.map((r) => r.region_ar)).toEqual(['الجوف السعوديّة', 'صحراء النقب']);
    expect(rows[0].similarity_pct).toBe(95);
    expect(rows[1]).toMatchObject({ similarity_pct: null, country_ar: null, relevance_ar: null, biggest_problem_ar: null });
    expect(analogRows(resp, 1)).toHaveLength(1);
    expect(analogRows(null)).toEqual([]);
    expect(analogRows({})).toEqual([]);
  });
});
