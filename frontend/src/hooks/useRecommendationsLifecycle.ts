// Recommendations Lifecycle hooks — ربط حيّ بنقاط P0 اليتيمة في
// services/sahool-platform/api/routers/recommendations.py (UI_DEBT_MAP):
//   GET  /api/v1/recommendations/engines             (كتالوج المحرّكات + السياسة الفعليّة)
//   GET  /api/v1/recommendations/capacity-profiles   (طبقات القدرة — مرجع شفّاف)
//   POST /api/v1/recommendations/candidates          (بدائل مُقيَّمة حسب الهدف)
//   POST /api/v1/recommendations/economic-adaptation (تكييف الخيارات حسب القدرة)
//   POST /api/v1/recommendations/outcomes            (تسجيل نتيجة — مسار كتابة v49)
// نفس نمط useApi.ts: عميل kongApi (البوّابة) + التقاط 404 وتحويله إلى حالة
// «غير مُفعَّل» صادقة (disabled) بدل خطأ مُفزِع؛ باقي الأخطاء تُرفَع كما هي.

import { useMutation, useQuery, UseMutationResult, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  CandidatesResponse, CapacityProfilesResponse, CropCandidateBody,
  EconomicAdaptationResponse, EnginesResponse, OutcomeRecordInput, OutcomeRecordResult,
} from '../lib/recommendationsLifecycle';

// نفس منطق useApi.ts (غير مُصدَّر هناك — يُعاد تعريفه محليّاً بلا تعديل ملفّ قائم).
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** هل خطأ الطفرة 404 (المسار غير مُفعَّل/غير منشور)؟ للعرض الصادق «غير مُفعَّل». */
export function isRecommendationsDisabled(e: unknown): boolean {
  return isDisabled404(e);
}

/** كتالوج محرّكات التوصيات + السياسة الفعليّة لهذا المستأجِر (قراءة فقط). */
export function useRecommendationEngines(enabled = true): UseQueryResult<EnginesResponse> {
  return useQuery<EnginesResponse>({
    queryKey: ['recommendations', 'engines'],
    queryFn: () => kongApi
      .get('/api/v1/recommendations/engines')
      .then((r) => r.data as EnginesResponse)
      .catch((e) => {
        if (isDisabled404(e)) return { engines: [], policy: null, effective_enabled: [], disabled: true };
        throw e;
      }),
    staleTime: 15 * 60_000,
    enabled,
    retry: false,
  });
}

/** ملفّات طبقات القدرة الاقتصاديّة — مرجع ثابت شفّاف ⇒ staleTime طويل. */
export function useCapacityProfiles(enabled = true): UseQueryResult<CapacityProfilesResponse> {
  return useQuery<CapacityProfilesResponse>({
    queryKey: ['recommendations', 'capacity-profiles'],
    queryFn: () => kongApi
      .get('/api/v1/recommendations/capacity-profiles')
      .then((r) => r.data as CapacityProfilesResponse)
      .catch((e) => {
        if (isDisabled404(e)) return { tiers: [], disabled: true };
        throw e;
      }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** توليد بدائل مُقيَّمة حسب هدف المزارع — طفرة (حساب على الخادم، لا كتابة دائمة).
 *  الجسم مصفوفة الخيارات نفسها؛ goal/top_n بارامترا استعلام (شكل FastAPI الفعليّ). */
export function useGenerateCandidates(): UseMutationResult<
  CandidatesResponse, Error, { candidates: CropCandidateBody[]; goal: string; topN?: number }
> {
  return useMutation({
    mutationFn: ({ candidates, goal, topN = 3 }) => kongApi
      .post('/api/v1/recommendations/candidates', candidates, { params: { goal, top_n: topN } })
      .then((r) => r.data as CandidatesResponse),
  });
}

/** تكييف خيارات المحاصيل حسب القدرة الاقتصاديّة — اقتراح متدرّج لا فرض.
 *  الجسم مصفوفة الخيارات؛ area_ha/annual_revenue_usd بارامترا استعلام اختياريّان. */
export function useEconomicAdaptation(): UseMutationResult<
  EconomicAdaptationResponse, Error,
  { cropOptions: Record<string, unknown>[]; areaHa?: number | null; annualRevenueUsd?: number | null }
> {
  return useMutation({
    mutationFn: ({ cropOptions, areaHa, annualRevenueUsd }) => kongApi
      .post('/api/v1/recommendations/economic-adaptation', cropOptions, {
        params: {
          area_ha: areaHa ?? undefined,
          annual_revenue_usd: annualRevenueUsd ?? undefined,
        },
      })
      .then((r) => r.data as EconomicAdaptationResponse),
  });
}

/** تسجيل نتيجة توصية (201) — مسار الكتابة لحلقة التعلّم. صدق: يسجَّل المُرسَل فقط؛
 *  النتيجة مجهولة حتى تُقاس. الخادم يدعم Idempotency-Key؛ إن غاب فالتنفيذ عاديّ. */
export function useRecordRecommendationOutcome(): UseMutationResult<
  OutcomeRecordResult, Error, OutcomeRecordInput
> {
  return useMutation({
    mutationFn: (input) => kongApi
      .post('/api/v1/recommendations/outcomes', input)
      .then((r) => r.data as OutcomeRecordResult),
  });
}
