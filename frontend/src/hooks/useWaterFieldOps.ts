// useWaterFieldOps — هوكات react-query لنقاط backend اليتيمة (P1): حساسيّة الإجهاد
// المائيّ (stress-risk/integrated-advice/wheat-calendar) + ميزان الماء FAO-56 +
// مورد السيول الواردة + تحليل ماء الريّ المخبريّ + تنبيهات/طبقات الطقس + خطّة 4R
// + إدامة نتيجة القرار (outcome/record) + تحديد الموقع الجغرافيّ.
//
// الأعراف مطابقة لـuseIrrigationDecisionAids.ts: kongApi عبر البوّابة (/api/v1/*)،
// retry:false لحالة صادقة عند الفشل، staleTime طويل للمعرفة المرجعيّة الثابتة،
// وPOST داخل queryFn (سابقة useFieldChange) للحسابات النقيّة القرائيّة فقط.
// الكتابات الحقيقيّة (lab/water-results تُخزِّن التحليل، outcome/record يُدِيم في
// Postgres) تبقى useMutation — لا تُعاد تلقائيّاً ولا تُخبَّأ.
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404 في useApi.ts: حالة «غير مُفعَّل»
// صادقة بدل خطأ مُفزِع؛ باقي الأخطاء (403/5xx) تُرفَع كما هي لتعرضها الواجهة.

import { useMutation, useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  FourRPlanResponse,
  GeoLocateFieldResponse,
  IntegratedAdviceInput,
  OutcomeRecordInput,
  OutcomeRecordResponse,
  Soil4RInput,
  StressRiskInput,
  StressRiskResponse,
  UpstreamFloodResponse,
  WaterBalanceInput,
  WaterBalanceResponse,
  WaterLabAnalysis,
  WaterSamplePayload,
  WeatherAlertsResponse,
  WeatherLayersResponse,
  WheatCalendarResponse,
} from '../lib/waterFieldOps';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** خطر الإجهاد المائيّ (محصول+مرحلة+نضوب من المستخدم) —
 *  POST /api/v1/water-sensitivity/stress-risk. لا يُستدعى بلا مدخلات كاملة. */
export function useWaterStressRisk(
  input: StressRiskInput | null,
): UseQueryResult<StressRiskResponse> {
  return useQuery<StressRiskResponse>({
    queryKey: [
      'water-sensitivity-stress-risk',
      input?.crop ?? 'none',
      input?.stage_key ?? 'none',
      input?.depletion_pct ?? 'none',
    ],
    queryFn: () => kongApi
      .post('/api/v1/water-sensitivity/stress-risk', input)
      .then((r) => r.data as StressRiskResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** النصيحة المائيّة المتكاملة (الحساسيّة «متى حرج» + الاحتياج «كم مم») —
 *  POST /api/v1/water-sensitivity/integrated-advice. تتمايز عن stress-risk
 *  بصافي الريّ (net_irrigation_mm) — غيابه ⇒ لا استدعاء. */
export function useIntegratedWaterAdvice(
  input: IntegratedAdviceInput | null,
): UseQueryResult<StressRiskResponse> {
  return useQuery<StressRiskResponse>({
    queryKey: [
      'water-sensitivity-integrated-advice',
      input?.crop ?? 'none',
      input?.stage_key ?? 'none',
      input?.depletion_pct ?? 'none',
      input?.net_irrigation_mm ?? 'none',
    ],
    queryFn: () => kongApi
      .post('/api/v1/water-sensitivity/integrated-advice', input)
      .then((r) => r.data as StressRiskResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** التقويم المائيّ للقمح (توافق خلفيّ + تحذير التشبّع المائيّ) —
 *  GET /api/v1/water-sensitivity/wheat-calendar. معرفة مرجعيّة ⇒ staleTime طويل.
 *  (التقويم العامّ حسب المحصول /calendar تعرضه ClimateRiskCard — لا تكرار.) */
export function useWheatWaterCalendar(enabled = true): UseQueryResult<WheatCalendarResponse> {
  return useQuery<WheatCalendarResponse>({
    queryKey: ['water-sensitivity-wheat-calendar'],
    queryFn: () => kongApi
      .get('/api/v1/water-sensitivity/wheat-calendar')
      .then((r) => r.data as WheatCalendarResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** ميزان الماء FAO-56 (ET₀→ETc→صافٍ بعد المطر، وقرار الملوحة عند تمرير تحليل) —
 *  POST /api/v1/water-balance. حساب نقيّ قرائيّ ⇒ POST داخل queryFn. */
export function useWaterBalance(
  input: WaterBalanceInput | null,
): UseQueryResult<WaterBalanceResponse> {
  return useQuery<WaterBalanceResponse>({
    // المفتاح بالجسم كاملاً: أيّ تغيير مدخل (حرارة/مطر/ملوحة…) يعيد الحساب.
    queryKey: ['water-balance', input ? JSON.stringify(input) : 'none'],
    queryFn: () => kongApi
      .post('/api/v1/water-balance', input)
      .then((r) => r.data as WaterBalanceResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** مورد السيول الواردة من أحواض أعلى (يتجاوز المطر المحلّيّ) —
 *  GET /api/v1/water-harvesting/upstream-flood. المطر المحلّيّ قياس من المستخدم. */
export function useUpstreamFlood(
  localRainMm: number | null,
  enabled = true,
): UseQueryResult<UpstreamFloodResponse> {
  return useQuery<UpstreamFloodResponse>({
    queryKey: ['water-harvesting-upstream-flood', localRainMm ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/water-harvesting/upstream-flood', { params: { local_rain_mm: localRainMm } })
      .then((r) => r.data as UpstreamFloodResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && localRainMm != null,
    retry: false,
  });
}

/** إرسال نتيجة تحليل ماء ريّ مخبريّ — POST /api/v1/lab/water-results.
 *  كتابة (الخادم يخزّن التحليل ويحدّث العيّنة إن وُجدت) ⇒ useMutation لا useQuery؛
 *  الأخطاء (403 صلاحيّة FIELD_EDIT / 404 غير مُفعَّل) تعالجها الواجهة بنصّ صادق. */
export function useSubmitWaterLabResult() {
  return useMutation<WaterLabAnalysis, Error, WaterSamplePayload>({
    mutationFn: (payload) =>
      kongApi.post('/api/v1/lab/water-results', payload).then((r) => r.data as WaterLabAnalysis),
  });
}

/** تنبيهات طقس زراعيّة مشتقّة بإحداثيّات (عامّة، بلا كتابة) —
 *  GET /api/v1/weather/alerts. الإحداثيّات من المستخدم/الحقل (لا تخمين). */
export function useWeatherAlerts(
  lat: number | null,
  lon: number | null,
  enabled = true,
): UseQueryResult<WeatherAlertsResponse> {
  return useQuery<WeatherAlertsResponse>({
    queryKey: ['weather-alerts', lat ?? 'none', lon ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/weather/alerts', { params: { lat, lon } })
      .then((r) => r.data as WeatherAlertsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    // تنبيهات لحظيّة — staleTime قصير كي لا نعرض خطراً قديماً كأنّه حاليّ.
    staleTime: 60_000,
    enabled: enabled && lat != null && lon != null,
    retry: false,
  });
}

/** manifest طبقات الطقس/العمليّات التي يرسمها SAHOOL — GET /api/v1/weather/layers.
 *  تعريفات شبه ثابتة ⇒ staleTime طويل. */
export function useWeatherLayers(enabled = true): UseQueryResult<WeatherLayersResponse> {
  return useQuery<WeatherLayersResponse>({
    queryKey: ['weather-layers'],
    queryFn: () => kongApi
      .get('/api/v1/weather/layers')
      .then((r) => r.data as WeatherLayersResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** خطّة تسميد 4R للتربة الكلسيّة — POST /api/v1/nutrients/4r-plan.
 *  حساب نقيّ من تحليل مخبريّ يُدخِله المستخدم (قيمة واحدة على الأقلّ). */
export function useNutrient4rPlan(
  input: Soil4RInput | null,
): UseQueryResult<FourRPlanResponse> {
  return useQuery<FourRPlanResponse>({
    queryKey: ['nutrients-4r-plan', input ? JSON.stringify(input) : 'none'],
    queryFn: () => kongApi
      .post('/api/v1/nutrients/4r-plan', input)
      .then((r) => r.data as FourRPlanResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** إدامة نتيجة قرار (القياس النقيّ ثمّ الكتابة في outcome_record + حدث) —
 *  POST /api/v1/outcome/record. تختلف عن /outcome/measure (حساب بلا إدامة —
 *  مغطّى في DecisionRuntimePage): هذه كتابة تتطلّب Postgres (503 عند تعذّرها)
 *  ⇒ useMutation، والواجهة تعرض persisted/replayed كما أعلنها الخادم. */
export function useRecordOutcome() {
  return useMutation<OutcomeRecordResponse, Error, OutcomeRecordInput>({
    mutationFn: (input) =>
      kongApi.post('/api/v1/outcome/record', input).then((r) => r.data as OutcomeRecordResponse),
  });
}

/** تحديد المحافظة + الإقليم المناخيّ من إحداثيّات الحقل —
 *  GET /api/v1/geo-locate/field. الارتفاع اختياريّ لكنّه يحسم التصنيف الجبليّ. */
export function useGeoLocateField(
  lat: number | null,
  lon: number | null,
  elevationM: number | null,
  enabled = true,
): UseQueryResult<GeoLocateFieldResponse> {
  return useQuery<GeoLocateFieldResponse>({
    queryKey: ['geo-locate-field', lat ?? 'none', lon ?? 'none', elevationM ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/geo-locate/field', {
        params: { lat, lon, elevation_m: elevationM ?? undefined },
      })
      .then((r) => r.data as GeoLocateFieldResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && lat != null && lon != null,
    retry: false,
  });
}
