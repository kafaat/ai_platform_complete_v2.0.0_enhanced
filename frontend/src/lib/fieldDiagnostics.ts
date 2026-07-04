// Field Diagnostics Workbench — يعكس ثلاث قدرات backend مُخزَّنة بلا قارئ واجهة:
// POST /api/v1/diagnose + GET /api/v1/diagnose/symptoms (تشخيص بقواعد الأعراض — لا قاطع)
// GET /api/v1/ipm/{pests,plan,crop-pests} (الإدارة المتكاملة للآفات — الكيميائيّ ملاذ أخير)
// POST /api/v1/salinity/assess (تصنيف FAO للملوحة + احتياج الغسيل + خطر الصوديوم).
// صدق صارم (نمط ledgerEntry.BuildResult): تحقّق محلّيّ برسالة عربيّة واضحة قبل الإرسال —
// لا 422 غامضة ولا قيم مُلفَّقة؛ أحكام الخادم (class/risk/category/next_step_ar) تمرّ
// حرفيّاً ولا يُعاد الحكم؛ التلوين للقيَم المعروفة فقط (المجهول ⇒ محايد)؛ null ⇒ «—»؛
// الغائب يسقط لا يُصفَّر؛ وحقول *_ar (provenance/disclaimer/philosophy/yemen_context) تُحفَظ.

import type { BuildResult } from './ledgerEntry';

export type { BuildResult } from './ledgerEntry';

export const DASH = '—';

/** نغمات العرض — تطابق بنيويّاً Tone في components/ds (بلا استيراد عبر الطبقات). */
export type Tone = 'ok' | 'warn' | 'danger' | 'info' | 'neutral';

/** تنسيق رقم للعرض — null/undefined/غير منتهٍ ⇒ «—» (لا تصفير). */
export function fmtNum(v: number | null | undefined, digits = 0): string {
  if (v == null || !Number.isFinite(v)) return DASH;
  return v.toFixed(digits);
}

/** رسالة الخادم لاستجابة غير مدعومة — تمرّ كما جاءت (unsupported ⇒ message_ar). */
export function serverMessage(
  resp: { supported?: boolean; message_ar?: string } | null | undefined,
): string | null {
  if (!resp || resp.supported !== false) return null;
  return resp.message_ar ?? null;
}

// ═══ التشخيص الأوّلي (api/disease_diagnosis.py + routers/diagnose.py) ═══

export interface SymptomOption {
  code: string;
  name_ar: string;
}

/** شكل GET /api/v1/diagnose/symptoms الحقيقيّ: {symptoms: [{code, name_ar}]} */
export interface SymptomCatalogResponse {
  symptoms?: SymptomOption[];
}

/** مرشّح تشخيص كما يعيده الخادم (DiagnosisCandidate.to_dict). */
export interface DiagnosisCandidate {
  issue_code: string;
  name_ar: string;
  /** disease | pest | nutrient | water_stress — حكم الخادم، يمرّ كما هو. */
  category: string;
  /** 0..1 (مُقرَّب لخانتين خادميّاً). */
  confidence: number;
  matched_ar: string;
}

/** مقتطف الحالة الموحّدة المُرفَق اختياريّاً عند تمرير field_id (Stage F) —
 *  حقوله قد تكون null بصدق (لا حدّ مُهدَّف/لا استنزاف موثوق). */
export interface DiagnoseFieldState {
  validity?: unknown;
  execution_mode?: string | null;
  agronomic?: { operational_truths?: Record<string, unknown> } | null;
  water?: unknown;
  boundary?: unknown;
  water_stress?: unknown;
  readiness?: unknown;
}

/** شكل POST /api/v1/diagnose الحقيقيّ (DiagnosisResult.to_dict + إرفاقات). */
export interface DiagnoseResponse {
  crop: string;
  observed_symptoms: string[];
  candidates: DiagnosisCandidate[];
  next_step_ar: string;
  /** ملاحظات مرجعيّة (مثل: ملوحة حرجة تحاكي أعراض الأمراض) — تمرّ كما جاءت. */
  advisory_notes_ar?: string[];
  field_state?: DiagnoseFieldState;
}

export interface DiagnosePayload {
  crop: string;
  symptoms: string[];
  field_id?: string;
}

export interface DiagnoseInput {
  crop: string | null | undefined;
  symptoms: string[];
  fieldId?: string | null;
}

/** يبني حمولة التشخيص — تحقّق صارم برسالة عربيّة (لا طلب فارغاً/بلا محصول). */
export function buildDiagnosePayload(input: DiagnoseInput): BuildResult<DiagnosePayload> {
  const crop = (input.crop ?? '').trim();
  if (!crop) return { ok: false, error: 'محصول الحقل مطلوب للتشخيص.' };
  const symptoms = [...new Set((input.symptoms ?? []).map((s) => s.trim()).filter(Boolean))];
  if (symptoms.length === 0) return { ok: false, error: 'اختر عرَضاً واحداً على الأقلّ من قائمة الأعراض.' };
  const payload: DiagnosePayload = { crop, symptoms };
  if (input.fieldId) payload.field_id = input.fieldId; // الغائب يسقط — لا إرفاق حالة بلا حقل
  return { ok: true, payload };
}

// تلوين فئات الخادم المعروفة فقط — فئة مجهولة ⇒ محايد (لا اختراع حكم).
const CATEGORY_TONE: Record<string, Tone> = {
  disease: 'danger',
  pest: 'warn',
  nutrient: 'info',
  water_stress: 'warn',
};

export function categoryTone(category: string | null | undefined): Tone {
  return CATEGORY_TONE[(category ?? '').toLowerCase()] ?? 'neutral';
}

// تسميات عرض للفئات المعروفة — المجهولة تمرّ كما جاءت من الخادم (صدق)، null ⇒ «—».
const CATEGORY_AR: Record<string, string> = {
  disease: 'مرض',
  pest: 'آفة',
  nutrient: 'نقص عنصر',
  water_stress: 'إجهاد مائيّ',
};

export function categoryLabelAr(category: string | null | undefined): string {
  if (category == null || category === '') return DASH;
  return CATEGORY_AR[category.toLowerCase()] ?? category;
}

/** ثقة الخادم (0..1) كنسبة عرض — null ⇒ «—» (لا تصفير). */
export function confidencePct(confidence: number | null | undefined): string {
  if (confidence == null || !Number.isFinite(confidence)) return DASH;
  return `${Math.round(confidence * 100)}٪`;
}

/** المرشّحون بترتيب الخادم كما هو (الخادم يرتّب بالثقة) — بلا مصفوفة ⇒ []. */
export function rankedCandidates(resp: DiagnoseResponse | null | undefined): DiagnosisCandidate[] {
  if (!resp || !Array.isArray(resp.candidates)) return [];
  return resp.candidates;
}

/** الملاحظات المرجعيّة المُرفَقة (advisory_notes_ar) — تمرّ حرفيّاً، الغائب ⇒ []. */
export function advisoryNotes(resp: DiagnoseResponse | null | undefined): string[] {
  if (!resp || !Array.isArray(resp.advisory_notes_ar)) return [];
  return resp.advisory_notes_ar;
}

// ═══ الإدارة المتكاملة للآفات (api/ipm_advisor.py + routers/ipm.py) ═══

/** عنصر GET /api/v1/ipm/pests (supported_pests). */
export interface IpmPestSummary {
  pest: string;
  name_ar: string;
  scientific: string;
  hosts_ar: string;
  severity_ar: string;
}

export interface IpmPestsResponse {
  pests?: IpmPestSummary[];
}

/** درجة سلّم IPM كما يعيدها الخادم (stage/stage_ar/actions_ar). */
export interface IpmLadderStage {
  stage: string;
  stage_ar: string;
  actions_ar: string[];
}

/** شكل GET /api/v1/ipm/plan الحقيقيّ (ipm_plan) — unsupported ⇒ message_ar. */
export interface IpmPlanResponse {
  supported: boolean;
  message_ar?: string;
  pest?: string;
  name_ar?: string;
  scientific?: string;
  hosts_ar?: string;
  severity_ar?: string;
  symptoms_ar?: string[];
  ipm_ladder?: IpmLadderStage[];
  economic_threshold_ar?: string;
  philosophy_ar?: string;
  disclaimer_ar?: string;
}

export interface CropPestMatch {
  pest: string;
  name_ar: string;
  severity_ar: string;
}

/** شكل GET /api/v1/ipm/crop-pests الحقيقيّ (pests_for_crop). */
export interface CropPestsResponse {
  supported: boolean;
  message_ar?: string;
  crop_ar?: string;
  pests?: CropPestMatch[];
  note_ar?: string;
}

// درجات السلّم المعروفة فقط تُلوَّن — الكيميائيّ ملاذ أخير (danger)، المجهول محايد.
const STAGE_TONE: Record<string, Tone> = {
  prevention: 'ok',
  monitoring: 'info',
  biological: 'ok',
  chemical: 'danger',
};

export function ipmStageTone(stage: string | null | undefined): Tone {
  return STAGE_TONE[(stage ?? '').toLowerCase()] ?? 'neutral';
}

/** سلّم الخطّة بترتيب الخادم — unsupported/بلا مصفوفة ⇒ [] (message_ar عبر serverMessage). */
export function planLadder(resp: IpmPlanResponse | null | undefined): IpmLadderStage[] {
  if (!resp?.supported || !Array.isArray(resp.ipm_ladder)) return [];
  return resp.ipm_ladder;
}

/** الآفات المدعومة كما يعيدها الخادم — بلا مصفوفة ⇒ []. */
export function supportedPestsList(resp: IpmPestsResponse | null | undefined): IpmPestSummary[] {
  if (!resp || !Array.isArray(resp.pests)) return [];
  return resp.pests;
}

/** آفات المحصول المحتملة — unsupported/بلا مصفوفة ⇒ []. */
export function cropPestMatches(resp: CropPestsResponse | null | undefined): CropPestMatch[] {
  if (!resp?.supported || !Array.isArray(resp.pests)) return [];
  return resp.pests;
}

// ═══ تقييم الملوحة (api/salinity_management.py + routers/salinity.py) ═══

export interface SoilSalinityComponent {
  ece_dsm: number;
  class: string;
  class_ar: string;
  effect_ar: string;
}

export interface WaterSalinityComponent {
  ecw_dsm: number;
  risk: string;
  risk_ar: string;
  note_ar: string;
}

export interface LeachingComponent {
  supported: boolean;
  feasible: boolean;
  leaching_fraction?: number;
  leaching_pct?: number;
  advice_ar?: string;
  yemen_note_ar?: string;
  note_ar?: string;
  message_ar?: string;
}

export interface SodiumHazardComponent {
  sar: number;
  class: string;
  class_ar: string;
  effect_ar: string;
  remedy_ar: string;
}

/** شكل POST /api/v1/salinity/assess الحقيقيّ (salinity_assessment). */
export interface SalinityAssessResponse {
  supported: boolean;
  message_ar?: string;
  components?: {
    soil_salinity?: SoilSalinityComponent;
    water_salinity?: WaterSalinityComponent;
    leaching?: LeachingComponent;
    sodium_hazard?: SodiumHazardComponent;
  };
  recommendations_ar?: string[];
  disclaimer_ar?: string;
  yemen_context_ar?: string;
}

export interface SalinityPayload {
  ece_dsm?: number;
  ecw_dsm?: number;
  sar?: number;
  crop_threshold_ece?: number;
}

export interface SalinityInput {
  eceDsm?: string | number | null;
  ecwDsm?: string | number | null;
  sar?: string | number | null;
  cropThresholdEce?: string | number | null;
}

// قياس اختياريّ: فارغ ⇒ يسقط بصدق؛ مُدخَل ⇒ رقم منتهٍ غير سالب وإلّا رفض عربيّ واضح.
function optionalMeasure(
  value: string | number | null | undefined,
  label: string,
): { ok: true; value: number | undefined } | { ok: false; error: string } {
  if (value == null || String(value).trim() === '') return { ok: true, value: undefined };
  const n = typeof value === 'number' ? value : Number(String(value).trim());
  if (!Number.isFinite(n) || n < 0) {
    return { ok: false, error: `${label} يجب أن يكون رقماً غير سالب (من قياس حقيقيّ).` };
  }
  return { ok: true, value: n };
}

/** يبني حمولة تقييم الملوحة — قياس واحد على الأقلّ، والغائب يسقط لا يُصفَّر. */
export function buildSalinityPayload(input: SalinityInput): BuildResult<SalinityPayload> {
  const ece = optionalMeasure(input.eceDsm, 'ملوحة التربة ECe');
  if (!ece.ok) return { ok: false, error: ece.error };
  const ecw = optionalMeasure(input.ecwDsm, 'ملوحة ماء الريّ ECw');
  if (!ecw.ok) return { ok: false, error: ecw.error };
  const sar = optionalMeasure(input.sar, 'نسبة امتصاص الصوديوم SAR');
  if (!sar.ok) return { ok: false, error: sar.error };
  const threshold = optionalMeasure(input.cropThresholdEce, 'عتبة تحمّل المحصول ECe');
  if (!threshold.ok) return { ok: false, error: threshold.error };

  if (ece.value === undefined && ecw.value === undefined && sar.value === undefined) {
    return { ok: false, error: 'أدخِل قياساً واحداً على الأقلّ: ECe (تربة) أو ECw (ماء) أو SAR.' };
  }
  // احتياج الغسيل يحتاج ECw + العتبة معاً (FAO-56 Eq.82) — عتبة بلا ماء لا معنى لها.
  if (threshold.value !== undefined && ecw.value === undefined) {
    return {
      ok: false,
      error: 'عتبة تحمّل المحصول تُستخدم مع ملوحة ماء الريّ ECw لحساب احتياج الغسيل — أدخِل ECw أيضاً.',
    };
  }
  if (threshold.value !== undefined && threshold.value <= 0) {
    return { ok: false, error: 'عتبة تحمّل المحصول ECe يجب أن تكون رقماً موجباً.' };
  }

  const payload: SalinityPayload = {};
  if (ece.value !== undefined) payload.ece_dsm = ece.value;
  if (ecw.value !== undefined) payload.ecw_dsm = ecw.value;
  if (sar.value !== undefined) payload.sar = sar.value;
  if (threshold.value !== undefined) payload.crop_threshold_ece = threshold.value;
  return { ok: true, payload };
}

// أصناف الخادم المعروفة فقط تُلوَّن (FAO) — المجهول ⇒ محايد، والنصّ العربيّ من الخادم.
const SOIL_CLASS_TONE: Record<string, Tone> = {
  non_saline: 'ok',
  slightly_saline: 'info',
  moderately_saline: 'warn',
  strongly_saline: 'danger',
  very_strongly_saline: 'danger',
};

const WATER_RISK_TONE: Record<string, Tone> = {
  none: 'ok',
  slight_moderate: 'warn',
  severe: 'danger',
};

const SODIUM_CLASS_TONE: Record<string, Tone> = {
  low: 'ok',
  medium: 'warn',
  high: 'danger',
  very_high: 'danger',
};

export function soilSalinityTone(cls: string | null | undefined): Tone {
  return SOIL_CLASS_TONE[(cls ?? '').toLowerCase()] ?? 'neutral';
}

export function waterRiskTone(risk: string | null | undefined): Tone {
  return WATER_RISK_TONE[(risk ?? '').toLowerCase()] ?? 'neutral';
}

export function sodiumHazardTone(cls: string | null | undefined): Tone {
  return SODIUM_CLASS_TONE[(cls ?? '').toLowerCase()] ?? 'neutral';
}

/** توصيات الخادم كما جاءت — unsupported/الغائب ⇒ []. */
export function salinityRecommendations(resp: SalinityAssessResponse | null | undefined): string[] {
  if (!resp?.supported || !Array.isArray(resp.recommendations_ar)) return [];
  return resp.recommendations_ar;
}
