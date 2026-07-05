// useSpecialtyCrops — هوكات react-query لنقاط backend اليتيمة (P2): قوائم المحاصيل
// المتخصّصة (عالية القيمة/متخصّصة تصديريّة/عطريّة/أعلاف بديلة) + بطاقة الإدخال
// وفحص ملاءمة الحقل + تخطيط البستان المختلط واقتصادياته + التوقيت الفلكي/الثقافي/
// الإقليمي (نجوم/تحقّق متقاطع/تقويم ثقافي/تقويم إقليمي).
//
// الأعراف مطابقة لـ useIrrigationDecisionAids.ts: kongApi عبر البوّابة (/api/v1/*)،
// retry:false لحالة صادقة عند الفشل، staleTime طويل للمعرفة المرجعيّة الثابتة،
// وPOST داخل queryFn (سابقة useFieldChange) لأنّ field-fit/cross-check حسابات قراءة
// نقيّة لا كتابات (رغم أنّهما POST مصادَقان على الخادم).
// 404 ⇒ {disabled:true} — نفس عرف isDisabled404 في useApi.ts: حالة «غير مُفعَّل»
// صادقة بدل خطأ مُفزِع؛ باقي الأخطاء (401/403/5xx) تُرفَع كما هي لتعرضها الواجهة.

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  AromaticCropsListResponse,
  CalendarStarsResponse,
  CrossCheckInput,
  CrossCheckResponse,
  CulturalCalendarResponse,
  FieldFitInput,
  FieldFitResponse,
  FodderAlternativesListResponse,
  HighValueCropsListResponse,
  IntroductionCardResponse,
  NicheCropsListResponse,
  OrchardEconomicsResponse,
  OrchardPlanResponse,
  RegionalCalendarResponse,
} from '../lib/specialtyCrops';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

/** محاصيل عالية القيمة مصنّفة بصدق حسب ملاءمة الجوف — GET /api/v1/high-value-crops/list.
 *  معرفة مرجعيّة ثابتة ⇒ staleTime طويل. */
export function useHighValueCropsList(enabled = true): UseQueryResult<HighValueCropsListResponse> {
  return useQuery<HighValueCropsListResponse>({
    queryKey: ['high-value-crops-list'],
    queryFn: () => kongApi
      .get('/api/v1/high-value-crops/list')
      .then((r) => r.data as HighValueCropsListResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** منتجات تصديريّة متخصّصة (صمغ/توابل/أصباغ) — GET /api/v1/niche-crops/list. */
export function useNicheCropsList(enabled = true): UseQueryResult<NicheCropsListResponse> {
  return useQuery<NicheCropsListResponse>({
    queryKey: ['niche-crops-list'],
    queryFn: () => kongApi
      .get('/api/v1/niche-crops/list')
      .then((r) => r.data as NicheCropsListResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** نباتات عطريّة/زيوت أساسيّة متحمّلة للجفاف — GET /api/v1/aromatic-crops/list. */
export function useAromaticCropsList(enabled = true): UseQueryResult<AromaticCropsListResponse> {
  return useQuery<AromaticCropsListResponse>({
    queryKey: ['aromatic-crops-list'],
    queryFn: () => kongApi
      .get('/api/v1/aromatic-crops/list')
      .then((r) => r.data as AromaticCropsListResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** أعلاف موفّرة للماء بديلة للبرسيم المستنزف — GET /api/v1/fodder-alternatives/list. */
export function useFodderAlternativesList(enabled = true): UseQueryResult<FodderAlternativesListResponse> {
  return useQuery<FodderAlternativesListResponse>({
    queryKey: ['fodder-alternatives-list'],
    queryFn: () => kongApi
      .get('/api/v1/fodder-alternatives/list')
      .then((r) => r.data as FodderAlternativesListResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** البطاقة التعريفيّة لمحصول/شجرة مرشّحة للإدخال — GET /api/v1/introduction/card.
 *  لا يُستدعى بلا اسم محصول يؤكّده المستخدم (لا نعتمد افتراض الخادم ضمنيّاً). */
export function useIntroductionCard(
  crop: string | null,
  enabled = true,
): UseQueryResult<IntroductionCardResponse> {
  return useQuery<IntroductionCardResponse>({
    queryKey: ['introduction-card', crop ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/introduction/card', { params: { crop } })
      .then((r) => r.data as IntroductionCardResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && !!crop,
    retry: false,
  });
}

/** فحص آلي لملاءمة تربة/ظروف الحقل لمحصول إدخال — POST /api/v1/introduction/field-fit.
 *  مصادَق على الخادم؛ لا يُستدعى بلا مدخلات كاملة (المحصول + pH + الملوحة قياسات
 *  يُدخِلها المستخدم — لا تخمين). الحكم (rating_ar) من الخادم لا الواجهة. */
export function useIntroductionFieldFit(
  input: FieldFitInput | null,
): UseQueryResult<FieldFitResponse> {
  return useQuery<FieldFitResponse>({
    queryKey: [
      'introduction-field-fit',
      input?.crop ?? 'none',
      input?.ph ?? 'none',
      input?.ec_dsm ?? 'none',
      input?.season_rain_mm ?? 'none',
      input?.temp_mean_c ?? 'none',
      input?.irrigated ?? true,
    ],
    queryFn: () => kongApi
      .post('/api/v1/introduction/field-fit', input)
      .then((r) => r.data as FieldFitResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** تخطيط بستان مختلط صحراوي (توزيع + كثافة + جدول عائد) — GET /api/v1/orchard/plan.
 *  المساحة قياس يُدخِله المستخدم (لا تخمين ⇒ لا استدعاء بلا مساحة موجبة). */
export function useOrchardPlan(
  areaHa: number | null,
  enabled = true,
): UseQueryResult<OrchardPlanResponse> {
  return useQuery<OrchardPlanResponse>({
    queryKey: ['orchard-plan', areaHa ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/orchard/plan', { params: { area_ha: areaHa } })
      .then((r) => r.data as OrchardPlanResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && areaHa != null && areaHa > 0,
    retry: false,
  });
}

/** ملاحظات اقتصاديّة تقديريّة للبستان (سيناريو لا وعد) — GET /api/v1/orchard/economics. */
export function useOrchardEconomics(
  areaHa: number | null,
  enabled = true,
): UseQueryResult<OrchardEconomicsResponse> {
  return useQuery<OrchardEconomicsResponse>({
    queryKey: ['orchard-economics', areaHa ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/orchard/economics', { params: { area_ha: areaHa } })
      .then((r) => r.data as OrchardEconomicsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled: enabled && areaHa != null && areaHa > 0,
    retry: false,
  });
}

/** نجوم التقويم الزراعي العربي كمرساة موسميّة رصديّة — GET /api/v1/astronomical-timing/stars.
 *  رصدي لا تنجيمي (is_astrological=false من الخادم) — معرفة ثابتة ⇒ staleTime طويل. */
export function useCalendarStars(enabled = true): UseQueryResult<CalendarStarsResponse> {
  return useQuery<CalendarStarsResponse>({
    queryKey: ['astronomical-stars'],
    queryFn: () => kongApi
      .get('/api/v1/astronomical-timing/stars')
      .then((r) => r.data as CalendarStarsResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** تحقّق متقاطع: المرساة الفلكيّة مقابل مرحلة GDD — POST /api/v1/astronomical-timing/cross-check.
 *  مصادَق على الخادم؛ التاريخ قياس يُدخِله المستخدم (لا تخمين). النصّ (agreement_ar)
 *  من الخادم حرفيّاً. لا يُستدعى بلا تاريخ. */
export function useAstronomicalCrossCheck(
  input: CrossCheckInput | null,
): UseQueryResult<CrossCheckResponse> {
  return useQuery<CrossCheckResponse>({
    queryKey: [
      'astronomical-cross-check',
      input?.current_date ?? 'none',
      input?.gdd_stage ?? 'none',
      input?.anchor ?? 'suhail_rising',
    ],
    queryFn: () => kongApi
      .post('/api/v1/astronomical-timing/cross-check', input)
      .then((r) => r.data as CrossCheckResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled: !!input,
    retry: false,
  });
}

/** التقويم الثقافي التراثي (عرض فقط — خارج محرّك القرار) — GET /api/v1/cultural-calendar. */
export function useCulturalCalendar(
  governorate: string | null,
  enabled = true,
): UseQueryResult<CulturalCalendarResponse> {
  return useQuery<CulturalCalendarResponse>({
    queryKey: ['cultural-calendar', governorate ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/cultural-calendar', {
        params: { governorate: governorate || undefined },
      })
      .then((r) => r.data as CulturalCalendarResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** التقويم الزراعي الإقليمي للمحافظة (حِميري/حضرمي) — GET /api/v1/regional-calendar.
 *  محافظة غير مطابقة ⇒ matched=false + المتاح (لا خطأ). */
export function useRegionalCalendar(
  governorate: string | null,
  enabled = true,
): UseQueryResult<RegionalCalendarResponse> {
  return useQuery<RegionalCalendarResponse>({
    queryKey: ['regional-calendar', governorate ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/regional-calendar', {
        params: { governorate: governorate || undefined },
      })
      .then((r) => r.data as RegionalCalendarResponse)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}
