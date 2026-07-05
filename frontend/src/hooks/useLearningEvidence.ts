// useLearningEvidence — هوكات react-query لنقاط backend اليتيمة (P3، سطح المرشد):
// بوّابة تفعيل التعلّم · مزج سابقة خارجيّة · معايرة التنبّؤ · اقتراح عتبات السياسة ·
// تغذية راجعة المعايرة · تسجيل مشاهدة · طبقات الخريطة · تغطية المؤشّرات · تظافر
// القرائن · بوّابة الثقة.
//
// الأعراف مطابقة لـuseAgroAnalytics.ts/useIrrigationDecisionAids.ts/useApi.ts:
// kongApi عبر البوّابة (/api/v1/*)، retry:false لحالة صادقة عند الفشل، وPOST داخل
// queryFn لنقاط الحساب النقيّة (لا كتابة فعليّة — سابقة useNdviConfidence/useCropRisk).
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404: حالة «غير مُفعَّل» صادقة بدل خطأ
// مُفزِع؛ باقي الأخطاء (403/5xx) تُرفَع كما هي لتعرضها الواجهة.
//
// GET vs POST vs كتابة:
//  • قراءات GET نقيّة (لا مُدخل حقل): activation-status/prediction-calibration/
//    threshold-suggestions/map-layers/coverage-report ⇒ useQuery.
//  • POST حساب نقيّ (لا يكتب حالة خادم — النوى النقيّة): external-prior-blend/
//    calibration-feedback/evidence-corroborate/confidence-gate ⇒ useQuery داخل queryFn.
//    ملاحظة صدق: calibration/feedback يُرجِع auto_adjust=false وcalibrated=false —
//    اقتراح مراجعة بشريّة لا كتابة؛ لذا هو قراءة حساب لا mutation (تمثيل صادق).
//  • كتابة فعليّة وحيدة: POST /api/v1/observations (يُدرِج في طابور المزامنة) ⇒
//    useMutation (نموذج إرسال صادق مع تأكيد op_id).

import { useMutation, useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  ActivationStatus,
  CalibrationFeedback,
  ConfidenceGateInput,
  ConfidenceGateResult,
  CorroborationInput,
  CorroborationResult,
  CoverageReport,
  EvidenceRecordInput,
  ExternalPriorBlend,
  ExternalPriorBlendInput,
  MapLayersResponse,
  ObservationInput,
  ObservationResult,
  PredictionCalibration,
  ThresholdSuggestions,
} from '../lib/learningEvidence';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** بوّابة تفعيل التعلّم للمستأجِر — GET /api/v1/learning/activation-status.
 *  مدفوعة بالبيانات (RECOMMENDATION_VIEW خادميّاً)؛ 503 عند تعذّر القاعدة. */
export function useActivationStatus(enabled = true): UseQueryResult<ActivationStatus> {
  return useQuery<ActivationStatus>({
    queryKey: ['learning-activation-status'],
    queryFn: () => kongApi
      .get('/api/v1/learning/activation-status')
      .then((r) => r.data as ActivationStatus)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled,
    retry: false,
  });
}

/** مزج سابقة خارجيّة منشورة ببيانات اليمن — POST /api/v1/learning/external-prior-blend.
 *  حساب نقيّ (لا كتابة)؛ لا يُستدعى بلا قرينة (blendReady في موقع الاستدعاء). */
export function useExternalPriorBlend(
  input: ExternalPriorBlendInput | null,
): UseQueryResult<ExternalPriorBlend> {
  return useQuery<ExternalPriorBlend>({
    queryKey: [
      'learning-external-prior-blend',
      input?.external_prior ?? 'none',
      input?.local_estimate ?? 'none',
      input?.n_local ?? 0,
      input?.crop_grown_in_yemen ?? false,
      input?.external_credibility ?? 0.5,
    ],
    queryFn: () => kongApi
      .post('/api/v1/learning/external-prior-blend', input)
      .then((r) => r.data as ExternalPriorBlend)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** معايرة التنبّؤ من التاريخ المتراكم — GET /api/v1/learning/prediction-calibration.
 *  crop_id اختياريّ (تصفية)؛ 503 عند تعذّر القاعدة. correction_factor=1.0 = لا تصحيح. */
export function usePredictionCalibration(
  cropId: string | null,
  enabled = true,
): UseQueryResult<PredictionCalibration> {
  return useQuery<PredictionCalibration>({
    queryKey: ['learning-prediction-calibration', cropId ?? 'all'],
    queryFn: () => kongApi
      .get('/api/v1/learning/prediction-calibration', {
        params: { crop_id: cropId || undefined },
      })
      .then((r) => r.data as PredictionCalibration)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled,
    retry: false,
  });
}

/** اقتراحات ضبط عتبات التنبيه للمستأجِر — GET /api/v1/policy-learning/threshold-suggestions.
 *  ANALYTICS_VIEW خادميّاً؛ human-in-the-loop (لا تُطبَّق آليّاً)؛ 503 عند تعذّر القاعدة. */
export function useThresholdSuggestions(enabled = true): UseQueryResult<ThresholdSuggestions> {
  return useQuery<ThresholdSuggestions>({
    queryKey: ['policy-threshold-suggestions'],
    queryFn: () => kongApi
      .get('/api/v1/policy-learning/threshold-suggestions')
      .then((r) => r.data as ThresholdSuggestions)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled,
    retry: false,
  });
}

/** تغذية راجعة المعايرة — POST /api/v1/calibration/feedback.
 *  حساب نقيّ (auto_adjust=false, calibrated=false — اقتراح مراجعة لا كتابة)؛ لا
 *  يُستدعى بلا سجلّ دليل واحد على الأقلّ. */
export function useCalibrationFeedback(
  records: EvidenceRecordInput[] | null,
): UseQueryResult<CalibrationFeedback> {
  return useQuery<CalibrationFeedback>({
    queryKey: ['calibration-feedback', JSON.stringify(records ?? [])],
    queryFn: () => kongApi
      .post('/api/v1/calibration/feedback', { evidence_records: records })
      .then((r) => r.data as CalibrationFeedback)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: Array.isArray(records) && records.length > 0,
    retry: false,
  });
}

/** كتالوج طبقات الخريطة (المؤشّرات القابلة للرسم) — GET /api/v1/indicators/map-layers.
 *  ثابت (لا قاعدة)، FIELD_VIEW خادميّاً ⇒ staleTime طويل. */
export function useMapLayers(enabled = true): UseQueryResult<MapLayersResponse> {
  return useQuery<MapLayersResponse>({
    queryKey: ['indicators-map-layers'],
    queryFn: () => kongApi
      .get('/api/v1/indicators/map-layers')
      .then((r) => r.data as MapLayersResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** تقرير تغطية المؤشّرات (المربوط بالقرار مقابل العرض) — GET /api/v1/indices/coverage-report.
 *  ثابت شفّاف (حوكمة)، FIELD_VIEW خادميّاً ⇒ staleTime طويل. */
export function useCoverageReport(enabled = true): UseQueryResult<CoverageReport> {
  return useQuery<CoverageReport>({
    queryKey: ['indices-coverage-report'],
    queryFn: () => kongApi
      .get('/api/v1/indices/coverage-report')
      .then((r) => r.data as CoverageReport)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** تظافر القرائن ⇒ درجة التوصية — POST /api/v1/evidence/corroborate.
 *  حساب نقيّ (لا كتابة)؛ لا يُستدعى بلا قرينة واحدة على الأقلّ. */
export function useCorroborate(
  input: CorroborationInput | null,
): UseQueryResult<CorroborationResult> {
  return useQuery<CorroborationResult>({
    queryKey: ['evidence-corroborate', JSON.stringify(input ?? {})],
    queryFn: () => kongApi
      .post('/api/v1/evidence/corroborate', input)
      .then((r) => r.data as CorroborationResult)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input && input.evidences.length > 0,
    retry: false,
  });
}

/** بوّابة الثقة الموحّدة ⇒ قرار (واثقة/مراجعة/محجوبة) — POST /api/v1/confidence-gate.
 *  حساب نقيّ (لا كتابة)؛ لا يُستدعى بلا إشارة محرّك واحدة على الأقلّ. */
export function useConfidenceGate(
  input: ConfidenceGateInput | null,
): UseQueryResult<ConfidenceGateResult> {
  return useQuery<ConfidenceGateResult>({
    queryKey: ['confidence-gate', JSON.stringify(input ?? {})],
    queryFn: () => kongApi
      .post('/api/v1/confidence-gate', input)
      .then((r) => r.data as ConfidenceGateResult)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input && input.signals.length > 0,
    retry: false,
  });
}

/** تسجيل مشاهدة حقليّة — POST /api/v1/observations (كتابة: طابور المزامنة offline-first).
 *  OBSERVATION_RECORD خادميّاً؛ 403 عند عدم تطابق المستأجِر أو نقص الصلاحيّة تُعرَض كما هي.
 *  الكتابة الوحيدة في هذه المجموعة ⇒ useMutation (إرسال صريح مع تأكيد op_id). */
export function useRecordObservation() {
  return useMutation({
    mutationFn: (input: ObservationInput) =>
      kongApi.post('/api/v1/observations', input).then((r) => r.data as ObservationResult),
  });
}
