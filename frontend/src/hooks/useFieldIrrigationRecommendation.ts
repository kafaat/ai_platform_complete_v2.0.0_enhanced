// useFieldIrrigationRecommendation — قارئ واجهة حقيقيّ لنقطة WS-D.2:
//   POST /api/v1/fields/{field_id}/irrigation-recommendation
// تُعيد النقطةُ «مرشَّح توصية ريّ» واعياً بالاستنزاف (Dr) — لا مهمّة مُنفَّذة.
// ملكيّة القرار النهائيّ لخدمة القرار (recommendation_candidate → decision-service).
//
// الأعراف مطابقة لـ useFieldDriftRisk / useIrrigationDecisionAids: kongApi عبر
// البوّابة (/api/v1/*)، retry:false لحالة صادقة عند الفشل، والجسم = الطقس لحساب ET₀.
// صدق صارم: عقد الاستجابة اتّحادٌ مُميَّز على `status` — على المستهلِك أن يعالج
// insufficient_data / inconsistent_state ولا يتظاهر بوجود توصية حين recommendation=null.

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';

/** جسم POST — الطقس لحساب ET₀ (Hargreaves/Penman حسب المتوفّر). t_min/t_max إلزاميّان. */
export interface IrrigationRecommendationWeatherInput {
  t_min_c: number;
  t_max_c: number;
  solar_rad_mj_m2?: number;
  rh_mean_pct?: number;
  wind_2m_ms?: number;
  day_of_year?: number;
  root_depth_m?: number;
  /** مقبض السياسة (اسم سياسة الريّ عند الخادم) — يُمرَّر كما هو إن حُدِّد. */
  policy?: string;
}

/** مدخلات القرار كما يعيدها الخادم (مصدر كلّ قيمة مُعلَن — soil_lab مقابل texture_fallback). */
export interface IrrigationRecommendationInputs {
  depletion_mm: number | null;
  taw_mm: number;
  raw_fraction: number;
  depletion_fraction: number | null;
  taw_source: 'soil_lab' | 'texture_fallback' | string;
  ledger_age_hours: number | null;
  crop: string | null;
  stage: string;
}

export type WaterStressClass = 'normal' | 'watch' | 'critical' | null;
export type IrrigationUrgency = 'none' | 'low' | 'moderate' | 'high';

/** المرشَّح نفسه — يظهر فقط عند status === 'recommendation_ready'. */
export interface IrrigationRecommendationCandidate {
  should_irrigate: boolean | null;
  trigger_reason: string;
  net_irrigation_mm: number;
  target_refill_mm: number | null;
  water_stress_class: WaterStressClass;
  urgency: IrrigationUrgency;
  policy_knobs: Record<string, unknown>;
}

/** الحقول المشتركة عبر كلّ الحالات (الملكيّة/الحدود/الأدلّة دائماً حاضرة). */
interface IrrigationRecommendationBase {
  field_id: string;
  season_id: string | null;
  inputs: IrrigationRecommendationInputs;
  ownership: string; // 'recommendation_candidate → decision-service'
  confidence: number | null;
  evidence_ids: string[];
  limitations: string[];
  calibrated: false;
}

/** توصية جاهزة — recommendation كائن غير فارغ + generated_on حاضر. */
export interface IrrigationRecommendationReady extends IrrigationRecommendationBase {
  status: 'recommendation_ready';
  generated_on: string; // YYYY-MM-DD
  recommendation: IrrigationRecommendationCandidate;
}

/** استنزاف/بيانات ناقصة — لا توصية (recommendation=null)، الحدود تفسّر السبب. */
export interface IrrigationRecommendationInsufficient extends IrrigationRecommendationBase {
  status: 'insufficient_data';
  generated_on?: undefined;
  recommendation: null;
}

/** حالة غير متّسقة (مثل Dr>TAW) — لا توصية، لا أرقام مُلفّقة. */
export interface IrrigationRecommendationInconsistent extends IrrigationRecommendationBase {
  status: 'inconsistent_state';
  generated_on?: undefined;
  recommendation: null;
}

/** الاتّحاد المُميَّز — التمييز على `status` يُجبر المستهلِك على معالجة الحالات المتدهورة. */
export type IrrigationRecommendationResponse =
  | IrrigationRecommendationReady
  | IrrigationRecommendationInsufficient
  | IrrigationRecommendationInconsistent;

/** حارس نوع: هل الاستجابة توصية جاهزة فعلاً؟ (recommendation غير null). */
export function isRecommendationReady(
  resp: IrrigationRecommendationResponse | undefined,
): resp is IrrigationRecommendationReady {
  return resp?.status === 'recommendation_ready' && resp.recommendation != null;
}

export interface UseFieldIrrigationRecommendationResult {
  data: IrrigationRecommendationResponse | undefined;
  loading: boolean;
  error: unknown;
  refetch: UseQueryResult<IrrigationRecommendationResponse>['refetch'];
}

/** يطلب مرشَّح توصية الريّ الواعي بالاستنزاف لحقل (POST WS-D.2) — توصية لا تنفيذ.
 *  لا يُستدعى بلا fieldId ولا بلا حرارة صغرى/كبرى حقيقيّة (ET₀ لا يُحسَب بلا طقس).
 *  الخطأ يُرفَع (retry:false) لتعرض الواجهة حالة صادقة — لا مرشَّح مُلفّق. */
export function useFieldIrrigationRecommendation(
  fieldId: string | null | undefined,
  weather: IrrigationRecommendationWeatherInput | null,
  enabled = true,
): UseFieldIrrigationRecommendationResult {
  const q = useQuery<IrrigationRecommendationResponse>({
    queryKey: [
      'field-irrigation-recommendation',
      fieldId ?? 'none',
      weather?.t_min_c ?? 'none',
      weather?.t_max_c ?? 'none',
      weather?.solar_rad_mj_m2 ?? 'none',
      weather?.rh_mean_pct ?? 'none',
      weather?.wind_2m_ms ?? 'none',
      weather?.day_of_year ?? 'none',
      weather?.root_depth_m ?? 'none',
      weather?.policy ?? 'none',
    ],
    enabled: enabled && !!fieldId && !!weather,
    retry: false,
    staleTime: 10 * 60_000,
    queryFn: () =>
      kongApi
        .post(
          `/api/v1/fields/${encodeURIComponent(fieldId as string)}/irrigation-recommendation`,
          weather,
        )
        .then((r) => r.data as IrrigationRecommendationResponse),
  });

  return { data: q.data, loading: q.isLoading, error: q.isError ? q.error : null, refetch: q.refetch };
}
