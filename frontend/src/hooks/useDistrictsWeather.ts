// useDistrictsWeather — هوكات react-query لنقاط backend اليتيمة (P2):
//   • المديريّات   GET /api/v1/districts · /districts/{id} · /districts/{id}/active-pests
//   • الموقع       GET /api/v1/geo-locate/recommend
//   • طقس الحقل    GET /api/v1/weather/field-weather-summary
//   • تحليلات طقس  POST /api/v1/weather-analytics/analyze · /planting-guide
//   • التهيئة      GET /api/v1/onboarding/questionnaire · POST /api/v1/onboarding/responses
//
// الأعراف مطابقة لـuseIrrigationDecisionAids.ts/useWaterFieldOps.ts: kongApi عبر
// البوّابة (/api/v1/*)، retry:false لحالة صادقة عند الفشل، staleTime طويل للمعرفة
// المرجعيّة الثابتة (المديريّات/الاستبيان) وأقصر للطقس اللحظيّ. POST داخل queryFn
// (سابقة useNdviConfidence) للحسابات القرائيّة النقيّة (analyze/planting-guide لا
// تكتب شيئاً). الكتابة الحقيقيّة الوحيدة (onboarding/responses تُدِيم الردّ في
// Postgres عبر RLS) تبقى useMutation — لا تُعاد تلقائيّاً ولا تُخبَّأ.
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404 في useApi.ts: «غير مُفعَّل» صادقة
// بدل خطأ مُفزِع؛ باقي الأخطاء (403/422/5xx) تُرفَع كما هي لتعرضها الواجهة.

import { useMutation, useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  ActivePestsResponse,
  DistrictCard,
  DistrictsIndexResponse,
  FieldWeatherSummaryResponse,
  GeoRecommendResponse,
  OnboardingSubmitPayload,
  OnboardingSubmitResponse,
  PlantingGuideResponse,
  QuestionnaireResponse,
  TileSeriesResponse,
  WeatherAnalysisResponse,
  WeatherRecord,
} from '../lib/districtsWeather';
import { lonLatToTile } from '../lib/districtsWeather';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** فهرس المديريّات (معرفة مرجعيّة إقليميّة ثابتة) — GET /api/v1/districts. */
export function useDistrictsIndex(enabled = true): UseQueryResult<DistrictsIndexResponse> {
  return useQuery<DistrictsIndexResponse>({
    queryKey: ['districts-index'],
    queryFn: () => kongApi
      .get('/api/v1/districts')
      .then((r) => r.data as DistrictsIndexResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** بطاقة مديريّة كاملة (نوافذ خطر الآفات بمصادرها) — GET /api/v1/districts/{id}.
 *  لا يُستدعى بلا اختيار مديريّة (لا تخمين). */
export function useDistrictDetail(
  districtId: string | null,
  enabled = true,
): UseQueryResult<DistrictCard> {
  return useQuery<DistrictCard>({
    queryKey: ['district-detail', districtId ?? 'none'],
    queryFn: () => kongApi
      .get(`/api/v1/districts/${encodeURIComponent(districtId as string)}`)
      .then((r) => r.data as DistrictCard)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!districtId,
    retry: false,
  });
}

/** الآفات النشطة لمديريّة في شهر (1..12) — GET /api/v1/districts/{id}/active-pests.
 *  الشهر يختاره المستخدم؛ لا استدعاء بلا مديريّة+شهر (الخادم يرفض خارج النطاق بـ422). */
export function useDistrictActivePests(
  districtId: string | null,
  month: number | null,
  enabled = true,
): UseQueryResult<ActivePestsResponse> {
  return useQuery<ActivePestsResponse>({
    queryKey: ['district-active-pests', districtId ?? 'none', month ?? 'none'],
    queryFn: () => kongApi
      .get(`/api/v1/districts/${encodeURIComponent(districtId as string)}/active-pests`, {
        params: { month },
      })
      .then((r) => r.data as ActivePestsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!districtId && month != null,
    retry: false,
  });
}

/** تحديد الموقع + توصية محاصيل مباشرة — GET /api/v1/geo-locate/recommend.
 *  الإحداثيّات من المستخدم/الحقل (لا تخمين)؛ الارتفاع اختياريّ يحسم التصنيف الجبليّ. */
export function useGeoLocateRecommend(
  lat: number | null,
  lon: number | null,
  elevationM: number | null,
  enabled = true,
): UseQueryResult<GeoRecommendResponse> {
  return useQuery<GeoRecommendResponse>({
    queryKey: ['geo-locate-recommend', lat ?? 'none', lon ?? 'none', elevationM ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/geo-locate/recommend', {
        params: { lat, lon, elevation_m: elevationM ?? undefined },
      })
      .then((r) => r.data as GeoRecommendResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && lat != null && lon != null,
    retry: false,
  });
}

/** ملخّص طقس زراعيّ للحقل (قراءة حاليّة + صلاحيّة عمليّات + تنبيهات) —
 *  GET /api/v1/weather/field-weather-summary. لحظيّ ⇒ staleTime قصير كي لا نعرض
 *  حالة قديمة كأنّها الآن. الإحداثيّات من المستخدم/الحقل (لا تخمين). */
export function useFieldWeatherSummary(
  lat: number | null,
  lon: number | null,
  enabled = true,
): UseQueryResult<FieldWeatherSummaryResponse> {
  return useQuery<FieldWeatherSummaryResponse>({
    queryKey: ['field-weather-summary', lat ?? 'none', lon ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/weather/field-weather-summary', { params: { lat, lon } })
      .then((r) => r.data as FieldWeatherSummaryResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled: enabled && lat != null && lon != null,
    retry: false,
  });
}

/** تحليل سجلّ طقس يوميّ (إجهاد حراريّ + ET₀ + عجز مائيّ) —
 *  POST /api/v1/weather-analytics/analyze. حساب قراءة نقيّ لا كتابة ⇒ queryFn.
 *  السجلّ يُدخِله المستخدم (لا تخمين ⇒ لا استدعاء بلا سجلّات مُحقَّقة). */
export function useWeatherAnalysis(
  records: WeatherRecord[] | null,
  enabled = true,
): UseQueryResult<WeatherAnalysisResponse> {
  return useQuery<WeatherAnalysisResponse>({
    queryKey: ['weather-analytics-analyze', records?.length ?? 0, records ? JSON.stringify(records) : 'none'],
    queryFn: () => kongApi
      .post('/api/v1/weather-analytics/analyze', records)
      .then((r) => r.data as WeatherAnalysisResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && !!records && records.length > 0,
    retry: false,
  });
}

/** دليل المواسم من السجلّ (متى الزراعة/الإجهاد شهريّاً) —
 *  POST /api/v1/weather-analytics/planting-guide. حساب قراءة نقيّ ⇒ queryFn. */
export function useWeatherPlantingGuide(
  records: WeatherRecord[] | null,
  enabled = true,
): UseQueryResult<PlantingGuideResponse> {
  return useQuery<PlantingGuideResponse>({
    queryKey: ['weather-analytics-planting-guide', records?.length ?? 0, records ? JSON.stringify(records) : 'none'],
    queryFn: () => kongApi
      .post('/api/v1/weather-analytics/planting-guide', records)
      .then((r) => r.data as PlantingGuideResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && !!records && records.length > 0,
    retry: false,
  });
}

/** تعريف استبيان التهيئة (phase=1 للإلزاميّ فقط، بلا معامل للكلّ) —
 *  GET /api/v1/onboarding/questionnaire. معرفة ثابتة ⇒ staleTime طويل. */
export function useOnboardingQuestionnaire(
  phase: number | null = null,
  enabled = true,
): UseQueryResult<QuestionnaireResponse> {
  return useQuery<QuestionnaireResponse>({
    queryKey: ['onboarding-questionnaire', phase ?? 'all'],
    queryFn: () => kongApi
      .get('/api/v1/onboarding/questionnaire', {
        params: { phase: phase ?? undefined },
      })
      .then((r) => r.data as QuestionnaireResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** إرسال ردّ الاستبيان — POST /api/v1/onboarding/responses.
 *  كتابة تُدِيم الردّ في Postgres (RLS مُطبَّق) ⇒ useMutation لا useQuery؛ الأخطاء
 *  (403/404/5xx) تعالجها الواجهة بنصّ صادق، والخادم يُرجِع missing_required للناقص. */
export function useSubmitOnboarding() {
  return useMutation<OnboardingSubmitResponse, Error, OnboardingSubmitPayload>({
    mutationFn: (payload) =>
      kongApi
        .post('/api/v1/onboarding/responses', payload)
        .then((r) => r.data as OnboardingSubmitResponse),
  });
}

/** سلسلة طقس زمنيّة لبلاطة مشتقّة من (lat,lon) — GET /api/v1/weather/tile-series/{z}/{x}/{y}.
 *  قيم JSON عبر إزاحات ساعيّة (animation/time-slider) لا بلاطة صور. z افتراضيّ 9 (إقليميّ). */
export function useWeatherTileSeries(
  lat: number | null,
  lon: number | null,
  layer: string,
  enabled: boolean,
  z = 9,
): UseQueryResult<TileSeriesResponse> {
  const tile = lat !== null && lon !== null ? lonLatToTile(lon, lat, z) : null;
  return useQuery<TileSeriesResponse>({
    queryKey: ['weather-tile-series', tile?.z, tile?.x, tile?.y, layer],
    queryFn: () => kongApi
      .get(`/api/v1/weather/tile-series/${tile!.z}/${tile!.x}/${tile!.y}`, { params: { layer } })
      .then((r) => r.data as TileSeriesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    enabled: enabled && tile !== null && !!layer,
    staleTime: 5 * 60_000,
    retry: false,
  });
}
