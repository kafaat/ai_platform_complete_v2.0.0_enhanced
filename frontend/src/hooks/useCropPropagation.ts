// useCropPropagation — هوكات react-query لنقاط backend اليتيمة (P3، معرفة زراعيّة
// اختصاصيّة): ملاءمة المحاصيل + تركيب حالة المحصول + الإكثار الخضري واختيار الأصل +
// الأساليب المحسّنة + صمود الجفاف (مفرد/مقارنة) + تقييم مصدر البذار + استراتيجيّة العيّنات.
//
// الأعراف مطابقة لـuseIrrigationDecisionAids.ts: kongApi عبر البوّابة (/api/v1/*)،
// retry:false لحالة صادقة عند الفشل، staleTime طويل للمعرفة المرجعيّة الثابتة، وPOST
// داخل queryFn لأنّ هذه النقاط حسابات قراءة نقيّة حتميّة لا كتابات (crop-twin/compose
// موسومة dry-run صراحةً «لا يُوزَّع للتنفيذ»؛ crop-suitability/seed/evaluate-source
// دوالّ نقيّة بلا إدامة) — فلا useMutation.
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404 في useApi.ts: حالة «غير مُفعَّل»
// صادقة بدل خطأ مُفزِع؛ باقي الأخطاء (403/5xx) تُرفَع كما هي لتعرضها الواجهة.

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  CompareDroughtResilienceResponse,
  CropSuitabilityResponse,
  CropTwinComposeResponse,
  DroughtResilienceResponse,
  PracticeGuideResponse,
  PracticesListResponse,
  PropagationMethodGuideResponse,
  PropagationMethodsResponse,
  RootstockResponse,
  SamplingStrategyResponse,
  SeedEvaluateResponse,
} from '../lib/cropPropagation';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

// ═══ 1. ملاءمة المحاصيل — POST /api/v1/crop-suitability (نقيّ ⇒ queryFn) ═══════

export interface CropSuitabilityInput {
  ph: number;
  ec_dsm: number;
  season_rain_mm?: number | null;
  temp_mean_c?: number | null;
  irrigated: boolean;
  crops?: string[] | null;
}

/** يرتّب المحاصيل بمعايير مرجّحة شفّافة — لا يُستدعى بلا pH/EC (يحجب الخادم دونهما). */
export function useCropSuitability(
  input: CropSuitabilityInput | null,
): UseQueryResult<CropSuitabilityResponse> {
  return useQuery<CropSuitabilityResponse>({
    queryKey: [
      'crop-suitability',
      input?.ph ?? 'none', input?.ec_dsm ?? 'none',
      input?.season_rain_mm ?? 'none', input?.temp_mean_c ?? 'none',
      input?.irrigated ?? true, (input?.crops ?? []).join(',') || 'all',
    ],
    queryFn: () => kongApi
      .post('/api/v1/crop-suitability', input)
      .then((r) => r.data as CropSuitabilityResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

// ═══ 2. تركيب حالة المحصول — POST /api/v1/crop-twin/compose (dry-run ⇒ queryFn) ═

export interface ComposeForecastDayInput {
  t_min_c: number;
  t_max_c: number;
  et0_mm: number;
  rain_mm?: number;
}
export interface CropTwinComposeInput {
  crop?: string | null;
  stage: string;
  ndvi?: number | null;
  forecast: ComposeForecastDayInput[];
}

/** يركّب حالة محصول مقروءة (تركيب نقيّ dry-run) — لا يُستدعى بلا يوم توقّع واحد صحيح. */
export function useCropTwinCompose(
  input: CropTwinComposeInput | null,
): UseQueryResult<CropTwinComposeResponse> {
  return useQuery<CropTwinComposeResponse>({
    queryKey: [
      'crop-twin-compose',
      input?.crop ?? 'none', input?.stage ?? 'mid', input?.ndvi ?? 'none',
      JSON.stringify(input?.forecast ?? []),
    ],
    queryFn: () => kongApi
      .post('/api/v1/crop-twin/compose', {
        crop: input?.crop || null,
        stage: input?.stage,
        ndvi: input?.ndvi ?? null,
        forecast: input?.forecast ?? [],
      })
      .then((r) => r.data as CropTwinComposeResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input && (input.forecast?.length ?? 0) > 0,
    retry: false,
  });
}

// ═══ 3. الإكثار الخضري — GET /api/v1/propagation/* ════════════════════════════

/** طرق الإكثار الخمس — معرفة مرجعيّة ثابتة ⇒ staleTime طويل. */
export function usePropagationMethods(enabled = true): UseQueryResult<PropagationMethodsResponse> {
  return useQuery<PropagationMethodsResponse>({
    queryKey: ['propagation-methods'],
    queryFn: () => kongApi
      .get('/api/v1/propagation/methods')
      .then((r) => r.data as PropagationMethodsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** دليل طريقة إكثار محدّدة — لا يُستدعى بلا اختيار طريقة. */
export function usePropagationMethodGuide(
  method: string | null,
  enabled = true,
): UseQueryResult<PropagationMethodGuideResponse> {
  return useQuery<PropagationMethodGuideResponse>({
    queryKey: ['propagation-method-guide', method ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/propagation/method-guide', { params: { method } })
      .then((r) => r.data as PropagationMethodGuideResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!method,
    retry: false,
  });
}

/** إرشاد اختيار الأصل المقاوم حسب الإجهاد (salinity افتراض الخادم). */
export function useRootstockSelection(
  stress: string,
  enabled = true,
): UseQueryResult<RootstockResponse> {
  return useQuery<RootstockResponse>({
    queryKey: ['propagation-rootstock', stress],
    queryFn: () => kongApi
      .get('/api/v1/propagation/rootstock', { params: { stress } })
      .then((r) => r.data as RootstockResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

// ═══ 4. الأساليب الزراعيّة المحسّنة — GET /api/v1/practices/* ══════════════════

/** الأساليب المحسّنة المدعومة — معرفة مرجعيّة ثابتة. */
export function usePracticesList(enabled = true): UseQueryResult<PracticesListResponse> {
  return useQuery<PracticesListResponse>({
    queryKey: ['practices-list'],
    queryFn: () => kongApi
      .get('/api/v1/practices/list')
      .then((r) => r.data as PracticesListResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** دليل أسلوب محسّن محدّد — لا يُستدعى بلا اختيار. */
export function usePracticeGuide(
  practice: string | null,
  enabled = true,
): UseQueryResult<PracticeGuideResponse> {
  return useQuery<PracticeGuideResponse>({
    queryKey: ['practice-guide', practice ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/practices/guide', { params: { practice } })
      .then((r) => r.data as PracticeGuideResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!practice,
    retry: false,
  });
}

// ═══ 5. صمود الجفاف — GET /api/v1/crops/(compare-)drought-resilience ══════════

/** درجة تحمّل الجفاف/الحرارة لمحصول من صفات موثّقة — لا يُستدعى بلا crop_id. */
export function useDroughtResilience(
  cropId: string | null,
  forecastMaxTempC: number | null,
  isIrrigated: boolean | null,
  enabled = true,
): UseQueryResult<DroughtResilienceResponse> {
  return useQuery<DroughtResilienceResponse>({
    queryKey: ['crop-drought-resilience', cropId ?? 'none', forecastMaxTempC ?? 'none', isIrrigated ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/crops/drought-resilience', {
        params: {
          crop_id: cropId,
          forecast_max_temp_c: forecastMaxTempC ?? undefined,
          is_irrigated: isIrrigated ?? undefined,
        },
      })
      .then((r) => r.data as DroughtResilienceResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 30 * 60_000,
    enabled: enabled && !!cropId,
    retry: false,
  });
}

/** يقارن تحمّل عدّة محاصيل (قائمة مفصولة بفواصل) — لا يُستدعى بلا محصولين. */
export function useCompareDroughtResilience(
  cropIds: string | null,
  forecastMaxTempC: number | null,
  isIrrigated: boolean | null,
  enabled = true,
): UseQueryResult<CompareDroughtResilienceResponse> {
  return useQuery<CompareDroughtResilienceResponse>({
    queryKey: ['crop-compare-drought-resilience', cropIds ?? 'none', forecastMaxTempC ?? 'none', isIrrigated ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/crops/compare-drought-resilience', {
        params: {
          crop_ids: cropIds,
          forecast_max_temp_c: forecastMaxTempC ?? undefined,
          is_irrigated: isIrrigated ?? undefined,
        },
      })
      .then((r) => r.data as CompareDroughtResilienceResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 30 * 60_000,
    enabled: enabled && !!cropIds,
    retry: false,
  });
}

// ═══ 6. تقييم مصدر البذار — POST /api/v1/seed/evaluate-source (نقيّ ⇒ queryFn) ═

export interface SeedSourceInput {
  certified: boolean;
  purity_pct?: number | null;
  germination_pct?: number | null;
}

/** يقيّم جودة مصدر بذار (اعتماد + نقاوة + إنبات) — نقيّ حتميّ بلا إدامة. */
export function useSeedEvaluate(
  input: SeedSourceInput | null,
): UseQueryResult<SeedEvaluateResponse> {
  return useQuery<SeedEvaluateResponse>({
    queryKey: [
      'seed-evaluate-source',
      input?.certified ?? 'none', input?.purity_pct ?? 'none', input?.germination_pct ?? 'none',
    ],
    queryFn: () => kongApi
      .post('/api/v1/seed/evaluate-source', {
        certified: input?.certified,
        purity_pct: input?.purity_pct ?? null,
        germination_pct: input?.germination_pct ?? null,
      })
      .then((r) => r.data as SeedEvaluateResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

// ═══ 7. استراتيجيّة أخذ العيّنات — GET /api/v1/sampling/strategy ═══════════════

export interface SamplingStrategyParams {
  areaHa: number | null;
  hasHistory: boolean;
  variability: string;
  crop?: string | null;
}

/** يوصي باستراتيجيّة أخذ عيّنات التربة — المساحة قياس المستخدم (لا استدعاء بلا مساحة). */
export function useSamplingStrategy(
  p: SamplingStrategyParams,
  enabled = true,
): UseQueryResult<SamplingStrategyResponse> {
  return useQuery<SamplingStrategyResponse>({
    queryKey: ['sampling-strategy', p.areaHa ?? 'none', p.hasHistory, p.variability, p.crop ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/sampling/strategy', {
        params: {
          area_ha: p.areaHa,
          has_history: p.hasHistory,
          variability: p.variability,
          crop: p.crop || undefined,
        },
      })
      .then((r) => r.data as SamplingStrategyResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 30 * 60_000,
    enabled: enabled && p.areaHa != null,
    retry: false,
  });
}
