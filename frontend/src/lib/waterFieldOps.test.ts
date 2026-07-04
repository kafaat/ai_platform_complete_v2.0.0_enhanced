import { describe, expect, it } from 'vitest';
import {
  alertRows,
  alertSeverityColor,
  build4rInput,
  buildIntegratedInput,
  buildOutcomeRecordInput,
  buildStressInput,
  buildWaterBalanceInput,
  buildWaterSamplePayload,
  classificationRows,
  floodParagraphs,
  fmtNum,
  fmtRange,
  geoFacts,
  httpStatusOf,
  layerCaption,
  layerRows,
  listOrText,
  nutrientNameAr,
  nutrientStatusBadge,
  outcomeMetricRows,
  outcomeSuccessLabel,
  parseMeasure,
  planRows,
  sensitivityColor,
  stagesForCrop,
  stressLevelColor,
  unsupportedMessage,
  waterBalanceFacts,
  waterIndicesFacts,
  writeErrorMessage,
  type OutcomeRecordFormText,
  type Soil4RFormText,
  type WaterBalanceFormText,
  type WaterSampleFormText,
} from './waterFieldOps';

const wbForm = (over: Partial<WaterBalanceFormText> = {}): WaterBalanceFormText => ({
  crop: 'wheat', stage: 'mid', tMin: '12', tMax: '28', rainMm: '', latitude: '', elevation: '',
  dayOfYear: '', soilEce: '', waterEcw: '', analysisAgeDays: '', analysisConfidencePct: '', ...over,
});

const sampleForm = (over: Partial<WaterSampleFormText> = {}): WaterSampleFormText => ({
  sampleId: 'w-1', source: 'well', na: '', ca: '', mg: '', hco3: '', co3: '', cl: '',
  ecDsm: '', ph: '', sampledAt: '', ...over,
});

const outcomeForm = (over: Partial<OutcomeRecordFormText> = {}): OutcomeRecordFormText => ({
  decisionId: '', recommendedIrrigationMm: '', predictedStressDays: '', expectedYieldTHa: '',
  seasonBudgetMm: '', actualIrrigationMm: '', observedStressDays: '', actualYieldTHa: '',
  actualWaterUsedMm: '', idempotencyKey: '', ...over,
});

describe('parseMeasure + fmtNum + fmtRange + listOrText — لا تصفير ولا تلفيق', () => {
  it('empty/non-numeric input is null (no guessed measurement)', () => {
    expect(parseMeasure('')).toBeNull();
    expect(parseMeasure('  ')).toBeNull();
    expect(parseMeasure('abc')).toBeNull();
    expect(parseMeasure('12.5')).toBe(12.5);
    expect(parseMeasure('0')).toBe(0);
  });
  it('missing numbers render as dash, never zero', () => {
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(undefined, 2)).toBe('—');
    expect(fmtNum(3.456, 1)).toBe('3.5');
  });
  it('range renders server pair as-is, incomplete is dash', () => {
    expect(fmtRange([15, 25], '°م')).toBe('15–25°م');
    expect(fmtRange(null)).toBe('—');
    expect(fmtRange([15])).toBe('—');
  });
  it('listOrText joins arrays, passes strings, null for empty', () => {
    expect(listOrText(['قمح', 'شعير'])).toBe('قمح، شعير');
    expect(listOrText('نصّ')).toBe('نصّ');
    expect(listOrText([])).toBeNull();
    expect(listOrText(null)).toBeNull();
  });
});

describe('unsupportedMessage — رسالة الخادم تمرّ كما جاءت', () => {
  it('returns message only when supported=false', () => {
    expect(unsupportedMessage({ supported: false, message_ar: 'غير مدعوم' })).toBe('غير مدعوم');
    expect(unsupportedMessage({ supported: true, message_ar: 'x' })).toBeNull();
    expect(unsupportedMessage(null)).toBeNull();
  });
});

describe('buildStressInput + buildIntegratedInput — لا استدعاء بلا مدخلات كاملة', () => {
  it('needs crop, stage and depletion', () => {
    expect(buildStressInput('wheat', 'flowering', '75')).toEqual({
      crop: 'wheat', stage_key: 'flowering', depletion_pct: 75,
    });
    expect(buildStressInput('', 'flowering', '75')).toBeNull();
    expect(buildStressInput('wheat', '', '75')).toBeNull();
    expect(buildStressInput('wheat', 'flowering', '')).toBeNull();
  });
  it('integrated advice additionally requires net irrigation mm', () => {
    expect(buildIntegratedInput('wheat', 'flowering', '75', '42')).toEqual({
      crop: 'wheat', stage_key: 'flowering', depletion_pct: 75, net_irrigation_mm: 42,
    });
    expect(buildIntegratedInput('wheat', 'flowering', '75', '')).toBeNull();
    expect(buildIntegratedInput('wheat', 'flowering', '', '42')).toBeNull();
  });
});

describe('stagesForCrop — مفاتيح عقد الخادم فقط، المجهول []', () => {
  it('returns backend stage keys per crop', () => {
    expect(stagesForCrop('wheat').map((s) => s.key)).toContain('stem_elongation');
    expect(stagesForCrop('sorghum').map((s) => s.key)).toContain('booting_flowering');
  });
  it('unknown/missing crop yields empty list (server declares unsupported itself)', () => {
    expect(stagesForCrop('mango')).toEqual([]);
    expect(stagesForCrop(null)).toEqual([]);
  });
});

describe('buildWaterBalanceInput — الإلزاميّ حرارتان ومحصول؛ الاختياريّ عند إدخاله فقط', () => {
  it('requires crop and both temperatures', () => {
    expect(buildWaterBalanceInput(wbForm({ tMin: '' }))).toBeNull();
    expect(buildWaterBalanceInput(wbForm({ tMax: '' }))).toBeNull();
    expect(buildWaterBalanceInput(wbForm({ crop: '  ' }))).toBeNull();
  });
  it('omits untouched optional fields so server defaults stay in charge', () => {
    const input = buildWaterBalanceInput(wbForm());
    expect(input).toEqual({ crop: 'wheat', stage: 'mid', t_min_c: 12, t_max_c: 28 });
    expect(input).not.toHaveProperty('rain_mm');
    expect(input).not.toHaveProperty('soil_ece');
  });
  it('sends salinity analysis only when provided, confidence as 0-1 fraction', () => {
    const input = buildWaterBalanceInput(
      wbForm({ soilEce: '3.1', analysisAgeDays: '90', analysisConfidencePct: '85' }),
    );
    expect(input?.soil_ece).toBe(3.1);
    expect(input?.analysis_age_days).toBe(90);
    expect(input?.analysis_confidence).toBeCloseTo(0.85);
    expect(input).not.toHaveProperty('water_ecw');
  });
});

describe('waterBalanceFacts — أرقام الخادم كما هي، الغائب يسقط', () => {
  it('maps only present fields', () => {
    const facts = waterBalanceFacts({ et0_mm: 5.12, net_irrigation_mm: 31.4 });
    expect(facts.map((f) => f.label)).toEqual(['ET₀', 'الصافي المطلوب']);
    expect(facts[0].value).toBe('5.12 مم/يوم');
  });
  it('empty for missing response', () => {
    expect(waterBalanceFacts(null)).toEqual([]);
  });
});

describe('floodParagraphs — نصوص الخادم بترتيبها، caution منفصل', () => {
  it('keeps present paragraphs in server order without caution_ar', () => {
    const out = floodParagraphs({
      concept_ar: 'أ', implication_ar: 'ب', caution_ar: 'تحذير', links_ar: 'ج',
    });
    expect(out).toEqual(['أ', 'ب', 'ج']);
  });
  it('empty for missing response', () => {
    expect(floodParagraphs(null)).toEqual([]);
  });
});

describe('buildWaterSamplePayload — sample_id إلزاميّ والغائب لا يُصفَّر', () => {
  it('null without a sample id', () => {
    expect(buildWaterSamplePayload(sampleForm({ sampleId: '  ' }))).toBeNull();
  });
  it('includes only entered measurements (server declares missing_inputs)', () => {
    const p = buildWaterSamplePayload(sampleForm({ na: '12', ca: '4.5', ecDsm: '1.2' }));
    expect(p).toEqual({ sample_id: 'w-1', source: 'well', na: 12, ca: 4.5, ec_dsm: 1.2 });
    expect(p).not.toHaveProperty('mg');
    expect(p).not.toHaveProperty('ph');
  });
});

describe('waterIndicesFacts + classificationRows — نصوص التصنيف حرفيّاً', () => {
  const analysis = {
    indices: { sar: 8.25, rsc_meq_l: null, ec_dsm: 1.4, ph: 7.6 },
    classification: {
      salinity: { class: 'moderate', restriction_ar: 'قيود متوسّطة — راقب الملوحة' },
      alkalinity_rsc: { class: null, note_ar: 'RSC غير محسوب (نقص أيونات)' },
      sodicity_sar: { class: 'low', hazard_ar: 'منخفض' },
    },
  };
  it('facts skip null indices', () => {
    expect(waterIndicesFacts(analysis).map((f) => f.label)).toEqual(['SAR', 'EC', 'pH']);
  });
  it('rows pass server wording including honest «غير محسوب»', () => {
    const rows = classificationRows(analysis);
    expect(rows).toHaveLength(3);
    expect(rows[1]).toEqual({ label_ar: 'القلويّة (RSC)', text_ar: 'RSC غير محسوب (نقص أيونات)' });
  });
  it('empty for missing analysis', () => {
    expect(waterIndicesFacts(null)).toEqual([]);
    expect(classificationRows(null)).toEqual([]);
  });
});

describe('alerts + layers — مصفوفات الخادم كما هي', () => {
  it('alertRows empty without array', () => {
    expect(alertRows(null)).toEqual([]);
    expect(alertRows({ alerts: [{ type: 'heat_wave', severity: 'critical' }] })).toHaveLength(1);
  });
  it('severity colors known levels, neutral otherwise', () => {
    expect(alertSeverityColor('critical')).toBe('#fca5a5');
    expect(alertSeverityColor('info')).toBe('#7dd3fc');
    expect(alertSeverityColor('odd')).toBe('#64748b');
    expect(alertSeverityColor(null)).toBe('#64748b');
  });
  it('layerRows + caption flag derived layers honestly', () => {
    expect(layerRows(null)).toEqual([]);
    expect(layerCaption({ key: 'et0', label_ar: 'البخر-نتح المرجعي', unit: 'mm' }))
      .toBe('البخر-نتح المرجعي (mm)');
    expect(layerCaption({ key: 'heat_stress', label_ar: 'الإجهاد الحراري', unit: '0..1', derived: true }))
      .toBe('الإجهاد الحراري (0..1) · مشتقّة');
  });
});

describe('build4rInput + planRows + nutrient badges — لا خطّة من لا شيء', () => {
  const empty4r: Soil4RFormText = { caco3Pct: '', ph: '', pPpm: '', fePpm: '', znPpm: '', omPct: '' };
  it('null without at least one lab value', () => {
    expect(build4rInput(empty4r)).toBeNull();
  });
  it('sends only entered values', () => {
    expect(build4rInput({ ...empty4r, caco3Pct: '22', ph: '8.1' })).toEqual({ caco3_pct: 22, ph: 8.1 });
  });
  it('planRows empty without array', () => {
    expect(planRows(null)).toEqual([]);
    expect(planRows({ plan: [{ nutrient: 'iron', status: 'blocked' }] })).toHaveLength(1);
  });
  it('status badge knows ok/advisory/blocked, unknown passes through neutrally', () => {
    expect(nutrientStatusBadge('blocked').color).toBe('#fca5a5');
    expect(nutrientStatusBadge('ok').color).toBe('#86efac');
    expect(nutrientStatusBadge('weird')).toEqual({ label_ar: 'weird', color: '#64748b' });
    expect(nutrientNameAr('zinc')).toBe('الزنك Zn');
    expect(nutrientNameAr('boron')).toBe('boron');
  });
});

describe('buildOutcomeRecordInput — لا إدامة سجلّ فارغ؛ الفارغ يبقى غائباً', () => {
  it('null when no planned/actual value entered', () => {
    expect(buildOutcomeRecordInput(outcomeForm(), 'f1')).toBeNull();
  });
  it('keeps entered values only and attaches field/decision/idempotency when set', () => {
    const input = buildOutcomeRecordInput(
      outcomeForm({ recommendedIrrigationMm: '40', actualIrrigationMm: '38', decisionId: 'd9', idempotencyKey: 'k1' }),
      'field-7',
    );
    expect(input).toEqual({
      planned: { recommended_irrigation_mm: 40 },
      actual: { actual_irrigation_mm: 38 },
      decision_id: 'd9',
      field_id: 'field-7',
      idempotency_key: 'k1',
    });
  });
  it('omits field_id when unknown (no fabricated linkage)', () => {
    const input = buildOutcomeRecordInput(outcomeForm({ actualYieldTHa: '2.4' }), null);
    expect(input).not.toHaveProperty('field_id');
  });
});

describe('outcome success/metrics — null من الخادم = بلا حكم لا فشل', () => {
  it('three honest states', () => {
    expect(outcomeSuccessLabel(true).color).toBe('#86efac');
    expect(outcomeSuccessLabel(false).color).toBe('#fca5a5');
    expect(outcomeSuccessLabel(null).label_ar).toBe('بلا حكم (لا مقياس مُقيَّم)');
  });
  it('metric rows read nested metrics.metrics, empty otherwise', () => {
    expect(outcomeMetricRows({ metrics: { metrics: [{ key: 'irrigation', status: 'followed' }] } })).toHaveLength(1);
    expect(outcomeMetricRows({})).toEqual([]);
    expect(outcomeMetricRows(null)).toEqual([]);
  });
});

describe('stress/sensitivity colors — معروف ملوَّن، مجهول محايد', () => {
  it('stress levels', () => {
    expect(stressLevelColor('severe')).toBe('#fca5a5');
    expect(stressLevelColor('ok')).toBe('#86efac');
    expect(stressLevelColor('x')).toBe('#64748b');
  });
  it('stage sensitivity', () => {
    expect(sensitivityColor('critical')).toBe('#fca5a5');
    expect(sensitivityColor(null)).toBe('#64748b');
  });
});

describe('geoFacts — supported=false ⇒ [] والمدى كما أرسله الخادم', () => {
  it('maps present facts only', () => {
    const facts = geoFacts({
      supported: true, governorate_ar: 'الجوف', zone_name_ar: 'صحراء داخليّة',
      annual_rain_mm: [80, 95],
    });
    expect(facts.map((f) => f.label)).toEqual(['المحافظة', 'الإقليم', 'المطر السنويّ']);
    expect(facts[2].value).toBe('80–95 مم');
  });
  it('unsupported or missing yields empty', () => {
    expect(geoFacts({ supported: false, message_ar: 'خارج اليمن' })).toEqual([]);
    expect(geoFacts(null)).toEqual([]);
  });
});

describe('httpStatusOf + writeErrorMessage — أخطاء الكتابة الصادقة', () => {
  const err = (status: number, detail?: string) => ({ response: { status, data: { detail } } });
  it('extracts status when shaped like axios error', () => {
    expect(httpStatusOf(err(503))).toBe(503);
    expect(httpStatusOf(new Error('x'))).toBeNull();
  });
  it('prefers server Arabic detail, then honest status text', () => {
    expect(writeErrorMessage(err(403, 'غير مصرَّح: الحقل ليس ضمن مستأجِرك')))
      .toBe('غير مصرَّح: الحقل ليس ضمن مستأجِرك');
    expect(writeErrorMessage(err(404))).toBe('هذه الميزة غير مُفعَّلة على هذا الخادم.');
    expect(writeErrorMessage(err(503))).toContain('لم يُسجَّل شيء');
    expect(writeErrorMessage(new Error('boom'))).toBe('تعذّر الإرسال إلى الخادم — لم يُسجَّل شيء.');
  });
});
