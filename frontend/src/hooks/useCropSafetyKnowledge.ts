// useCropSafetyKnowledge — هوكات react-query لنقاط backend اليتيمة (P1):
// فحص السلامة الكيميائيّة + المحظورات + تقويم الزراعة (محاصيل/نافذة) +
// آفات ما بعد الحصاد + تفصيل المحاصيل عالية القيمة/المتخصّصة + مرشّحي الإدخال.
//
// الأعراف مطابقة لـ useIrrigationDecisionAids.ts: kongApi عبر البوّابة (/api/v1/*)،
// retry:false لحالة صادقة عند الفشل، staleTime طويل للمعرفة المرجعيّة الثابتة،
// وPOST داخل queryFn (سابقة useFieldChange) لأنّ فحص المادّة قراءة نقيّة لا كتابة.
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404: حالة «غير مُفعَّل» صادقة بدل
// خطأ مُفزِع؛ باقي الأخطاء (401/403/5xx) تُرفَع كما هي لتعرضها الواجهة.

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  BannedChemicalsResponse,
  ChemicalCheckInput,
  ChemicalCheckResponse,
  HighValueCropDetailResponse,
  IntroductionCandidatesResponse,
  NicheCropDetailResponse,
  PlantingCropsResponse,
  PlantingWindowResponse,
  StoragePestsResponse,
} from '../lib/cropSafetyKnowledge';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** فحص مادّة كيميائيّة ضدّ الحظر والجرعة — POST /api/v1/chemical-safety/check.
 *  سلامة حرجة: لا يُستدعى إلّا باسم مادّة أكّده المستخدم (زرّ فحص، لا كتابة حيّة)
 *  والحكم يُعرَض من الخادم حرفيّاً — لا إعادة حكم في الواجهة. */
export function useChemicalSafetyCheck(
  input: ChemicalCheckInput | null,
): UseQueryResult<ChemicalCheckResponse> {
  return useQuery<ChemicalCheckResponse>({
    queryKey: ['chemical-safety-check', input?.chemical ?? 'none', input?.dose_kg_ha ?? 'none'],
    queryFn: () => kongApi
      .post('/api/v1/chemical-safety/check', input)
      .then((r) => r.data as ChemicalCheckResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** قائمة المحظورات الدوليّة (شفافيّة) — GET /api/v1/chemical-safety/banned.
 *  معرفة مرجعيّة ثابتة ⇒ staleTime طويل. */
export function useBannedChemicals(enabled = true): UseQueryResult<BannedChemicalsResponse> {
  return useQuery<BannedChemicalsResponse>({
    queryKey: ['chemical-safety-banned'],
    queryFn: () => kongApi
      .get('/api/v1/chemical-safety/banned')
      .then((r) => r.data as BannedChemicalsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** المحاصيل المدعومة بتقويم مواعيد الزراعة — GET /api/v1/planting/crops. */
export function usePlantingCrops(enabled = true): UseQueryResult<PlantingCropsResponse> {
  return useQuery<PlantingCropsResponse>({
    queryKey: ['planting-crops'],
    queryFn: () => kongApi
      .get('/api/v1/planting/crops')
      .then((r) => r.data as PlantingCropsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** نافذة الزراعة المثلى + مخاطر التبكير/التأخير — GET /api/v1/planting/window.
 *  لا يُستدعى بلا محصول يختاره المستخدم (لا نعتمد افتراض الخادم wheat ضمنيّاً). */
export function usePlantingWindow(
  crop: string | null,
  enabled = true,
): UseQueryResult<PlantingWindowResponse> {
  return useQuery<PlantingWindowResponse>({
    queryKey: ['planting-window', crop ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/planting/window', { params: { crop } })
      .then((r) => r.data as PlantingWindowResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!crop,
    retry: false,
  });
}

/** الآفات المخزنيّة الرئيسيّة للحبوب — GET /api/v1/postharvest/pests. */
export function usePostharvestPests(enabled = true): UseQueryResult<StoragePestsResponse> {
  return useQuery<StoragePestsResponse>({
    queryKey: ['postharvest-pests'],
    queryFn: () => kongApi
      .get('/api/v1/postharvest/pests')
      .then((r) => r.data as StoragePestsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** تفصيل محصول عالي القيمة (بالاسم العربي — مطابقة جزئيّة عند الخادم) —
 *  GET /api/v1/high-value-crops/detail. لا يُستدعى بلا اسم يؤكّده المستخدم. */
export function useHighValueCropDetail(
  cropAr: string | null,
  enabled = true,
): UseQueryResult<HighValueCropDetailResponse> {
  return useQuery<HighValueCropDetailResponse>({
    queryKey: ['high-value-crop-detail', cropAr ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/high-value-crops/detail', { params: { crop_ar: cropAr } })
      .then((r) => r.data as HighValueCropDetailResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!cropAr,
    retry: false,
  });
}

/** تفصيل منتج تصديري متخصّص + ميزته اليمنيّة — GET /api/v1/niche-crops/detail. */
export function useNicheCropDetail(
  cropAr: string | null,
  enabled = true,
): UseQueryResult<NicheCropDetailResponse> {
  return useQuery<NicheCropDetailResponse>({
    queryKey: ['niche-crop-detail', cropAr ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/niche-crops/detail', { params: { crop_ar: cropAr } })
      .then((r) => r.data as NicheCropDetailResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!cropAr,
    retry: false,
  });
}

/** مرشّحو الإدخال حسب المنطقة — GET /api/v1/introduction/candidates.
 *  zone=all ⇒ بلا مُعامل (الخادم يعيد الكلّ). */
export function useIntroductionCandidates(
  zone: string,
  enabled = true,
): UseQueryResult<IntroductionCandidatesResponse> {
  return useQuery<IntroductionCandidatesResponse>({
    queryKey: ['introduction-candidates', zone],
    queryFn: () => kongApi
      .get('/api/v1/introduction/candidates', {
        params: { zone: zone !== 'all' ? zone : undefined },
      })
      .then((r) => r.data as IntroductionCandidatesResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}
