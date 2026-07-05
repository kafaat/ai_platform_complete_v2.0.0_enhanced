// useGisTemporalOps — هوكات react-query لنقاط backend اليتيمة (P3, agronomist):
// عمليّات نواة GIS (buffer/union/split/validate، dry-run محروسة بعَلَم) + التحكيم
// الزمني (check/coherence) + محاكاة ماذا-لو (WOFOST) + مخاطر المرحلة الموسميّة +
// إعادة البناء من الأحداث + رابط النَّسَب (محروس بعَلَم) + تحليل التجارب الحقليّة.
//
// الأعراف مطابقة لـuseApi.ts/useIrrigationDecisionAids.ts: kongApi عبر البوّابة،
// retry:false لحالة صادقة عند الفشل، و404 ⇒ {disabled:true} (عرف isDisabled404):
// «الميزة غير مُفعَّلة» صادقة بدل خطأ مُفزِع؛ باقي الأخطاء (422/403/5xx) تُرفَع.
//
// قرار GET مقابل POST — لماذا الأغلب useMutation لا useQuery-in-queryFn:
//   • عمليّات GIS تحسب من GeoJSON يلصقه المستخدم في textarea ⇒ تُشغَّل بضغطة «احسب»
//     الصريحة لا مع كلّ ضغطة مفتاح (تفادي إطلاق حساب PostGIS على مُدخَل نصفيّ).
//   • simulate/what-if يُشغّل WOFOST مرّتين (ثقيل) ⇒ عند الطلب فقط.
//   • lineage/link كتابة فعليّة (INSERT + حدث outbox) ⇒ mutation دلاليّاً.
//   • temporal/*, replay, trials حسابات POST يُجمّع المستخدم مدخلاتها ثمّ يُرسِل.
// أمّا seasonal-risk/stage-check فقراءة GET رخيصة بمعاملَي استعلام (zone/stage) ⇒
// useQuery (سابقة useMoistureDecision GET).

import { useMutation, useQuery, UseMutationResult, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  CoherenceResult,
  GisBufferResult,
  GisSplitResult,
  GisUnionResult,
  GisValidateResult,
  ReplayStateResult,
  StageCheckResult,
  TemporalCheckResult,
  TrialVerdictResult,
  WhatIfResult,
} from '../lib/gisTemporalOps';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** يغلّف mutationFn لعمليّة POST: 404 ⇒ {disabled:true} صادق؛ غيره يُرفَع كما هو. */
function postOp<TIn, TOut extends { disabled?: boolean }>(path: string) {
  return (input: TIn): Promise<TOut> =>
    kongApi
      .post(path, input)
      .then((r) => r.data as TOut)
      .catch((e) => {
        if (isDisabled404(e)) return { disabled: true } as TOut;
        throw e;
      });
}

// ─── عمليّات نواة GIS (dry-run، محروسة بـFEATURE_GIS_KERNEL) ─────────
// أحد المصدرين إلزاميّ خادميّاً لكلّ هندسة: geometry (GeoJSON) أو field_id — لا كلاهما.

export interface GisBufferInput {
  geometry?: object | null;
  field_id?: string | null;
  distance_m: number;
}
export interface GisUnionInput {
  geometry_a?: object | null;
  field_id_a?: string | null;
  geometry_b?: object | null;
  field_id_b?: string | null;
}
export interface GisSplitInput {
  geometry?: object | null;
  field_id?: string | null;
  blade: object;
}
export interface GisValidateInput {
  geometry?: object | null;
  field_id?: string | null;
}

/** POST /api/v1/gis/buffer — ST_Buffer(geom, distance_m) dry-run. */
export function useGisBuffer(): UseMutationResult<GisBufferResult, unknown, GisBufferInput> {
  return useMutation({ mutationFn: postOp<GisBufferInput, GisBufferResult>('/api/v1/gis/buffer'), retry: false });
}

/** POST /api/v1/gis/union — ST_Union لهندستين/حقلين dry-run. */
export function useGisUnion(): UseMutationResult<GisUnionResult, unknown, GisUnionInput> {
  return useMutation({ mutationFn: postOp<GisUnionInput, GisUnionResult>('/api/v1/gis/union'), retry: false });
}

/** POST /api/v1/gis/split — ST_Split(geom, blade) ⇒ أجزاء dry-run. */
export function useGisSplit(): UseMutationResult<GisSplitResult, unknown, GisSplitInput> {
  return useMutation({ mutationFn: postOp<GisSplitInput, GisSplitResult>('/api/v1/gis/split'), retry: false });
}

/** POST /api/v1/gis/validate — ST_IsValid + ST_MakeValid dry-run. */
export function useGisValidate(): UseMutationResult<GisValidateResult, unknown, GisValidateInput> {
  return useMutation({ mutationFn: postOp<GisValidateInput, GisValidateResult>('/api/v1/gis/validate'), retry: false });
}

// ─── التحكيم الزمني ─────────────────────────────────────────────────

export interface TemporalMeasurementInput {
  source: string; // قيمة DataSource (ndvi_sentinel, weather_eto, …)
  timestamp: string; // ISO
  value?: number | null;
}
export interface TemporalCheckInput {
  measurements: TemporalMeasurementInput[];
  crop?: string | null;
  stage?: string | null;
}
export interface CoherenceInput {
  current_date: string; // YYYY-MM-DD
  planting_date?: string | null;
  gdd_days_counted?: number | null;
}

/** POST /api/v1/temporal/check — اتّساق زمني للقراءات المُجمَّعة. */
export function useTemporalCheck(): UseMutationResult<TemporalCheckResult, unknown, TemporalCheckInput> {
  return useMutation({ mutationFn: postOp<TemporalCheckInput, TemporalCheckResult>('/api/v1/temporal/check'), retry: false });
}

/** POST /api/v1/temporal/coherence — مرجع زمني موحّد + كشف الانحراف الدلالي. */
export function useTemporalCoherence(): UseMutationResult<CoherenceResult, unknown, CoherenceInput> {
  return useMutation({ mutationFn: postOp<CoherenceInput, CoherenceResult>('/api/v1/temporal/coherence'), retry: false });
}

// ─── محاكاة ماذا-لو (WOFOST) — مرتبطة بحقل ─────────────────────────

export interface WhatIfInput {
  field_id: string;
  crop?: string;
  lat?: number | null;
  lon?: number | null;
  soil_type?: string;
  planting_date?: string | null;
  scenario?: string; // reduce_irrigation | no_irrigation
}

/** POST /api/v1/simulate/what-if — أثر سيناريو على المحصول والماء (ثقيل ⇒ عند الطلب). */
export function useSimulateWhatIf(): UseMutationResult<WhatIfResult, unknown, WhatIfInput> {
  return useMutation({ mutationFn: postOp<WhatIfInput, WhatIfResult>('/api/v1/simulate/what-if'), retry: false });
}

// ─── مخاطر المرحلة الموسميّة — GET (قراءة رخيصة مُفهرَسة) ─────────────

/** GET /api/v1/seasonal-risk/stage-check — مخاطر مرحلة نموّ في إقليم. */
export function useStageRiskCheck(
  zone: string | null,
  stageAr: string | null,
  enabled = true,
): UseQueryResult<StageCheckResult> {
  return useQuery<StageCheckResult>({
    queryKey: ['seasonal-risk-stage-check', zone ?? 'none', stageAr ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/seasonal-risk/stage-check', { params: { zone, stage_ar: stageAr } })
      .then((r) => r.data as StageCheckResult)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 30 * 60_000,
    enabled: enabled && !!zone?.trim() && !!stageAr?.trim(),
    retry: false,
  });
}

// ─── إعادة البناء من الأحداث ────────────────────────────────────────

export interface ReplayInput {
  entity_type: string;
  entity_id: string;
  events: Array<Record<string, unknown>>; // [{event_type, occurred_at, payload}, …]
}

/** POST /api/v1/replay/reconstruct — إعادة بناء حالة الكيان من سجلّ الأحداث. */
export function useReplayReconstruct(): UseMutationResult<ReplayStateResult, unknown, ReplayInput> {
  return useMutation({ mutationFn: postOp<ReplayInput, ReplayStateResult>('/api/v1/replay/reconstruct'), retry: false });
}

// ─── رابط النَّسَب (محروس بـFEATURE_UNIFIED_LINEAGE) — كتابة ──────────

export interface LineageLinkInput {
  ref_type: string; // decision | dispatch | command | execution | outcome
  ref_id: string;
  lineage_id?: string | null; // يُسَكّ إن غاب
}
export interface LineageLinkResult {
  disabled?: boolean;
  lineage_id?: string;
  ref_type?: string;
  ref_id?: string;
  linked_by?: string;
}

/** POST /api/v1/lineage/link — يربط مرجعاً بمعرّف نَسَب عالميّ موحّد (INSERT + حدث). */
export function useLineageLink(): UseMutationResult<LineageLinkResult, unknown, LineageLinkInput> {
  return useMutation({ mutationFn: postOp<LineageLinkInput, LineageLinkResult>('/api/v1/lineage/link'), retry: false });
}

// ─── تحليل التجارب الحقليّة ─────────────────────────────────────────

export interface TrialBlockInput {
  block_number: number;
  treatment_yield: number;
  control_yield: number;
}
export interface TrialAnalysisInput {
  blocks: TrialBlockInput[];
  confidence_level?: number;
  treatment_label_ar?: string;
}

/** POST /api/v1/trials/analyze — t-test مزدوج + LSD وحُكم صادق. */
export function useTrialAnalyze(): UseMutationResult<TrialVerdictResult, unknown, TrialAnalysisInput> {
  return useMutation({ mutationFn: postOp<TrialAnalysisInput, TrialVerdictResult>('/api/v1/trials/analyze'), retry: false });
}
