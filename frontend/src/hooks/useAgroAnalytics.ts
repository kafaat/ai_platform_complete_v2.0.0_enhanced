// useAgroAnalytics — هوكات react-query لنقاط backend اليتيمة (P1) للتحليلات الزراعيّة-
// البيئيّة: مخاطر المحصول · الدورة الزراعيّة · دليل القرار · سلسلة Kc (لحقل + مقارنة) ·
// التغذية الراجعة نبات-تربة · مقارنة المواسم · تقييم التصعيد · نسب أصل الحقل.
//
// الأعراف مطابقة لـuseIrrigationDecisionAids.ts/useApi.ts: kongApi عبر البوّابة
// (/api/v1/*)، retry:false لحالة صادقة عند الفشل، وPOST داخل queryFn لأنّ نقاط agro
// حسابات قراءة نقيّة (النوى النقيّة) لا كتابات فعليّة (سابقة useNdviConfidence).
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404: حالة «غير مُفعَّل» صادقة بدل خطأ
// مُفزِع؛ باقي الأخطاء (403/5xx) تُرفَع كما هي لتعرضها الواجهة.
//
// استُبعِد POST /api/v1/agro/kc-timeseries عمداً: كتابة إدامة (IRRIGATION_MANAGE، upsert
// في crop_kc_timeseries) لا قراءة تحليليّة — تخصّ مسار إدارة الريّ لا بطاقة القراءة هذه.
// القراءتان GET /{field_id} و/{field_id}/compare هما سطح القراءة المُغطّى هنا.

import { useMutation, useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  CropRiskInput,
  CropRiskResponse,
  DecisionPlaybook,
  DecisionPlaybookInput,
  EscalationAssessInput,
  EscalationAssessResponse,
  FieldLineageResponse,
  KcCompareResponse,
  KcSeriesResponse,
  PlantSoilFeedback,
  RotationAssessment,
  SeasonComparisonResponse,
  SeasonCropInput,
  SeasonMetricsInput,
  SoilFeedbackInput,
} from '../lib/agroAnalytics';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** مخاطر المحصول من إشارات الطقس — POST /api/v1/agro/crop-risk.
 *  لا يُستدعى بلا محصول مختار (لا تخمين). */
export function useCropRisk(input: CropRiskInput | null): UseQueryResult<CropRiskResponse> {
  return useQuery<CropRiskResponse>({
    queryKey: [
      'agro-crop-risk',
      input?.crop ?? 'none',
      input?.disease_risk_score ?? 'none',
      input?.heat_stress_hours ?? 'none',
      input?.frost_risk_hours ?? 'none',
      input?.humidity_avg_percent ?? 'none',
    ],
    queryFn: () => kongApi
      .post('/api/v1/agro/crop-risk', input)
      .then((r) => r.data as CropRiskResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** تقييم جودة الدورة الزراعيّة — POST /api/v1/agro/crop-rotation.
 *  لا يُستدعى بلا مواسم في التاريخ (سجلّ فارغ = لا سؤال). */
export function useCropRotation(
  history: SeasonCropInput[] | null,
): UseQueryResult<RotationAssessment> {
  return useQuery<RotationAssessment>({
    queryKey: ['agro-crop-rotation', JSON.stringify(history ?? [])],
    queryFn: () => kongApi
      .post('/api/v1/agro/crop-rotation', { history })
      .then((r) => r.data as RotationAssessment)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: Array.isArray(history) && history.length > 0,
    retry: false,
  });
}

/** دليل قرار قابل للتفسير — POST /api/v1/agro/decision-playbook.
 *  يُركّب إشارات الطقس + مخاطر المحصول + التغذية الراجعة إلى حُكم واحد. */
export function useDecisionPlaybook(
  input: DecisionPlaybookInput | null,
): UseQueryResult<DecisionPlaybook> {
  return useQuery<DecisionPlaybook>({
    queryKey: ['agro-decision-playbook', JSON.stringify(input ?? {})],
    queryFn: () => kongApi
      .post('/api/v1/agro/decision-playbook', input)
      .then((r) => r.data as DecisionPlaybook)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** سلسلة Kc التاريخيّة لحقل — GET /api/v1/agro/kc-timeseries/{field_id}.
 *  معزول بـRLS من الخادم. لا يُستدعى بلا حقل مختار. */
export function useKcSeries(
  fieldId: string | null,
  cropId: string | null,
  scenarioType: string | null,
  enabled = true,
): UseQueryResult<KcSeriesResponse> {
  return useQuery<KcSeriesResponse>({
    queryKey: ['agro-kc-series', fieldId ?? 'none', cropId ?? 'none', scenarioType ?? 'none'],
    queryFn: () => kongApi
      .get(`/api/v1/agro/kc-timeseries/${encodeURIComponent(fieldId ?? '')}`, {
        params: { crop_id: cropId || undefined, scenario_type: scenarioType || undefined },
      })
      .then((r) => r.data as KcSeriesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && !!fieldId,
    retry: false,
  });
}

/** مقارنة Kc موسمين لنفس الحقل/المحصول — GET /api/v1/agro/kc-timeseries/{field_id}/compare.
 *  يتطلّب المحصول والموسمين (query إجباريّة من الخادم)؛ 404 إن غاب موسم. */
export function useKcCompare(
  fieldId: string | null,
  cropId: string | null,
  currentSeason: string | null,
  previousSeason: string | null,
  scenarioType: string,
  enabled = true,
): UseQueryResult<KcCompareResponse> {
  return useQuery<KcCompareResponse>({
    queryKey: [
      'agro-kc-compare',
      fieldId ?? 'none', cropId ?? 'none',
      currentSeason ?? 'none', previousSeason ?? 'none', scenarioType,
    ],
    queryFn: () => kongApi
      .get(`/api/v1/agro/kc-timeseries/${encodeURIComponent(fieldId ?? '')}/compare`, {
        params: {
          crop_id: cropId,
          current_season: currentSeason,
          previous_season: previousSeason,
          scenario_type: scenarioType,
        },
      })
      .then((r) => r.data as KcCompareResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: enabled && !!fieldId && !!cropId && !!currentSeason && !!previousSeason,
    retry: false,
  });
}

/** التغذية الراجعة نبات-تربة (PSFI) من مؤشّرات الإدارة — POST /api/v1/agro/plant-soil-feedback.
 *  كلّ المؤشّرات اختياريّة (None = مجهول)؛ لا يُستدعى قبل إدخال مؤشّر واحد على الأقلّ. */
export function usePlantSoilFeedback(
  input: SoilFeedbackInput | null,
): UseQueryResult<PlantSoilFeedback> {
  const hasAny = !!input && Object.values(input).some((v) => v != null);
  return useQuery<PlantSoilFeedback>({
    queryKey: ['agro-plant-soil-feedback', JSON.stringify(input ?? {})],
    queryFn: () => kongApi
      .post('/api/v1/agro/plant-soil-feedback', input)
      .then((r) => r.data as PlantSoilFeedback)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: hasAny,
    retry: false,
  });
}

/** مقارنة موسمين (الحاليّ مقابل السابق) — POST /api/v1/agro/season-comparison.
 *  لا يُستدعى بلا موسمين بمعرّفَيهما (الخادم يتطلّب current/previous). */
export function useSeasonComparison(
  current: SeasonMetricsInput | null,
  previous: SeasonMetricsInput | null,
): UseQueryResult<SeasonComparisonResponse> {
  return useQuery<SeasonComparisonResponse>({
    queryKey: [
      'agro-season-comparison',
      JSON.stringify(current ?? {}), JSON.stringify(previous ?? {}),
    ],
    queryFn: () => kongApi
      .post('/api/v1/agro/season-comparison', { current, previous })
      .then((r) => r.data as SeasonComparisonResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!current && !!previous,
    retry: false,
  });
}

/** تقييم تصعيد الشكّ لإنسان — POST /api/v1/escalation/assess.
 *  confidence=None أو has_answer=false ⇒ BLOCKED من الخادم (لا تأليف). */
export function useEscalationAssess(
  input: EscalationAssessInput | null,
): UseQueryResult<EscalationAssessResponse> {
  return useQuery<EscalationAssessResponse>({
    queryKey: [
      'escalation-assess',
      input?.source ?? 'none',
      input?.confidence ?? 'none',
      input?.has_answer ?? true,
      JSON.stringify(input?.uncertain_points ?? []),
    ],
    queryFn: () => kongApi
      .post('/api/v1/escalation/assess', input)
      .then((r) => r.data as EscalationAssessResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input && !!input.source,
    retry: false,
  });
}

/** نسب أصل الحقل: قراراته المُدامة + نتائجها المربوطة — GET /api/v1/field/{field_id}/lineage.
 *  معزول بـRLS. مسار قراءة تكامليّ (يتطلّب Postgres) — قد يعيد 503 عند تعذّر القاعدة. */
export function useFieldLineage(
  fieldId: string | null,
  limit = 50,
  enabled = true,
): UseQueryResult<FieldLineageResponse> {
  return useQuery<FieldLineageResponse>({
    queryKey: ['field-lineage', fieldId ?? 'none', limit],
    queryFn: () => kongApi
      .get(`/api/v1/field/${encodeURIComponent(fieldId ?? '')}/lineage`, { params: { limit } })
      .then((r) => r.data as FieldLineageResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled: enabled && !!fieldId,
    retry: false,
  });
}

/** حفظ/تحديث Kc موسم (upsert) — POST /api/v1/agro/kc-timeseries.
 *  كتابة مدير (IRRIGATION_MANAGE خادميّاً؛ 403 لغير المخوّل تُعرَض كما هي).
 *  قيم المراحل الاختياريّة تُرسَل null حين تُترَك فارغة — «ناقص لا يُختلق». */
export interface KcPersistInput {
  field_id: string;
  crop_id: string;
  season_id: string;
  scenario_type?: string;
  kc_ini?: number | null;
  kc_mid?: number | null;
  kc_end?: number | null;
}

export function usePersistKc() {
  return useMutation({
    mutationFn: (input: KcPersistInput) =>
      kongApi.post('/api/v1/agro/kc-timeseries', input).then(
        (r) => r.data as { kc_id?: number; season_id?: string; scenario_type?: string },
      ),
  });
}

/** اتّجاه التغذية الراجعة نبات-تربة عبر عدّة مواسم — POST /api/v1/agro/plant-soil-feedback/trend.
 *  حساب نقيّ (لا حفظ)؛ يحتاج موسمين+ لاشتقاق اتّجاه. القيم الفارغة تُرسَل null. */
export interface FeedbackTrendSeason {
  season_id: string;
  inputs: SoilFeedbackInput;
}
export interface FeedbackTrendResponse {
  seasons_analyzed?: number;
  positive_series?: [string, number][];
  net_series?: [string, number][];
  positive_delta?: number | null;
  net_delta?: number | null;
  direction?: string;
  slope_per_season?: number | null;
  drivers_ar?: string[];
  verdict_ar?: string;
  disabled?: boolean;
}
export function usePlantSoilFeedbackTrend() {
  return useMutation({
    mutationFn: (seasons: FeedbackTrendSeason[]) =>
      kongApi.post('/api/v1/agro/plant-soil-feedback/trend', { seasons }).then(
        (r) => r.data as FeedbackTrendResponse,
      ).catch((e) => { if (isDisabled404(e)) return { disabled: true } as FeedbackTrendResponse; throw e; }),
  });
}
