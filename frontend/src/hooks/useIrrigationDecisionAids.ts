// useIrrigationDecisionAids — هوكات react-query لنقاط backend اليتيمة (P0/P1 من
// docs/api/UI_DEBT_MAP.md): ثقة القراءة/التوصية + قرار الرطوبة RWC + أنواع التربة +
// الإجمالي المسحوب + محاصيل حساسيّة الماء + بروتوكول عيّنة التربة.
//
// الأعراف مطابقة لـ useApi.ts: kongApi عبر البوّابة (/api/v1/*)، retry:false لحالة
// صادقة عند الفشل، staleTime طويل للمعرفة المرجعيّة الثابتة، وPOST داخل queryFn
// (سابقة useFieldChange) لأنّ هذه حسابات قراءة نقيّة لا كتابات.
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404 في useApi.ts: حالة «غير مُفعَّل»
// صادقة بدل خطأ مُفزِع؛ باقي الأخطاء (403/5xx) تُرفَع كما هي لتعرضها الواجهة.

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  AggregatedConfidenceResponse,
  GrossIrrigationResponse,
  IrrigationConfidenceInput,
  MoistureDecisionResponse,
  NdviConfidenceInput,
  NdviConfidenceResponse,
  SamplingDepthResponse,
  SamplingProtocolResponse,
  SamplingSubsamplesResponse,
  SoilTypesResponse,
  WaterSensitivityCropsResponse,
} from '../lib/irrigationDecisionAids';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** ثقة قراءة NDVI (cloud+temporal+coverage+source) — POST /api/v1/confidence/ndvi.
 *  لا يُستدعى بلا مدخلات كاملة (قيمة/تاريخ/مساحة من المستخدم — لا تخمين). */
export function useNdviConfidence(
  input: NdviConfidenceInput | null,
): UseQueryResult<NdviConfidenceResponse> {
  return useQuery<NdviConfidenceResponse>({
    queryKey: [
      'confidence-ndvi',
      input?.ndvi_value ?? 'none',
      input?.observation_date ?? 'none',
      input?.field_area_ha ?? 'none',
      input?.cloud_pct ?? 'none',
      input?.has_ground_truth ?? false,
    ],
    queryFn: () => kongApi
      .post('/api/v1/confidence/ndvi', input)
      .then((r) => r.data as NdviConfidenceResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** ثقة توصية ريّ مُجمَّعة (ET₀ حرج — غيابه يجعلها unsafe من الخادم) —
 *  POST /api/v1/confidence/irrigation. الكسور 0-1 يُدخِلها المستخدم. */
export function useIrrigationConfidence(
  input: IrrigationConfidenceInput | null,
): UseQueryResult<AggregatedConfidenceResponse> {
  return useQuery<AggregatedConfidenceResponse>({
    queryKey: [
      'confidence-irrigation',
      input?.ndvi_confidence ?? 'none',
      input?.et0_confidence ?? 'none',
      input?.soil_moisture_confidence ?? 'none',
      input?.weather_forecast_confidence ?? 'none',
    ],
    queryFn: () => kongApi
      .post('/api/v1/confidence/irrigation', input)
      .then((r) => r.data as AggregatedConfidenceResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

export interface MoistureDecisionParams {
  /** الرطوبة الحجميّة كسر 0-1 كما يتوقّع الخادم (تحويل ٪÷100 في الواجهة). */
  vwc: number | null;
  soilType: string;
  crop?: string | null;
  growthStage?: string | null;
  thetaFc?: number | null;
  thetaWp?: number | null;
  rootDepthM?: number | null;
}

/** قرار ريّ من قراءة مستشعر الرطوبة (VWC→RWC→قرار+كمّيّة) —
 *  GET /api/v1/irrigation/moisture-decision. لا يُستدعى بلا قراءة حقيقيّة. */
export function useMoistureDecision(
  p: MoistureDecisionParams,
  enabled = true,
): UseQueryResult<MoistureDecisionResponse> {
  return useQuery<MoistureDecisionResponse>({
    queryKey: [
      'irrigation-moisture-decision',
      p.vwc ?? 'none', p.soilType, p.crop ?? 'none', p.growthStage ?? 'none',
      p.thetaFc ?? 'none', p.thetaWp ?? 'none', p.rootDepthM ?? 'none',
    ],
    queryFn: () => kongApi
      .get('/api/v1/irrigation/moisture-decision', {
        params: {
          vwc: p.vwc,
          soil_type: p.soilType,
          crop: p.crop || undefined,
          growth_stage: p.growthStage || undefined,
          theta_fc: p.thetaFc ?? undefined,
          theta_wp: p.thetaWp ?? undefined,
          root_depth_m: p.rootDepthM ?? undefined,
        },
      })
      .then((r) => r.data as MoistureDecisionResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && p.vwc != null,
    retry: false,
  });
}

/** أنواع التربة وقيمها المرجعيّة (NRCCA) — GET /api/v1/irrigation/soil-types.
 *  معرفة مرجعيّة ثابتة ⇒ staleTime طويل. */
export function useIrrigationSoilTypes(enabled = true): UseQueryResult<SoilTypesResponse> {
  return useQuery<SoilTypesResponse>({
    queryKey: ['irrigation-soil-types'],
    queryFn: () => kongApi
      .get('/api/v1/irrigation/soil-types')
      .then((r) => r.data as SoilTypesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** الصافي ⇒ الإجمالي المسحوب (÷ كفاءة التطبيق، FAO موسومة calibrated=false) —
 *  POST /api/v1/irrigation-method/gross. حساب الخادم لا الواجهة. */
export function useGrossIrrigation(
  netMm: number | null,
  method: string | null,
  applicationEfficiency: number | null,
  enabled = true,
): UseQueryResult<GrossIrrigationResponse> {
  return useQuery<GrossIrrigationResponse>({
    queryKey: ['irrigation-method-gross', netMm ?? 'none', method ?? 'none', applicationEfficiency ?? 'none'],
    queryFn: () => kongApi
      .post('/api/v1/irrigation-method/gross', {
        net_mm: netMm,
        method: method || null,
        application_efficiency: applicationEfficiency ?? null,
      })
      .then((r) => r.data as GrossIrrigationResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && netMm != null && netMm > 0,
    retry: false,
  });
}

/** المحاصيل المدعومة بحساسيّة المراحل المائيّة — GET /api/v1/water-sensitivity/crops. */
export function useWaterSensitivityCrops(enabled = true): UseQueryResult<WaterSensitivityCropsResponse> {
  return useQuery<WaterSensitivityCropsResponse>({
    queryKey: ['water-sensitivity-crops'],
    queryFn: () => kongApi
      .get('/api/v1/water-sensitivity/crops')
      .then((r) => r.data as WaterSensitivityCropsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** عدد العيّنات الفرعيّة حسب مساحة الحقل — GET /api/v1/soil-sampling/subsamples.
 *  المساحة قياس يُدخِله المستخدم (لا تخمين ⇒ لا استدعاء بلا مساحة). */
export function useSoilSamplingSubsamples(
  areaHa: number | null,
  enabled = true,
): UseQueryResult<SamplingSubsamplesResponse> {
  return useQuery<SamplingSubsamplesResponse>({
    queryKey: ['soil-sampling-subsamples', areaHa ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/soil-sampling/subsamples', { params: { area_ha: areaHa } })
      .then((r) => r.data as SamplingSubsamplesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && areaHa != null,
    retry: false,
  });
}

/** عمق العيّنة حسب الغرض — GET /api/v1/soil-sampling/depth. */
export function useSoilSamplingDepth(
  purpose: string,
  enabled = true,
): UseQueryResult<SamplingDepthResponse> {
  return useQuery<SamplingDepthResponse>({
    queryKey: ['soil-sampling-depth', purpose],
    queryFn: () => kongApi
      .get('/api/v1/soil-sampling/depth', { params: { purpose } })
      .then((r) => r.data as SamplingDepthResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** البروتوكول الكامل لأخذ عيّنة تربة صحيحة — GET /api/v1/soil-sampling/protocol.
 *  areaHa اختياريّة (الخادم يضمّن قسم العيّنات الفرعيّة عند توفّرها). */
export function useSoilSamplingProtocol(
  areaHa: number | null,
  purpose: string,
  enabled = true,
): UseQueryResult<SamplingProtocolResponse> {
  return useQuery<SamplingProtocolResponse>({
    queryKey: ['soil-sampling-protocol', areaHa ?? 'none', purpose],
    queryFn: () => kongApi
      .get('/api/v1/soil-sampling/protocol', {
        params: { area_ha: areaHa ?? undefined, purpose },
      })
      .then((r) => r.data as SamplingProtocolResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}
