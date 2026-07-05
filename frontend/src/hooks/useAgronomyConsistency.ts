// useAgronomyConsistency — هوكات react-query لنقاط backend اليتيمة (P2): فحوص اتّساق
// القرار (ريّ + نضارة) · تقييم الدورة الزراعيّة ومبادئها · إرشاد تكيّف WOFOST وأنواعه ·
// توصية ريّ موحّدة · الحالة التشغيليّة للحقل · تحسين محفظة الحقول · التحقّق من صحّة الهندسة ·
// تصدير تقرير العمليّات (CSV مدير).
//
// الأعراف مطابقة لـuseIrrigationDecisionAids.ts/useApi.ts: kongApi عبر البوّابة (/api/v1/*)،
// retry:false لحالة صادقة عند الفشل، staleTime طويل للمعرفة المرجعيّة الثابتة (المبادئ/
// أنواع النماذج)، وPOST داخل queryFn (سابقة useNdviConfidence) لأنّ optimize/validate/
// irrigation-recommendation حسابات قراءة نقيّة (نوى حتميّة بلا كتابة DB) لا كتابات.
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404: حالة «غير مُفعَّل» صادقة بدل خطأ مُفزِع؛
// باقي الأخطاء (403/5xx) تُرفَع كما هي لتعرضها الواجهة.
//
// استثناء واحد: POST /api/v1/reports/operation يُصدِّر ملفّ CSV (تحقّق مستأجِر خادميّ) —
// إجراء تصدير بضغطة لا استعلام تفاعليّ ⇒ useMutation (لا queryFn). ليس كتابة DB لكنّه
// «توليد ملفّ» عند الطلب.

import { useMutation, useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  ConsistencyResponse,
  GeometryValidateResponse,
  IrrigationRecommendationResponse,
  OperationalStateResponse,
  PortfolioOptimizeResponse,
  RotationEvaluateResponse,
  RotationPrinciplesResponse,
  WofostCropTypesResponse,
  WofostGuidanceResponse,
} from '../lib/agronomyConsistency';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

// ── فحوص الاتّساق (agronomic_consistency.py) — GET، كلّ المدخلات اختياريّة ──────

export interface ConsistencyIrrigationParams {
  irrigation_delta_pct: number | null;
  rain_forecast_mm: number | null;
  soil_moisture_ratio: number | null;
  et0_mm: number | null;
  recommendation_confidence: number | null;
}

/** فحص توصية ريّ ضدّ الظروف الحاليّة — GET /api/v1/consistency/irrigation.
 *  يُطلَق فقط بعد إدخال مدخل واحد على الأقلّ (لا فحص فارغ). */
export function useConsistencyIrrigation(
  p: ConsistencyIrrigationParams,
  enabled = true,
): UseQueryResult<ConsistencyResponse> {
  const hasAny = Object.values(p).some((v) => v != null);
  return useQuery<ConsistencyResponse>({
    queryKey: [
      'consistency-irrigation',
      p.irrigation_delta_pct ?? 'none', p.rain_forecast_mm ?? 'none',
      p.soil_moisture_ratio ?? 'none', p.et0_mm ?? 'none', p.recommendation_confidence ?? 'none',
    ],
    queryFn: () => kongApi
      .get('/api/v1/consistency/irrigation', {
        params: {
          irrigation_delta_pct: p.irrigation_delta_pct ?? undefined,
          rain_forecast_mm: p.rain_forecast_mm ?? undefined,
          soil_moisture_ratio: p.soil_moisture_ratio ?? undefined,
          et0_mm: p.et0_mm ?? undefined,
          recommendation_confidence: p.recommendation_confidence ?? undefined,
        },
      })
      .then((r) => r.data as ConsistencyResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && hasAny,
    retry: false,
  });
}

export interface ConsistencyFreshnessParams {
  ndvi_age_days: number | null;
  soil_age_days: number | null;
  weather_age_hours: number | null;
}

/** فحص أعمار البيانات الداخلة في القرار — GET /api/v1/consistency/freshness. */
export function useConsistencyFreshness(
  p: ConsistencyFreshnessParams,
  enabled = true,
): UseQueryResult<ConsistencyResponse> {
  const hasAny = Object.values(p).some((v) => v != null);
  return useQuery<ConsistencyResponse>({
    queryKey: [
      'consistency-freshness',
      p.ndvi_age_days ?? 'none', p.soil_age_days ?? 'none', p.weather_age_hours ?? 'none',
    ],
    queryFn: () => kongApi
      .get('/api/v1/consistency/freshness', {
        params: {
          ndvi_age_days: p.ndvi_age_days ?? undefined,
          soil_age_days: p.soil_age_days ?? undefined,
          weather_age_hours: p.weather_age_hours ?? undefined,
        },
      })
      .then((r) => r.data as ConsistencyResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && hasAny,
    retry: false,
  });
}

// ── الدورة الزراعيّة (crop_rotation.py) — GET ───────────────────────────────

/** تقييم تعاقب محصولَين — GET /api/v1/rotation/evaluate (previous+candidate إجباريّان). */
export function useRotationEvaluate(
  previous: string | null,
  candidate: string | null,
  enabled = true,
): UseQueryResult<RotationEvaluateResponse> {
  return useQuery<RotationEvaluateResponse>({
    queryKey: ['rotation-evaluate', previous ?? 'none', candidate ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/rotation/evaluate', { params: { previous, candidate } })
      .then((r) => r.data as RotationEvaluateResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!previous && !!candidate,
    retry: false,
  });
}

/** مبادئ الدورة + المحاصيل المصنّفة — GET /api/v1/rotation/principles (معرفة مرجعيّة ثابتة). */
export function useRotationPrinciples(enabled = true): UseQueryResult<RotationPrinciplesResponse> {
  return useQuery<RotationPrinciplesResponse>({
    queryKey: ['rotation-principles'],
    queryFn: () => kongApi
      .get('/api/v1/rotation/principles')
      .then((r) => r.data as RotationPrinciplesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

// ── WOFOST عبر المحاصيل (wofost_crop_params.py) — GET ────────────────────────

/** دليل تعديل بارامترات WOFOST لمحصول — GET /api/v1/wofost/adaptation-guidance (crop إجباريّ). */
export function useWofostAdaptationGuidance(
  crop: string | null,
  enabled = true,
): UseQueryResult<WofostGuidanceResponse> {
  return useQuery<WofostGuidanceResponse>({
    queryKey: ['wofost-adaptation-guidance', crop ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/wofost/adaptation-guidance', { params: { crop } })
      .then((r) => r.data as WofostGuidanceResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!crop,
    retry: false,
  });
}

/** أنواع نماذج المحاصيل وإطار كلّ منها — GET /api/v1/wofost/crop-types (معرفة مرجعيّة ثابتة). */
export function useWofostCropTypes(enabled = true): UseQueryResult<WofostCropTypesResponse> {
  return useQuery<WofostCropTypesResponse>({
    queryKey: ['wofost-crop-types'],
    queryFn: () => kongApi
      .get('/api/v1/wofost/crop-types')
      .then((r) => r.data as WofostCropTypesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

// ── الحالة التشغيليّة للحقل (field_operational_state.py) — GET ────────────────

export interface OperationalStateParams {
  confidence_level: string | null;
  irrigation_delta_pct: number | null;
  rain_forecast_mm: number | null;
  soil_moisture_ratio: number | null;
  et0_mm: number | null;
  ndvi_age_days: number | null;
  soil_age_days: number | null;
  weather_age_hours: number | null;
}

/** تركيب النضارة + الثقة + التناقض في حالة واحدة رسميّة — GET /api/v1/field/operational-state.
 *  field_id إجباريّ (المعرّف من الحقل المختار)؛ باقي الإشارات اختياريّة (الغائب يتخطّاه). */
export function useFieldOperationalState(
  fieldId: string | null,
  p: OperationalStateParams,
  enabled = true,
): UseQueryResult<OperationalStateResponse> {
  return useQuery<OperationalStateResponse>({
    queryKey: [
      'field-operational-state', fieldId ?? 'none',
      p.confidence_level ?? 'none', p.irrigation_delta_pct ?? 'none', p.rain_forecast_mm ?? 'none',
      p.soil_moisture_ratio ?? 'none', p.et0_mm ?? 'none',
      p.ndvi_age_days ?? 'none', p.soil_age_days ?? 'none', p.weather_age_hours ?? 'none',
    ],
    queryFn: () => kongApi
      .get('/api/v1/field/operational-state', {
        params: {
          field_id: fieldId,
          confidence_level: p.confidence_level || undefined,
          irrigation_delta_pct: p.irrigation_delta_pct ?? undefined,
          rain_forecast_mm: p.rain_forecast_mm ?? undefined,
          soil_moisture_ratio: p.soil_moisture_ratio ?? undefined,
          et0_mm: p.et0_mm ?? undefined,
          ndvi_age_days: p.ndvi_age_days ?? undefined,
          soil_age_days: p.soil_age_days ?? undefined,
          weather_age_hours: p.weather_age_hours ?? undefined,
        },
      })
      .then((r) => r.data as OperationalStateResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && !!fieldId,
    retry: false,
  });
}

// ── توصية ريّ موحّدة (irrigation_recommendation_policy.py) — POST نقيّ في queryFn ──

export interface IrrigationRecommendationInput {
  crop?: string | null;
  stage?: string;
  t_min_c: number;
  t_max_c: number;
  rain_recent_mm?: number;
  forecast_rain_mm?: number;
  soil_moisture_pct?: number | null;
  // مدخلات الملوحة/الغسل (مشروطة — تُمرَّر فقط عند توفّرها؛ لا تُختلق)
  soil_ece?: number | null;
  crop_salt_tolerance_ece?: number | null;
  water_ec?: number | null;
  drainage?: string | null;
  irrigation_efficiency?: number | null;
}

/** توصية ريّ (صافٍ + إجهاد ملوحة عند توفّر EC + غسل مشروط) — POST /api/v1/irrigation-recommendation.
 *  حساب قراءة نقيّ (يحسب ET0 داخليّاً)؛ لا يُستدعى بلا حرارتَي min/max (إجباريّتان خادميّاً). */
export function useIrrigationRecommendation(
  input: IrrigationRecommendationInput | null,
): UseQueryResult<IrrigationRecommendationResponse> {
  return useQuery<IrrigationRecommendationResponse>({
    queryKey: ['irrigation-recommendation', JSON.stringify(input ?? {})],
    queryFn: () => kongApi
      .post('/api/v1/irrigation-recommendation', input)
      .then((r) => r.data as IrrigationRecommendationResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

// ── تحسين محفظة الحقول (field_portfolio.py) — POST نقيّ في queryFn ────────────

export interface PortfolioFieldInput {
  field_id: string;
  expected_margin: number;
  water_demand_m3: number;
  area_ha?: number;
}
export interface PortfolioOptimizeInput {
  fields: PortfolioFieldInput[];
  total_water_m3: number;
}

/** توزيع ماء المزرعة المحدود عبر الحقول لتعظيم العائد — POST /api/v1/field-portfolio/optimize.
 *  نواة نقيّة حتميّة (لا كتابة DB)؛ الهوامش/الاحتياجات يُمرِّرها المستخدم (لا تُلفَّق). */
export function useFieldPortfolioOptimize(
  input: PortfolioOptimizeInput | null,
): UseQueryResult<PortfolioOptimizeResponse> {
  return useQuery<PortfolioOptimizeResponse>({
    queryKey: ['field-portfolio-optimize', JSON.stringify(input ?? {})],
    queryFn: () => kongApi
      .post('/api/v1/field-portfolio/optimize', input)
      .then((r) => r.data as PortfolioOptimizeResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input && input.fields.length > 0,
    retry: false,
  });
}

// ── التحقّق من صحّة الهندسة (geospatial_integrity.py) — POST نقيّ في queryFn ────

/** تحقّق حدود حقل قبل الحفظ (CRS/تقاطع ذاتي/مساحة/داخل اليمن) — POST /api/v1/fields/validate-geometry.
 *  تحقّق نقيّ لا كتابة؛ لا يُستدعى بلا GeoJSON صالح بنيويّاً (parsed من إدخال المستخدم). */
export function useValidateGeometry(
  geojson: object | null,
  declaredCrs: string | null,
): UseQueryResult<GeometryValidateResponse> {
  return useQuery<GeometryValidateResponse>({
    queryKey: ['validate-geometry', JSON.stringify(geojson ?? null), declaredCrs ?? 'none'],
    queryFn: () => kongApi
      .post('/api/v1/fields/validate-geometry', {
        geojson,
        declared_crs: declaredCrs || undefined,
      })
      .then((r) => r.data as GeometryValidateResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!geojson,
    retry: false,
  });
}

// ── تقرير العمليّات (reports.py) — POST يُصدِّر CSV ⇒ useMutation ─────────────

/** ReportFieldInput (api_models.py) — هويّة الحقل + مقاييسه؛ الافتراضات صفر خادميّاً. */
export interface OperationReportFieldInput {
  field_id: string;
  field_name_ar: string;
  farm_id?: string;
  tenant_id?: string;
  area_ha?: number;
  crop?: string;
  season_label?: string;
  planting_date?: string | null;
  harvest_date?: string | null;
  lifecycle_stage?: string;
  irrigation_events?: number;
  total_water_m3?: number;
  fertilizer_events?: number;
  total_nitrogen_kg?: number;
  avg_ndvi?: number | null;
  estimated_yield_kg_ha?: number | null;
}
export interface OperationReportInput {
  tenant_id: string;
  operation_name_ar: string;
  period_start: string;
  period_end: string;
  fields: OperationReportFieldInput[];
  lang?: string;
}

/** تصدير تقرير المزرعة كاملة كـCSV (ثنائي اللغة) — POST /api/v1/reports/operation.
 *  يتحقّق الخادم من تطابق المستأجِر (403 عند عدمه)؛ الردّ نصّ CSV خام (PlainTextResponse).
 *  الاستهلاك (تحويله Blob وتنزيله) في موقع الاستدعاء — تأثير DOM لا يخصّ الهوك. */
export function useOperationReportCsv() {
  return useMutation({
    mutationFn: (input: OperationReportInput) =>
      kongApi
        .post('/api/v1/reports/operation', input, { responseType: 'text' })
        .then((r) => r.data as string),
  });
}
