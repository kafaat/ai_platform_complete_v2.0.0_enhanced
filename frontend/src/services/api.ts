// ═══════════════════════════════════════════════════════════════
// SAHOOL v9.0 — Unified API Client
// Compatibility facade: keep legacy imports stable while domain modules
// move out incrementally under frontend/src/services/api/*.ts.
// ═══════════════════════════════════════════════════════════════

import {
  MOCK_MODE,
  tryReal,
  kongApi,
  weatherApi,
  soilApi,
  indicatorsApi,
  vegetationApi,
  rasterApi,
  authApi,
} from './api/client';

// Calibration domain lives in ./api/calibration; the DECISION STUDIO / EVIDENCE MAP
// sections below still consume a few of its exports, so bind them locally here.
import { fetchDecisionLineage } from './api/calibration';
import type {
  DecisionLineage,
  EvidenceLevel,
  LineageDecision,
  LineageOutcome,
} from './api/calibration';

export {
  MOCK_MODE,
  tryReal,
  kongApi,
  weatherApi,
  soilApi,
  indicatorsApi,
  vegetationApi,
  rasterApi,
  authApi,
} from './api/client';

// ══════════════════════════════════════════════════════════════════
// AUTH — extracted to services/api/auth.ts; re-exported for compatibility
// ══════════════════════════════════════════════════════════════════
export {
  login,
  register,
  logout,
  requestPasswordReset,
  confirmPasswordReset,
  mfaSetup,
  mfaActivate,
  mfaDisable,
  changePassword,
  getVerificationStatus,
  requestVerification,
  confirmVerification,
  createInvitation,
  listInvitations,
  acceptInvitation,
  revokeInvitation,
  listTeamUsers,
  getCurrentUser,
  provisionTenant,
  changeUserRole,
  asApiError,
  isMfaRequiredError,
  apiErrorMessage,
  apiFieldErrors,
  deactivateUser,
} from './api/auth';
// إعادة التصدير أعلاه لا تربط الأسماء في نطاق هذه الوحدة — الواجهة تستخدمها داخليّاً.
import { asApiError, apiErrorMessage } from './api/auth';
import { getAccessToken } from '../lib/authStorage';
export type {
  LoginPayload,
  AuthResponse,
  ApiErrorDetailItem,
  ApiError,
  RegisterPayload,
  MfaSetupResponse,
  VerifyChannel,
  VerificationStatus,
  InviteableRole,
  CreateInvitationResult,
  PendingInvitation,
  TeamUser,
  AssignableRole,
  CurrentUser,
  TenantProvisionResult,
} from './api/auth';


// ══════════════════════════════════════════════════════════════════
// FIELD OPERATING CONTRACTS — readiness/completeness/timeline/priority queue
// ══════════════════════════════════════════════════════════════════
export {
  getFieldReadiness,
  getFieldDataCompleteness,
  getFieldUnifiedTimeline,
  getFarmPriorityQueue,
  getFieldPriorityQueue,
} from './api/fieldOperating';
export type {
  CompletenessStatus,
  FieldReadinessItem,
  FieldReadinessResponse,
  FieldDataCompletenessResponse,
  FieldTimelineEvent,
  FieldUnifiedTimelineResponse,
  PriorityQueueItem,
  PriorityQueueResponse,
} from './api/fieldOperating';

// ══════════════════════════════════════════════════════════════════
// SAHOOL-PLATFORM (core) — وحدات قرار حيّة عبر البوابة الموحّدة (kong)
// ربط حقيقيّ: لا fallback وهميّ (قرارات زراعيّة — الخطأ يُعلَن للـUI).
// ══════════════════════════════════════════════════════════════════
// ── Tenant Config (#206): تكوين المستأجِر للعلامة التجاريّة + الوحدات/اللغة ──
// GET /api/v1/tenant/config → {branding:{logo_url, primary_color, name_ar}, units,
// language, crops}. الحقول كلّها اختياريّة/قد تكون null (الافتراضيّ): الواجهة
// تتجاهل أيّ حقل غائب وتُبقي سلوكها الحاليّ. أفضل-جهد: عند أيّ خطأ نُرجِع null
// (لا fallback مُفبرَك، ولا كسر) فتعمل الواجهة بالافتراضيّات كما هي اليوم.
export interface TenantBranding {
  logo_url:      string | null;
  primary_color: string | null;
  name_ar:       string | null;
}
export interface TenantConfig {
  branding: TenantBranding | null;
  units:    string | null;
  language: string | null;
  crops:    string[] | null;
}

/** يجلب تكوين المستأجِر (#206). أفضل-جهد: أيّ خطأ/استجابة غير صالحة ⇒ null
 *  فتُبقي الواجهة الافتراضيّات (لا كسر، لا علامة تجاريّة مُفبرَكة). */
export const fetchTenantConfig = (): Promise<TenantConfig | null> =>
  kongApi
    .get<TenantConfig>('/api/v1/tenant/config')
    .then((r) => (r.data && typeof r.data === 'object' ? r.data : null))
    .catch(() => null);

export interface WaterSampleInput {
  sample_id: string;
  source?: string;
  na?: number | null; ca?: number | null; mg?: number | null;
  hco3?: number | null; co3?: number | null; cl?: number | null;
  ec_dsm?: number | null; ph?: number | null;
  sampled_at?: string | null;
}
export interface WaterClass {
  class: string | null;
  restriction_ar?: string;
  hazard_ar?: string;
  note_ar?: string;
}
export interface WaterAnalysisResult {
  sample_id: string;
  source: string;
  indices: { sar: number | null; rsc_meq_l: number | null; ec_dsm: number | null; ph: number | null };
  classification: {
    salinity: WaterClass;
    alkalinity_rsc: WaterClass;
    sodicity_sar: WaterClass;
  };
  hazard_flags_ar: string[];
  suitable_ar: string;
  missing_inputs: string[];
  data_complete: boolean;
}
export const analyzeWaterSample = (payload: WaterSampleInput): Promise<WaterAnalysisResult> =>
  kongApi.post<WaterAnalysisResult>('/api/v1/irrigation/water-analysis', payload).then(r => r.data);

// ── شفافيّة قدرات متحكّم الريّ الهرميّ المعجميّ (Lexicographic MPC) ──────────
// قراءة فقط: ما يُنمذِجه الحلّال (J1..J4) مقابل المُؤجَّل صراحةً (طاقة/آبار/أفق ساعيّ)،
// وإصداره، وأنّه توصية-فقط بنيويّاً (لا تنفيذ تلقائيّ). لا مدخلات/تلفيق — نقطة العقد نفسها.
export interface MpcCapabilities {
  solver_version: string;
  modeled_capabilities: string[];
  not_modeled: string[];
  execution_allowed: boolean;
  recommendation_only: boolean;
}
export const fetchMpcCapabilities = (): Promise<MpcCapabilities> =>
  kongApi.get<MpcCapabilities>('/api/v1/irrigation/mpc/capabilities').then(r => r.data);

// ── خطّة الريّ التنبّؤيّة (POST /api/v1/irrigation-plan) — خطّ «مركز المحاصيل» ──
// نسيج+عمق ⇒ TAW ⇒ سياسة ⇒ جدول ريّ عبر أفق التنبّؤ (FAO-56). كلّ القيم موسومة calibrated.
export interface ForecastDayInput {
  et0_mm: number; kc: number; rain_mm?: number; runoff_mm?: number;
}
export interface IrrigationPlanInput {
  forecast: ForecastDayInput[];
  soil_texture?: string | null;
  root_depth_m?: number | null;
  taw_mm?: number | null;
  raw_fraction?: number;
  policy?: string;
  initial_depletion_mm?: number;
  max_application_mm?: number | null;
  season_budget_mm?: number | null;
  water_price_per_m3?: number | null;
  yield_value_per_ha?: number | null;
}
export interface SoilWaterParams {
  texture: string | null;
  texture_known: boolean;
  taw_mm_per_m: number;
  root_depth_m: number;
  taw_mm: number;
  raw_fraction: number;
  raw_mm: number;
  calibrated: boolean;
  warnings_ar: string[];
}
export interface PlannedDay {
  day_index: number;
  etc_mm: number;
  eff_rain_mm: number;
  dr_before_irrig_mm: number;
  irrigation_mm: number;
  dr_end_mm: number;
  deep_perc_mm: number;
  stressed: boolean;
}
export interface IrrigationPlan {
  policy: string;
  taw_mm: number;
  raw_mm: number;
  total_irrigation_mm: number;
  total_irrigation_m3_ha: number;
  n_events: number;
  stress_days: number[];
  total_deep_perc_mm: number;
  final_depletion_mm: number;
  budget_exhausted: boolean;
  calibrated: boolean;
  notes_ar: string[];
  days: PlannedDay[];
}
export interface DataQuality {
  confidence: number;       // مقياس اكتمال/جودة مدخلات شفّاف [0,1] (لا فاصل إحصائيّ)
  data_quality: string;     // low | medium | high
  assumptions: string[];    // رموز آليّة
  assumptions_ar: string[]; // وصف عربيّ للمستخدم
  calibrated: boolean;
}
export interface IrrigationPlanResult {
  soil: SoilWaterParams;
  taw_mm_used: number;
  quality: DataQuality;
  plan: IrrigationPlan;
}
export const computeIrrigationPlan = (payload: IrrigationPlanInput): Promise<IrrigationPlanResult> =>
  kongApi.post<IrrigationPlanResult>('/api/v1/irrigation-plan', payload).then(r => r.data);

// ── توأم المياه (POST /api/v1/fields/{id}/water-twin) — مُغذّى بدفتر المياه v98 ──
// يحاكي مسار نضوب الجذور الأماميّ (FAO-56) لسيناريوهَي ريّ (أساس مقابل تأجيل/تخفيض)
// مُغذّى بأحدث صفوف الدفتر. صدق: لا غلّة مُلفّقة — أيّام إجهاد/استهلاك ماء فقط.
export interface WaterTwinDayState {
  day: number; depletion_mm: number; soil_moisture_pct: number;
  ks: number; eta_mm: number; stressed: boolean;
}
export interface WaterTwinTrajectory {
  days: number; total_irrigation_mm: number; total_eta_mm: number; stress_days: number;
  max_depletion_mm: number; final_depletion_mm: number; final_soil_moisture_pct: number;
  states: WaterTwinDayState[];
}
export interface WaterTwinComparison {
  metric_ar: string; baseline: number; scenario: number; delta: number; unit: string;
}
export interface WaterTwinSeed {
  initial_depletion_mm: number; initial_depletion_source: string;
  daily_etc_mm: number; daily_etc_source: string;
  ledger_rows_used: number; horizon_days: number;
}
export interface WaterTwinResult {
  scenario_type: string;
  baseline: WaterTwinTrajectory;
  scenario: WaterTwinTrajectory;
  comparisons: WaterTwinComparison[];
  summary_ar: string;
  field_id: string;
  seed: WaterTwinSeed;
}
export interface FieldWaterTwinInput {
  taw_mm: number;
  raw_mm: number;
  horizon_days?: number;
  baseline_irrigation_mm?: number;
  daily_rain_mm?: number;
  daily_etc_mm?: number | null;
  initial_depletion_mm?: number | null;
  recent_days_window?: number;
  scenario_kind: 'delay' | 'scale';
  delay_days?: number;
  scale_factor?: number;
}
export const simulateFieldWaterTwin = (
  fieldId: string,
  payload: FieldWaterTwinInput,
): Promise<WaterTwinResult> =>
  kongApi.post<WaterTwinResult>(`/api/v1/fields/${fieldId}/water-twin`, payload).then(r => r.data);

// ── ETc المزدوج (FAO-56) لحقل، مُغذّى بـNDVI الحيّ (POST /api/v1/fields/{id}/etc-dual) ──
// يحسب ETc بنهج المعامل المزدوج (Kcb·Ks + Ke)·ET0 (#462). الطقس يمرّره المتّصِل؛
// NDVI/المحصول/العمر/الملوحة تُحقَن من الحقل ما لم تُمرَّر تجاوزات. مصدر كلّ قيمة مُعلَن.
export interface EtcDualInput {
  // الطقس (لـET0 — Penman-Monteith)
  temp_max_c: number;
  temp_min_c: number;
  humidity_pct: number;
  wind_speed_m_s: number;
  solar_radiation_mj_m2: number;
  latitude_deg: number;
  elevation_m?: number;
  day_of_year: number;
  // تجاوزات اختياريّة (الافتراضات FAO-56 موثّقة في المحرّك)
  de_mm?: number;
  texture?: string;
  crop_height_m?: number;
  fw?: number;
  ndvi_bare?: number;
  ndvi_full?: number;
  // تجاوزات تسبق الحقن من الحقل (غياب ⇒ يُحقَن من الحقل)
  ndvi?: number | null;
  soil_ece?: number | null;
  days_after_planting?: number | null;
}
// شكل الردّ: حقول DualKcResult (asdict) + field_id + ndvi + inputs (راجع routers/etc_dual.py).
export interface EtcDualResult {
  et0_mm: number;
  kcb: number;
  ks: number;
  kc_max: number;
  kr: number;
  few: number;
  ke: number;
  kc_dual: number;       // Kcb·Ks + Ke (المعامل الفعّال المركّب)
  etc_dual_mm: number;   // (Kcb·Ks + Ke)·ET0
  etc_single_mm: number; // Kc·Ks·ET0 (للمقارنة الشفّافة)
  stage: string;
  assumptions: string[];
  field_id: string;
  ndvi: { used: number | null; source: string; date: string | null };
  inputs: {
    crop_id: string;
    days_after_planting: number;
    soil_ece: number;
    soil_ece_source: string;
  };
}
function localEtcDualFallback(fieldId: string, payload: EtcDualInput): EtcDualResult {
  const tMean = (payload.temp_max_c + payload.temp_min_c) / 2;
  const et0 = Math.max(0, 0.0023 * (tMean + 17.8) * Math.sqrt(Math.max(0.1, payload.temp_max_c - payload.temp_min_c)) * Math.max(0, payload.solar_radiation_mj_m2 / 2.45));
  const ndvi = payload.ndvi ?? null;
  const kcbFromNdvi = ndvi == null ? null : Math.max(0.15, Math.min(1.15, 1.25 * ((ndvi - (payload.ndvi_bare ?? 0.15)) / Math.max(0.01, (payload.ndvi_full ?? 0.8) - (payload.ndvi_bare ?? 0.15)))));
  const das = payload.days_after_planting ?? 45;
  const kcb = kcbFromNdvi ?? Math.max(0.25, Math.min(1.05, 0.25 + das / 80));
  const ks = payload.soil_ece && payload.soil_ece > 4 ? Math.max(0.55, 1 - (payload.soil_ece - 4) * 0.04) : 1;
  const ke = Math.max(0.05, Math.min(0.25, (100 - payload.humidity_pct) / 500));
  const kcDual = Math.min(1.35, kcb * ks + ke);
  const etcDual = et0 * kcDual;
  return {
    et0_mm: Number(et0.toFixed(2)),
    kcb: Number(kcb.toFixed(3)),
    ks: Number(ks.toFixed(3)),
    kc_max: 1.35,
    kr: 1,
    few: payload.fw ?? 0.35,
    ke: Number(ke.toFixed(3)),
    kc_dual: Number(kcDual.toFixed(3)),
    etc_dual_mm: Number(etcDual.toFixed(2)),
    etc_single_mm: Number((et0 * kcb * ks).toFixed(2)),
    stage: 'client_fallback',
    assumptions: ['حساب محلي مؤقت لأن قاعدة ETc الخلفية غير مفعّلة أو غير متاحة', 'فعّل DATABASE_URL في الخدمة الخلفية للاعتماد الإنتاجي'],
    field_id: fieldId,
    ndvi: { used: ndvi, source: ndvi == null ? 'not_provided' : 'manual_override', date: null },
    inputs: { crop_id: 'unknown', days_after_planting: das, soil_ece: payload.soil_ece ?? 0, soil_ece_source: payload.soil_ece == null ? 'not_provided' : 'manual_override' },
  };
}

export const computeFieldEtcDual = async (
  fieldId: string,
  payload: EtcDualInput,
): Promise<EtcDualResult> => {
  try {
    return await kongApi.post<EtcDualResult>(`/api/v1/fields/${fieldId}/etc-dual`, payload).then(r => r.data);
  } catch (e) {
    const msg = apiErrorMessage(e, '');
    if (msg.includes('DATABASE_URL') || msg.includes('القاعدة غير مفعّلة')) {
      return localEtcDualFallback(fieldId, payload);
    }
    throw e;
  }
};

// ── توزيع ماء المزرعة (POST /api/v1/field-portfolio/allocate) ──
// يوزّع ماء آبار محدودة على حقول متعدّدة وفق الأولويّة والحدّ الأدنى لكلّ حقل،
// فيُظهر أيّ الحقول مَحميّ وأيّها مُجهَد/غير مُلبّى — قرار محفظة لا حقل واحد.
export interface PortfolioFieldInput {
  field_id: string;
  expected_margin: number;
  water_demand_m3: number;
  priority?: number;
  min_water_fraction?: number;
  source_ids?: string[];
}
export interface PortfolioSourceInput {
  source_id: string;
  capacity_m3: number;
}
export interface PortfolioAllocInput {
  fields: PortfolioFieldInput[];
  sources: PortfolioSourceInput[];
}
export interface PortfolioFieldResult {
  field_id: string;
  priority: number;
  water_demand_m3: number;
  allocated_m3: number;
  fraction: number;
  water_productivity: number | null;
  expected_margin_captured: number;
  stressed: boolean;
  status: string; // full | partial | protected_min | unmet
  sources_used: Record<string, number>;
}
export interface PortfolioSourceResult {
  source_id: string;
  capacity_m3: number;
  used_m3: number;
  remaining_m3: number;
}
export interface PortfolioAllocResult {
  fields: PortfolioFieldResult[];
  sources: PortfolioSourceResult[];
  total_expected_margin: number;
  total_allocated_m3: number;
  protected_fields: string[];
  stressed_fields: string[];
  unmet_fields: string[];
  calibrated: boolean;
  warnings_ar: string[];
}
export const computePortfolioAllocation = (payload: PortfolioAllocInput): Promise<PortfolioAllocResult> =>
  kongApi.post<PortfolioAllocResult>('/api/v1/field-portfolio/allocate', payload).then(r => r.data);

// ── استعلام GIS باللغة الطبيعيّة (POST /api/v1/nl-gis/query) — قراءة فقط ──
// يصنّف استعلاماً عربيّاً حرّاً إلى نيّة مغلقة (تنبيه/انخفاض NDVI/فجوة ريّ) ويُعيد
// معاينة قراءة-فقط للحقول المطابقة من بيانات المستأجِر — لا تنفيذ ولا تعديل (read_only).
// خلف العلم FEATURE_NATURAL_LANGUAGE_GIS؛ مُطفأً ⇒ 404 (تلتقطه الواجهة برسالة «الميزة
// غير مُفعَّلة»). 503 ⇒ القاعدة غير متاحة (حالة خطأ صادقة). العناصر متغايرة المفاتيح
// حسب النيّة (تُعرَض أعمدةً ديناميكيّةً)، وقيمها بدائيّات JSON (نصّ/رقم/null؛ التواريخ
// مُنصَّصة مسبقاً). لا fallback وهميّ: الخطأ يُرفع لتعرض الواجهة حالة صادقة عبر
// .response?.status (مطابقةً لبقيّة الصفحات التي تكشف 404).
export interface NlGisQueryInput {
  query: string;
}
// عنصر نتيجة متغاير المفاتيح حسب النيّة — قيمه بدائيّات JSON فقط (لا كائنات متداخلة).
export type NlGisItem = Record<string, string | number | boolean | null>;
export interface NlGisResult {
  read_only:   boolean;
  intent:      string;                 // alert_filter | ndvi_drop | irrigation_gap | unsupported
  supported:   boolean;
  status:      string;                 // ok | needs_data | unsupported
  slots?:      Record<string, string | number | null>;
  confidence?: number;
  api_called?: string;
  items:       NlGisItem[];
  count:       number;
  note_ar?:    string | null;          // شرح الفراغ/الحاجة للبيانات
  reason_ar?:  string | null;          // سبب عدم الدعم (intent=unsupported)
  tenant_id?:  string;
}
/** يستعلم GIS باللغة الطبيعيّة (POST /api/v1/nl-gis/query) — قراءة فقط لا تنفيذ.
 *  يرمي عند الخطأ (404 العلم مُطفأ — تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»؛
 *  503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const queryNlGis = (payload: NlGisQueryInput): Promise<NlGisResult> =>
  kongApi.post<NlGisResult>('/api/v1/nl-gis/query', payload).then(r => r.data);

/** يصدّر الوصفة كـShapefile (ZIP: .shp/.shx/.dbf/.prj) عبر الخادم (مصادقة JWT) — تنزيل ثنائيّ.
 *  Shapefile للمُتحكِّمات الزراعيّة (CultiWise)؛ GeoJSON/CSV يُنتَجان في الواجهة؛ ISOXML TODO. */
export async function exportPrescriptionShapefile(fieldId: string, prescriptionId: string): Promise<Blob> {
  const res = await kongApi.get(
    `/api/v1/fields/${encodeURIComponent(fieldId)}/prescriptions/${encodeURIComponent(prescriptionId)}/export`,
    { params: { format: 'shapefile' }, responseType: 'blob' },
  );
  return res.data as Blob;
}

export interface NlSqlResult {
  sql: string;
}
/** مساعد NL→SQL (POST /api/v1/nl-sql): يُرسِل سؤالاً عربيّاً، يعيد SELECT (للقراءة) يُنفَّذ في
 *  DuckDB العميل. يرمي عند الخطأ (404 العلم مُطفأ · 503 المفتاح مفقود) — تلتقطه الواجهة برسالة صادقة. */
export const generateSqlFromNl = (question: string): Promise<NlSqlResult> =>
  kongApi.post<NlSqlResult>('/api/v1/nl-sql', { question }).then(r => r.data);

// ── دبابيس الاستطلاع الدائمة (FieldView Scouting Pins) ──
// نقطة القراءة GET /api/v1/scouting/pins?field_id=… تُرجِع المشاهدات المُثبَّتة في
// scouting_pins (v94) معزولةً بالمستأجِر (RLS) — تكتبها نقطة الإنشاء
// POST /api/v1/fields/{field_id}/pins. صدق: القاعدة غير مفعّلة ⇒ pins:[] + note_ar
// (لا اختراع مشاهدات)؛ 503 ⇒ القاعدة غير متاحة (حالة خطأ صادقة تكشفها الواجهة).
// الحقول مطابقة لـ ScoutingPin.to_dict في api/scouting_pins.py حقلاً بحقل.
export interface ScoutingPinRecord {
  pin_id:         string;
  field_id:       string;
  lat:            number;
  lng:            number;
  issue_category: string;            // disease|pest|weed|nutrient|water_stress|abiotic|other
  severity:       string;            // low|medium|high
  status:         string;            // new|confirmed|under_treatment|resolved
  persistence:    string;            // seasonal|permanent
  crop:           string | null;
  issue_code:     string | null;     // من الـtaxonomy (مثل tomato.tuta)
  note_ar:        string | null;
  photo_uri:      string | null;
  color:          string | null;     // ترميز لوني (واجهة)
  created_by:     string | null;
  created_at:     string;            // ISO
}

export interface ScoutingPinsResponse {
  field_id: string;
  pins:     ScoutingPinRecord[];
  total:    number;
  note_ar?: string;                  // سبب الفراغ (القاعدة غير مفعّلة)
}

/** يجلب دبابيس مشاهدة الحقل المُخزَّنة (GET /api/v1/scouting/pins?field_id=…). */
export const fetchScoutingPins = (fieldId: string): Promise<ScoutingPinsResponse> =>
  kongApi
    .get<ScoutingPinsResponse>('/api/v1/scouting/pins', { params: { field_id: fieldId } })
    .then(r => r.data);

// حمولة إنشاء دبّوس — مطابقة لـ PinCreateRequest في الخادم (pin_id من العميل،
// idempotency عبر ON CONFLICT). الإنشاء يبقى على نقطة الحقل القائمة (POST).
export interface ScoutingPinCreateInput {
  pin_id:         string;
  field_id:       string;
  lat:            number;
  lng:            number;
  issue_category: string;
  severity?:      string;
  status?:        string;
  persistence?:   string;
  crop?:          string | null;
  issue_code?:    string | null;
  note_ar?:       string | null;
  photo_uri?:     string | null;
  color?:         string | null;
}

// استجابة الإنشاء = الدبّوس المُطبَّع + علم persisted (هل ثُبِّت في القاعدة؟ best-effort).
export type ScoutingPinCreated = ScoutingPinRecord & { persisted?: boolean };

/** ينشئ دبّوس مشاهدة (POST /api/v1/fields/{field_id}/pins) — يتحقّق ثمّ يُديم (RLS). */
export const createScoutingPin = (input: ScoutingPinCreateInput): Promise<ScoutingPinCreated> =>
  kongApi
    .post<ScoutingPinCreated>(
      `/api/v1/fields/${encodeURIComponent(input.field_id)}/pins`,
      input,
    )
    .then(r => r.data);

// ── تقطيع الحقل المُساعَد (POST /api/segmentation/v1/segment) — اقتراح حدّ لا فرضه ──
// خدمة تقطيع الحقول المُوكَّلة عبر البوّابة: تأخذ نطاق (bbox) ووضعاً (تلقائيّ/هجين)
// فتقترح مضلّع حدود يُحمَّل في طبقة الرسم القابلة للتحرير ليؤكّده المستخدم أو يعدّله —
// لا يُعتمَد بلا مراجعة بشريّة. صدق صارم: لا مضلّع مُفبرَك عند غياب النموذج. الخادم
// يردّ 503 برمز model_not_configured حين لا يُهيَّأ نموذج (SAM2/GeoSAM) — تعرضه الواجهة
// كرسالة صريحة وتُبقي الرسم اليدويّ. غياب النشر (404) يُعامَل كـ«غير متاح» بلطف.
// bbox بترتيب GeoJSON: [minLon, minLat, maxLon, maxLat]. mode: auto (تلقائيّ كامل)
// أو hybrid (هجين — تلميح بشريّ + نموذج). قد يُمرَّر field_id/crop اختياريّاً للسياق.
export type SegmentationMode = 'auto' | 'hybrid';
export interface SegmentFieldInput {
  bbox:      [number, number, number, number]; // [minLon, minLat, maxLon, maxLat]
  mode:      SegmentationMode;
  field_id?: string;
  crop?:     string | null;
  // صورة viewport اختيارية: عند زر تلقائي نحاول إرسال لقطة الخريطة كي يطبّق
  // field-segmentation مؤشر ExG قبل SAM2. قد تفشل اللقطة مع مزوّدات بلا CORS.
  image_base64?: string;
  preprocessing?: 'none' | 'exg' | 'auto_exg';
  fallback_to_original_on_low_exg?: boolean;
  // تلميحات نقطيّة [lon, lat] للوضع الهجين (اختياريّة — النموذج يستخدمها كبذور).
  hints?:    Array<[number, number]>;
}
// الردّ الناجح: مضلّع GeoJSON مُقترَح (إحداثيّات [lon, lat]) + ثقة اختياريّة وعلَم
// تقريبيّ. الحقول كلّها دفاعيّة (مصدر نموذج خارجيّ) — تُقرأ بحذر في الواجهة.
export interface SegmentFieldResult {
  // هندسة Polygon GeoJSON المُقترَحة — تُحمَّل في طبقة التحرير للمراجعة.
  geometry:    { type: 'Polygon'; coordinates: number[][][] };
  mode:        SegmentationMode | string;
  confidence?: number | null;     // [0,1] إن توفّرت — تُعرَض كمؤشّر، لا تُعتمَد آليّاً
  source?:     string | null;     // sam2 | geosam | manual | …
  model?:      string | null;     // sam2 | geosam | … (شفافيّة المصدر)
  metadata?:   Record<string, unknown> | null; // model/image/post-processing provenance
  approximate?: boolean;          // علَم صريح أنّ النتيجة تقريبيّة تتطلّب تحريراً
  note_ar?:    string | null;
}

// تصنيف خطأ التقطيع لرسالة صادقة في الواجهة (بلا تخمين، بلا مضلّع مزيّف):
//   model_not_configured → 503 ورمز model_not_configured (نموذج غير مُهيَّأ).
//   unavailable          → 404 (الخدمة غير منشورة) أو 503 بلا رمز معروف.
//   error                → أيّ خطأ آخر (شبكة/4xx/5xx) — يُعرَض نصّه عبر apiErrorMessage.
export type SegmentationErrorKind = 'model_not_configured' | 'unavailable' | 'error';

/** يصنّف خطأ التقطيع إلى نوع تتعامل معه الواجهة بصدق (لا تلفيق هندسة).
 *  503 + detail/error == 'model_not_configured' ⇒ نموذج غير مُهيَّأ (رسالة صريحة).
 *  404 (غير منشورة) ⇒ غير متاح بلطف. ما عداه ⇒ خطأ عامّ يُعرَض نصّه. */
export function classifySegmentationError(e: unknown): SegmentationErrorKind {
  const err = asApiError(e);
  const status = err.response?.status;
  const data = err.response?.data as
    | { detail?: unknown; error?: unknown; code?: unknown }
    | undefined;
  // يقرأ رمز السبب من أيّ من الحقول الشائعة. FastAPI قد يضع detail ككائن
  // {error: "model_not_configured"} وليس كنص فقط.
  const codeFields = [data?.detail, data?.error, data?.code];
  const hasModelCode = codeFields.some((v) => {
    if (typeof v === 'string') return v.includes('model_not_configured');
    if (v && typeof v === 'object') {
      const obj = v as Record<string, unknown>;
      return [obj.error, obj.code, obj.detail].some(
        (x) => typeof x === 'string' && x.includes('model_not_configured'),
      );
    }
    return false;
  });
  if (status === 503 && hasModelCode) return 'model_not_configured';
  if (status === 404) return 'unavailable';
  if (status === 503) return 'unavailable'; // 503 بلا رمز معروف ⇒ الخدمة غير متاحة مؤقّتاً
  return 'error';
}

/** يطلب تقطيعاً مُساعَداً لحدّ الحقل (POST /api/segmentation/v1/segment) — اقتراح فقط.
 *  يرمي عند الخطأ ليصنّفه classifySegmentationError في الواجهة (503 نموذج غير مُهيَّأ
 *  ⇒ رسالة صريحة + رسم يدويّ؛ 404 غير منشورة ⇒ غير متاح بلطف). لا fallback مُفبرَك. */
export const segmentField = (payload: SegmentFieldInput): Promise<SegmentFieldResult> =>
  kongApi.post<SegmentFieldResult>('/api/segmentation/v1/segment', payload, { timeout: 90_000 }).then(r => r.data);

// ── مركز قيادة المحفظة (POST /api/v1/portfolio/command) ──
// يقارن سياسات ريّ متعدّدة عبر حقول المزرعة تحت قيود مصادر الماء، فيُراكِب الربح×المخاطرة
// لكلّ سياسة ويوصي بأفضلها — توصية فقط لا تنفيذ ولا حجز ماء. خلف العلم
// FEATURE_PORTFOLIO_COMMAND؛ مُطفأً ⇒ 404 (تتعامل معه الواجهة برسالة «الميزة غير مُفعَّلة»).
// kind للمصدر: well | pump | pivot | network. للمضخّة: السعة الفعليّة =
// min(capacity, max_rate_m3_per_day × window_days). source_ids على الحقل = أيّ المصادر
// تخدمه (تغطية المحور)؛ فارغة ⇒ كلّ المصادر.
export type PortfolioCommandSourceKind = 'well' | 'pump' | 'pivot' | 'network';
export interface PortfolioCommandFieldInput {
  field_id: string;
  expected_margin: number;
  water_demand_m3: number;
  priority?: number;
  min_water_fraction?: number;
  source_ids?: string[];
}
export interface PortfolioCommandSourceInput {
  source_id: string;
  capacity_m3: number;
  kind?: PortfolioCommandSourceKind;
  max_rate_m3_per_day?: number | null;
  window_days?: number | null;
}
export interface PortfolioCommandScenarioInput {
  policy_label: string;
  fields: PortfolioCommandFieldInput[];
  sources: PortfolioCommandSourceInput[];
}
export interface PortfolioCommandInput {
  scenarios: PortfolioCommandScenarioInput[];
  risk_aversion?: number;
}
// قيد مصدر مُحلّ لسياسة (السعة الفعليّة مقابل الاسميّة + هل قيَّده تدفّقه/نافذته).
export interface PortfolioCommandConstraint {
  source_id: string;
  kind: PortfolioCommandSourceKind | string;
  capacity_m3: number;
  effective_capacity_m3: number;
  throughput_bound: boolean;
}
// التوزيع التفصيليّ لسياسة (نفس عقد field-portfolio/allocate تقريباً) — شكل مرن.
export interface PortfolioCommandAllocation {
  fields: Array<Record<string, unknown>>;
  sources: Array<Record<string, unknown>>;
  total_expected_margin: number;
  total_allocated_m3: number;
  protected_fields: string[];
  stressed_fields: string[];
  unmet_fields: string[];
  calibrated: boolean;
  warnings_ar: string[];
}
export interface PortfolioCommandPolicyResult {
  policy: string;
  total_expected_margin: number;
  total_allocated_m3: number;
  total_demand_m3: number;
  served_fraction: number;
  risk_score: number;
  fields_count: number;
  protected_count: number;
  stressed_count: number;
  unmet_count: number;
  constraints: PortfolioCommandConstraint[];
  constraints_bound: string[];
  objective_score: number;
  allocation: PortfolioCommandAllocation;
}
export interface PortfolioCommandResult {
  policies: PortfolioCommandPolicyResult[];
  recommended_policy: string;
  risk_aversion: number;
  calibrated: boolean;
  warnings_ar: string[];
  tenant_id: string;
}
/** يقارن سياسات الريّ عبر الحقول تحت قيود المصادر (POST /api/v1/portfolio/command).
 *  توصية فقط لا تنفيذ. يرمي عند الخطأ (404 العلم مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503/422 تُعرَض كحالة خطأ صادقة). */
export const computePortfolioCommand = (payload: PortfolioCommandInput): Promise<PortfolioCommandResult> =>
  kongApi.post<PortfolioCommandResult>('/api/v1/portfolio/command', payload).then(r => r.data);

// ── توأم شبكة الريّ (irrigation network feasibility) ──────────────────────────
// المستخدم يُعرّف شبكة ريّ (عُقد + حوافّ: بئر→مضخّة→…→منطقة)، والمحرّك يفحص جدوى
// التنفيذ قبل أيّ ريّ (اتّصاليّة/توفّر ماء/تدفّق/ضغط) ويُبرِز الاختناقات. توصية فقط
// لا تنفيذ ولا فتح صمّامات. القيود غير المحدَّدة تُعرَض صراحةً كـunchecked (لا تُفترَض ناجحة).
export type IrrigationNetworkNodeKind =
  'well' | 'pump' | 'filter' | 'fertilizer' | 'main_line' | 'submain' | 'valve' | 'zone';
export interface IrrigationNetworkNode {
  node_id: string;
  kind: IrrigationNetworkNodeKind;
  capacity_m3?: number | null;
  max_throughput_m3?: number | null;
  max_pressure_bar?: number | null;
  min_pressure_bar?: number | null;
  demand_m3?: number | null;
}
export interface IrrigationNetworkEdge {
  from_id: string;
  to_id: string;
}
export interface IrrigationNetworkInput {
  nodes: IrrigationNetworkNode[];
  edges: IrrigationNetworkEdge[];
}
// حالة جدوى المنطقة: feasible (كلّ الفحوص المعروفة تمرّ ولا شيء غير مفحوص)،
// feasible_unverified (تمرّ المعروفة لكن توجد قيود غير مفحوصة — تُعرَض بلون كهرمانيّ
// مع قائمة unchecked)، infeasible (انتهاك صلب في reasons_ar).
export type IrrigationZoneStatus = 'feasible' | 'feasible_unverified' | 'infeasible';
export interface IrrigationZoneFeasibility {
  zone_id: string;
  demand_m3: number;
  status: IrrigationZoneStatus;
  path: string[] | null;
  reasons_ar?: string[];
  bottlenecks: string[];
  unchecked: string[];
}
export interface IrrigationWellLoad {
  well_id: string;
  capacity_m3: number;
  load_m3: number;
  over_capacity: boolean;
}
export interface IrrigationNetworkResult {
  zones: IrrigationZoneFeasibility[];
  wells: IrrigationWellLoad[];
  overall_feasible: boolean;
  zone_count: number;
  feasible_count: number;
  calibrated: string;
  warnings_ar: string[];
  tenant_id: string;
}
/** يفحص جدوى تنفيذ شبكة الريّ قبل أيّ ريّ (POST /api/v1/irrigation/network/feasibility).
 *  توصية فقط لا تنفيذ ولا فتح صمّامات. يرمي عند الخطأ (404 العلم مُطفأ
 *  FEATURE_IRRIGATION_NETWORK — تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»؛
 *  503/422 تُعرَض كحالة خطأ صادقة). */
export const checkIrrigationNetworkFeasibility = (payload: IrrigationNetworkInput): Promise<IrrigationNetworkResult> =>
  kongApi.post<IrrigationNetworkResult>('/api/v1/irrigation/network/feasibility', payload).then(r => r.data);

// ══════════════════════════════════════════════════════
// CALIBRATION — extracted to services/api/calibration.ts; re-exported for compatibility.
// (DecisionLineage/EvidenceLevel/Lineage*/fetchDecisionLineage are imported at the top of this
//  file too, because the DECISION STUDIO / EVIDENCE MAP sections below still reference them.)
// ══════════════════════════════════════════════════════
export * from './api/calibration';

// ══════════════════════════════════════════════════════════════════
// AGRONOMIC REPLAY — إعادة تشغيل الموسم: خطّ زمنيّ واحد قابل للـscrub يعيد
// تشغيل موسم الحقل كاملاً (NDVI/طقس/ريّ/قرار/نتيجة ميدانيّة) من سجلّات مُدامة
// فقط. تستهلك GET /api/v1/fields/{field_id}/agronomic-replay.
// صدق: العلم مُطفأً (FEATURE_REPLAY_MAP) ⇒ 404؛ القاعدة غير متاحة ⇒ 503. span قد
// يكون null (لا أحداث) ⇒ حالة فارغة صادقة لا خطّ زمنيّ مخترَع. value متغايرة
// (رقم/منطقيّ/كائن/null) — تُصيَّر دفاعيّاً. الأحداث مرتّبة تصاعديّاً بالتاريخ.
// ══════════════════════════════════════════════════════════════════
export type ReplayTrackKey = 'ndvi' | 'weather' | 'irrigation' | 'decision' | 'outcome';

/** وصف مسار (track) واحد: المفتاح + تسميته العربيّة. */
export interface ReplayTrackMeta {
  track:    ReplayTrackKey;
  track_ar: string;
}
/** حدث واحد على الخطّ الزمنيّ. value متغايرة (رقم/منطقيّ/كائن/null). */
export interface ReplayEvent {
  date:     string;          // ISO (تاريخ فقط أو طابع زمنيّ كامل)
  track:    ReplayTrackKey;
  track_ar: string;
  label_ar: string;
  value:    number | boolean | Record<string, unknown> | null;
  ref_id:   string | null;
}
/** نتيجة إعادة التشغيل الكاملة (يطابق عقد agronomic-replay). */
export interface AgronomicReplayResult {
  field_id:        string;
  generated_at:    string;
  tracks:          ReplayTrackMeta[];
  events:          ReplayEvent[];
  counts_by_track: Record<string, number>;
  event_count:     number;
  span:            { start: string; end: string } | null; // null حين لا أحداث
  provenance:      { calibrated: string; note_ar: string };
  source_status?:  Record<string, 'available' | 'empty' | 'unavailable' | 'forbidden' | 'incomplete'>;
  tenant_id:       string;
}

export const fetchAgronomicReplay = (fieldId: string): Promise<AgronomicReplayResult> =>
  kongApi
    .get<AgronomicReplayResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/agronomic-replay`)
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// EVIDENCE MAP — خريطة الدليل (GET /api/v1/evidence/map) — قراءة فقط ──
// لكلّ حقل للمستأجِر: مستوى الدليل خلف قراراته (مؤكَّد/مدعوم/إرشاديّ/يحتاج بيانات)
// على خريطة 2D حقيقيّة + قائمة. خلف العلم FEATURE_EVIDENCE_MAP؛ مُطفأً ⇒ 404
// (تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»). 503 ⇒ القاعدة غير متاحة (حالة خطأ
// صادقة). صدق: مستوى الدليل من القرارات/القياسات المُدامة فقط؛ عتبة التحقّق الميدانيّ
// تقديريّة. الحقول بلا إحداثيّات (has_coords=false) لا تُرسَم (لا إحداثيّات مُختلَقة).
// needs_data «لا دليل بعد» صادق (رماديّ) لا حالة إيجابيّة. لا fallback وهميّ: الخطأ
// يُرفع لتعرض الواجهة حالة صادقة عبر .response?.status (مطابقةً لبقيّة صفحات العلم).
export type EvidenceMapTier =
  | 'field_verified' | 'field_preliminary' | 'indicative' | 'needs_data';
// لون الفئة من الخادم — يُربَط بألوان CSS/علامات محدّدة في الواجهة (لا فئات إضافيّة).
export type EvidenceMapColor = 'green' | 'amber' | 'blue' | 'gray';
export interface EvidenceMapLegendItem {
  tier:    EvidenceMapTier;
  tier_ar: string;
  color:   EvidenceMapColor | string;
}
export interface EvidenceMapField {
  field_id:            string;
  name:                string;
  crop:                string;
  gov:                 string;
  lat:                 number | null;
  lon:                 number | null;
  has_coords:          boolean;       // false ⇒ لا يُرسَم (لا إحداثيّات مُختلَقة)
  decisions:           number;
  outcomes:            number;
  successes:           number;
  success_rate:        number | null; // null ⇒ «—» (لا تلفيق)
  samples_to_verified: number;
  last_outcome_at:     string | null;
  tier:                EvidenceMapTier;
  tier_ar:             string;
  color:               EvidenceMapColor | string;
}
export interface EvidenceMapResult {
  generated_at:       string;
  legend:             EvidenceMapLegendItem[];
  fields:             EvidenceMapField[];
  totals_by_tier:     Record<string, number>;
  field_count:        number;
  plottable_count:    number;
  verified_threshold: number;
  provenance:         { calibrated: string; note_ar: string };
  tenant_id:          string;
}
/** يجلب خريطة الدليل (GET /api/v1/evidence/map) — قراءة فقط لا تنفيذ.
 *  يرمي عند الخطأ (404 العلم مُطفأ — تلتقطه الواجهة برسالة «الميزة غير مُفعَّلة»؛
 *  503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchEvidenceMap = (): Promise<EvidenceMapResult> =>
  kongApi.get<EvidenceMapResult>('/api/v1/evidence/map').then(r => r.data);

// ── توائم الأجهزة وثقة الحسّاس (Device Twin & Sensor Confidence) — قراءة فقط ──
// لكلّ جهاز IoT توأم رقميّ: هويّة + حالة + درجة صحّة/ثقة شفّافة (موزونة على الإشارات
// المتوفّرة فقط)، مع تلخيص ثقة الأسطول. صدق: missing_signals مُعلَنة لا مُفترَضة؛
// health_score/fleet_confidence قد تكون null ⇒ «غير محسوبة» لا 0. لا أوامر تشغيل.
// level من الخادم (healthy|degraded|stale|offline|poor|unknown) — تُربَط بألوان الواجهة.
export type DeviceTwinLevel =
  | 'healthy' | 'degraded' | 'stale' | 'offline' | 'poor' | 'unknown';
export interface DeviceTwin {
  device_id:       string;
  name:            string;
  type:            string;
  field_id:        string | null;
  status:          string;
  firmware:        string | null;
  age_sec:         number | null;            // ثوانٍ منذ آخر ظهور؛ null ⇒ لم يُرسِل بعد
  health_score:    number | null;            // 0..1، أو null عند الغياب ⇒ «—»
  level:           DeviceTwinLevel | string;
  level_ar:        string;
  factors:         Record<string, number>;   // الإشارات المتوفّرة فقط
  missing_signals: string[];                  // مُعلَنة لا مُفترَضة
  note_ar:         string | null;
}
export interface DeviceTwinResult {
  generated_at:     string;
  devices:          DeviceTwin[];
  device_count:     number;
  scored_count:     number;
  by_level:         Record<string, number>;
  fleet_confidence: number | null;           // متوسّط المُسجَّلين؛ null ⇒ «غير محسوبة»
  provenance:       { calibrated: string; note_ar: string };
  tenant_id:        string;
}
/** يجلب توائم الأجهزة (GET /api/v1/devices/twin) — قراءة فقط لا أوامر.
 *  يرمي عند الخطأ (404 العلم FEATURE_DEVICE_TWIN مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchDeviceTwin = (): Promise<DeviceTwinResult> =>
  kongApi.get<DeviceTwinResult>('/api/v1/devices/twin').then(r => r.data);

// ── رصد حلقة التنفيذ (Execution Feedback) — قراءة فقط ──
// تستهلك GET /api/v1/execution/feedback: لكلّ قرار حديث هل نُفِّذ (من سجلّ التنفيذ)
// وهل طابقت النتيجة الخطّة — إغلاق حلقة القرار→التنفيذ→النتيجة. لا إصدار أوامر ولا
// إعادة تنفيذ. صدق: loop_status من سجلّات مُدامة فقط؛ execution_unknown «يحتاج بيانات»
// (رماديّ) لا «نُفِّذ»؛ executed_unmeasured كهرمانيّ لا نجاح؛ closure_rate قد تكون null.
export type ExecutionLoopStatus =
  | 'closed_ok' | 'executed_off_plan' | 'executed_unmeasured' | 'execution_failed' | 'execution_unknown';
export interface ExecutionFeedbackDecision {
  decision_id:       string;
  decision_type:     string;
  field_id:          string | null;
  created_at:        string;
  execution_outcome: 'executed' | 'failed' | null; // null ⇒ لا قيد في سجلّ التنفيذ
  executed_at:       string | null;
  exec_note_ar:      string | null;
  outcome_measured:  boolean;
  outcome_success:   boolean | null;               // null حين لا تُقاس ⇒ «—» لا false
  loop_status:       ExecutionLoopStatus;
  loop_status_ar:    string;
  color:             'green' | 'red' | 'amber' | 'gray';
  note_ar:           string | null;                // تفسير صادق للحالة المجهولة/غير المقيسة
}
export interface ExecutionFeedbackResult {
  generated_at:   string;
  decisions:      ExecutionFeedbackDecision[];
  decision_count: number;
  by_status:      Record<ExecutionLoopStatus, number>;
  totals:         { executed: number; failed: number; measured: number; closed_ok: number };
  closure_rate:   number | null;                   // closed_ok/executed؛ null حين لا تنفيذ ⇒ «غير محسوبة»
  provenance:     { calibrated: string; note_ar: string };
  tenant_id:      string;
}
/** يجلب رصد حلقة التنفيذ (GET /api/v1/execution/feedback) — قراءة فقط لا أوامر.
 *  يرمي عند الخطأ (404 العلم FEATURE_EXECUTION_FEEDBACK مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchExecutionFeedback = (): Promise<ExecutionFeedbackResult> =>
  kongApi.get<ExecutionFeedbackResult>('/api/v1/execution/feedback').then(r => r.data);

// ── ثقة القرار الموحَّدة (Decision Confidence) — قراءة فقط، نطاق حقل ──
// GET /api/v1/fields/{id}/decision-confidence: درجة ثقة موحَّدة مدموجة من أربعة
// مصادر (حسّاس + دليل ميدانيّ + استشعار + طقس)، كلٌّ بوزنه وقيمته وتوفّره. صدق:
// confidence/level قد تكونان null/«insufficient» حين لا مصدر متاح ⇒ «غير كافية»
// (رماديّ) لا 0%. كلّ مكوّن يُعلِن available — غير المتوفّر رماديّ «يحتاج بيانات» لا
// مساهم بصفر. الدرجة المدموجة محسوبة خادميّاً على المتوفّر فقط — عرض فقط لا تعديل.
// العلم FEATURE_DECISION_CONFIDENCE مُطفأً ⇒ 404 (تلتقطه الواجهة برسالة «الميزة غير
// مُفعَّلة»)؛ 503 ⇒ القاعدة غير متاحة (حالة خطأ صادقة). لا fallback وهميّ.
export type DecisionConfidenceLevel = 'high' | 'medium' | 'low' | 'insufficient';
export interface DecisionConfidenceComponent {
  source:    string;          // sensor | evidence | satellite | weather
  label_ar:  string;
  weight:    number;          // 0..1
  value:     number | null;   // 0..1، أو null حين غير متوفّر ⇒ «—» (لا 0)
  available: boolean;         // false ⇒ رماديّ «يحتاج بيانات» (لا مساهم بصفر)
  detail_ar: string;
}
export interface DecisionConfidenceResult {
  generated_at:  string;
  confidence:    number | null;            // 0..1، أو null حين لا مصدر ⇒ «غير كافية» (لا 0)
  level:         DecisionConfidenceLevel | string;
  level_ar:      string;
  components:    DecisionConfidenceComponent[];
  present_count: number;
  missing:       string[];
  provenance:    { calibrated: string; note_ar: string };
  field_id:      string;
  tenant_id:     string;
}
/** يجلب ثقة القرار الموحَّدة لحقل (GET /api/v1/fields/{id}/decision-confidence) — قراءة فقط.
 *  يرمي عند الخطأ (404 العلم FEATURE_DECISION_CONFIDENCE مُطفأ — تلتقطه الواجهة برسالة
 *  «الميزة غير مُفعَّلة»؛ 503 القاعدة غير متاحة تُعرَض كحالة خطأ صادقة). */
export const fetchDecisionConfidence = (fieldId: string): Promise<DecisionConfidenceResult> =>
  kongApi
    .get<DecisionConfidenceResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/decision-confidence`)
    .then(r => r.data);

// ── لوحة رصد التعلّم/النَّسَب (قراءة فقط) — سرد القرارات المُدامة + تلخيص حلقة التعلّم ──
// تستهلك GET /api/v1/decision/records (سرد القرارات المُدامة للمستأجِر، معزولة بـRLS):
//   {decisions: DecisionRecord[], count}. شكل القرار مطابق لـ_shape_decision_row
//   (نفس LineageDecision: decision_id/field_id/decision_type/region/stage/decision_value/
//   confidence/created_by/created_at). صدق: لا fallback وهميّ — 503 (تعذّر القاعدة)
//   يُرفع لتعرض الواجهة حالة صادقة.
export type DecisionRecord = LineageDecision;
export interface DecisionRecordsResult {
  decisions: DecisionRecord[];
  count:     number;
  degraded?: boolean;
  source?:   string;
  reason?:   string;
  status_code?: number;
  warning_ar?: string;
}
export const fetchDecisionRecords = (limit = 200): Promise<DecisionRecordsResult> =>
  kongApi
    .get<DecisionRecordsResult>('/api/v1/decision/records', { params: { limit } })
    .then(r => ({
      decisions: Array.isArray(r.data?.decisions) ? r.data.decisions : [],
      count: typeof r.data?.count === 'number' ? r.data.count : 0,
      degraded: Boolean(r.data?.degraded),
      source: r.data?.source,
      reason: r.data?.reason,
      status_code: r.data?.status_code,
      warning_ar: r.data?.warning_ar,
    }))
    .catch((err) => {
      // Learning/lineage dashboard is a read-side observability surface. If the
      // authoritative platform read is unavailable (404/502/503/504), degrade to an
      // honest empty state — never fabricate numbers — instead of collapsing the page.
      // Auth/RBAC failures (401/403) stay hard: they are not availability degradation.
      const status = err?.response?.status;
      if ([404, 502, 503, 504].includes(status)) {
        return {
          decisions: [],
          count: 0,
          degraded: true,
          source: 'sahool-platform',
          reason: 'decision_records_unavailable',
          status_code: status,
          warning_ar: 'تعذّر جلب سجلّ القرارات المُدامة. تُعرَض اللوحة كحالة متدهورة صادقة دون أرقام مُلفَّقة.',
        };
      }
      throw err;
    });

// تلخيص حلقة التعلّم لكلّ منطقة (GET /api/v1/learning/summary) — قد لا تتوفّر النقطة بعد.
// صدق: نستهلكها إن نجحت، ونُعيد null عند 404/أيّ خطأ (لا تلفيق) فتعرض الواجهة حالةً
// فارغة صادقة بدل أرقام مُختلَقة. الشكل دفاعيّ (كلّ الحقول اختياريّة) لتفادي افتراض
// عقد غير مُثبَّت في هذا الفرع.
export interface LearningSummaryRegion {
  region?:                     string;
  sample_count?:               number;
  evidence_level?:             EvidenceLevel | string;
  success_rate?:               number | null;
  outcome_count?:              number;
  samples_to_verified?:        number;
  field_verified_min_samples?: number;
  calibrated?:                 boolean;
  warnings_ar?:                string[];
}
export interface LearningSummary {
  regions?:           LearningSummaryRegion[];
  decision_count?:    number;
  outcome_count?:     number;
  success_rate?:      number | null;
  regions_verified?:  number;
  calibrated?:        boolean;
  warnings_ar?:       string[];
  [k: string]:        unknown;
}
/** يجلب تلخيص حلقة التعلّم. أفضل-جهد: أيّ خطأ/استجابة غير صالحة (404 نقطة غير
 *  مُتاحة بعد، 503 DB) ⇒ null فتعرض الواجهة حالةً فارغة صادقة (لا تلفيق). */
export const fetchLearningSummary = (): Promise<LearningSummary | null> =>
  kongApi
    .get<LearningSummary>('/api/v1/learning/summary')
    .then((r) => (r.data && typeof r.data === 'object' ? r.data : null))
    .catch(() => null);

// ══════════════════════════════════════════════════════════════════
// DECISION STUDIO — شرح القرار (Signals → Policy → Constraints → Final) + إعادة
// التشغيل (قراءة فقط). تستهلك أوّلاً GET /api/v1/decision/{id}/explain (خلف العلم
// FEATURE_DECISION_STUDIO؛ قد يكون مُطفأً ⇒ 404)، وترتدّ عند 404 إلى السلسلة
// المُدامة GET /api/v1/decision/{id}/lineage فتشتقّ منها شرحاً صادقاً من
// decision_value (policy_decision.reasons_ar/risks/confidence). صدق: لا تلفيق —
// القرار غير المُدام يُعرَض «غير متاح»، وغياب المعايرة (calibrated=false) يُبرَز.
// ══════════════════════════════════════════════════════════════════

/** إشارة قرار واحدة (مدخَل أثّر في القرار) — مع حالة لونيّة صادقة من الخادم. */
export interface DecisionSignal {
  key:      string;
  label_ar: string;
  value:    unknown;
  status:   string; // ok | warn | risk | info | neutral … (من الخادم، لا نفترض حصراً)
}
/** قرار السياسة المُحلّ (auto/manual) مع أسبابه العربيّة. */
export interface DecisionPolicyView {
  resolved:   string | null;
  applied:    string | null;
  auto:       boolean;
  reasons_ar: string[];
}
/** قيد واحد على القرار (سقف ميزانيّة/تطبيق…). شكل مرن (الخادم قد يثريه). */
export interface DecisionConstraint {
  key?:      string;
  label_ar?: string;
  value?:    unknown;
  [k: string]: unknown;
}
/** جوهر الشرح: ثقة + إشارات + سياسة + قيود + القرار النهائيّ. */
export interface DecisionExplanation {
  confidence:  number | null;
  calibrated:  boolean;          // false ⇒ تقديريّ غير مُعايَر (يُبرَز صراحةً)
  signals:     DecisionSignal[];
  policy:      DecisionPolicyView | null;
  constraints: DecisionConstraint[];
  final:       Record<string, unknown>;
  warnings_ar: string[];
}
/** نتيجة الشرح الكاملة: شرح + «ماذا حدث فعلاً» (outcomes) + دليل. */
export interface DecisionExplainResult {
  decision_id:   string;
  decision_type: string;
  found:         boolean;        // false ⇒ القرار غير مُدام (لا نختلق شرحاً)
  source:        'explain' | 'lineage_derived'; // من أين جاء الشرح (شفافيّة)
  explanation:   DecisionExplanation | null;
  outcomes:      LineageOutcome[];
  evidence:      Record<string, unknown> | null;
}

// شكل ردّ /explain الخام من الخادم (حين يكون العلم مُفعَّلاً) — كلّ الحقول دفاعيّة.
interface RawExplainResponse {
  decision_id?:   string;
  decision_type?: string;
  found?:         boolean;
  explanation?: {
    confidence?:  number | null;
    calibrated?:  boolean;
    signals?:     Partial<DecisionSignal>[];
    policy?: {
      resolved?:   string | null;
      applied?:    string | null;
      auto?:       boolean;
      reasons_ar?: string[];
    } | null;
    constraints?: DecisionConstraint[];
    final?:       Record<string, unknown>;
    warnings_ar?: string[];
  } | null;
  outcomes?: LineageOutcome[];
  evidence?: Record<string, unknown> | null;
}

// يطبّع ردّ /explain الخام إلى DecisionExplainResult (حقول غائبة ⇒ افتراضات صادقة).
function _normalizeExplain(d: RawExplainResponse, decisionId: string): DecisionExplainResult {
  const ex = d.explanation ?? null;
  return {
    decision_id:   d.decision_id ?? decisionId,
    decision_type: d.decision_type ?? '—',
    found:         d.found ?? !!ex,
    source:        'explain',
    explanation: ex
      ? {
          confidence:  typeof ex.confidence === 'number' ? ex.confidence : null,
          calibrated:  ex.calibrated === true,
          signals:     (ex.signals ?? []).map((s) => ({
            key:      String(s.key ?? ''),
            label_ar: String(s.label_ar ?? s.key ?? ''),
            value:    s.value ?? null,
            status:   String(s.status ?? 'neutral'),
          })),
          policy: ex.policy
            ? {
                resolved:   ex.policy.resolved ?? null,
                applied:    ex.policy.applied ?? null,
                auto:       ex.policy.auto === true,
                reasons_ar: Array.isArray(ex.policy.reasons_ar) ? ex.policy.reasons_ar : [],
              }
            : null,
          constraints: Array.isArray(ex.constraints) ? ex.constraints : [],
          final:       ex.final && typeof ex.final === 'object' ? ex.final : {},
          warnings_ar: Array.isArray(ex.warnings_ar) ? ex.warnings_ar : [],
        }
      : null,
    outcomes: Array.isArray(d.outcomes) ? d.outcomes : [],
    evidence: d.evidence && typeof d.evidence === 'object' ? d.evidence : null,
  };
}

// يقرأ مصفوفة نصوص عربيّة بأمان من قيمة مجهولة (reasons_ar/risks/warnings الخام).
function _strList(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v
    .map((x) =>
      typeof x === 'string'
        ? x
        : typeof x === 'object' && x
          ? String(
              (x as Record<string, unknown>).label_ar ??
                (x as Record<string, unknown>).level_ar ??
                '',
            )
          : String(x ?? ''),
    )
    .filter(Boolean);
}

// يشتقّ شرحاً صادقاً من decision_value المُدام (ارتداد عند 404 على /explain).
// الإشارات تُبنى من الحقائق المُدامة فعلاً فقط (لا اختلاق): ثقة/سياسة/مخاطر/تحذيرات.
function _deriveFromLineage(lin: DecisionLineage): DecisionExplainResult {
  const dec = lin.decision;
  if (!dec) {
    return {
      decision_id:   lin.decision_id,
      decision_type: '—',
      found:         false,
      source:        'lineage_derived',
      explanation:   null,
      outcomes:      lin.outcomes,
      evidence:      null,
    };
  }
  const val = dec.decision_value ?? {};
  const pd = (val.policy_decision ?? null) as Record<string, unknown> | null;
  const confidence =
    typeof dec.confidence === 'number'
      ? dec.confidence
      : typeof val.confidence === 'number'
        ? (val.confidence as number)
        : null;
  const calibrated = val.calibrated === true;

  // إشارات من الحقائق المُدامة (كلّ إشارة مرتبطة بقيمة فعليّة موجودة — لا اختلاق).
  const signals: DecisionSignal[] = [];
  const ws = (val.water_state ?? null) as Record<string, unknown> | null;
  if (ws && typeof ws.needs_irrigation === 'boolean') {
    signals.push({
      key: 'needs_irrigation',
      label_ar: 'حاجة الريّ',
      value: ws.needs_irrigation ? 'نعم' : 'لا',
      status: ws.needs_irrigation ? 'warn' : 'ok',
    });
  }
  const irr = (val.irrigation ?? null) as Record<string, unknown> | null;
  if (irr && typeof irr.stress_days === 'number') {
    signals.push({
      key: 'stress_days',
      label_ar: 'أيّام الإجهاد',
      value: irr.stress_days,
      status: (irr.stress_days as number) > 0 ? 'risk' : 'ok',
    });
  }
  if (typeof val.data_quality === 'string') {
    signals.push({ key: 'data_quality', label_ar: 'جودة البيانات', value: val.data_quality, status: 'info' });
  }
  for (const r of (Array.isArray(val.risks) ? val.risks : []) as Record<string, unknown>[]) {
    if (r && typeof r === 'object') {
      signals.push({
        key: String(r.key ?? 'risk'),
        label_ar: String(r.label_ar ?? 'مخاطرة'),
        value: String(r.level_ar ?? ''),
        status: 'risk',
      });
    }
  }

  const policy: DecisionPolicyView | null = pd
    ? {
        resolved:   (pd.resolved_policy as string) ?? null,
        applied:    (pd.applied_policy as string) ?? null,
        auto:       pd.auto === true,
        reasons_ar: _strList(pd.reasons_ar),
      }
    : null;

  // القيود: سقوف التطبيق/الميزانيّة إن أُدِيمت فعلاً (لا نخترعها).
  const constraints: DecisionConstraint[] = [];
  if (irr && irr.policy != null) constraints.push({ key: 'policy', label_ar: 'سياسة الريّ', value: irr.policy });
  if (irr && irr.total_mm != null) constraints.push({ key: 'total_mm', label_ar: 'إجماليّ الريّ (مم)', value: irr.total_mm });

  // القرار النهائيّ: ملخّص الأفعال المُدامة (ريّ/تسميد) — أرقام حقيقيّة لا مُلفَّقة.
  const final: Record<string, unknown> = {};
  if (irr && irr.action_ar != null) final['الريّ'] = irr.action_ar;
  const fert = (val.fertilization ?? null) as Record<string, unknown> | null;
  if (fert && fert.action_ar != null) final['التسميد'] = fert.action_ar;

  return {
    decision_id:   lin.decision_id,
    decision_type: dec.decision_type,
    found:         true,
    source:        'lineage_derived',
    explanation: {
      confidence,
      calibrated,
      signals,
      policy,
      constraints,
      final,
      warnings_ar: _strList(val.warnings_ar),
    },
    outcomes: lin.outcomes,
    evidence: null,
  };
}

/** يجلب شرح القرار: يجرّب /explain أوّلاً، ويرتدّ عند 404 (العلم مُطفأ) إلى
 *  /lineage فيشتقّ شرحاً صادقاً من decision_value. أيّ خطأ آخر (503/403) يُرفع
 *  لتعرض الواجهة حالة خطأ صادقة. */
export const fetchDecisionExplain = (decisionId: string): Promise<DecisionExplainResult> => {
  const id = decisionId.trim();
  return kongApi
    .get<RawExplainResponse>(`/api/v1/decision/${encodeURIComponent(id)}/explain`)
    .then((r) => _normalizeExplain(r.data ?? {}, id))
    .catch((e: unknown) => {
      // 404 فقط ⇒ العلم FEATURE_DECISION_STUDIO مُطفأ/النقطة غير موجودة: ارتدّ للنسَب.
      if (asApiError(e).response?.status === 404) {
        return fetchDecisionLineage(id).then(_deriveFromLineage);
      }
      throw e;
    });
};


// ══════════════════════════════════════════════════════════════════
// FIELD GEOMETRY HISTORY — Timeline + Comparison Mode source.
// تستهلك GET /api/v1/fields/{field_id}/geometry/history. لا fallback وهميّ:
// إن تعذّر الجلب يظهر الخطأ في الواجهة، وإن لم توجد مراجعات تعرض الواجهة الحالي فقط.
// ══════════════════════════════════════════════════════════════════
export interface FieldGeometryHistoryRevision {
  revision:   number;
  geometry:   unknown;
  changed_by: string | null;
  changed_at: string | null;
  reason:     string | null;
  source:     string | null;
  metadata:   Record<string, unknown>;
}
export interface FieldGeometryHistory {
  field_id: string;
  revisions: FieldGeometryHistoryRevision[];
}
export const fetchFieldGeometryHistory = (
  fieldId: string,
  limit = 50,
): Promise<FieldGeometryHistory> => kongApi
  .get<FieldGeometryHistory>(`/api/v1/fields/${encodeURIComponent(fieldId)}/geometry/history`, {
    params: { limit },
  })
  .then((r) => {
    const d = r.data ?? ({} as FieldGeometryHistory);
    return {
      field_id: d.field_id ?? fieldId,
      revisions: Array.isArray(d.revisions) ? d.revisions.map((rev) => ({
        revision: Number(rev.revision),
        geometry: rev.geometry,
        changed_by: rev.changed_by ?? null,
        changed_at: rev.changed_at ?? null,
        reason: rev.reason ?? null,
        source: rev.source ?? null,
        metadata: rev.metadata && typeof rev.metadata === 'object' ? rev.metadata : {},
      })).filter((rev) => Number.isFinite(rev.revision)) : [],
    };
  });

// ══════════════════════════════════════════════════════════════════
// AGRONOMIC TIMELINE — الخطّ الزمنيّ الموحّد للحقل (مثل Git history، قراءة فقط).
// تستهلك GET /api/v1/fields/{field_id}/unified-timeline (assemble_timeline:
// تصنيف+فرز+إحصاءات عبر RLS). صدق: عند تعطّل القاعدة يُرجِع خطّاً فارغاً + note_ar
// (لا تاريخ مخترَع) — تعرضه الواجهة EmptyState. لا fallback وهميّ.
// ══════════════════════════════════════════════════════════════════
export type AgronomicTimelineCategory =
  | 'lifecycle' | 'operation' | 'observation' | 'calibration' | 'weather' | 'system' | string;

/** حدث واحد في الخطّ الزمنيّ (يطابق TimelineEvent.to_dict الخلفيّ). */
export interface UnifiedTimelineEvent {
  timestamp:   string;
  event_type:  string;
  category:    AgronomicTimelineCategory;
  summary_ar:  string;
  actor_id:    string | null;
  payload:     Record<string, unknown>;
}
/** الخطّ الزمنيّ الكامل (يطابق FieldTimeline.to_dict). */
export interface UnifiedTimeline {
  field_id:        string;
  total_events:    number;
  earliest_at:     string | null;
  latest_at:       string | null;
  category_counts: Record<string, number>;
  events:          UnifiedTimelineEvent[];
  note_ar?:        string; // يظهر عند تعطّل القاعدة (لا تاريخ حيّ) — حالة فارغة صادقة
  error?:          string; // يظهر عند فشل الجلب الداخليّ (الخادم يُعلنه لا يخترع)
}

export const fetchUnifiedTimeline = (
  fieldId: string,
  opts: { limit?: number; newestFirst?: boolean; category?: string } = {},
): Promise<UnifiedTimeline> => {
  const { limit = 200, newestFirst = true, category } = opts;
  return kongApi
    .get<UnifiedTimeline>(`/api/v1/fields/${encodeURIComponent(fieldId)}/unified-timeline`, {
      params: {
        limit,
        newest_first: newestFirst,
        ...(category ? { category } : {}),
      },
    })
    .then((r) => {
      const d = r.data ?? ({} as UnifiedTimeline);
      return {
        field_id:        d.field_id ?? fieldId,
        total_events:    typeof d.total_events === 'number' ? d.total_events : 0,
        earliest_at:     d.earliest_at ?? null,
        latest_at:       d.latest_at ?? null,
        category_counts: d.category_counts && typeof d.category_counts === 'object' ? d.category_counts : {},
        events:          Array.isArray(d.events) ? d.events : [],
        note_ar:         d.note_ar,
        error:           d.error,
      };
    });
};

// ── قرار المحصول الموحّد (POST /api/v1/crop-twin/decision) ──
// ريّ + تسميد + مخاطر + ثقة من حالة محصول واحدة. الاقتصاد محجوز (not_configured).
export interface CropDecisionForecastDay {
  t_min_c: number; t_max_c: number; et0_mm: number;
  kc?: number | null; rain_mm?: number; irrigation_mm?: number; runoff_mm?: number;
}
export interface CropDecisionInput {
  field_id?: string | null;
  crop?: string | null;
  stage?: string;
  forecast: CropDecisionForecastDay[];
  ndvi?: number | null;
  soil?: { texture?: string | null; root_depth_m?: number | null; raw_fraction?: number; taw_mm?: number | null };
  management?: { target_uptake_kg_ha?: number; initial_depletion_mm?: number; auto_irrigate?: boolean };
  policy?: string;
  max_application_mm?: number | null;
  season_budget_mm?: number | null;
  water_price_per_m3?: number | null;
  yield_value_per_ha?: number | null;
}
export interface UnifiedRisk { key: string; label_ar: string; level_ar: string }
export interface UnifiedFlag { code: string; label_ar: string }
export interface CropDecisionResult {
  crop: string | null;
  crop_known: boolean;
  dynamic_kc: number;
  phenology: { stage: string; progress: number; past_maturity: boolean; gdd_cumulative?: number };
  water_state: { taw_mm: number; raw_mm: number; depletion_mm: number; depletion_pct?: number; needs_irrigation: boolean };
  nutrient_state: { stage: string | null; target_uptake_kg_ha: number; uptake_to_date_kg_ha: number };
  irrigation: {
    policy: string; total_mm: number; n_events: number;
    next_event_day: number | null; next_event_mm: number; stress_days: number; action_ar: string;
  };
  fertilization: {
    stage: string | null; uptake_to_date_kg_ha: number; remaining_need_kg_ha: number; due: boolean; action_ar: string;
  };
  risks: UnifiedRisk[];
  stress_flags: UnifiedFlag[];
  confidence: number;
  data_quality: string;
  assumptions: string[];
  assumptions_ar: string[];
  economic_state: EconomicState;
  calibrated: boolean;
  warnings_ar: string[];
}
export interface EconomicState {
  status: string;                       // not_configured | partial | ok
  required_inputs?: string[];
  gross_revenue?: number | null;
  water_cost?: number | null;
  energy_cost?: number | null;
  fertilizer_cost?: number | null;
  total_cost?: number | null;
  expected_margin?: number | null;
  margin_uncertainty?: number | null;
  confidence?: number;
  missing_inputs?: string[];
}
export const computeCropDecision = (payload: CropDecisionInput): Promise<CropDecisionResult> =>
  kongApi.post<CropDecisionResult>('/api/v1/crop-twin/decision', payload).then(r => r.data);

// ── القرار الواعي بالربح (POST /api/v1/crop-twin/decision/profit-aware) ──
export interface ProfitAwareDecisionInput extends CropDecisionInput {
  auto_policy?: boolean;
  water_source?: string | null;
  water_cost?: string | null;
  energy_cost?: string | null;
  region?: string | null;
  expected_yield_t_ha?: number | null;
  crop_price_per_t?: number | null;
  energy_kwh_ha?: number | null;
  energy_price_per_kwh?: number | null;
  fertilizer_price_per_kg?: number | null;
}
export interface PolicyDecision {
  resolved_policy: string;
  applied_policy: string;
  auto: boolean;
  reasons_ar: string[];
}
export interface ProfitAwareDecisionResult extends CropDecisionResult {
  policy_decision: PolicyDecision;
}
export const computeProfitAwareDecision = (payload: ProfitAwareDecisionInput): Promise<ProfitAwareDecisionResult> =>
  kongApi.post<ProfitAwareDecisionResult>('/api/v1/crop-twin/decision/profit-aware', payload).then(r => r.data);

export interface PestEscalationInput {
  workflow_id: string;
  field_id?: string;
  pest_type?: string;
  severity?: number;
  approval_status?: string; // للاستئناف بعد التعليق: approved/rejected
}
export interface WorkflowTrace {
  workflow_id: string;
  status: string; // running|suspended|completed|failed|compensated
  completed_steps: string[];
  compensated_steps: string[];
  current_step: string | null;
  steps_done: number;
  error: string | null;
}
export interface PestEscalationResult {
  workflow: WorkflowTrace;
  context: Record<string, unknown>;
  step_results: Record<string, Record<string, unknown>>;
}
export const runPestEscalation = (payload: PestEscalationInput): Promise<PestEscalationResult> =>
  kongApi.post<PestEscalationResult>('/api/v1/pest-escalation/run', payload).then(r => r.data);

export interface FieldRecommendationInput {
  field_id: string;
  farm_id?: string;
  crop: string;
  current_indicators?: Record<string, unknown>;
  growth_stage?: string;
  district_id?: string;
}
export interface RecommendationResult {
  delivered: boolean;
  rec_id?: string;
  // مخرجات المحرّك الحقيقيّ: {status, headline, quality_grade, confidence, ...}
  recommendation?: Record<string, unknown>;
  cross_reference_count?: number;
  cross_reference_note_ar?: string;
  model_versions_count?: number;
  timestamp?: string;
  reason_ar?: string; // عند delivered=false (محجوب/مرفوض)
}
// نقبل فقط الحالات المقصودة: 200 (مُسلَّمة) و422/403 (محجوب/مرفوض ⇒ reason_ar).
// نترك 401 تُرفض ليعمل interceptor تسجيل الخروج، و400/500 تُعامَل كأخطاء فعليّة.
export const getFieldRecommendation = (
  payload: FieldRecommendationInput,
): Promise<RecommendationResult> =>
  kongApi
    .post<RecommendationResult>('/api/v1/recommendations/for-field', payload, {
      validateStatus: (s) => s === 200 || s === 422 || s === 403,
    })
    .then(r => r.data);

// TTS — تحويل نصّ عربيّ إلى صوت (صوت يمنيّ). يُرجِع MP3 كـBlob للتشغيل في المتصفّح.
// قيمة للأمّيّين/ضعاف البصر: قراءة التوصيات/التنبيهات صوتيّاً.
export const synthesizeSpeech = (text: string, voice?: string): Promise<Blob> =>
  kongApi
    .post('/tts/synthesize', { text, ...(voice ? { voice } : {}) }, { responseType: 'blob' })
    .then(r => r.data as Blob);

// المايسترو — التحليل الموحّد لحقل (operational truths + قرار السياسة + تنبيهات).
export interface FieldIntelInput {
  field_id: string;
  lat?: number;
  lon?: number;
  crop?: string;
}
export interface FieldIntelResult {
  field_id: string;
  generated_at?: string;
  operational_truths?: Record<string, unknown>;
  confidence?: string; // high | medium | low | none — نصّ من المحرّك (لا رقم)
  confidence_reason?: string;
  contradictions?: unknown[];
  missing_signals?: unknown[];
  policy_decision?: Record<string, unknown>;
  governance?: Record<string, unknown>;
  alerts?: Record<string, unknown>[];
  alerts_summary?: Record<string, unknown>;
  simulation?: Record<string, unknown>;
  provenance?: unknown[]; // قائمة لقطات المصدريّة (list لا object)
  correlation_id?: string;
  [k: string]: unknown;
}
export type FieldIntelJobStatusValue = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface FieldIntelJobStatus {
  job_id: string;
  status: FieldIntelJobStatusValue;
  field_id: string;
  progress: number;
  stage: string;
  created_at?: string;
  updated_at?: string;
  cancel_requested?: boolean;
  result?: FieldIntelResult;
  error?: { code?: string; message?: string } | string;
}

export const startAnalyzeFieldIntelligence = (input: FieldIntelInput): Promise<FieldIntelJobStatus> =>
  kongApi
    .post<FieldIntelJobStatus>('/api/v1/field-intelligence/analyze', null, {
      params: {
        field_id: input.field_id,
        ...(input.lat != null ? { lat: input.lat } : {}),
        ...(input.lon != null ? { lon: input.lon } : {}),
        ...(input.crop ? { crop: input.crop } : {}),
      },
    })
    .then(r => r.data);

export const getFieldIntelligenceJob = (jobId: string): Promise<FieldIntelJobStatus> =>
  kongApi.get<FieldIntelJobStatus>(`/api/v1/field-intelligence/analyze/jobs/${encodeURIComponent(jobId)}`).then(r => r.data);

export const cancelFieldIntelligenceJob = (jobId: string): Promise<FieldIntelJobStatus> =>
  kongApi.post<FieldIntelJobStatus>(`/api/v1/field-intelligence/analyze/jobs/${encodeURIComponent(jobId)}/cancel`).then(r => r.data);

// Compatibility shim: callers that still need the final result can poll explicitly here.
// New UI should prefer startAnalyzeFieldIntelligence + getFieldIntelligenceJob to show progress.
export const analyzeFieldIntelligence = async (input: FieldIntelInput): Promise<FieldIntelResult> => {
  const started = await startAnalyzeFieldIntelligence(input);
  let job = started;
  for (let i = 0; i < 120; i += 1) {
    if (job.status === 'completed' && job.result) return job.result;
    if (job.status === 'failed') throw new Error(typeof job.error === 'string' ? job.error : job.error?.message || 'field intelligence job failed');
    if (job.status === 'cancelled') throw new Error('field intelligence job cancelled');
    await new Promise(resolve => setTimeout(resolve, 1000));
    job = await getFieldIntelligenceJob(started.job_id);
  }
  throw new Error('field intelligence job timed out while polling');
};

// ══════════════════════════════════════════════════════════════════
// ANALYTICS — تحليلات التكلفة (حيّة، مُقيَّدة بالدور analytics:view وبالمستأجِر)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — أرقام مالية، الخطأ يُعلَن
// للـUI (حالة خطأ/فراغ). 503 يُرمى عند تعطيل قاعدة البيانات على الخادم.
// ══════════════════════════════════════════════════════════════════
export interface CostBySource {
  source:    string;
  total_usd: number;
}
export interface CostAnalytics {
  by_source:  CostBySource[];
  total_usd:  number;
  task_count: number;
}
export const getCostAnalytics = (): Promise<CostAnalytics> =>
  kongApi.get<CostAnalytics>('/api/v1/analytics/costs').then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// YIELD ANALYSIS — تحليل الغلّة (نمط FieldView، حيّ، tenant-scoped + analytics:view)
// GET /api/v1/analysis/yield: زراعة↔حصاد لكلّ موسم + أداء الهجن — من بيانات مُخزَّنة
// فقط (جدول seasons). لا fallback وهميّ: حين تغيب الغلّة الفعليّة تكون القوائم فارغة
// وتُعلَن الفجوة عبر provenance.note_ar. 503 (DB) / 403 / 404 يُرفع لتعرض الواجهة
// حالة صادقة. الغلّة بالطنّ/هكتار (t/ha). null = فجوة بيانات (لا 0 مُختلَق).
// ══════════════════════════════════════════════════════════════════
export interface YieldPlantingHarvestRow {
  season_id:         string | null;
  field_id:          string | null;
  field_name:        string | null;
  crop:              string | null;
  hybrid:            string | null;
  maturity:          string | null;
  sowing_date:       string | null;
  season_end:        string | null;
  status:            string | null;
  target_yield_t_ha: number | null;
  actual_yield_t_ha: number | null;
  yield_gap_t_ha:    number | null;
  has_harvest:       boolean;
}
export interface YieldHybridPerformanceRow {
  hybrid:         string;
  crops:          string[];
  season_count:   number;
  field_count:    number;
  avg_yield_t_ha: number;
  min_yield_t_ha: number;
  max_yield_t_ha: number;
}
export interface YieldAnalysisResult {
  scope:   { field_id: string | null; season: string | null };
  summary: {
    seasons_total:        number;
    seasons_with_harvest: number;
    hybrids_compared:     number;
  };
  planting_vs_harvest: YieldPlantingHarvestRow[];
  hybrid_performance:  YieldHybridPerformanceRow[];
  units:      { yield: string };
  provenance: { source: string; honesty: string; note_ar: string | null };
  tenant_id?: string;
}
export const getYieldAnalysis = (
  fieldId?: string,
  season?: string,
): Promise<YieldAnalysisResult> =>
  kongApi
    .get<YieldAnalysisResult>('/api/v1/analysis/yield', {
      params: { field_id: fieldId || undefined, season: season || undefined },
    })
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// REPORTS — تقارير وتحليلات (حيّة، tenant-scoped + RBAC field:view)
// تجميع من جداول قائمة (مزارع/حقول/مواسم/عمليّات/تنبيهات) عبر COUNT/SUM/GROUP BY.
// لا fallback وهميّ — الخطأ (503 DB / 404 / 403) يُرفع لتعرض الواجهة حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export interface AreaByCrop {
  crop:    string;
  area_ha: number;
}
export interface FarmSummary {
  farms_count:          number;
  fields_count:         number;
  total_area_ha:        number;
  active_seasons_count: number;
  activities_total:     number;
  activities_by_status: Record<string, number>;
  open_alerts_count:    number;
  area_by_crop:         AreaByCrop[];
}
export const getFarmSummary = (): Promise<FarmSummary> =>
  kongApi.get<FarmSummary>('/api/v1/reports/farm-summary').then(r => r.data);

export interface ReportAlert {
  alert_id:   string;
  field_id:   string | null;
  alert_type: string;
  severity:   string;
  title_ar:   string | null;
  message_ar: string | null;
  status:     string;
  created_at: string | null;
}
export interface FieldReportSeason {
  season_id:   string;
  crops:       string[];
  cultivar:    string | null;
  sowing_date: string | null;
  season_end:  string | null;
  status:      string;
}
export interface FieldReportSummary {
  field_id:             string;
  name:                 string;
  area_ha:              number;
  crop:                 string | null;
  soil_type:            string | null;
  current_season:       FieldReportSeason | null;
  activities_total:     number;
  activities_by_type:   Record<string, number>;
  activities_by_status: Record<string, number>;
  recent_alerts:        ReportAlert[];
}
export const getFieldReportSummary = (fieldId: string): Promise<FieldReportSummary> =>
  kongApi.get<FieldReportSummary>(`/api/v1/reports/field/${fieldId}/summary`).then(r => r.data);

export interface SeasonReportSummary {
  season_id:        string;
  field_id:         string;
  crops:            string[];
  cultivar:         string | null;
  irrigation_type:  string | null;
  sowing_date:      string | null;
  season_end:       string | null;
  status:           string;
  stage_count:      number;
  activities_count: number;
}
export const getSeasonReportSummary = (seasonId: string): Promise<SeasonReportSummary> =>
  kongApi.get<SeasonReportSummary>(`/api/v1/reports/season/${seasonId}/summary`).then(r => r.data);

// ── محاكاة الموسم (Crop-model simulation, RUE/FAO-56) — v39 ──────────
// تقديرات نموذجيّة (إنتاج/GDD/LAI/ماء) بنطاق وثقة صريحة — لا أرقام قاطعة.
export interface SeasonSimResult {
  season_id:           string;
  crop:                string;
  crop_recognized:     boolean;
  days_simulated:      number;
  gdd_total:           number;
  gdd_to_maturity:     number;
  maturity_reached:    boolean;
  lai_max:             number;
  biomass_kg_ha:       number;
  yield_kg_ha:         number;
  yield_low_kg_ha:     number;
  yield_high_kg_ha:    number;
  water_need_mm:       number;
  water_supply_mm:     number | null;
  water_stress_factor: number;
  confidence:          number;
  rationale_ar:        string;
  assumptions_ar:      string[];
  warnings_ar:         string[];
  sim_ran_at:          string;
}
// يشغّل محاكاة محصوليّة للموسم ويحفظ ناتجها على الخادم (FIELD_EDIT). 503 عند تعذّر
// الطقس/القاعدة، 404 إن غاب الموسم عن المستأجِر.
export const simulateSeason = (seasonId: string): Promise<SeasonSimResult> =>
  kongApi.post<SeasonSimResult>(`/api/v1/seasons/${seasonId}/simulate`).then(r => r.data);

// ── مواسم الحقل (مع نتائج المحاكاة المُخزَّنة sim_*) — حيّة عبر البوّابة ──
// GET /api/v1/fields/{field_id}/seasons (SeasonSummary[]، الأحدث أولاً، tenant-scoped
// + FIELD_VIEW). حقول sim_* تكون مملوءة فقط بعد تشغيل /simulate (تقديريّة)، وإلّا null
// ⇒ تعرضها الواجهة كحالة "—" صادقة لا أرقاماً مُلفَّقة. لا fallback وهميّ.
export interface SeasonSummary {
  season_id:        string;
  field_id:         string;
  crops:            string[];
  cultivar:         string | null;
  irrigation_type:  string | null;
  seed_rate_kg_ha:  number | null;
  land_leveling_date: string | null;
  plowing_date:     string | null;
  sowing_date:      string | null;
  season_end:       string | null;
  stages:           Record<string, unknown>[];
  status:           string; // active | closed | ...
  created_at:       string | null;
  // مؤشّرات الموسم الزراعيّة (v42) — تُدخَل عند الإنشاء/التحديث، وإلّا null
  target_yield_kg_ha:  number | null; // الغلّة المستهدفة كجم/هـ
  plant_density:       number | null; // كثافة النبات (نبتة/م²)
  row_spacing_cm:      number | null; // المسافة بين الخطوط (سم)
  seed_variety_source: string | null; // مصدر/صنف البذور
  // حقول أغرونوميّة (v52) — اختياريّة، وإلّا null
  maturity:            string | null; // فترة النضج (early/medium/late)
  tillage_type:        string | null; // نوع الحراثة
  actual_yield_kg_ha:  number | null; // الغلّة الفعليّة بعد الحصاد كجم/هـ
  notes_ar:            string | null; // ملاحظات
  // نتائج المحاكاة (تُملأ عند تشغيل /simulate، وإلّا null — تقديريّة بنطاق وثقة)
  sim_yield_kg_ha:   number | null;
  sim_biomass_kg_ha: number | null;
  sim_gdd_total:     number | null;
  sim_lai_max:       number | null;
  sim_water_mm:      number | null;
  sim_ran_at:        string | null;
}

export const fetchSeasons = (fieldId: string): Promise<SeasonSummary[]> =>
  kongApi.get<SeasonSummary[]>(`/api/v1/fields/${fieldId}/seasons`).then(r => (Array.isArray(r.data) ? r.data : []));

// ══════════════════════════════════════════════════════════════════
// INVENTORY — مخزون المدخلات (حيّ، مُقيَّد بالدور inventory:view/manage وبالمستأجِر)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — كميّات/مخزون حقيقيّة، الخطأ
// يُعلَن للـUI (حالة خطأ/فراغ). 503 يُرمى عند تعطيل قاعدة البيانات على الخادم.
// ══════════════════════════════════════════════════════════════════
export interface InventoryItem {
  item_id:        string;
  category:       string;
  name:           string;
  unit:           string | null;
  reorder_level:  number | null;
  total_quantity: number;
  low_stock:      boolean;
}
export interface ExpiringBatch {
  batch_id:    string;
  item_id:     string;
  name:        string;
  quantity:    number;
  unit:        string | null;
  expiry_date: string;
}
export interface NewInventoryItem {
  category:       string;
  name:           string;
  unit?:          string;
  reorder_level?: number;
  notes?:         string;
}
export interface NewInventoryBatch {
  quantity:     number;
  unit?:        string;
  batch_code?:  string;
  expiry_date?: string;
  received_at?: string;
  supplier?:    string;
  notes?:       string;
}

export const getInventoryItems = (): Promise<InventoryItem[]> =>
  kongApi.get<InventoryItem[]>('/api/v1/inventory/items').then(r => (Array.isArray(r.data) ? r.data : []));

export const getExpiringBatches = (days = 30): Promise<ExpiringBatch[]> =>
  kongApi.get<ExpiringBatch[]>('/api/v1/inventory/expiring', { params: { days } }).then(r => (Array.isArray(r.data) ? r.data : []));

export const createInventoryItem = (payload: NewInventoryItem): Promise<InventoryItem> =>
  kongApi.post<InventoryItem>('/api/v1/inventory/items', payload).then(r => r.data);

export const addInventoryBatch = (itemId: string, payload: NewInventoryBatch): Promise<unknown> =>
  kongApi.post(`/api/v1/inventory/items/${itemId}/batches`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// EQUIPMENT — إدارة المعدّات وسجلّ الصيانة (حيّ، مُقيَّد بالدور والمستأجِر)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — حالة المعدّة وتكلفة
// الصيانة قرارات تشغيليّة/ماليّة، الخطأ يُعلَن للـUI. 503 عند تعطيل DB.
// ══════════════════════════════════════════════════════════════════
export type EquipmentType   = 'tractor' | 'pump' | 'harvester' | 'sprayer' | 'other';
export type MaintenanceKind = 'scheduled' | 'repair' | 'breakdown' | 'inspection';

export interface Equipment {
  equipment_id:    string;
  name:            string;
  type:            EquipmentType | string;
  status:          string; // active | broken | maintenance | … (من الخادم)
  operating_hours: number;
  purchase_date:   string | null;
}

export interface EquipmentCreateInput {
  name:             string;
  type:             EquipmentType;
  operating_hours?: number;
  purchase_date?:   string;
  notes?:           string;
}

export interface MaintenanceRecord {
  maintenance_id:  string;
  kind:            MaintenanceKind | string;
  status:          string | null;
  scheduled_date:  string | null;
  performed_date:  string | null;
  cost_usd:        number | null;
  notes:           string | null;
}

export interface MaintenanceCreateInput {
  kind:            MaintenanceKind;
  status?:         string;
  scheduled_date?: string;
  performed_date?: string;
  cost_usd?:       number;
  notes?:          string;
}

export const fetchEquipment = (): Promise<Equipment[]> =>
  kongApi.get<Equipment[]>('/api/v1/equipment').then(r => (Array.isArray(r.data) ? r.data : []));

export const createEquipment = (payload: EquipmentCreateInput): Promise<Equipment> =>
  kongApi.post<Equipment>('/api/v1/equipment', payload).then(r => r.data);

export const fetchMaintenance = (equipmentId: string): Promise<MaintenanceRecord[]> =>
  kongApi.get<MaintenanceRecord[]>(`/api/v1/equipment/${equipmentId}/maintenance`).then(r => (Array.isArray(r.data) ? r.data : []));

// تسجيل صيانة. kind=breakdown يقلب حالة المعدّة إلى broken خادميّاً.
export const logMaintenance = (
  equipmentId: string,
  payload: MaintenanceCreateInput,
): Promise<MaintenanceRecord> =>
  kongApi.post<MaintenanceRecord>(`/api/v1/equipment/${equipmentId}/maintenance`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// FIELD ACTIVITIES — العمليّات الزراعيّة لكلّ حقل (sahool-platform v35).
// ربط حيّ بلا تلفيق: field:view للقراءة، field:edit للتسجيل. عند الخطأ
// (503 DB / 404 حقل / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export type ActivityType =
  | 'planting' | 'fertilization' | 'irrigation'
  | 'spraying' | 'pruning' | 'harvest' | 'scouting';

export interface Activity {
  activity_id:   string;
  field_id:      string;
  season_id:     string | null;
  activity_type: ActivityType | string;
  title_ar:      string | null;
  details:       Record<string, unknown>;
  scheduled_for: string | null;
  performed_on:  string | null;
  status:        string; // planned | done | skipped (من الخادم)
  created_at:    string | null;
}

export interface ActivityCreateInput {
  activity_type: ActivityType;
  title_ar?:     string;
  details?:      Record<string, unknown>;
  scheduled_for?: string;
  performed_on?: string;
  season_id?:    string;
}

export const fetchActivities = (fieldId: string): Promise<Activity[]> =>
  kongApi.get<Activity[]>(`/api/v1/fields/${fieldId}/activities`).then(r => (Array.isArray(r.data) ? r.data : []));

export const createActivity = (
  fieldId: string,
  payload: ActivityCreateInput,
): Promise<Activity> =>
  kongApi.post<Activity>(`/api/v1/fields/${fieldId}/activities`, payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// WEATHER ADVICE — توصية ريّ (FAO-56) + مخاطر أمراض لكلّ حقل (Sprint 5a).
// تُحسبان من الطقس الحيّ (Open-Meteo) ومحصول الموسم النشط. ربط حيّ بلا تلفيق:
// عند الخطأ (503 طقس/قاعدة، 404 حقل، 422 بلا إحداثيّات، 403 RBAC) يُرمى
// ليعرض الـUI حالة صادقة (StateViews).
// ══════════════════════════════════════════════════════════════════
export interface IrrigationAdvice {
  recommended_mm: number;
  urgency:        'none' | 'low' | 'moderate' | 'high' | string;
  timing_ar:      string;
  et0:            number;
  kc:             number;
  rationale_ar:   string;
  field_id:       string;
  crop:           string | null;
  stage:          string;
  source:         string;
}

export interface DiseaseRisk {
  risk_level:     'low' | 'moderate' | 'high' | string;
  diseases_ar:    string[];
  advice_ar:      string;
  field_id:       string;
  crop:           string | null;
  temperature_c:  number;
  humidity_pct:   number;
  rain_mm_3d:     number;
  source:         string;
}

export const fetchIrrigationAdvice = (fieldId: string): Promise<IrrigationAdvice> =>
  kongApi.get<IrrigationAdvice>(`/api/v1/fields/${fieldId}/weather/irrigation-advice`).then(r => r.data);

export const fetchDiseaseRisk = (fieldId: string): Promise<DiseaseRisk> =>
  kongApi.get<DiseaseRisk>(`/api/v1/fields/${fieldId}/weather/disease-risk`).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// UNIFIED RECOMMENDATIONS — عمود التوصيات الموحَّد لكلّ حقل.
// يجمع الخادم (api.recommendations_hub، نقيّ) الريّ + التسميد + الأمراض + الحصاد
// في قائمة واحدة مفروزة بالأولويّة. تدهور رشيق: عند تعذّر الطقس يُرجع توصيات
// التسميد/الحصاد فقط (weather_available=false) — لا بيانات وهميّة. عند الخطأ
// (503 لا سياق كافٍ، 404 حقل، 403 RBAC) يُرفع ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export type RecommendationCategory = 'irrigation' | 'fertilizer' | 'disease' | 'yield';
export type RecommendationPriority = 'high' | 'medium' | 'low';

export interface FieldRecommendation {
  category:  RecommendationCategory | string;
  priority:  RecommendationPriority | string;
  title_ar:  string;
  detail_ar: string;
  source:    string;
  safety?:   boolean;   // توصية سلامة (تُبرَز) — تُرسلها الخلفيّة (recommendations_hub)
}

// حالة الحقل القانونيّة المُرفقة بالتوصيات (تُرسلها الخلفيّة أصلاً — Provenance UX).
export interface RecFieldState {
  validity?:         string;
  execution_mode?:   string;
  confidence_level?: string | null;  // high | medium | low | none — نصّ لا رقم
  reasons_ar?:       string[];
}

export interface FieldRecommendationsResult {
  field_id:           string;
  crop:               string | null;
  stage:              string;
  weather_available:  boolean;
  recommendations:    FieldRecommendation[];
  requires_review?:   boolean;        // execution_mode != auto ⇒ مراجعة بشريّة
  field_state?:       RecFieldState;
}

export const fetchFieldRecommendations = (fieldId: string): Promise<FieldRecommendationsResult> =>
  kongApi
    .get<FieldRecommendationsResult>(`/api/v1/fields/${fieldId}/recommendations`)
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// ALERTS — التنبيهات الزراعيّة المُصنَّفة لكلّ مستأجِر (sahool-platform v36).
// ربط حيّ بلا fallback وهميّ: عند الخطأ (503 DB / 403 RBAC) يُرمى ليعرض الـUI
// حالة صادقة. field:view للقراءة، field:edit للإنشاء/الإقرار.
// ══════════════════════════════════════════════════════════════════
export type AlertType =
  | 'low_moisture' | 'heavy_rain' | 'disease_risk'
  | 'heat_stress' | 'frost_risk' | 'other';

export type AlertSeverity = 'info' | 'warning' | 'critical';
export type AlertStatus = 'active' | 'acknowledged' | 'resolved';

export interface AlertRecord {
  alert_id:    string;
  field_id:    string | null;
  alert_type:  AlertType | string;
  severity:    AlertSeverity | string;
  title_ar:    string | null;
  message_ar:  string | null;
  status:      AlertStatus | string;
  created_at:  string | null;
}

export interface AlertCreateInput {
  alert_type: AlertType;
  severity:   AlertSeverity;
  title_ar?:  string;
  message_ar?: string;
  field_id?:  string;
}

export interface AlertListFilters {
  status?:   AlertStatus;
  severity?: AlertSeverity;
}

export const fetchAlerts = (filters: AlertListFilters = {}): Promise<AlertRecord[]> =>
  kongApi.get<AlertRecord[]>('/api/v1/alerts', { params: filters }).then(r => (Array.isArray(r.data) ? r.data : []));

export const createAlert = (payload: AlertCreateInput): Promise<AlertRecord> =>
  kongApi.post<AlertRecord>('/api/v1/alerts', payload).then(r => r.data);

export const acknowledgeAlert = (alertId: string): Promise<AlertRecord> =>
  kongApi.patch<AlertRecord>(`/api/v1/alerts/${alertId}/acknowledge`).then(r => r.data);

// تقييم تلقائيّ لتنبيهات حقل: يُولّد تنبيهات مُصنَّفة من ظروف الحقل الحاليّة
// (الطقس الحيّ) ويُدرِجها في جدول alerts (v36) مع حذف تكرار النوع النشط.
export interface AlertEvaluateResult {
  created:           AlertRecord[];
  skipped_existing:  number;
}

export const evaluateFieldAlerts = (fieldId: string): Promise<AlertEvaluateResult> =>
  kongApi.post<AlertEvaluateResult>(`/api/v1/fields/${fieldId}/alerts/evaluate`).then(r => r.data);

// تشغيل تقييم التنبيهات لكلّ حقول المستأجِر دفعةً واحدة (أتمتة عند الطلب). معزول
// لكلّ حقل: الحقل المتعثّر يظهر بـerror دون إسقاط البقيّة (تدهور رشيق، لا 500).
export interface AlertsRunFieldSummary {
  field_id:  string;
  created:    number;
  skipped:    number;
  error?:     string;
}
export interface AlertsRunResult {
  fields_total:      number;
  fields_evaluated:  number;
  fields_failed:     number;
  created_total:     number;
  skipped_total:     number;
  per_field:         AlertsRunFieldSummary[];
}

export const runAllFieldsAlerts = (): Promise<AlertsRunResult> =>
  kongApi.post<AlertsRunResult>('/api/v1/automation/alerts/run').then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// NOTIFICATION PREFERENCES — قنوات تسليم التنبيهات لكلّ مستخدم (sahool-platform
// v9+v38). القنوات (بريد/SMS/Push/واتساب) + عناوينها + أنواع الأحداث المُشترَك بها
// + أرضيّة خطورة دنيا. ربط حيّ بلا تلفيق: عند الخطأ (503 DB / 403 RBAC) يُرمى
// لتعرض الواجهة حالة صادقة. field:view للقراءة، field:edit للحفظ (UPSERT).
// ══════════════════════════════════════════════════════════════════
export type NotifEventType =
  | 'satellite' | 'weather_alert' | 'pest_alert' | 'irrigation_rec'
  | 'fertilizer_rec' | 'low_stock' | 'task_assigned' | 'economic_analysis'
  | 'low_moisture' | 'heavy_rain' | 'disease_risk' | 'heat_stress'
  | 'frost_risk' | 'other';

export interface NotificationPreferences {
  email_enabled:    boolean;
  email_address:    string | null;
  sms_enabled:      boolean;
  sms_number:       string | null;
  push_enabled:     boolean;
  push_token:       string | null;
  whatsapp_enabled: boolean;
  whatsapp_number:  string | null;
  event_types:      string[];
  min_severity:     AlertSeverity | null;
}

export const fetchNotificationPreferences = (): Promise<NotificationPreferences> =>
  kongApi.get<NotificationPreferences>('/api/v1/notifications/preferences').then(r => r.data);

export const updateNotificationPreferences = (
  payload: NotificationPreferences,
): Promise<NotificationPreferences> =>
  kongApi.put<NotificationPreferences>('/api/v1/notifications/preferences', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// IoT DEVICES — أجهزة استشعار حيّة عبر البوابة (kong). ربط حقيقيّ بلا تلفيق:
// عند الخطأ (503 DB مُعطَّلة / 403 RBAC / انقطاع) يُرمى ليعرض الـUI حالة صادقة.
// device:view للقراءة، device:manage للتسجيل، observation:record لرفع قياس.
// ══════════════════════════════════════════════════════════════════
export type DeviceType =
  | 'soil_moisture' | 'weather_station' | 'water_meter'
  | 'camera' | 'actuator' | 'other';

export interface Device {
  device_id:         string;
  name:              string;
  type:              DeviceType;
  field_id:          string | null;
  status:            string;
  online:            boolean; // مُحتسَب خادميّاً (من last_seen_at)
  last_seen_at:      string | null;
  firmware_version:  string | null;
}

export interface DeviceRegisterInput {
  name:              string;
  type:              DeviceType;
  field_id?:         string;
  firmware_version?: string;
}

export interface TelemetryPoint {
  sensor_type: string;
  value:       number;
  unit:        string | null;
  recorded_at: string;
}

export interface TelemetryRecordInput {
  sensor_type: string;
  value:       number;
  unit?:       string;
  recorded_at?:string;
}

/** قائمة الأجهزة (device:view). online مُحتسَب على الخادم. */
export const listDevices = (): Promise<Device[]> =>
  kongApi.get<Device[]>('/api/v1/devices').then(r => (Array.isArray(r.data) ? r.data : []));

/** تسجيل جهاز جديد (device:manage). */
export const registerDevice = (payload: DeviceRegisterInput): Promise<Device> =>
  kongApi.post<Device>('/api/v1/devices', payload).then(r => r.data);

/** قياسات حديثة لجهاز (device:view). */
export const getDeviceTelemetry = (deviceId: string, limit = 20): Promise<TelemetryPoint[]> =>
  kongApi.get<TelemetryPoint[]>(`/api/v1/devices/${deviceId}/telemetry`, { params: { limit } }).then(r => (Array.isArray(r.data) ? r.data : []));

/** رفع قياس لجهاز (observation:record). */
export const recordTelemetry = (deviceId: string, payload: TelemetryRecordInput): Promise<TelemetryPoint> =>
  kongApi.post<TelemetryPoint>(`/api/v1/devices/${deviceId}/telemetry`, payload).then(r => r.data);

/** أحدث قراءة رطوبة تربة (٪) لأجهزة الحقل من telemetry الحيّ. reading=null إن لا قراءة. */
export interface SoilMoistureReading {
  soil_moisture_pct: number;
  recorded_at:       string;
  device_id:         string | null;
  unit:              string | null;
}

export interface FieldSoilMoisture {
  field_id: string;
  reading:  SoilMoistureReading | null;
}

/** أحدث رطوبة تربة لحقل من أجهزته (field:view). reading=null عند غياب قراءة صالحة. */
export const getFieldSoilMoisture = (fieldId: string): Promise<FieldSoilMoisture> =>
  kongApi.get<FieldSoilMoisture>(`/api/v1/fields/${fieldId}/soil-moisture`).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// IRRIGATION OPS — صمّامات الريّ + جداول الريّ المُخزَّنة (حيّة عبر البوابة)
// مُقيَّدة بالدور irrigation:view / irrigation:manage. 503 عند تعطيل قاعدة
// البيانات على الخادم. ربط حقيقيّ — لا fallback وهميّ (تشغيل ريّ فعليّ).
// ملاحظة: state يسجّل النيّة فقط؛ التشغيل الفيزيائيّ يمرّ عبر HIL (موافقة بشريّة).
// ══════════════════════════════════════════════════════════════════
export type ValveStatus = 'open' | 'closed' | 'unknown';
export type ValveStateIntent = 'open' | 'closed';
export type ValveType = 'solenoid' | 'manual' | 'drip_header' | 'gate';

export interface Valve {
  valve_id:        string;
  name:            string;
  field_id?:       string | null;
  device_id?:      string | null;
  valve_type?:     ValveType | string | null;
  status:          ValveStatus;
  flow_rate_lpm?:  number | null;
  last_changed_at?: string | null;
}
export interface CreateValveInput {
  name:           string;
  field_id?:      string;
  device_id?:     string;
  valve_type?:    ValveType;
  flow_rate_lpm?: number;
}
export interface IrrigationSchedule {
  schedule_id:     string;
  field_id?:       string | null;
  valve_id?:       string | null;
  name:            string;
  start_time:      string; // 'HH:MM'
  duration_min:    number;
  days_of_week?:   number[] | null; // 0..6
  water_target_mm?: number | null;
  enabled:         boolean;
  last_run_at?:    string | null;
}
export interface CreateScheduleInput {
  name:            string;
  field_id?:       string;
  valve_id?:       string;
  start_time:      string; // 'HH:MM'
  duration_min:    number;
  days_of_week?:   number[];
  water_target_mm?: number;
  enabled?:        boolean;
}

export const listValves = (): Promise<Valve[]> =>
  kongApi.get<Valve[]>('/api/v1/irrigation/valves').then(r => (Array.isArray(r.data) ? r.data : []));

export const createValve = (payload: CreateValveInput): Promise<Valve> =>
  kongApi.post<Valve>('/api/v1/irrigation/valves', payload).then(r => r.data);

export const setValveState = (valveId: string, status: ValveStateIntent): Promise<Valve> =>
  kongApi.post<Valve>(`/api/v1/irrigation/valves/${valveId}/state`, { status }).then(r => r.data);

export const listSchedules = (fieldId?: string): Promise<IrrigationSchedule[]> =>
  kongApi.get<IrrigationSchedule[]>('/api/v1/irrigation/schedules', {
    params: fieldId ? { field_id: fieldId } : {},
  }).then(r => (Array.isArray(r.data) ? r.data : []));

export const createSchedule = (payload: CreateScheduleInput): Promise<IrrigationSchedule> =>
  kongApi.post<IrrigationSchedule>('/api/v1/irrigation/schedules', payload).then(r => r.data);

export const deleteSchedule = (scheduleId: string): Promise<void> =>
  kongApi.delete(`/api/v1/irrigation/schedules/${scheduleId}`).then(() => undefined);

// ══════════════════════════════════════════════════════════════════
// MASTER DATA — كتالوج البيانات المرجعيّة (محصول/تربة/سماد/مبيد/صنف/معدّة)
// ربط حقيقيّ عبر البوابة (kong). لا fallback وهميّ — بيانات مرجعيّة تُبنى عليها
// قرارات، فالخطأ يُعلَن للـUI. 503 عند تعطيل قاعدة البيانات، 409 عند التكرار
// (tenant,category,code). مُقيَّد بالدور master_data:view / master_data:manage.
// ══════════════════════════════════════════════════════════════════
export type MasterDataCategory =
  | 'crop' | 'soil_type' | 'fertilizer' | 'pesticide'
  | 'seed_variety' | 'equipment_type' | 'other';

export interface MasterDataEntry {
  md_id:    string;
  category: MasterDataCategory;
  code:     string;
  name_ar:  string;
  name_en?: string;
  metadata?: Record<string, unknown>;
}

export interface MasterDataCreateInput {
  category:  MasterDataCategory;
  code:      string;
  name_ar:   string;
  name_en?:  string;
  metadata?: Record<string, unknown>;
}

export const fetchMasterData = (category: MasterDataCategory): Promise<MasterDataEntry[]> =>
  kongApi.get<MasterDataEntry[]>('/api/v1/master-data', { params: { category } }).then(r => (Array.isArray(r.data) ? r.data : []));

export const createMasterDataEntry = (payload: MasterDataCreateInput): Promise<MasterDataEntry> =>
  kongApi.post<MasterDataEntry>('/api/v1/master-data', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// DOCUMENTS — سجلّ الوثائق (عقود/تقارير/صور/خرائط/نتائج مخبريّة)
// سجلّ بيانات وصفيّة فقط: الملفّ الفعليّ في تخزين الكائنات، وstorage_ref مسار/رابط.
// ربط حيّ عبر البوابة (kong)، مُقيَّد بالدور (document:view / document:manage)
// وبالمستأجِر. لا fallback وهميّ — 503 يُرمى عند تعطيل قاعدة البيانات.
// ══════════════════════════════════════════════════════════════════
export type DocumentCategory = 'contract' | 'report' | 'image' | 'map' | 'lab_result' | 'other';

export interface DocumentRecord {
  doc_id:       string;
  category:     DocumentCategory;
  title:        string;
  storage_ref:  string | null;
  content_type: string | null;
  size_bytes:   number | null;
  version:      number;
  field_id:     string | null;
  created_at:   string;
}

export interface DocumentCreateInput {
  category:      DocumentCategory;
  title:         string;
  storage_ref?:  string;
  content_type?: string;
  size_bytes?:   number;
  field_id?:     string;
}

export const listDocuments = (
  filters?: { category?: DocumentCategory; field_id?: string },
): Promise<DocumentRecord[]> =>
  kongApi.get<DocumentRecord[]>('/api/v1/documents', {
    params: {
      ...(filters?.category ? { category: filters.category } : {}),
      ...(filters?.field_id ? { field_id: filters.field_id } : {}),
    },
  }).then(r => (Array.isArray(r.data) ? r.data : []));

export const getDocument = (docId: string): Promise<DocumentRecord> =>
  kongApi.get<DocumentRecord>(`/api/v1/documents/${docId}`).then(r => r.data);

export const createDocument = (payload: DocumentCreateInput): Promise<DocumentRecord> =>
  kongApi.post<DocumentRecord>('/api/v1/documents', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// GOVERNANCE & AUDIT — أصل/أحداث/أوامر كيان + مفاتيح المشاركة (حيّ عبر البوابة)
// قراءة-غالباً + إنشاء مفتاح. كلّها DB-backed عبر tenant_connection (RLS مُطبَّق)؛
// عند تعطيل قاعدة البيانات يُرمى 503 ليعرض الـUI حالة صادقة. لا بيانات مُلفَّقة —
// التتبّع/التدقيق سجلّ حقيقيّ أو لا شيء. مفتاح المشاركة يُعرَض نصّاً مرّة واحدة فقط.
// ══════════════════════════════════════════════════════════════════
export interface LineageEntry {
  timestamp:   string;
  source_type: string;
  source_id:   string | null;
  action:      string | null;
  summary_ar:  string | null;
}
export interface EntityLineage {
  entity_type:    string;
  entity_id:      string;
  total_entries:  number;
  earliest_at:    string | null;
  latest_at:      string | null;
  commands_count: number;
  events_count:   number;
  entries:        LineageEntry[];
}
export interface SharingKey {
  key_id:       string;
  key_prefix?:  string;
  scope?:       string;
  created_by?:  string;
  expires_at?:  string | null;
  revoked_at?:  string | null; // الخادم يُرجِع طابعاً زمنيّاً (أو null) لا boolean
  [k: string]: unknown; // الخادم قد يُرجِع حقولاً إضافيّة — لا نقصّها
}
// SharingScope على الخادم = 'read' | 'read_write' (لا 'write').
export type SharingScope = 'read' | 'read_write';
export interface NewSharingKey {
  scope?:            SharingScope;
  valid_days?:       number;
  third_party_name?: string;
  third_party_type?: string;
  allowed_field_ids?: string[];
}
export interface SharingKeyCreated {
  key_id:        string;
  key_plaintext: string; // مرّة واحدة فقط — لا يُعاد عرضه
  key_prefix:    string;
  scope:         string;
  expires_at:    string | null;
}

/** أصل (lineage) كامل لكيان (command+event+lifecycle+journal+trueup). */
export const getEntityLineage = (
  entityType: string,
  entityId: string,
  limit = 500,
): Promise<EntityLineage> =>
  kongApi.get<EntityLineage>(
    `/api/v1/lineage/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    { params: { limit } },
  ).then(r => r.data);

/** تاريخ أحداث كيان من ناقل الأحداث. */
export const getEntityEvents = (
  entityType: string,
  entityId: string,
  limit = 100,
): Promise<{ events: unknown[] }> =>
  kongApi.get<{ events: unknown[] }>(
    `/api/v1/events/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
    { params: { limit } },
  ).then(r => r.data);

/** البحث عن أمر بالمعرّف (404 عند عدم الوجود). */
export const getCommand = (commandId: string): Promise<{ command_id: string; found: boolean }> =>
  kongApi.get<{ command_id: string; found: boolean }>(
    `/api/v1/commands/${encodeURIComponent(commandId)}`,
  ).then(r => r.data);

/** سرد مفاتيح المشاركة للمستأجِر. */
export const listSharingKeys = (includeRevoked = false): Promise<{ keys: SharingKey[] }> =>
  kongApi.get<{ keys: SharingKey[] }>('/api/v1/sharing/keys', {
    params: { include_revoked: includeRevoked },
  }).then(r => r.data);

/** إنشاء مفتاح مشاركة (يتطلّب صلاحيّة دعوة المستخدم). النصّ يُعرَض مرّة واحدة. */
export const createSharingKey = (payload: NewSharingKey): Promise<SharingKeyCreated> =>
  kongApi.post<SharingKeyCreated>('/api/v1/sharing/keys', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// FARMS — المزارع (أب الحقول). إنشاء/سرد حيّ عبر البوابة (kong)، مُقيَّد بالدور
// farm:create / farm:view وبالمستأجِر (RLS). لا fallback وهميّ — 503 عند تعطيل
// قاعدة البيانات. تُستخدم لبوّابة التأهيل: مستخدم جديد يُنشئ مزرعة قبل اللوحة.
// ══════════════════════════════════════════════════════════════════
export type FarmUnits = 'metric' | 'imperial';

export interface Farm {
  farm_id:        string;
  name:           string;
  location:       string | null;
  area_ha:        number | null;
  centroid_lat:   number | null;
  centroid_lon:   number | null;
  country?:       string | null;
  region?:        string | null;
  timezone?:      string | null;
  units?:         FarmUnits | null;
  currency?:      string | null;
  description?:   string | null;
  activity_type?: string | null;
  created_at?:    string | null;
}

export interface FarmCreateInput {
  name:           string;
  location?:      string;
  area_ha?:       number;
  country?:       string;
  region?:        string;
  timezone?:      string;
  units?:         FarmUnits;
  currency?:      string;
  description?:   string;
  activity_type?: string;
}

export interface FarmCreated {
  farm_id:    string;
  name:       string;
  message_ar: string;
}

export const fetchFarms = (): Promise<Farm[]> =>
  kongApi.get<Farm[]>('/api/v1/farms').then(r => (Array.isArray(r.data) ? r.data : []));

export const createFarm = (payload: FarmCreateInput): Promise<FarmCreated> =>
  kongApi.post<FarmCreated>('/api/v1/farms', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// FIELD DETAIL — تفاصيل الحقل المتقدّمة (sahool-platform v37). ملء تدريجيّ
// بعد الإنشاء: كيمياء التربة + المناخ الدقيق + الملكيّة. ربط حيّ بلا تلفيق —
// field:view للقراءة (GET /fields/{id})، field:edit للتحديث الجزئيّ (PATCH).
// عند الخطأ (503 DB / 404 حقل / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export interface FieldDetail {
  field_id:        string;
  farm_id:         string;
  name_ar:         string;
  crop:            string;
  area_ha:         number;
  quality_grade:   string;
  health_summary_ar: string;
  soil_type?:      string | null;
  manager?:        string | null;
  field_code?:     string | null;
  description?:    string | null;
  water_source?:   string | null;
  ownership_type?: string | null;
  country?:        string | null;
  region?:         string | null;
  lat?:            number | null;
  lon?:            number | null;
  geometry?:       Record<string, unknown> | null;
  // كيمياء التربة (نتائج مختبر)
  soil_ph?:        number | null;
  soil_ec?:        number | null;
  soil_om?:        number | null; // المادّة العضويّة %
  soil_n?:         number | null;
  soil_p?:         number | null;
  soil_k?:         number | null;
  // المناخ الدقيق / التضاريس
  elevation_m?:        number | null;
  slope_pct?:          number | null;
  aspect?:             string | null;
  climate_zone?:       string | null;
  annual_rainfall_mm?: number | null;
  // تفاصيل الملكيّة
  owner_name?:     string | null;
  lease_years?:    number | null;
  registry_no?:    string | null;
  // ملفّ الريّ/المياه التفصيليّ (v41) — يعيدها الخادم؛ تُعرَض للقراءة بحالة "—" صادقة
  irrigation_type?:           string | null;
  irrigation_efficiency_pct?: number | null;
  flow_rate_m3h?:             number | null; // تدفّق المضخّة م³/ساعة
  pump_type?:                 string | null;
  well_depth_m?:              number | null;
  water_ec?:                  number | null; // ملوحة الماء dS/m
  zone_key?:                  string | null; // مفتاح الإقليم القانوني (v49)
  manager_user_id?:           number | null; // FK إلى users(id) (v47)
}

// تحديث جزئيّ: كلّ الحقول اختياريّة — تُرسَل المُعدَّلة فقط (الخادم يحدّثها فقط).
export interface FieldUpdatePatch {
  soil_ph?:            number | null;
  soil_ec?:            number | null;
  soil_om?:            number | null;
  soil_n?:             number | null;
  soil_p?:             number | null;
  soil_k?:             number | null;
  elevation_m?:        number | null;
  slope_pct?:          number | null;
  aspect?:             string | null;
  climate_zone?:       string | null;
  annual_rainfall_mm?: number | null;
  owner_name?:         string | null;
  lease_years?:        number | null;
  registry_no?:        string | null;
}

/** تفاصيل حقل كاملة (field:view). 404 لو ليس للمستأجِر، 503 عند تعطيل DB. */
export const fetchFieldDetail = (fieldId: string): Promise<FieldDetail> =>
  kongApi.get<FieldDetail>(`/api/v1/fields/${fieldId}`).then(r => r.data);

/** تحديث جزئيّ لتفاصيل حقل (field:edit). تُرسَل الحقول المُعدَّلة فقط. */
export const updateField = (fieldId: string, patch: FieldUpdatePatch): Promise<FieldDetail> =>
  kongApi.patch<FieldDetail>(`/api/v1/fields/${fieldId}`, patch).then(r => r.data);

// ── وصفات المعدّل المتغيّر اليدويّة (Manual VRT Prescriptions، v95) ──
// FieldView "manual prescriptions": وصفة **يدويّة** صرفة — المستخدِم يرسم المناطق
// (geometry GeoJSON) ويضبط لكلّ منطقة معدّلاً + وحدة، ثمّ يحفظها (tenant-scoped، RLS).
// لا توليد agronomic آليّ هنا. التصدير (GeoJSON/CSV) يتمّ في الواجهة (Blob/URL).
export interface SavedPrescriptionZone {
  geometry: unknown;   // GeoJSON Polygon (يرسمه المستخدِم)
  rate:     number;    // المعدّل (seeds/m² أو kg/ha)
  unit:     string;    // الوحدة
}

export interface SavedPrescription {
  prescription_id: string;
  field_id:        string;
  name:            string;
  product_type:    'seed' | 'fertility';
  zones:           SavedPrescriptionZone[];
  created_by?:     string | null;
  created_at?:     string;
}

export interface PrescriptionCreateInput {
  prescription_id: string;
  name:            string;
  product_type:    'seed' | 'fertility';
  zones:           SavedPrescriptionZone[];
}

export interface PrescriptionListResponse {
  field_id:      string;
  prescriptions: SavedPrescription[];
  total:         number;
  note_ar?:      string;   // سبب صادق حين القائمة فارغة (DB مُعطَّلة)
}

/** سرد الوصفات المحفوظة لحقل (field:view). 503 عند تعطّل DB، فارغ صادق حين لا وصفات. */
export const fetchPrescriptions = (fieldId: string): Promise<PrescriptionListResponse> =>
  kongApi.get<PrescriptionListResponse>(`/api/v1/fields/${fieldId}/prescriptions`).then(r => r.data);

/** حفظ وصفة يدويّة (field:edit). 422 نوع منتج غير مدعوم، 503 عند تعطّل DB. */
export const createPrescription = (
  fieldId: string,
  payload: PrescriptionCreateInput,
): Promise<SavedPrescription & { persisted: boolean }> =>
  kongApi.post<SavedPrescription & { persisted: boolean }>(
    `/api/v1/fields/${fieldId}/prescriptions`, payload,
  ).then(r => r.data);

// ── استيراد حدّ حقل من ملفّ (GeoJSON/KML) أو نقاط GPS (field:create) ──
// بدل الرسم اليدويّ: نرسل نصّ الملفّ (content) أو نقاط GPS (points) للخادم،
// الذي يحلّلها إلى GeoJSON Polygon ثمّ يعيد استخدام نفس مسار التحقّق/الحفظ
// كإنشاء حقل مرسوم. 400 = تحليل تالف، 422 = هندسة غير صالحة (يُعرَضان بصدق).
export interface FieldImportInput {
  format:        'geojson' | 'kml' | 'gps';
  content?:      string;          // نصّ ملفّ GeoJSON/KML
  points?:       number[][];      // مسار GPS [[lon,lat],...]
  name:          string;
  crop?:         string;
  soil_type?:    string;
  manager?:      string;
  field_code?:   string;
  water_source?: string;
  country?:      string;
  region?:       string;
  boundary_metadata?: Record<string, unknown>;
  idempotency_key?: string;
}

/** يستورد حقلاً من ملفّ/نقاط GPS. يُرجع FieldSummary المُنشأ من ردّ الخادم. */
export const importField = (payload: FieldImportInput): Promise<unknown> => {
  const { idempotency_key, ...body } = payload;
  const config = idempotency_key ? { headers: { 'Idempotency-Key': idempotency_key } } : undefined;
  return kongApi.post('/api/v1/fields/import', body, config).then(r => r.data);
};

// ── دمج/انقسام الحقول ذرّيّاً (POST /merge · /split) — معاملة خادميّة واحدة ──
// تستبدل لاذرّيّة الواجهة (POST جديد + حلقة DELETE) التي كانت تُخلّف حقولاً يتيمة
// عند فشل الحذف. الخادم يُنشئ المدموج/الأطفال ويحذف المصادر في معاملة واحدة (الكلّ
// أو لا شيء)؛ الخطأ (404/409/422/503) يُرمى ليُعرَض بصدق. الهندسة محسوبة @turf في
// الواجهة ويتحقّق منها الخادم (guard_field_geometry).
export interface FieldMergeInput {
  source_field_ids: string[];     // ≥2 معرّفات الحقول المصدر
  name:             string;       // اسم الحقل المدموج
  geometry:         unknown;      // GeoJSON Polygon المدموج (اتّحاد @turf)
  crop?:            string | null;
  soil_type?:       string | null;
  manager?:         string | null;
  farm_id?:         string | null;
  field_code?:      string | null;
  description?:     string | null;
  water_source?:    string | null;
  irrigation_type?: string | null;
  ownership_type?:  string | null;
  gov?:             string | null;
  country?:         string | null;
  region?:          string | null;
}

export interface SplitChildInput {
  name:             string;
  geometry:         unknown;      // GeoJSON Polygon للجزء (محسوب @turf)
  crop?:            string | null;
  soil_type?:       string | null;
  manager?:         string | null;
  field_code?:      string | null;
  description?:     string | null;
  water_source?:    string | null;
  irrigation_type?: string | null;
  ownership_type?:  string | null;
}

export interface FieldSplitInput {
  source_field_id: string;
  children:        SplitChildInput[];   // 2..10 حقول وليدة
}

/** يدمج حقولاً مصدر في حقل واحد ذرّيّاً (field:create). يُرجِع FieldSummary المدموج. */
export const mergeFields = (payload: FieldMergeInput): Promise<unknown> =>
  kongApi.post('/api/v1/fields/merge', payload).then(r => r.data);

/** يقسّم حقلاً إلى حقول وليدة ذرّيّاً (field:create). يُرجِع قائمة FieldSummary للأطفال. */
export const splitField = (payload: FieldSplitInput): Promise<unknown> =>
  kongApi.post('/api/v1/fields/split', payload).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// FIELD WORKSPACE — مساحة عمل الحقل (المصدر الأساسيّ لكرت «Field Workspace Map»)
// GET /api/v1/fields/{field_id}/workspace (fields.py:508 ⇒ assemble_workspace):
// ملخّص الحقل + كتالوج طبقات قابلة للتبديل (كلّ طبقة تُعلن توفّرها بصدق:
// available/on_demand/missing) + تفسير التضاريس + خطّ زمنيّ من أحداث مسجّلة فقط.
// عرض صرف (display_only) — لا قرار مفروض. لا fallback وهميّ: عند الخطأ (404 حقل
// ليس للمستأجِر / 503 DB) يُرمى ليعرض الـUI حالة صادقة. الحدود (geometry) تُجلب
// عبر fetchFieldDetail، وطبقة NDVI الحقيقيّة من خدمة الراستر (rasterApi) عند الطلب.
// ══════════════════════════════════════════════════════════════════

/** حالة توفّر طبقة كما يُعلنها الخادم بصدق. */
export type WorkspaceLayerStatus = 'available' | 'on_demand' | 'missing';

/** طبقة عرض واحدة في كتالوج مساحة العمل (display_only — لا تفرض قراراً). */
export interface WorkspaceLayer {
  key:          string;
  label_ar:     string;
  category:     string; // vegetation | terrain | soil | water
  available:    boolean;
  status:       WorkspaceLayerStatus | string;
  display_only: boolean;
  note_ar:      string;
}

/** ملخّص الحقل المُضمَّن في مساحة العمل (مأخوذ من أعمدة الحقل، قد يكون null). */
export interface WorkspaceFieldSummary {
  name_ar:   string | null;
  crop:      string | null;
  area_ha:   number | null;
  soil_type: string | null;
}

/** بطاقة خطّ زمنيّ واحدة (من أحداث مسجّلة فقط — لا تاريخ مخترَع). */
export interface WorkspaceTimelineCard {
  occurred_at: string;
  event_type:  string;
  op_ar:       string;
  category:    string;
  issue_tags:  string[];
}

/** تفسير التضاريس المُضمَّن (enrich_terrain) — شكل مفتوح، اختياريّ بالكامل. */
export interface WorkspaceTerrain {
  field_id?:        string;
  elevation_m?:     number | null;
  slope_pct?:       number | null;
  aspect?:          string | null;
  [k: string]:      unknown;
}

/** مساحة عمل الحقل الكاملة (GET /workspace) — عرض صرف. */
export interface FieldWorkspace {
  field_id:               string | null;
  display_only:           boolean;
  field:                  WorkspaceFieldSummary;
  layers:                 WorkspaceLayer[];
  available_layer_count:  number;
  terrain:                WorkspaceTerrain | null;
  timeline:               WorkspaceTimelineCard[];
  timeline_total:         number;
  honesty_note_ar:        string;
}

/** يجلب مساحة عمل الحقل (field:view). 404 لو ليس للمستأجِر، 503 عند تعطيل DB.
 *  لا fallback وهميّ — الخطأ يُرمى ليعرض الـUI حالة صادقة. */
export const fetchFieldWorkspace = (
  fieldId: string,
  timelineLimit = 50,
): Promise<FieldWorkspace> =>
  kongApi
    .get<FieldWorkspace>(`/api/v1/fields/${fieldId}/workspace`, {
      params: { timeline_limit: timelineLimit },
    })
    .then(r => r.data);

/** قاعدة عنوان خدمة الراستر (بلا شرطة لاحقة) — لبناء رابط قالب بلاطات NDVI
 *  الحقيقيّة ({z}/{x}/{y}) التي يفسّرها Leaflet. نفس مصدر FieldIndicatorMap. */
export const rasterBaseUrl = (): string =>
  (rasterApi.defaults.baseURL || '').replace(/\/+$/, '');


export const normalizeIndicatorIndex = (index?: string | null): string => {
  const key = (index || 'ndvi').trim().toLowerCase().replace(/[\s-]+/g, '_');
  const aliases: Record<string, string> = {
    ndvu: 'ndvi',
    vegetation: 'ndvi',
    moisture: 'ndmi',
    salinity: 'salinity',
    salt: 'salinity',
    soil_salinity: 'salinity',
  };
  return aliases[key] || key;
};

/** رابط قالب بلاطات مؤشّر حقل من خدمة الراستر (NDVI افتراضيّاً). نُبقي
 *  {z}/{x}/{y} حرفيّاً ليفسّرها Leaflet. لا تلوين مفبرك: إن لم تتوفّر صورة COG
 *  صافية للحقل/التاريخ تُرجِع الخدمة بلاطات فارغة (لا طبقة مُختلَقة). */
// مصادقة بلاطات <img> خلف بوّابة الإنتاج (auth_request): بلاطة Leaflet/MapLibre تُحمَّل
// كـ<img> ولا تحمل ترويسة Authorization، فنُلحق JWT كـ`access_token` لتقرأه البوّابة
// ($arg_access_token) وتُمرّره لـ/auth/verify. نمط صناعيّ معتمَد (Mapbox/ArcGIS)؛ مُخفَّف
// بتوكن قصير العمر + تنظيف access_token من سجلّ nginx + Referrer-Policy صارم.
const appendTileAccessToken = (params: URLSearchParams): void => {
  // في الإنتاج: لا نُلحق JWT في رابط البلاطة. المصادقة تمرّ عبر كوكي HttpOnly `sahool_at`
  // (تضبطها خدمة auth عند الدخول/التجديد، تُرسَل تلقائيّاً مع <img> نفس‌المصدر، تقرأها
  // البوّابة كمصدر auth_request). يمنع تسريب JWT عبر سجلّ المتصفّح/الـReferrer/التلمترة.
  // التطوير فقط (بلا بوّابة/كوكي) يُلحق access_token كـfallback مباشر لخدمة الراستر.
  if (import.meta.env.PROD) return;
  const tok = getAccessToken();
  if (tok) params.set('access_token', tok);
};

export const fieldIndicatorTileUrl = (
  fieldId: string,
  index = 'ndvi',
  date = 'latest',
  tenantId?: string | null,
  cacheVersion?: string | number | null,
): string => {
  // عقد التاريخ (متابعة D، توحيد main↔cert): لا نمرّر date حين latest/فارغ — backend
  // يعامل الغياب كأحدث مشهد، فلا نُسرّب date=latest في رابط البلاطة.
  const params = new URLSearchParams({ index: normalizeIndicatorIndex(index) });
  if (date && date !== 'latest') params.set('date', date);
  // الإنتاج: البوّابة تشتقّ المستأجِر من JWT الموثّق (X-Tenant-Id) فلا حاجة لـtid في الرابط؛
  // التطوير يُبقيه كـfallback لخدمة الراستر (raster_security_context يقرأ الرأس أوّلاً ثمّ tid).
  if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);
  if (cacheVersion !== undefined && cacheVersion !== null && String(cacheVersion) !== '') params.set('v', String(cacheVersion));
  appendTileAccessToken(params);
  const qs = params.toString();
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
};

// عقد القصّ الموحَّد لـCDSE (poly + bbox) كـ`Record<string,string>` — مصدر حقيقة واحد
// يستعمله باني البلاطة والمُصغَّرة **و** فحص cdse-tilejson (v8-F4)، كي تحمل روابط
// TileJSON نفس هندسة البلاطات الفعليّة (لا تباعد بين المُعاينة والقصّ الحقيقيّ).
export const cdseClipParams = (
  geometry?: { type?: string; coordinates?: unknown } | null,
  bbox?: [number, number, number, number] | null,
): Record<string, string> => {
  const out: Record<string, string> = {};
  if (bbox && bbox.length === 4) {
    out.bbox_w = String(bbox[0]); out.bbox_s = String(bbox[1]);
    out.bbox_e = String(bbox[2]); out.bbox_n = String(bbox[3]);
  }
  const ring = (() => {
    const g = geometry as { type?: string; coordinates?: number[][][] } | undefined;
    if (!g || !g.coordinates) return null;
    if (g.type === 'Polygon') return g.coordinates[0] ?? null;
    if (g.type === 'MultiPolygon') return (g.coordinates as unknown as number[][][][])[0]?.[0] ?? null;
    return null;
  })();
  if (ring && ring.length >= 3) {
    out.poly = ring.map((c) => `${c[0]},${c[1]}`).join(';');
  }
  return out;
};

// باني رابط بلاطات CDSE الحيّة (Sentinel Hub) — توحيد main↔cert: يدعم قصّ المضلّع
// (poly) + bbox. العقد الموحَّد: poly="lng,lat;lng,lat;..." (ترتيب lng,lat). date مشروط (D).
export const fieldCdseTileUrl = (
  fieldId: string,
  index = 'ndvi',
  date = 'latest',
  tenantId?: string | null,
  cacheVersion?: string | number | null,
  geometry?: { type?: string; coordinates?: unknown } | null,
  bbox?: [number, number, number, number] | null,
): string => {
  const params = new URLSearchParams({ index: normalizeIndicatorIndex(index) });
  if (date && date !== 'latest') params.set('date', date);
  // الإنتاج: البوّابة تشتقّ المستأجِر من JWT الموثّق (X-Tenant-Id) فلا حاجة لـtid في الرابط؛
  // التطوير يُبقيه كـfallback لخدمة الراستر (raster_security_context يقرأ الرأس أوّلاً ثمّ tid).
  if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);
  if (cacheVersion !== undefined && cacheVersion !== null && String(cacheVersion) !== '') params.set('v', String(cacheVersion));
  // عقد القصّ الموحَّد (poly/bbox) — نفس ما يفحصه cdse-tilejson (مصدر حقيقة واحد).
  for (const [k, v] of Object.entries(cdseClipParams(geometry, bbox))) params.set(k, v);
  appendTileAccessToken(params);  // مصادقة بلاطة <img> خلف بوّابة auth_request
  const qs = params.toString();
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/cdse-tiles/{z}/{x}/{y}.png?${qs}`;
};

// مُصغَّرة كاملة لصورة الحقل (مؤشّر/تاريخ) — لبطاقات شريط السجلّ الزمنيّ. نفس عقد
// القصّ (poly/bbox) والمصادقة كبلاطة cdse-tiles، لكن صورة واحدة مباشرة (لا {z}/{x}/{y}).
export const fieldCdseThumbnailUrl = (
  fieldId: string,
  index = 'ndvi',
  date = 'latest',
  tenantId?: string | null,
  geometry?: { type?: string; coordinates?: unknown } | null,
  bbox?: [number, number, number, number] | null,
  size = 160,
): string => {
  const params = new URLSearchParams({ index: normalizeIndicatorIndex(index) });
  if (date && date !== 'latest') params.set('date', date);
  // الإنتاج: البوّابة تشتقّ المستأجِر من JWT الموثّق (X-Tenant-Id) فلا حاجة لـtid في الرابط؛
  // التطوير يُبقيه كـfallback لخدمة الراستر (raster_security_context يقرأ الرأس أوّلاً ثمّ tid).
  if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);
  params.set('size', String(size));
  // بطاقات السجلّ الزمنيّ تعرض أصلاً مُدَاماً مُعلَناً للتاريخ/المؤشّر، لا اكتشافاً حيّاً.
  // source=persisted يجعل الغياب fail-closed (404 → onError) بدل 200 + PNG شفّاف صامت.
  params.set('source', 'persisted');
  // عقد القصّ الموحَّد (poly/bbox) — نفس المصدر المشترك مع البلاطة وTileJSON.
  for (const [k, v] of Object.entries(cdseClipParams(geometry, bbox))) params.set(k, v);
  appendTileAccessToken(params);
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/cdse-thumbnail.png?${params.toString()}`;
};

// ══════════════════════════════════════════════════════════════════
// TERRAIN — التضاريس (Hillshade / Slope / Contours) من DEM حقيقيّ عبر raster-service
// عقد الخادم (مثبّت — لا يُعدَّل من الواجهة):
//   • GET /v1/elevation/hillshade/{z}/{x}/{y}.png?tid=<tenant> → PNG رماديّ (شفّاف بلا DEM)
//   • GET /v1/slope/{z}/{x}/{y}.png?tid=<tenant>              → PNG مُصنَّف مُلوَّن (شفّاف بلا DEM)
//   • GET /v1/terrain/tilejson?layer=hillshade|slope          → TileJSON + available/legend/user_message
//   • GET /v1/fields/{id}/contours.geojson?bbox=…&interval_m=… → FeatureCollection<MultiLineString>
// صدق صارم (كسائر المنصّة): عند available:false / computed:false / features:[] لا
// نخترع تضاريس؛ تعرض الواجهة حالة فارغة/معطّلة أو رسالة user_message من الخادم.
// ══════════════════════════════════════════════════════════════════
export type TerrainLayer = 'hillshade' | 'slope';

// درجة أسطورة الانحدار (من tilejson.legend حين layer=slope) — لون + مدى نسبة مئويّة + وصف.
export interface TerrainLegendStop {
  min_pct: number;
  max_pct: number;
  color: string;
  label: string;
}

// TileJSON لطبقة تضاريس. available:false + user_message حين لا DEM مُهيّأ (حالة صادقة).
export interface TerrainTileJson {
  tilejson?: string;
  tiles: string[];            // قوالب روابط البلاطات ({z}/{x}/{y}) — قد تكون [] عند عدم التوفّر
  bounds?: [number, number, number, number];
  available: boolean;
  layer: string;              // hillshade | slope
  reason?: string;
  user_message?: string;      // رسالة عربيّة صريحة حين available:false (لا DEM)
  legend?: TerrainLegendStop[];
}

/** يجلب TileJSON لطبقة تضاريس (hillshade|slope) عبر raster-service. عند غياب DEM يعيد
 *  available:false + user_message — تعرضه الواجهة كحالة صادقة (لا تلفيق تضاريس). */
export const fetchTerrainTileJson = (
  layer: TerrainLayer,
  tenantId?: string | null,
): Promise<TerrainTileJson> =>
  rasterApi
    .get<TerrainTileJson>('/v1/terrain/tilejson', {
      params: { layer, ...(tenantId ? { tid: tenantId } : {}) },
    })
    .then(r => r.data);

// روابط قوالب بلاطات التضاريس ({z}/{x}/{y}) — نُبقيها حرفيّة ليفسّرها Leaflet/MapLibre،
// على نمط fieldCdseTileUrl: tid للمستأجِر + access_token لمصادقة بلاطة <img> خلف البوّابة.
export const hillshadeTileUrl = (tenantId?: string | null): string => {
  const params = new URLSearchParams();
  // الإنتاج: البوّابة تشتقّ المستأجِر من JWT الموثّق (X-Tenant-Id) فلا حاجة لـtid في الرابط؛
  // التطوير يُبقيه كـfallback لخدمة الراستر (raster_security_context يقرأ الرأس أوّلاً ثمّ tid).
  if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);
  appendTileAccessToken(params);
  const qs = params.toString();
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/elevation/hillshade/{z}/{x}/{y}.png${qs ? `?${qs}` : ''}`;
};

export const slopeTileUrl = (tenantId?: string | null): string => {
  const params = new URLSearchParams();
  // الإنتاج: البوّابة تشتقّ المستأجِر من JWT الموثّق (X-Tenant-Id) فلا حاجة لـtid في الرابط؛
  // التطوير يُبقيه كـfallback لخدمة الراستر (raster_security_context يقرأ الرأس أوّلاً ثمّ tid).
  if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);
  appendTileAccessToken(params);
  const qs = params.toString();
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/slope/{z}/{x}/{y}.png${qs ? `?${qs}` : ''}`;
};

// خصائص عنصر كنتور — الارتفاع بالمتر مضمون؛ بقيّة المفاتيح متسامِحة (مصدر خارجيّ).
export interface ContourFeatureProperties {
  elevation_m: number;
  [key: string]: unknown;
}
export type ContourFeature = GeoJSON.Feature<GeoJSON.MultiLineString, ContourFeatureProperties>;

// FeatureCollection لخطوط الكنتور + أعلام الحساب. computed:false + features:[] حين لا DEM.
export interface FieldContours
  extends GeoJSON.FeatureCollection<GeoJSON.MultiLineString, ContourFeatureProperties> {
  computed: boolean;
  source?: string;
  field_id?: string;
  reason?: string;
  user_message?: string;
}

/** يجلب خطوط كنتور الحقل (GeoJSON MultiLineString) من DEM حقيقيّ عبر raster-service.
 *  bbox بترتيب [minLon,minLat,maxLon,maxLat] (اختياريّ)؛ intervalM فاصل الكنتور بالمتر.
 *  عند غياب DEM يعيد computed:false + features:[] — لا نخترع خطوطاً. */
export const fetchFieldContours = (
  fieldId: string,
  bbox?: [number, number, number, number] | null,
  intervalM?: number,
  geometry?: { type?: string; coordinates?: unknown } | null,
): Promise<FieldContours> =>
  rasterApi
    .get<FieldContours>(`/v1/fields/${fieldId}/contours.geojson`, {
      params: {
        ...(bbox && bbox.length === 4 ? { bbox: bbox.join(',') } : {}),
        ...(intervalM ? { interval_m: intervalM } : {}),
        // poly = حدّ الحقل ⇒ الخادم يقصّ الكنتور داخل الحقل (لا على المستطيل المحيط).
        ...(cdseClipParams(geometry).poly ? { poly: cdseClipParams(geometry).poly } : {}),
      },
    })
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// SOIL (SoilGrids) — خصائص التربة التقديريّة (~250م) عبر raster-service
// عقد الخادم (مثبّت — لا يُعدَّل من الواجهة):
//   • GET /v1/soil/tiles/{prop}/{depth}/{z}/{x}/{y}.png?tid=<tenant> → PNG مُلوَّن نصف-شفّاف (شفّاف بلا مصدر)
//   • GET /v1/soil/tilejson?property=<prop>&depth=<depth> → TileJSON + available/legend/disclaimer/user_message
//   • GET /v1/soil/properties → قائمة الخصائص + الأعماق + source_configured + disclaimer
// صدق صارم: SoilGrids تقدير عالميّ (~250م) لإرشاد أخذ العيّنات فقط — ليس بديلاً
// عن تحليل مختبر. الـdisclaimer يُعرَض دوماً حين الطبقة مفعّلة. عند available:false
// لا نبني بلاطة؛ نعرض user_message الصادق من الخادم (لا نختلق قيم تربة).
// ══════════════════════════════════════════════════════════════════
export type SoilProperty =
  | 'phh2o' | 'clay' | 'sand' | 'silt' | 'soc' | 'cec' | 'nitrogen' | 'bdod';

// درجة أسطورة التربة (من tilejson.legend) — قيمة + لون.
export interface SoilLegendStop {
  value: number;
  color: string;
}

// TileJSON لطبقة تربة. available:false + user_message حين لا مصدر مُهيّأ (حالة صادقة).
// disclaimer حاضر دوماً (تقدير SoilGrids — إرشاد أخذ عيّنات فقط، لا بديل مختبر).
export interface SoilTileJson {
  tilejson?: string;
  tiles?: string[];           // قوالب روابط البلاطات ({z}/{x}/{y}) — قد تغيب عند عدم التوفّر
  bounds?: [number, number, number, number];
  available: boolean;
  property: string;           // phh2o | clay | ...
  name_ar: string;            // اسم الخاصّيّة بالعربيّة
  unit: string;               // الوحدة (مثل pH / g/kg / cmol(+)/kg)
  depth: string;              // 0-5cm | 5-15cm | ...
  legend: SoilLegendStop[];   // قيمة + لون لكلّ درجة
  disclaimer: string;         // إخلاء مسؤوليّة إلزاميّ العرض
  reason?: string;
  user_message?: string;      // رسالة عربيّة صريحة حين available:false (لا مصدر)
}

// عنصر قائمة خصائص التربة (GET /v1/soil/properties) — المفتاح + التسمية + المدى.
export interface SoilPropertyMeta {
  key: SoilProperty;
  name_ar: string;
  unit: string;
  vmin: number;
  vmax: number;
}
export interface SoilPropertiesResponse {
  properties: SoilPropertyMeta[];
  depths: string[];
  source_configured: boolean;
  disclaimer: string;
}

/** يجلب TileJSON لخاصّيّة تربة (property/depth) عبر raster-service. عند غياب المصدر
 *  يعيد available:false + user_message — تعرضه الواجهة كحالة صادقة (لا تلفيق قيم تربة).
 *  الـdisclaimer حاضر دوماً ويجب عرضه حين الطبقة مفعّلة. */
export const fetchSoilTileJson = (
  property: SoilProperty,
  depth: string,
  tenantId?: string | null,
): Promise<SoilTileJson> =>
  rasterApi
    .get<SoilTileJson>('/v1/soil/tilejson', {
      params: { property, depth, ...(tenantId ? { tid: tenantId } : {}) },
    })
    .then(r => r.data);

// رابط قالب بلاطات التربة ({z}/{x}/{y}) — نُبقيها حرفيّة ليفسّرها Leaflet/MapLibre،
// على نمط hillshadeTileUrl/slopeTileUrl: tid للمستأجِر + access_token لمصادقة بلاطة
// <img> خلف البوّابة. البلاطة نصف-شفّافة، وشفّافة تماماً حيث لا مصدر (لا اختراع تربة).
export const soilTileUrl = (
  property: SoilProperty,
  depth: string,
  tenantId?: string | null,
): string => {
  const params = new URLSearchParams();
  // الإنتاج: البوّابة تشتقّ المستأجِر من JWT الموثّق (X-Tenant-Id) فلا حاجة لـtid في الرابط؛
  // التطوير يُبقيه كـfallback لخدمة الراستر (raster_security_context يقرأ الرأس أوّلاً ثمّ tid).
  if (!import.meta.env.PROD && tenantId) params.set('tid', tenantId);
  appendTileAccessToken(params);
  const qs = params.toString();
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/soil/tiles/${property}/${depth}/{z}/{x}/{y}.png${qs ? `?${qs}` : ''}`;
};

/** يجلب قائمة خصائص التربة المدعومة + الأعماق + هل المصدر مُهيّأ (source_configured)
 *  + إخلاء المسؤوليّة. أفضل-جهد للتعبئة الديناميكيّة للقوائم المنسدلة. */
export const fetchSoilProperties = (): Promise<SoilPropertiesResponse> =>
  rasterApi
    .get<SoilPropertiesResponse>('/v1/soil/properties')
    .then(r => r.data);

// ── نقاط أخذ العيّنات المقترَحة (soil sampling plan) عبر raster-service ──
// عقد الخادم (مثبّت — لا يُعدَّل من الواجهة):
//   GET /v1/fields/{field_id}/soil/sampling-plan?bbox=minLon,minLat,maxLon,maxLat
//       &depth=0-5cm&zones=3&samples_per_zone=1
//   → GeoJSON FeatureCollection من نقاط (Point) + أعلام حساب. عند غياب مصدر
//     SoilGrids المُهيّأ ⇒ { computed:false, features:[] } — لا نخترع نقاطاً.
// خصائص كلّ نقطة: point_id (soil_A1) · zone_id (A) · reason_ar (شرح عربيّ)
// · tests (قائمة الفحوص) · soil (لقطة قيم التربة التقديريّة، متسامِحة).
export interface SoilSamplePointProperties {
  point_id: string;
  zone_id: string;
  reason_ar: string;
  tests: string[];
  soil?: Record<string, unknown>;
  [key: string]: unknown;
}
export type SoilSamplePointFeature = GeoJSON.Feature<GeoJSON.Point, SoilSamplePointProperties>;

// FeatureCollection لنقاط أخذ العيّنات + أعلام الحساب. computed:false + features:[]
// حين لا مصدر تربة مُهيّأ (حالة صادقة — لا تلفيق نقاط).
export interface SoilSamplingPlan
  extends GeoJSON.FeatureCollection<GeoJSON.Point, SoilSamplePointProperties> {
  computed: boolean;
  source?: string;
  field_id?: string;
  reason?: string;
  user_message?: string;
}

/** يجلب خطّة أخذ عيّنات التربة (GeoJSON نقاط Point) لحقل عبر raster-service.
 *  bbox بترتيب [minLon,minLat,maxLon,maxLat] (اختياريّ)؛ opts: العمق/عدد المناطق/
 *  عيّنات لكلّ منطقة. عند غياب مصدر SoilGrids يعيد computed:false + features:[] —
 *  لا نخترع نقاطاً (نفس نمط fetchFieldContours / fetchSoilTileJson). */
export const fetchSoilSamplingPlan = (
  fieldId: string,
  bbox?: [number, number, number, number] | null,
  opts?: { depth?: string; zones?: number; samplesPerZone?: number; geometry?: { type?: string; coordinates?: unknown } | null },
): Promise<SoilSamplingPlan> =>
  rasterApi
    .get<SoilSamplingPlan>(`/v1/fields/${fieldId}/soil/sampling-plan`, {
      params: {
        ...(bbox && bbox.length === 4 ? { bbox: bbox.join(',') } : {}),
        ...(opts?.depth ? { depth: opts.depth } : {}),
        ...(opts?.zones ? { zones: opts.zones } : {}),
        ...(opts?.samplesPerZone ? { samples_per_zone: opts.samplesPerZone } : {}),
        // poly = حدّ الحقل ⇒ عيّنات داخل الحقل فقط (لا على المستطيل المحيط).
        ...(cdseClipParams(opts?.geometry).poly ? { poly: cdseClipParams(opts?.geometry).poly } : {}),
      },
    })
    .then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// INDICATORS DASHBOARD — لوحة المؤشّرات المُجمَّعة (حيّة عبر البوّابة)
// صدق المصدر: indicators-service خدمة stub صحّيّة فقط (لا منطق). اللوحة والكتالوج
// الحقيقيّان مُخدَّمان من sahool-platform عبر /api/v1/indicators/* (تجميع من
// fields/seasons/alerts، tenant-scoped + FIELD_VIEW). لا fallback وهميّ — عند
// الخطأ (503 DB / 403) يُرمى لتعرض الواجهة حالة صادقة (إلّا في MOCK_MODE الصريح).
// ══════════════════════════════════════════════════════════════════

/** لوحة المؤشّرات المُجمَّعة للمستأجِر: kpis + alerts + fields_summary */
export const fetchDashboard = () =>
  tryReal(
    () => kongApi.get('/api/v1/indicators/dashboard').then(r => r.data),
    () => MOCK_DASHBOARD
  );

/** كتالوج المؤشّرات المُنفَّذة فعلاً + مصادرها (لا ٣٣ مؤشّراً مُلفَّقاً) */
export const fetchIndicatorCatalog = () =>
  tryReal(
    () => kongApi.get('/api/v1/indicators/catalog').then(r => r.data),
    () => ({ total:14, categories:{} })
  );

// ملحوظة صدق: المؤشّرات الطيفيّة لكلّ حقل (NDVI/EVI/...) تُجلب من vegetation/raster
// لكلّ حقل (شاشة الأقمار) لا من نقطة 33-مؤشّر وهميّة. لذا fetchFieldIndicators/
// fetchSingleIndicator/fetchNatsStatus (التي كانت تستهدف indicators-service الـstub
// بلا خلفيّة حقيقيّة) أُزيلت لمصلحة الربط الحيّ الموحَّد عبر vegetation/raster.

/** Probes */
export const fetchIndicatorsHealth = () =>
  indicatorsApi.get('/health').then(r => r.data).catch(() => ({ status:'unavailable' }));

// ══════════════════════════════════════════════════════════════════
// VEGETATION SERVICE — مسارات حيّة مطابقة لـvegetation-analysis-service
// ربط حقيقيّ بلا تلفيق (إلّا MOCK_MODE الصريح). صدق المصدر: المؤشّرات تقديرات
// متوسّط-حقل من نطاقات تركيبيّة (real_data=false) — البكسلات الحقيقيّة في
// raster-service. أُصلحت المسارات/الأفعال لتطابق الخادم الفعليّ (GET /v1/*).
// ══════════════════════════════════════════════════════════════════

/** تشغيل معالجة صور Sentinel-2 الحقيقيّة للحقل عبر المنصّة/raster-service. */
export const refreshFieldImagery = (fieldId: string, date?: string | null, geometry?: unknown) => {
  const body: Record<string, unknown> = {};
  if (date && date !== 'latest') body.date = date;
  if (geometry) body.geometry = geometry;
  return kongApi.post(
    `/api/v1/fields/${fieldId}/imagery/refresh`,
    Object.keys(body).length ? body : undefined,
  ).then(r => r.data);
};

/** V8-05 PR2: زرّ «عالِج هذا التاريخ» الصريح — يُجدوِل معالجة مشهد مفرد لتاريخٍ اختاره
 *  المستخدم عبر بوّابة المنصّة (لا يُطلقه اختيار التاريخ). يعيد
 *  ``{run_id,item_id,status,reused_existing_job}``؛ ``reused_existing_job`` يعني أنّ الأصل
 *  جاهز/قيد المعالجة أصلاً (لا معالجة مكرّرة). */
export interface ProcessImageryDateResult {
  field_id: string;
  date: string;
  index: string;
  scene_id: string;
  run_id: number | null;
  item_id: number | null;
  status: string;
  reused_existing_job: boolean;
}
export const processFieldImageryDate = (
  fieldId: string,
  params: { date: string; index: string; scene_id: string; geometry?: unknown },
): Promise<ProcessImageryDateResult> => {
  const body: Record<string, unknown> = {
    date: params.date,
    index: params.index,
    scene_id: params.scene_id,
  };
  if (params.geometry) body.geometry = params.geometry;
  return kongApi
    .post(`/api/v1/fields/${fieldId}/imagery/process-date`, body)
    .then((r) => r.data as ProcessImageryDateResult);
};

/** UI deeper-fix: غلاف متوافق للخلف — أيّ كود قديم يستدعي analyzeVegetation يجب ألّا
 *  يذهب إلى vegetation-service /v1/analyze بمعرّفات platform (fld_*) لأنّها لا تملكها
 *  (⇒ «field_id not found»). نُوجّهه للمسار القانونيّ نفسه: platform → raster-service. */
export const analyzeVegetation = (fieldId: string, _satellite = 'sentinel-2', _tenantId = 'default') =>
  tryReal(
    () => refreshFieldImagery(fieldId),
    () => mockVegetationAnalysis(fieldId)
  );


export interface FieldImageryDateOption {
  date: string;
  cloud_pct?: number | null;
  cloud_cover?: number | null;
  // AOI-CLOUD-CONTRACT (#636): scene vs field cloud — aoi_cloud_pct=null=«لم تُحسب» لا 0%.
  scene_cloud_pct?: number | null;
  aoi_cloud_pct?: number | null;
  clear_pct?: number | null;
  quality_label?: 'high' | 'medium' | 'cloudy' | 'unknown' | string | null;
  has_cog?: boolean;
  scene_id?: string | null;
  // FINDING-006: المؤشّرات المتوفّرة لهذا التاريخ (الخادم يُرجِعها) — كي لا يُختار
  // تاريخٌ «جاهز» لمؤشّر غير المؤشّر النشط فتظهر بلاطة شفّافة. تُستعمَل للتصفية.
  indices?: string[];
  // وقت الالتقاط الحقيقيّ (ISO8601 UTC) من كتالوج STAC حين يتوفّر — لعرض «تاريخ الالتقاط».
  // غيابه (null) ⇒ الواجهة تعرض التاريخ وحده بصدق (acquisition_date تاريخ بلا وقت).
  acquisition_datetime?: string | null;
  // رابط المصغّرة القانونيّ حين يأتي العنصر من واجهة `/imagery/timeline`
  // (تبنيه الواجهة الخلفيّة بـ`source=persisted`). مسار `available-dates`
  // لا يُرجِعه، فيبنيه العميل بالسياسة نفسها.
  thumbnail_url?: string | null;
}

/** تواريخ Sentinel/CDSE المتاحة للحقل؛ تُستخدم لربط زر التاريخ فعلياً برابط البلاطات.
 *  index اختياريّ: عند تمريره يقصر الخادم التواريخ على ما له COG لذلك المؤشّر
 *  (يُغني عن اختيار تاريخ لا يملك المؤشّر النشط — FINDING-006). */
// إحصاءات تضاريس الحقل (ارتفاع/انحدار/اتّجاه + حصاد المياه) من DEM حقيقيّ عبر
// المنصّة → raster-service. صدق: قد يعود `computed:false` بمصدره (لا DEM/لا bbox)
// وتعرضه الواجهة كحالة صادقة بدل رقم مفبرك.
export interface FieldTerrain {
  computed: boolean;
  source?: string;
  reason?: string;
  elevation_m?: { min: number | null; max: number | null; mean: number | null };
  slope_deg?: { min: number; max: number; mean: number };
  flat_pct?: number;
  steep_pct?: number;
  dominant_aspect?: string | null;
  water_harvesting?: { recommended_technique?: string; suitability?: string };
}
// مصدر الحقيقة الموحّد للحقل: قراءة واحدة تجمع (field/geometry/season/canonical_state/
// soil_samples/irrigation/…) لتفادي تشتّت الشاشات عبر عدّة نداءات. الأقسام غير المتاحة
// تُعلَن available:false بصدق (لا تلفيق) — انظر backend /state/full.
export interface FieldStateFull {
  field_id: string;
  field?: Record<string, unknown> | null;
  geometry?: unknown;
  crop?: string | null;
  season?: { available: boolean; crop?: string | null; stage?: string | null; sowing_date?: string | null } & Record<string, unknown>;
  canonical_state?: Record<string, unknown>;
  alerts?: unknown[];
  soil_samples?: unknown[] | { available: boolean; reason?: string };
  irrigation?: { water_ledger?: unknown; recent_runs?: unknown[] };
  recommendations?: { available: boolean; reason?: string; endpoint?: string };
  water_samples?: { available: boolean; reason?: string };
  economics?: { available: boolean; reason?: string };
}
export const fetchFieldState = (fieldId: string): Promise<FieldStateFull> =>
  kongApi.get(`/api/v1/fields/${fieldId}/state/full`).then((r) => r.data as FieldStateFull);

// خطّ زمنيّ جاهز للأقمار من الخادم (تواريخ COG حقيقيّة + thumbnail_url لكل تاريخ)،
// محدود بآخر N شهراً. الواجهة تُحمّل المصغّرات كسولاً عبر thumbnail_url بدل جلب الكلّ.
export interface ImageryTimelineItem {
  date: string;
  has_cog: boolean;
  cloud_pct: number | null;
  // AOI-CLOUD-CONTRACT (#636): سحابة صريحة مزدوجة القيمة —
  //  • scene_cloud_pct: سحابة المشهد كاملاً (STAC).
  //  • aoi_cloud_pct: السحابة فوق مضلّع الحقل؛ null=«لم تُحسب» (ليس 0%).
  scene_cloud_pct?: number | null;
  aoi_cloud_pct?: number | null;
  clear_pct?: number | null;
  quality_label?: 'high' | 'medium' | 'cloudy' | 'unknown' | string | null;
  indices: string[];
  scene_id?: string | null;
  acquisition_datetime?: string | null;
  thumbnail_url: string;
}
export interface ImageryTimeline {
  field_id: string;
  months: number;
  count: number;
  items: ImageryTimelineItem[];
}
export const fetchFieldImageryTimeline = (fieldId: string, months = 24): Promise<ImageryTimeline> =>
  kongApi
    .get(`/api/v1/fields/${fieldId}/imagery/timeline`, { params: { months } })
    .then((r) => r.data as ImageryTimeline);

export const fetchFieldTerrain = (fieldId: string): Promise<FieldTerrain> =>
  kongApi.get(`/api/v1/fields/${fieldId}/terrain`).then((r) => {
    // الخادم يُرجِع تفسير enrich_terrain + dem_auto_fill.computed (المظروف الخام من
    // حساب DEM الحيّ). نقرأ الكتلة المحسوبة؛ غيابها ⇒ computed=false صادق.
    const c = r.data?.dem_auto_fill?.computed;
    return (c && typeof c === 'object' ? c : { computed: false }) as FieldTerrain;
  });

export const fetchFieldImageryAvailableDates = (
  fieldId: string,
  index?: string,
  limit = 240,
  opts?: { includeProvider?: boolean; months?: number },
): Promise<FieldImageryDateOption[]> =>
  kongApi.get(`/api/v1/fields/${fieldId}/available-dates`, {
    params: {
      ...(index ? { index } : {}),
      limit,
      // TIMELINE-PROVIDER-DATES: يدمج الخادم تواريخ التقاط المزوّد (STAC) — غير
      // المعالَج يصل has_cog=false فيظهر «ينتظر COG» بتاريخه الحقيقيّ بلا صورة.
      ...(opts?.includeProvider ? { include_provider: true, months: opts?.months ?? 24 } : {}),
    },
  }).then((r) => {
    const raw = r.data?.dates ?? r.data?.items ?? r.data ?? [];
    if (!Array.isArray(raw)) return [];
    return raw
      .map((x: unknown) => {
        if (typeof x === 'string') return { date: x } as FieldImageryDateOption;
        if (!x || typeof x !== 'object') return null;
        const obj = x as Record<string, unknown>;
        const date = String(obj.date ?? obj.acquisition_date ?? obj.datetime ?? '').slice(0, 10);
        if (!date) return null;
        return {
          date,
          cloud_pct: typeof obj.cloud_pct === 'number' ? obj.cloud_pct : (typeof obj.cloud_cover === 'number' ? obj.cloud_cover : null),
          cloud_cover: typeof obj.cloud_cover === 'number' ? obj.cloud_cover : null,
          // AOI-CLOUD-CONTRACT (#636): scene vs field cloud — null=«لم تُحسب» لا 0%.
          scene_cloud_pct: typeof obj.scene_cloud_pct === 'number' ? obj.scene_cloud_pct : null,
          aoi_cloud_pct: typeof obj.aoi_cloud_pct === 'number' ? obj.aoi_cloud_pct : null,
          clear_pct: typeof obj.clear_pct === 'number' ? obj.clear_pct : null,
          quality_label: typeof obj.quality_label === 'string' ? obj.quality_label : null,
          has_cog: Boolean(obj.has_cog ?? obj.ready ?? false),
          scene_id: typeof obj.scene_id === 'string' ? obj.scene_id : null,
          indices: Array.isArray(obj.indices)
            ? (obj.indices as unknown[]).map((v) => String(v))
            : undefined,
          acquisition_datetime:
            typeof obj.acquisition_datetime === 'string' ? obj.acquisition_datetime : null,
        } as FieldImageryDateOption;
      })
      .filter(Boolean) as FieldImageryDateOption[];
  }).catch(() => []);


export type ImageryBackfillPreset = 'auto_12_months' | 'extended_3_years' | 'research_5_years' | 'custom';

export interface HistoricalImageryBackfillPayload {
  preset?: ImageryBackfillPreset;
  from_date?: string;
  to_date?: string;
  months?: number;
  indices?: string[];
  max_cloud_pct?: number;
  limit_per_month?: number;
  apply_cloud_mask?: boolean;
  clip_polygon_geojson?: unknown;
  dry_run?: boolean;
}

/** خيارات قابلة للتبديل لسحب الصور التاريخية: 12 شهر/3 سنوات/5 سنوات/مخصص. */
export const fetchImageryBackfillPolicy = () =>
  rasterApi.get('/v1/imagery/backfill/policy').then(r => r.data);

/** إنشاء خطة/مهمة backfill تاريخية للحقل. dry_run=true يعطي تقدير تكلفة/عدد مشاهد قبل التشغيل.
 * يمرّ عبر بوّابة sahool-platform (لا مباشرةً إلى raster-service) كي لا يُكشف X-Agent-Token للمتصفّح. */
export interface HistoricalImageryBackfillStatus {
  run_id?: number;
  id?: number;
  field_id?: string;
  status?: string;
  items_persisted?: number;
  items_failed?: number;
  items_skipped?: number;
  jobs_scheduled?: number;
  scenes_selected?: number;
  months_scanned?: number;
  item_status_counts?: Record<string, number>;
  error?: string | null;
  updated_at?: string | null;
}

export const isTerminalBackfillStatus = (status?: string | null) =>
  ['completed', 'completed_with_errors', 'failed', 'cancelled'].includes(String(status || '').toLowerCase());

/** إنشاء خطة/مهمة backfill تاريخية للحقل. dry_run=true يعطي تقدير تكلفة/عدد مشاهد قبل التشغيل.
 * يمرّ عبر بوّابة sahool-platform (لا مباشرةً إلى raster-service) كي لا يُكشف X-Agent-Token للمتصفّح. */
export const runHistoricalImageryBackfill = (fieldId: string, payload: HistoricalImageryBackfillPayload) =>
  kongApi.post(`/api/v1/fields/${fieldId}/imagery/backfill`, payload).then(r => r.data);

/** استطلاع حالة backfill اللاتزامني عبر بوابة المنصة، ثم إعادة مزامنة Timeline عند الاكتمال. */
export const fetchHistoricalImageryBackfillStatus = (fieldId: string, runId: number) =>
  kongApi.get(`/api/v1/fields/${fieldId}/imagery/backfill/${runId}`).then(r => r.data as HistoricalImageryBackfillStatus);

// ══════════════════════════════════════════════════════════════════
// كتالوج الأصناف المرجعيّ — reference_only_not_operational (PR #627)
// قراءة صرفة: بيانات أصناف الحبوب اليمنيّة الموثّقة المصدر. كلّ ردّ يحمل بوّابة الحوكمة
// decision_engine_use_status=reference_only_not_operational — مرجعٌ للعرض/الخبير، محجوبٌ
// عن التنفيذ الآليّ. لا كتابة، لا قرار. (يستهلك GET /api/v1/varieties/food-grains[/{id}])
// ══════════════════════════════════════════════════════════════════

export const VARIETY_REFERENCE_ONLY_STATUS = 'reference_only_not_operational';

export interface FoodGrainVariety {
  id: string;
  name_ar?: string;
  crop_code?: string;
  decision_engine_use_status: string;
  source_pages?: unknown;
  source_verification?: unknown;
  [key: string]: unknown;
}

export interface FoodGrainVarietyCatalog {
  decision_engine_use_status: string;
  metadata: Record<string, unknown>;
  count: number;
  varieties: FoodGrainVariety[];
  quality_issues: Array<Record<string, unknown>>;
}

/** كتالوج أصناف الحبوب الموثّق (اختياريّاً مُرشَّح بمحصول: wheat/barley/…). مرجعيّ فقط. */
export const fetchFoodGrainVarieties = (cropCode?: string): Promise<FoodGrainVarietyCatalog> =>
  kongApi
    .get('/api/v1/varieties/food-grains', { params: cropCode ? { crop_code: cropCode } : {} })
    .then((r) => r.data as FoodGrainVarietyCatalog);

/** صنفٌ واحد بمعرّفه — مرجعيّ فقط (404 إن لم يوجد في الكتالوج الموثّق). */
export const fetchFoodGrainVariety = (
  varietyId: string,
): Promise<{ decision_engine_use_status: string; variety: FoodGrainVariety }> =>
  kongApi
    .get(`/api/v1/varieties/food-grains/${encodeURIComponent(varietyId)}`)
    .then((r) => r.data);

/** سلسلة زمنية NDVI — GET /v1/timeseries/{fieldId} */
export const fetchVegetationTimeseries = (fieldId: string, days = 30) =>
  tryReal(
    () => vegetationApi.get(`/v1/timeseries/${fieldId}`, { params:{ days } }).then(r => r.data),
    () => mockTimeseries(fieldId, days)
  );

/** NDVI الحالي — GET /v1/ndvi/current/{fieldId} */
export const fetchCurrentNDVI = (fieldId: string) =>
  tryReal(
    () => vegetationApi.get(`/v1/ndvi/current/${fieldId}`).then(r => r.data),
    () => ({ field_id:fieldId, ndvi:{ current:0.62 }, classification:{ level:'good', label_ar:'جيد', color:'#65a30d' } })
  );

// ══════════════════════════════════════════════════════════════════
// WEATHER — موحّد على المنصّة (sahool-platform/api/routers/weather.py)
// ══════════════════════════════════════════════════════════════════
// weather-service يملك منطق الطقس الحقيقيّ (Open-Meteo + ET₀ FAO-56)، والمنصّة
// تعرضه عبر BFF آمن: /api/v1/weather/{current,forecast,historical}. لذلك تبقى
// الواجهة على kongApi ولا تستدعي weatherApi مباشرةً من المتصفح. الردّ بشكل المنصّة
// الخام (days[].temp_max_c …).

export const fetchCurrentWeather = (lat = 15.05, lon = 45.55) =>
  tryReal(
    () => kongApi.get('/api/v1/weather/current', { params:{ lat, lon } }).then(r => r.data),
    () => ({ current: MOCK_WEATHER_TODAY, location:{ lat, lon, region:'البيضاء، اليمن' } })
  );

export const fetchWeatherForecast = (days = 7, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => kongApi.get('/api/v1/weather/forecast', { params:{ days, lat, lon } }).then(r => r.data),
    () => ({ forecast:mockWeatherDays(days), days, summary:{ total_gdd:85, total_et0_mm:31, avg_tmax_c:31 } })
  );

export const fetchWeatherHistorical = (days = 30, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => {
      // المنصّة تتطلّب نطاق تاريخ صريح (start_date/end_date) لا عدد أيّام.
      const end = new Date();
      const start = new Date(end.getTime() - days * 86_400_000);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      return kongApi
        .get('/api/v1/weather/historical', { params:{ lat, lon, start_date: iso(start), end_date: iso(end) } })
        .then(r => r.data);
    },
    () => ({ period_days:days, data:mockWeatherDays(days), summary:{ total_gdd:300, water_deficit_mm:45, total_et0_mm:130, total_rainfall_mm:85 } })
  );

export const fetchWofostFormat = (days = 30, lat = 15.05, lon = 45.55) =>
  // لا نقطة wofost_format على المنصّة؛ نشتقّ مدخلات WOFOST من توقّعات المنصّة الحقيقيّة.
  tryReal(
    () => kongApi.get('/api/v1/weather/forecast', { params:{ days, lat, lon } }).then(r => {
      const rawDays = Array.isArray(r.data?.days) ? r.data.days : [];
      return {
        wofost_input: rawDays.map((d: { date?: string; temp_max_c?: number; temp_min_c?: number; solar_radiation_mj_m2?: number; et0_mm?: number; precipitation_mm?: number }) => ({
          date: d.date ?? null, tmax: d.temp_max_c ?? null, tmin: d.temp_min_c ?? null,
          radiation_mj: d.solar_radiation_mj_m2 ?? null, et0: d.et0_mm ?? null,
          precipitation: d.precipitation_mm ?? null,
        })),
        total_days: rawDays.length,
        source: 'sahool-platform',
      };
    }),
    () => ({ wofost_input:mockWeatherDays(days).map(d => ({ date:d.date, tmax:d.tmax, tmin:d.tmin, radiation_mj:18, et0:d.et0, precipitation:d.rain, soil_moisture_pct:35 })), total_days:days, source:'demo-only' })
  );

// ملاحظة صدق: لا نقطة agro-indicators مكافئة ضمن BFF المنصّة حتى الآن. غير
// مُستهلَكة في أيّ واجهة. مُبقاة للـMOCK_MODE فقط؛ خارجه ترمي بصدق (لا تلفيق)
// حتى تُبنى نقطة مكافئة وتُمرّر عبر المنصّة.
export const fetchAgroIndicators = (_days = 30) =>
  tryReal(
    () => Promise.reject(new Error('agro-indicators: لا نقطة مكافئة على المنصّة بعد')),
    () => ({ gdd_accumulated:305, et0_accumulated_mm:132, rainfall_accumulated_mm:87, water_deficit_mm:45, drought_stress_days:5 })
  );

// ══════════════════════════════════════════════════════════════════
// SOIL — صدق: خدمة soil-service غير منشورة (مُعلّقة في compose؛ nginx يردّ 503 على
// /api/soil/) ولا مكافئ لتركيب التربة على المنصّة. الدوالّ أدناه غير مُستهلَكة في
// أيّ واجهة (المكوّن الوحيد FarmAdvisoryReport يستعمل hooks مُعطّلة خلف FEATURE_FLAGS.soil
// مع حالة «بيانات التربة غير متاحة» الصادقة). مُبقاة للـMOCK_MODE ولِما بعد نشر
// soil-service بتنفيذ حقيقيّ؛ خارج MOCK_MODE تضرب /api/soil ⇒ 503 صادق (لا تلفيق).
// ══════════════════════════════════════════════════════════════════

export const fetchSoilData = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/${fieldId}`).then(r => r.data),
    () => mockSoilData(fieldId)
  );

export const fetchAllSoilData = () =>
  tryReal(
    () => soilApi.get('/soil/all').then(r => r.data),
    () => ({ readings:MOCK_FIELDS.map(f => mockSoilData(f.field_id)), total:8 })
  );

export const fetchSoilWofostParams = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/wofost_params/${fieldId}`).then(r => r.data),
    () => ({ rdmsol:1.2, soil_water_capacity_mm:150, wilting_point_pct:15, field_capacity_pct:35, suitable_for_wofost:true })
  );

export const fetchNitrogenRecommendation = (fieldId: string, targetYield = 5.0) =>
  tryReal(
    () => soilApi.get('/soil/nitrogen/recommendation', { params:{ field_id:fieldId, target_yield_t_ha:targetYield } }).then(r => r.data),
    () => ({ recommended_n_kg_ha:87.5, n_demand_kg_ha:125, n_available_kg_ha:37.5, method:'FAO adjusted', timing:'40% زراعة + 30% تفريع + 30% تطاول' })
  );

export const fetchSoilRecommendations = (fieldId: string) =>
  tryReal(
    () => soilApi.get(`/soil/${fieldId}/recommendations`).then(r => r.data),
    () => ({ recommendations:['✅ التربة في حالة جيدة — استمر بنفس الإدارة'], priority:'روتيني' })
  );

export const postSoilReading = (data: { field_id:string; ph?:number; moisture_pct?:number; nitrogen_mg_kg?:number }) =>
  tryReal(
    () => soilApi.post('/soil/reading', data).then(r => r.data),
    () => ({ status:'received', nats_published:false })
  );

// ── حوكمة التربة الكنسيّة (soil-service P4 عبر بوّابة /api/soil) ──
// قراءة فقط، بلا mock: البوّابة تحقن التوكن+المستأجر، وsoil-service يخدم /v1/...
// عند غياب لقطة تربة يعيد الخادم 404/503 صادقاً وتُظهِر البطاقة حالة «لا لقطة بعد».
export const fetchSoilProfileSnapshot = (fieldId: string) =>
  soilApi.get(`/v1/fields/${fieldId}/soil/profile`).then(r => r.data);

export const fetchSoilClosedLoop = (fieldId: string) =>
  soilApi.get(`/v1/fields/${fieldId}/soil/closed-loop`).then(r => r.data);

export const fetchSoilProfileHistory = (fieldId: string) =>
  soilApi.get(`/v1/fields/${fieldId}/soil/profile/history`).then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// PROBES — فحص صحة كل الخدمات
// ══════════════════════════════════════════════════════════════════
export const checkAllServices = async () => {
  const checks = await Promise.allSettled([
    indicatorsApi.get('/health').then(r => ({ name:'indicators', ...r.data })),
    vegetationApi.get('/health').then(r => ({ name:'vegetation',  ...r.data })),
    weatherApi.get('/health').then(r    => ({ name:'weather',     ...r.data })),
    soilApi.get('/health').then(r       => ({ name:'soil',        ...r.data })),
    kongApi.get('/').then(r             => ({ name:'kong',         status:'ok' })),
  ]);
  return checks.map((r, i) =>
    r.status === 'fulfilled'
      ? r.value
      : { name:['indicators','vegetation','weather','soil','kong'][i], status:'unavailable' }
  );
};

// ══════════════════════════════════════════════════════════════════
// FLEET HEALTH — صحّة أسطول الأجهزة (كشف استباقي للأجهزة الصامتة، مرتّب بالخطورة).
// تستهلك GET /api/v1/devices/fleet-health (devices.py ⇒ assess_fleet): ملخّص عدديّ
// + قائمة الأجهزة الصامتة. مُقيَّد device:view. لا fallback وهميّ: عند الخطأ (503 DB
// مُعطَّلة / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة (بلاطة المعدّات لها حالة خطأ مستقلّة).
// ══════════════════════════════════════════════════════════════════
export type DeviceCriticalityLevel = 'critical' | 'important' | 'optional';

/** جهاز صامت واحد في تقرير صحّة الأسطول (مرتّب: الحرج أوّلاً). */
export interface SilentDeviceHealth {
  device_id:            string;
  name:                 string;
  type:                 string;
  field_id:             string | null;
  silent:               boolean;
  criticality:          DeviceCriticalityLevel | string;
  detail_ar:            string;
  criticality_note_ar:  string;
  threshold_minutes:    number;
}

/** صحّة الأسطول كاملة (ملخّص عدديّ + الأجهزة الصامتة مرتّبة بالخطورة). */
export interface FleetHealth {
  total_devices:    number;
  online:           number;
  silent:           number;
  critical_silent:  number;
  fleet_status_ar:  string;
  silent_devices:   SilentDeviceHealth[];
  proactive_note_ar?: string;
}

/** يجلب صحّة الأسطول (device:view). الخطأ (503/403) يُرفع لحالة صادقة. نطبّع
 *  silent_devices دفاعيّاً إن اختلف شكلها (لا انهيار .map). */
export const fetchFleetHealth = (): Promise<FleetHealth> =>
  kongApi.get<FleetHealth>('/api/v1/devices/fleet-health').then((r) => {
    const d = (r.data ?? {}) as Partial<FleetHealth>;
    return {
      total_devices:   typeof d.total_devices === 'number' ? d.total_devices : 0,
      online:          typeof d.online === 'number' ? d.online : 0,
      silent:          typeof d.silent === 'number' ? d.silent : 0,
      critical_silent: typeof d.critical_silent === 'number' ? d.critical_silent : 0,
      fleet_status_ar: typeof d.fleet_status_ar === 'string' ? d.fleet_status_ar : '',
      silent_devices:  Array.isArray(d.silent_devices) ? d.silent_devices : [],
      proactive_note_ar: typeof d.proactive_note_ar === 'string' ? d.proactive_note_ar : undefined,
    };
  });

// ══════════════════════════════════════════════════════════════════
// OPERATION CENTER WALL — التلخيص التشغيليّ الموحّد للمستأجِر (جدار مركز العمليّات).
// المصدر الأساسيّ: GET /api/v1/operations/summary خلف العلم FEATURE_OPERATIONS_WALL
// (حقول/تنبيهات بالخطورة/معدّات+أجهزة/قرارات/ريّ). أفضل-جهد: قد يكون العلم مُطفأً أو
// النقطة غير منشورة ⇒ 404. fetchOperationsSummary يُرجِع null عند 404/أيّ خطأ (لا
// تلفيق)، فترتدّ الصفحة إلى النقاط المنفصلة لكلّ بلاطة (تدهور رشيق، صدق المصدر).
// كلّ الحقول اختياريّة (عقد غير مُثبَّت في هذا الفرع) ⇒ قراءة دفاعيّة، لا any.
// ══════════════════════════════════════════════════════════════════
export interface OpsSeverityCounts {
  critical?: number;
  warning?:  number;
  info?:     number;
}

export interface OpsSectionStatus {
  status:         'ok' | 'degraded' | 'unavailable';
  freshness_sec?: number;
  error?:         string;
}

// عقد استجابة GET /api/v1/operations/summary — مطابق لـ``shape_operations_summary``
// الخادميّة (api/operations_summary.py): totals/alerts/irrigation + sections صدق التشغيل.
export interface OperationsSummary {
  generated_at?: string | null;
  // partial=أيّ قسم ليس ok؛ sections لكلّ قسم status حيّ/متدهور/غير متاح — يُمكّن
  // الجدار من إظهار ما هو حيّ/متدهور/غير متاح بصدق (لا تلفيق).
  partial?:      boolean | null;
  sections?:     Record<string, OpsSectionStatus> | null;
  totals?: {
    fields?:           number;
    equipment?:        number;
    iot_devices?:      number;
    decision_records?: number;
    active_alerts?:    number;
  } | null;
  alerts?: {
    active_total?: number;
    by_severity?:  OpsSeverityCounts;
    available?:    boolean;
  } | null;
  irrigation?: {
    valves?:    number;
    schedules?: number;
    available?: boolean;
  } | null;
  last_activity_at?: string | null;
  provenance?:       { calibrated?: string; note_ar?: string } | null;
  [k: string]:       unknown;
}

/** يجلب التلخيص التشغيليّ الموحّد. أفضل-جهد: 404 (العلم مُطفأ / النقطة غير منشورة)
 *  أو أيّ خطأ/استجابة غير كائن ⇒ null، فترتدّ الصفحة لكلّ بلاطة لنقطتها المنفصلة.
 *  لا تلفيق: null حالةٌ صريحة لا خطأ. */
export const fetchOperationsSummary = (): Promise<OperationsSummary | null> =>
  kongApi
    .get<OperationsSummary>('/api/v1/operations/summary')
    .then((r) => (r.data && typeof r.data === 'object' && !Array.isArray(r.data) ? r.data : null))
    .catch(() => null);

// ══════════════════════════════════════════════════════════════════
// DEMO-ONLY DATA (used only when VITE_MOCK_MODE=true)
// ══════════════════════════════════════════════════════════════════
export const MOCK_FIELDS = [
  { field_id:'demo-field-01', name:'حقل وادي سبأ',        area:23.5, crop:'قمح صلب',   ndvi:0.72, stage:'ملء الحبوب', gdd:960,  yield:2.8 },
  { field_id:'demo-field-02', name:'حقل البيضاء الشمالي', area:32.0, crop:'شعير',       ndvi:0.58, stage:'نمو خضري',  gdd:825,  yield:2.5 },
  { field_id:'demo-field-03', name:'حقل البيضاء الجنوبي', area:18.7, crop:'ذرة صفراء',  ndvi:0.44, stage:'تزهير',     gdd:980,  yield:3.9 },
  { field_id:'demo-field-04', name:'حقل رداع الغربي',     area:41.3, crop:'طماطم',      ndvi:0.66, stage:'ثمرة',      gdd:780,  yield:4.2 },
  { field_id:'demo-field-05', name:'حقل ذي السفال',       area:28.9, crop:'قمح صلب',   ndvi:0.74, stage:'ملء الحبوب', gdd:1020, yield:3.1 },
  { field_id:'demo-field-06', name:'حقل عتمة الشرقي',    area:37.5, crop:'شعير',       ndvi:0.51, stage:'نمو خضري',  gdd:792,  yield:2.4 },
  { field_id:'demo-field-07', name:'حقل الرياشية',        area:22.1, crop:'خضروات',     ndvi:0.55, stage:'حصاد',      gdd:660,  yield:5.5 },
  { field_id:'demo-field-08', name:'حقل ذي ناعم',         area:45.0, crop:'بطاطس',      ndvi:0.61, stage:'درنات',     gdd:680,  yield:6.8 },
];

const MOCK_ALERTS = [
  { id:'a1', field_id:'demo-field-06', field_name:'حقل عتمة الشرقي', level:'critical', severity:'critical', message:'NDVI حرج — إجهاد مائي', color:'#dc2626', recommendation:'ري فوري', timestamp:new Date().toISOString() },
  { id:'a2', field_id:'demo-field-03', field_name:'حقل البيضاء الجنوبي', level:'warning', severity:'warning', message:'رطوبة تربة منخفضة', color:'#f59e0b', recommendation:'تقليل ET0', timestamp:new Date().toISOString() },
  { id:'a3', field_id:'demo-field-01', field_name:'حقل وادي سبأ', level:'info', severity:'info', message:'موعد التسميد البوتاسي', color:'#38bdf8', recommendation:'إضافة K2O', timestamp:new Date().toISOString() },
];

const MOCK_WEATHER_TODAY = { tmax:31, tmin:17, tmean:24, humidity_pct:52, rainfall_mm:0, et0_mm:4.2, et0:4.2, gdd:14, wind_speed_kmh:12, irrigation_needed:true, heat_stress:false };

function mockWeatherDays(n: number) {
  return Array.from({length:n},(_,i) => {
    const d = new Date(); d.setDate(d.getDate()-n+i+1);
    return { date:d.toISOString().split('T')[0], tmax:28+Math.random()*6, tmin:14+Math.random()*5, tmean:21+Math.random()*4, rain:+(Math.random()*3).toFixed(2), et0:+(3.5+Math.random()*2).toFixed(2), gdd:+(8+Math.random()*8).toFixed(1), rainfall_mm:+(Math.random()*3).toFixed(2) };
  });
}

function mockSoilData(fieldId: string) {
  const s = Math.abs(fieldId.split('').reduce((a,c) => a+c.charCodeAt(0),0)) % 100;
  return { field_id:fieldId, ph:+(6+s%28/20).toFixed(1), ec_ds_m:+(0.3+s%40/20).toFixed(2), moisture_pct:+(20+s%55).toFixed(1), nitrogen_mg_kg:+(12+s%60).toFixed(1), phosphorus_mg_kg:+(6+s%35).toFixed(1), potassium_mg_kg:+(40+s%120).toFixed(1), organic_matter_pct:+(0.8+s%28/10).toFixed(2), texture:'مزيجية', health:{ status:'good', status_ar:'جيد', color:'#65a30d' } };
}

function mockFieldIndicators(fieldId: string) {
  const s = Math.abs(fieldId.split('').reduce((a,c) => a+c.charCodeAt(0),0)) % 100;
  return {
    field_id:fieldId, total_indicators:33,
    indicators:{
      ndvi:{ value:+(0.35+s%55/100).toFixed(4), unit:'', status:'good', status_ar:'جيد', color:'#65a30d', category:'vegetation' },
      evi: { value:+(0.30+s%45/100).toFixed(4), unit:'', status:'good', status_ar:'جيد', color:'#15803d', category:'vegetation' },
      soil_moisture:{ value:+(20+s%55).toFixed(1), unit:'%', status:'fair', status_ar:'مقبول', color:'#ca8a04', category:'water' },
      soil_ph:{ value:+(6+s%28/20).toFixed(1), unit:'', status:'good', status_ar:'جيد', color:'#92400e', category:'soil' },
      yield_est:{ value:+(2.5+s%40/10).toFixed(2), unit:'t/ha', status:'good', status_ar:'جيد', color:'#a855f7', category:'productivity' },
      temperature:{ value:+(20+s%20).toFixed(1), unit:'°C', status:'good', status_ar:'جيد', color:'#f97316', category:'weather' },
    },
    wofost:{ gdd_accumulated:s*10, progress_pct:s/2, lai:+(2+s%30/10).toFixed(2), yield_t_ha:+(2+s%40/10).toFixed(2), engine:'WOFOST-RUE-v9' },
  };
}

function mockVegetationAnalysis(fieldId: string) {
  return {
    field_id:fieldId, satellite:'sentinel-2', cloud_coverage:5,
    indices:{ ndvi:0.72, evi:0.61, savi:0.45, ndwi:0.18, ndmi:0.22, gndvi:0.68, lai:3.82 },
    classification:{ level:'good', label_ar:'جيد', color:'#65a30d' },
    nats_event:{ published:false, subject:`sahool.tenant.default.satellite.ndvi.computed` },
    analyzed_at:new Date().toISOString(),
  };
}

function mockTimeseries(fieldId: string, days: number) {
  const series = Array.from({length:days},(_,i) => {
    const d = new Date(); d.setDate(d.getDate()-days+i+1);
    return { date:d.toISOString().split('T')[0], ndvi:+(0.45+Math.sin(i/8)*0.15+Math.random()*0.04).toFixed(4), evi:+(0.38+Math.sin(i/8)*0.12+Math.random()*0.03).toFixed(4), lai:+(2+Math.sin(i/8)*1.2+Math.random()*0.3).toFixed(2) };
  });
  return { field_id:fieldId, period_days:days, timeseries:series, data:series, statistics:{ ndvi_mean:0.58, slope:0.001, r_squared:0.72, trend_direction:'stable' } };
}

const MOCK_DASHBOARD = {
  generated_at:new Date().toISOString(),
  total_fields:8, total_indicators:33, active_alerts:2, nats_events_processed:0,
  kpis:[
    { id:'ndvi',    name:'متوسط NDVI',      value:0.623, unit:'',       status:'good',      trend_direction:'improving', category:'vegetation',   sparkline:[0.58,0.60,0.61,0.62,0.63,0.62,0.63], color:'#16a34a' },
    { id:'wue',     name:'كفاءة المياه',    value:2.1,   unit:'kg/m³',  status:'good',      trend_direction:'stable',    category:'water',        sparkline:[1.9,2.0,2.0,2.1,2.1,2.1,2.1],       color:'#0ea5e9' },
    { id:'soil_ph', name:'pH التربة',       value:6.8,   unit:'',       status:'excellent', trend_direction:'stable',    category:'soil',         sparkline:[6.8,6.8,6.9,6.8,6.8,6.9,6.8],       color:'#92400e' },
    { id:'yield_est',name:'توقع الإنتاج',  value:3.6,   unit:'t/ha',   status:'good',      trend_direction:'improving', category:'productivity', sparkline:[3.2,3.3,3.4,3.5,3.5,3.6,3.6],       color:'#a855f7' },
    { id:'stress',  name:'مؤشر الإجهاد',  value:0.18,  unit:'',       status:'good',      trend_direction:'declining', category:'health',       sparkline:[0.22,0.21,0.20,0.19,0.19,0.18,0.18], color:'#f59e0b' },
    { id:'temperature',name:'الحرارة',     value:30.2,  unit:'°C',     status:'fair',      trend_direction:'stable',    category:'weather',      sparkline:[28,29,30,30,31,30,30],               color:'#f97316' },
  ],
  fields_summary:MOCK_FIELDS.map(f => ({
    field_id:f.field_id, field_name:f.name, ndvi:f.ndvi, crop:f.crop, real_data:false,
    composite:+(f.ndvi*0.5+0.3).toFixed(3), color:'#65a30d', status:'جيد',
  })),
  alerts:MOCK_ALERTS,
  data_freshness:{ source:'demo-only', last_update:new Date().toISOString() },
  status:'demo-only',
};


// ── Lab Sampling: soil/water sample points + laboratory results ─────────────
// Inspired by OneSoil soil-sampling map best practice: point coordinates are first-class
// data and the map layer reads the same API as forms/reports. No fabricated fallback.
export type LabSampleKind = 'soil' | 'water';
export type LabSampleStatus = 'planned' | 'collected' | 'submitted' | 'analyzed' | 'approved';
export interface LabSampleRecord {
  sample_id: string;
  field_id: string;
  kind: LabSampleKind;
  latitude: number;
  longitude: number;
  sampled_on?: string | null;
  depth_cm_from?: number | null;
  depth_cm_to?: number | null;
  source?: string | null;
  status: LabSampleStatus;
  gps_accuracy_m?: number | null;
  ph?: number | null;
  ec_dsm?: number | null;
  organic_matter_pct?: number | null;
  nitrogen_mg_kg?: number | null;
  phosphorus_mg_kg?: number | null;
  potassium_mg_kg?: number | null;
  sar?: number | null;
  rsc_meq_l?: number | null;
  approved?: boolean;
}
export interface LabSampleCreateInput {
  field_id: string;
  kind: LabSampleKind;
  latitude: number;
  longitude: number;
  sampled_on?: string | null;
  depth_cm_from?: number | null;
  depth_cm_to?: number | null;
  source?: string | null;
  status?: LabSampleStatus;
  gps_accuracy_m?: number | null;
}
export interface SoilLabResultInput {
  sample_id: string;
  ph?: number | null;
  ec_dsm?: number | null;
  organic_matter_pct?: number | null;
  nitrogen_mg_kg?: number | null;
  phosphorus_mg_kg?: number | null;
  potassium_mg_kg?: number | null;
  cec_cmol_kg?: number | null;
  calcium_carbonate_pct?: number | null;
  texture?: string | null;
  approved?: boolean;
}
export interface SoilLabAnalysisResult {
  sample_id: string;
  approved: boolean;
  classification: Record<string, { class: string | null; note_ar?: string }>;
  nutrients: Record<string, string | number | null>;
  hazard_flags_ar: string[];
  missing_inputs: string[];
  data_complete: boolean;
  decision_usable: boolean;
}
export interface LabDecisionContext {
  soil_lab_ready_for_fertilizer: boolean;
  water_lab_available: boolean;
  blockers_ar: string[];
  warnings_ar: string[];
  recommendation_gate: 'allow' | 'needs_review' | string;
}
export const listLabSamples = (fieldId?: string): Promise<LabSampleRecord[]> =>
  kongApi
    .get<LabSampleRecord[]>('/api/v1/lab/samples', { params: fieldId ? { field_id: fieldId } : undefined })
    .then(r => Array.isArray(r.data) ? r.data : []);
export const createLabSample = (payload: LabSampleCreateInput): Promise<LabSampleRecord> =>
  kongApi.post<LabSampleRecord>('/api/v1/lab/samples', payload).then(r => r.data);
export const submitSoilLabResult = (payload: SoilLabResultInput): Promise<SoilLabAnalysisResult> =>
  kongApi.post<SoilLabAnalysisResult>('/api/v1/lab/soil-results', payload).then(r => r.data);
export const fetchLabDecisionContext = (fieldId: string): Promise<LabDecisionContext> =>
  kongApi.get<LabDecisionContext>(`/api/v1/fields/${encodeURIComponent(fieldId)}/lab-context`).then(r => r.data);


// ── OneSoil-inspired productivity zones / sampling / daily brief ───────────
export type ProductivityZoneClass = 'low' | 'medium' | 'high' | 'problem';
export type ActionPriority = 'critical' | 'high' | 'medium' | 'low';
export interface ProductivityObservationInput {
  id: string;
  area_ha: number;
  ndvi_mean?: number | null;
  ndvi_cv?: number | null;
  yield_rel?: number | null;
  soil_ec_dsm?: number | null;
  soil_ph?: number | null;
  lat?: number | null;
  lng?: number | null;
}
export interface ProductivityZoneResult {
  field_id: string;
  tenant_id?: string;
  zones: Array<{
    zone_id: string;
    zone_class: ProductivityZoneClass;
    area_ha: number;
    observation_ids: string[];
    score: number;
    confidence: number;
    limiting_factors_ar: string[];
    sampling_priority: ActionPriority;
  }>;
  summary: Record<string, { area_ha: number; count: number; area_pct: number; mean_score: number; limiting_factors_ar: string[] }>;
  total_area_ha: number;
  mean_confidence: number;
  data_sufficiency: 'sufficient' | 'limited' | string;
  source_policy?: string;
}
export interface ZoneSamplingPlanResult {
  field_id: string;
  tenant_id?: string;
  sample_points: Array<{
    sample_id: string;
    zone_id: string;
    zone_class: ProductivityZoneClass;
    latitude: number;
    longitude: number;
    depth_cm_from: number;
    depth_cm_to: number;
    priority: ActionPriority;
    reason_ar: string;
  }>;
  unplaceable_observation_ids: string[];
  count: number;
  source_policy?: string;
}
export interface DailyAiBriefResult {
  field_id?: string | null;
  tenant_id?: string;
  headline_ar: string;
  actions: Array<{
    action_id: string;
    priority: ActionPriority;
    title_ar: string;
    reason_ar: string;
    field_id?: string | null;
    zone_id?: string | null;
    source: string;
  }>;
  source_count: number;
  is_grounded: boolean;
  source_policy?: string;
}
export const buildProductivityZones = (fieldId: string, observations: ProductivityObservationInput[]): Promise<ProductivityZoneResult> =>
  kongApi
    .post<ProductivityZoneResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/productivity-zones`, { field_id: fieldId, observations })
    .then(r => r.data);
export const buildZoneSamplingPlan = (fieldId: string, observations: ProductivityObservationInput[]): Promise<ZoneSamplingPlanResult> =>
  kongApi
    .post<ZoneSamplingPlanResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/zone-sampling-plan`, { field_id: fieldId, observations })
    .then(r => r.data);
export const fetchDailyAiBrief = (fieldId: string, signals: Record<string, unknown> = {}, tasks: Record<string, unknown>[] = []): Promise<DailyAiBriefResult> =>
  kongApi
    .post<DailyAiBriefResult>(`/api/v1/fields/${encodeURIComponent(fieldId)}/daily-ai-brief`, { field_id: fieldId, signals, tasks })
    .then(r => r.data);

// ── Phase 5 GIS Workbench / STAC / OGC / AI boundary adapters ─────────────
export interface StacSearchParams {
  field_id?: string;
  index_type?: string;
  min_quality?: number;
  max_cloud?: number;
  bbox?: number[];
  limit?: number;
}
export interface SceneProcessingPlan {
  pipeline: string[];
  selected_scene_ids: string[];
  ranked: Array<{ scene_id: string; rank: number; score: number; accepted: boolean; reason: string }>;
  mosaic_ready: boolean;
}
export interface TileCachePlan {
  strategy: string;
  entries: Array<{ raster_id: string; index_type: string; cache_key: string; minzoom: number; maxzoom: number; ttl_seconds: number }>;
  purge_on: string[];
}
export interface BoundaryExtractionPlan {
  field_id: string;
  model: string;
  input_type: string;
  bbox?: number[] | null;
  steps: string[];
  status: string;
  requires_human_review: boolean;
}
export interface ManagementZoneSummary {
  n_zones?: number;
  zones: Array<{ zone: string; count: number; pct: number }>;
  error?: string;
  count?: number;
}
export interface EditingUndoRedoResult {
  field_id: string;
  undo_stack: unknown[];
  redo_stack: unknown[];
  can_undo: boolean;
  can_redo: boolean;
}

export const fetchStacRoot = (): Promise<Record<string, unknown>> =>
  kongApi.get<Record<string, unknown>>('/api/v1/gis/cloud-native/stac').then(r => r.data);
export const searchStacItems = (params: StacSearchParams = {}): Promise<Record<string, unknown>> =>
  kongApi.post<Record<string, unknown>>('/api/v1/gis/cloud-native/stac/search', params).then(r => r.data);
export const fetchSceneProcessingPlan = (fieldId?: string, indexType?: string): Promise<SceneProcessingPlan> =>
  kongApi
    .get<SceneProcessingPlan>('/api/v1/gis/cloud-native/scene-processing-plan', { params: { field_id: fieldId, index_type: indexType } })
    .then(r => r.data);
export const fetchTileCachePlan = (fieldId?: string, indexType?: string): Promise<TileCachePlan> =>
  kongApi
    .get<TileCachePlan>('/api/v1/gis/cloud-native/tile-cache-plan', { params: { field_id: fieldId, index_type: indexType } })
    .then(r => r.data);
export const fetchOgcCollections = (): Promise<Record<string, unknown>> =>
  kongApi.get<Record<string, unknown>>('/api/v1/gis/cloud-native/ogc/collections').then(r => r.data);
export const planAiBoundaryExtraction = (fieldId: string, inputType = 'sentinel2', bbox?: number[], model = 'sam2-geosam'): Promise<BoundaryExtractionPlan> =>
  kongApi
    .post<BoundaryExtractionPlan>('/api/v1/gis/cloud-native/ai-boundary/plan', { field_id: fieldId, input_type: inputType, bbox, model })
    .then(r => r.data);
export const summarizeManagementZones = (values: number[], nZones = 3): Promise<ManagementZoneSummary> =>
  kongApi
    .post<ManagementZoneSummary>('/api/v1/gis/cloud-native/management-zones/summary', { values, n_zones: nZones })
    .then(r => r.data);
export const updateEditingUndoRedo = (fieldId: string, action: 'push' | 'undo' | 'redo', event?: Record<string, unknown>): Promise<EditingUndoRedoResult> =>
  kongApi
    .post<EditingUndoRedoResult>('/api/v1/gis/cloud-native/editing-sessions/undo-redo', { field_id: fieldId, action, event })
    .then(r => r.data);


// ══════════════════════════════════════════════════════════════════
// FEATURE REGISTRY — extracted to services/api/features.ts; re-exported for compatibility
// ══════════════════════════════════════════════════════════════════
export { getFeatureRegistry } from './api/features';
export type { FeatureRegistryItem, FeatureRegistryResponse } from './api/features';
export * from './api/fieldTasks';

// FIELD WORKSPACE TAB FACADES — UI-24/UI-26 compatibility exports
export * from './api/fieldImagery';
export * from './api/fieldWeather';
export * from './api/fieldIrrigation';

// FIELD WORKSPACE TIMELINE FACADE — UI-32 compatibility export
export * from './api/fieldTimeline';
