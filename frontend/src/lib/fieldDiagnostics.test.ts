import { describe, expect, it } from 'vitest';
import {
  advisoryNotes,
  buildDiagnosePayload,
  buildSalinityPayload,
  categoryLabelAr,
  categoryTone,
  confidencePct,
  cropPestMatches,
  fmtNum,
  ipmStageTone,
  planLadder,
  rankedCandidates,
  salinityRecommendations,
  serverMessage,
  sodiumHazardTone,
  soilSalinityTone,
  supportedPestsList,
  waterRiskTone,
  type DiagnoseResponse,
  type IpmPlanResponse,
} from './fieldDiagnostics';

// شكل نجاح حقيقيّ كما يعيده api/disease_diagnosis.py::diagnose(...).to_dict()
// (صدأ قمح: بثور برتقاليّة + اصفرار داعم ⇒ 0.7 + 0.1) + إرفاق Stage F.
const realDiagnosis: DiagnoseResponse = {
  crop: 'wheat',
  observed_symptoms: ['leaf_yellowing', 'orange_pustules'],
  candidates: [
    {
      issue_code: 'wheat.rust',
      name_ar: 'صدأ القمح',
      category: 'disease',
      confidence: 0.8,
      matched_ar: 'تطابق: leaf_yellowing, orange_pustules',
    },
  ],
  next_step_ar: 'الأرجح: صدأ القمح (ثقة 80%). ثبّت بصورة عالية الدقّة + مهندس قبل أيّ مبيد. هذا تشخيص أوّلي لا قاطع.',
  advisory_notes_ar: ['إجهاد الملوحة قد يحاكي/يفاقم أعراض الأمراض — راجِع حالة التربة.'],
  field_state: { execution_mode: 'advisory' },
};

// شكل خطّة حقيقيّ كما يعيده api/ipm_advisor.py::ipm_plan('wheat_rust') (مُقتضَب).
const realPlan: IpmPlanResponse = {
  supported: true,
  pest: 'wheat_rust',
  name_ar: 'صدأ القمح',
  scientific: 'Puccinia spp.',
  hosts_ar: 'القمح، الشعير',
  severity_ar: 'عالية — يقلّل المحصول وجودة الحبوب',
  symptoms_ar: ['بثرات صفراء/برتقاليّة/بنّيّة على الأوراق والسيقان'],
  ipm_ladder: [
    { stage: 'prevention', stage_ar: '١. الوقاية (الأساس)', actions_ar: ['زراعة أصناف مقاومة للصدأ'] },
    { stage: 'monitoring', stage_ar: '٢. المراقبة والرصد', actions_ar: ['الفحص الدوري للأوراق السفليّة (تظهر الإصابة أوّلاً)'] },
    { stage: 'biological', stage_ar: '٣. المكافحة الحيويّة', actions_ar: ['لا مكافحة حيويّة عمليّة واسعة — التركيز على الأصناف المقاومة والوقاية'] },
    { stage: 'chemical', stage_ar: '٤. الكيميائيّة (ملاذ أخير)', actions_ar: ['مبيدات فطريّة عند الإصابة المبكّرة وبظروف مواتية للانتشار.'] },
  ],
  economic_threshold_ar: 'عند أوّل ظهور للبثرات بظروف طقس مواتية للانتشار.',
  philosophy_ar: 'ابدأ بالوقاية والمراقبة. المكافحة الكيميائيّة ملاذ أخير عند تجاوز العتبة الاقتصاديّة فقط…',
  disclaimer_ar: 'إرشاد عامّ من أدبيّات وقاية النبات + FAO. لا يصف مبيدات محدّدة…',
};

describe('buildDiagnosePayload — strict Arabic validation', () => {
  it('builds the real payload shape and drops field_id when absent', () => {
    const withField = buildDiagnosePayload({
      crop: 'wheat',
      symptoms: ['orange_pustules', ' leaf_yellowing ', 'orange_pustules'],
      fieldId: 'f-1',
    });
    expect(withField).toEqual({
      ok: true,
      payload: { crop: 'wheat', symptoms: ['orange_pustules', 'leaf_yellowing'], field_id: 'f-1' },
    });
    const noField = buildDiagnosePayload({ crop: 'coffee', symptoms: ['wilting'], fieldId: null });
    expect(noField.ok && !('field_id' in noField.payload)).toBe(true);
  });

  it('rejects missing crop or empty symptoms with clear Arabic messages', () => {
    expect(buildDiagnosePayload({ crop: '  ', symptoms: ['wilting'] })).toEqual({
      ok: false,
      error: 'محصول الحقل مطلوب للتشخيص.',
    });
    expect(buildDiagnosePayload({ crop: 'wheat', symptoms: [' '] })).toEqual({
      ok: false,
      error: 'اختر عرَضاً واحداً على الأقلّ من قائمة الأعراض.',
    });
  });
});

describe('diagnosis rendering — server verdict passthrough', () => {
  it('keeps the server ranking, confidence and advisory notes as-is', () => {
    const ranked = rankedCandidates(realDiagnosis);
    expect(ranked).toHaveLength(1);
    expect(ranked[0].name_ar).toBe('صدأ القمح');
    expect(confidencePct(ranked[0].confidence)).toBe('80٪');
    expect(confidencePct(null)).toBe('—');
    expect(advisoryNotes(realDiagnosis)).toEqual([
      'إجهاد الملوحة قد يحاكي/يفاقم أعراض الأمراض — راجِع حالة التربة.',
    ]);
    expect(rankedCandidates(null)).toEqual([]);
    expect(advisoryNotes({ ...realDiagnosis, advisory_notes_ar: undefined })).toEqual([]);
  });

  it('colors only known categories — unknown stays neutral, label passes through', () => {
    expect(categoryTone('disease')).toBe('danger');
    expect(categoryTone('pest')).toBe('warn');
    expect(categoryTone('nutrient')).toBe('info');
    expect(categoryTone('water_stress')).toBe('warn');
    expect(categoryTone('mystery_new_category')).toBe('neutral');
    expect(categoryLabelAr('disease')).toBe('مرض');
    expect(categoryLabelAr('mystery_new_category')).toBe('mystery_new_category');
    expect(categoryLabelAr(null)).toBe('—');
  });
});

describe('IPM — real plan shape and honest unsupported', () => {
  it('returns the 4-stage ladder in server order with last-resort chemical toned danger', () => {
    const ladder = planLadder(realPlan);
    expect(ladder.map((s) => s.stage)).toEqual(['prevention', 'monitoring', 'biological', 'chemical']);
    expect(ipmStageTone('chemical')).toBe('danger');
    expect(ipmStageTone('prevention')).toBe('ok');
    expect(ipmStageTone('future_stage')).toBe('neutral');
    // حقول provenance/disclaimer تبقى محفوظة على الاستجابة كما جاءت
    expect(realPlan.disclaimer_ar).toContain('FAO');
    expect(realPlan.economic_threshold_ar).toContain('ظهور');
  });

  it('is empty for unsupported plans and passes the server message through', () => {
    const unsupported: IpmPlanResponse = {
      supported: false,
      message_ar: 'لا خطّة IPM لـ«locust». المدعوم: دودة الحشد الخريفيّة، صدأ القمح، المنّ',
    };
    expect(planLadder(unsupported)).toEqual([]);
    expect(serverMessage(unsupported)).toBe(unsupported.message_ar);
    expect(serverMessage(realPlan)).toBeNull();
  });

  it('reads pests lists as the server ordered them, [] when absent', () => {
    expect(
      supportedPestsList({
        pests: [{ pest: 'aphid', name_ar: 'المنّ', scientific: 'Aphidoidea', hosts_ar: 'القمح…', severity_ar: 'متوسّطة…' }],
      })[0].name_ar,
    ).toBe('المنّ');
    expect(supportedPestsList(null)).toEqual([]);
    const cropResp = {
      supported: true,
      crop_ar: 'القمح',
      pests: [{ pest: 'wheat_rust', name_ar: 'صدأ القمح', severity_ar: 'عالية…' }],
      note_ar: 'آفات محتملة لهذا المحصول…',
    };
    expect(cropPestMatches(cropResp)).toHaveLength(1);
    expect(cropPestMatches({ supported: false, message_ar: 'المحصول «x» غير معروف.' })).toEqual([]);
  });
});

describe('buildSalinityPayload — user measurements only, absent fields dropped', () => {
  it('builds snake_case payload and drops empty measurements instead of zeroing', () => {
    expect(buildSalinityPayload({ eceDsm: '6.5', ecwDsm: 2, sar: '12', cropThresholdEce: 6 })).toEqual({
      ok: true,
      payload: { ece_dsm: 6.5, ecw_dsm: 2, sar: 12, crop_threshold_ece: 6 },
    });
    expect(buildSalinityPayload({ eceDsm: '3.1', ecwDsm: '', sar: null })).toEqual({
      ok: true,
      payload: { ece_dsm: 3.1 },
    });
  });

  it('rejects no-measurement, negative, and threshold-without-ECw with Arabic messages', () => {
    expect(buildSalinityPayload({})).toEqual({
      ok: false,
      error: 'أدخِل قياساً واحداً على الأقلّ: ECe (تربة) أو ECw (ماء) أو SAR.',
    });
    expect(buildSalinityPayload({ eceDsm: '-1' })).toEqual({
      ok: false,
      error: 'ملوحة التربة ECe يجب أن يكون رقماً غير سالب (من قياس حقيقيّ).',
    });
    expect(buildSalinityPayload({ eceDsm: 4, cropThresholdEce: 6 })).toEqual({
      ok: false,
      error: 'عتبة تحمّل المحصول تُستخدم مع ملوحة ماء الريّ ECw لحساب احتياج الغسيل — أدخِل ECw أيضاً.',
    });
  });
});

describe('salinity rendering — FAO classes colored only when known', () => {
  it('maps known server classes/risks to tones, unknown → neutral', () => {
    expect(soilSalinityTone('non_saline')).toBe('ok');
    expect(soilSalinityTone('moderately_saline')).toBe('warn');
    expect(soilSalinityTone('very_strongly_saline')).toBe('danger');
    expect(soilSalinityTone('new_fao_class')).toBe('neutral');
    expect(waterRiskTone('none')).toBe('ok');
    expect(waterRiskTone('severe')).toBe('danger');
    expect(waterRiskTone(undefined)).toBe('neutral');
    expect(sodiumHazardTone('medium')).toBe('warn');
    expect(sodiumHazardTone('very_high')).toBe('danger');
    expect(sodiumHazardTone('odd')).toBe('neutral');
  });

  it('passes recommendations/disclaimer through and formats nulls as «—»', () => {
    const resp = {
      supported: true,
      components: { soil_salinity: { ece_dsm: 6.5, class: 'moderately_saline', class_ar: 'ملوحة متوسّطة', effect_ar: 'تتأثّر كثير من المحاصيل؛ اختر المتحمّلة (شعير، نخيل).' } },
      recommendations_ar: ['التربة ملوحة متوسّطة — اختر محاصيل متحمّلة (شعير، نخيل) أو طبّق غسيلاً.'],
      disclaimer_ar: 'تقييم إرشادي بمعايير FAO…',
      yemen_context_ar: 'الملوحة مشكلة محلّيّة في مناطق محدّدة…',
    };
    expect(salinityRecommendations(resp)).toEqual(resp.recommendations_ar);
    expect(salinityRecommendations({ supported: false, message_ar: 'قدّم على الأقلّ ECe (تربة) أو ECw (ماء) أو SAR.' })).toEqual([]);
    expect(serverMessage({ supported: false, message_ar: 'قدّم على الأقلّ ECe (تربة) أو ECw (ماء) أو SAR.' })).toContain('ECe');
    expect(fmtNum(null)).toBe('—');
    expect(fmtNum(0.187, 3)).toBe('0.187');
  });
});
