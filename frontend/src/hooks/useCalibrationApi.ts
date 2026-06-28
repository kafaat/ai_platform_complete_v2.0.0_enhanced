// SAHOOL v9.0 — src/hooks/useCalibrationApi.ts — هوكات المعايرة (مقتطعة من useApi.ts)
// نقل حرفيّ سلوكيّاً-محايد لمنضدة المعايرة (Calibration Workbench) + حالة المعايرة
// الإقليميّة من useApi.ts. وحدة دومين ورقيّة: تستورد دوال/أنواع الخدمة من
// ../services/api ومتجر المصادقة فقط (لا اعتماد دائريّ على useApi.ts). يُعاد تصديرها
// من useApi.ts (export *) للحفاظ على كلّ `import { … } from '.../hooks/useApi'` القائمة
// — بما فيها تجسّس الاختبار `vi.spyOn(useApiModule, 'useCalibration…')`.
import { useQuery, useMutation, useQueryClient, UseQueryResult, UseMutationResult } from '@tanstack/react-query';
import {
  fetchCalibration, type CalibrationOverview,
  fetchRegionCalibration, fetchResolvedCalibration,
  type CalibrationProfile, type ResolvedCalibration,
  proposeCalibrationValues, setRegionOverride, deleteRegionOverride, applyAdaptFromEvidence,
  fetchCalibrationOverrides, fetchCalibrationAudit,
  type CalibrationValuesInput, type CalibrationValidation,
  type CalibrationOverrideResult, type AdaptApplyResult, type AdaptApplyInput,
  type CalibrationOverridesResult, type CalibrationAudit,
} from '../services/api';
import { useAuthStore } from './useAuth';

// حالة المعايرة الإقليميّة (GET /api/v1/calibration) — قراءة فقط. تكشف لكلّ إقليم
// هل ثوابته الأغرونوميّة مُتحقَّق منها ميدانيّاً أم ما تزال افتراضات FAO عامّة. ثابتة
// نسبيّاً (تتغيّر مع جمع بيانات ميدانيّة) ⇒ staleTime طويل. لا fallback وهميّ.
export function useCalibration(): UseQueryResult<CalibrationOverview, Error> {
  return useQuery<CalibrationOverview, Error>({
    queryKey: ['calibration'],
    queryFn:  () => fetchCalibration(),
    staleTime:60 * 60_000,
    retry:    false,
  });
}

// ── منضدة المعايرة (Calibration Workbench) — مقارنة القاعدة بالمُدام + اقتراح/موافقة/رفض/تدقيق ──
// كلّها معزولة بالمستأجِر خادميّاً (RLS). مُفتاح الكاش بالمنطقة. لا fallback وهميّ:
// الخطأ (503 DB / 403 RBAC) يُرفض الاستعلام لتعرض المنضدة حالة صادقة. retry:false.

// القاعدة الموروثة لمنطقة (GET /{region}) — مرجع المقارنة. ثابتة نسبيّاً.
export function useRegionCalibration(region?: string): UseQueryResult<CalibrationProfile, Error> {
  const r = (region ?? '').trim();
  return useQuery<CalibrationProfile, Error>({
    queryKey: ['calibration-base', r],
    queryFn:  () => fetchRegionCalibration(r),
    staleTime:60 * 60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// الملفّ المُحلّ مع التجاوز المُدام (GET /{region}/resolved) — الطرف الآخر للمقارنة.
// staleTime قصير (يتغيّر مع الإدامة/الحذف) ⇒ يُعاد جلبه فور الإبطال بعد الكتابة.
export function useResolvedCalibration(region?: string): UseQueryResult<ResolvedCalibration, Error> {
  const r = (region ?? '').trim();
  return useQuery<ResolvedCalibration, Error>({
    queryKey: ['calibration-resolved', r],
    queryFn:  () => fetchResolvedCalibration(r),
    staleTime:60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// كلّ التجاوزات المُدامة للمستأجِر (GET /overrides/all) — مصدر التدقيق البديل + إدارة.
export function useCalibrationOverrides(): UseQueryResult<CalibrationOverridesResult, Error> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useQuery<CalibrationOverridesResult, Error>({
    queryKey: ['calibration-overrides', tid],
    queryFn:  () => fetchCalibrationOverrides(),
    staleTime:60_000,
    retry:    false,
  });
}

// سجلّ تدقيق منطقة (GET /{region}/audit) — أفضل-جهد: null عند 404/خطأ (النقطة قد
// لا تتوفّر) فترتدّ المنضدة إلى overrides/all. data=null حالةٌ صريحة لا خطأ.
export function useCalibrationAudit(region?: string): UseQueryResult<CalibrationAudit | null, Error> {
  const r = (region ?? '').trim();
  return useQuery<CalibrationAudit | null, Error>({
    queryKey: ['calibration-audit', r],
    queryFn:  () => fetchCalibrationAudit(r),
    staleTime:60_000,
    retry:    false,
    enabled:  !!r,
  });
}

// اقتراح/تحقّق (POST /{region}/propose-values) — يقترح ولا يكتب. طفرة بلا إبطال
// (لا تغيّر حالة مُدامة): تُعيد accepted/rejected لعرضها بأسباب عربيّة.
export function useProposeCalibrationValues(): UseMutationResult<
  CalibrationValidation, Error, { region: string; values: CalibrationValuesInput }
> {
  return useMutation<CalibrationValidation, Error, { region: string; values: CalibrationValuesInput }>({
    mutationFn: ({ region, values }) => proposeCalibrationValues(region, values),
  });
}

// موافقة/إدامة (POST /{region}/override) — يُبطِل القاعدة/المُحلّ/التجاوزات/التدقيق
// للمنطقة كي تظهر القيم المُعايَرة فوراً في المقارنة. الخطأ (422/503) يُرفع للنموذج.
export function useSetRegionOverride(): UseMutationResult<
  CalibrationOverrideResult, Error, { region: string; values: CalibrationValuesInput }
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<CalibrationOverrideResult, Error, { region: string; values: CalibrationValuesInput }>({
    mutationFn: ({ region, values }) => setRegionOverride(region, values),
    onSuccess:  (_d, { region }) => {
      qc.invalidateQueries({ queryKey: ['calibration-resolved', region] });
      qc.invalidateQueries({ queryKey: ['calibration-base', region] });
      qc.invalidateQueries({ queryKey: ['calibration-audit', region] });
      qc.invalidateQueries({ queryKey: ['calibration-overrides', tid] });
    },
  });
}

// رفض/عكس (DELETE /{region}/override) — يعيد المنطقة للوراثة ويُبطِل نفس المفاتيح.
export function useDeleteRegionOverride(): UseMutationResult<
  { region: string; reverted: boolean }, Error, string
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<{ region: string; reverted: boolean }, Error, string>({
    mutationFn: (region) => deleteRegionOverride(region),
    onSuccess:  (_d, region) => {
      qc.invalidateQueries({ queryKey: ['calibration-resolved', region] });
      qc.invalidateQueries({ queryKey: ['calibration-base', region] });
      qc.invalidateQueries({ queryKey: ['calibration-audit', region] });
      qc.invalidateQueries({ queryKey: ['calibration-overrides', tid] });
    },
  });
}

// تطبيق التكيّف بدليل مُدام (POST /{region}/adapt-from-evidence/apply, confirm=true).
// يُبطِل المفاتيح كالإدامة (قد يُدِيم تجاوزاً عند التأهّل). الخطأ (422/503) يُرفع.
export function useApplyAdaptFromEvidence(): UseMutationResult<
  AdaptApplyResult, Error, { region: string; input: AdaptApplyInput }
> {
  const qc  = useQueryClient();
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  return useMutation<AdaptApplyResult, Error, { region: string; input: AdaptApplyInput }>({
    mutationFn: ({ region, input }) => applyAdaptFromEvidence(region, input),
    onSuccess:  (_d, { region }) => {
      qc.invalidateQueries({ queryKey: ['calibration-resolved', region] });
      qc.invalidateQueries({ queryKey: ['calibration-base', region] });
      qc.invalidateQueries({ queryKey: ['calibration-audit', region] });
      qc.invalidateQueries({ queryKey: ['calibration-overrides', tid] });
    },
  });
}
