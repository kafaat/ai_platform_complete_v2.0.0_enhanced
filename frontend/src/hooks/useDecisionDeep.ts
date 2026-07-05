// useDecisionDeep — هوكات نقاط القرار العميقة اليتيمة (P0 في UI_DEBT_MAP).
// نفس اصطلاحات useApi.ts حرفيّاً: kongApi عبر البوّابة، مفاتيح react-query
// ثابتة، retry:false، و404 على النقاط المحروسة بعلم SAHOOL_DECISION_DISPATCH
// يتحوّل إلى حالة {disabled:true} صادقة (isDisabled404) بدل خطأ مُفزِع —
// النقاط الأخرى (for-location/explain/record) غير محروسة بعلم فيمرّ خطؤها كما هو.
// ملفّ جديد (لا تعديل على useApi.ts) — قرار شريحة P0 لتفادي تضخيم الملفّ القائم.
import {
  useMutation, useQuery, useQueryClient, UseQueryResult,
} from '@tanstack/react-query';
import { kongApi } from '../services/api';
import {
  isFeatureDisabled404,
  type DecisionEconomicsResult,
  type DecisionExplainDeepResult,
  type DecisionForLocationResult,
  type DecisionRecordInput,
  type DecisionRecordResult,
  type DispatchExecuteInput,
  type DispatchExecuteResult,
  type ForLocationParams,
  type PolicyResolveInput,
  type PolicyResolveResult,
  type UnifiedDecisionInput,
  type UnifiedDecisionResult,
} from '../lib/decisionDeep';

/** القرار الزراعيّ المتكامل من موقع (GET /api/v1/decision/for-location).
 *  غير محروس بعلم — supported=false تأتي من الخادم بسبب صريح (لا 404 هنا). */
export function useDecisionForLocation(
  params: ForLocationParams | null,
): UseQueryResult<DecisionForLocationResult> {
  return useQuery<DecisionForLocationResult>({
    // المعاملات كلّها في المفتاح: تغيير أيّ مدخل يُبطل الكاش ويعيد الجلب.
    queryKey: ['decision-for-location', params ?? 'none'],
    queryFn:  () => kongApi
      .get('/api/v1/decision/for-location', { params: params ?? {} })
      .then(r => r.data as DecisionForLocationResult),
    staleTime: 10 * 60_000,
    enabled:   !!params,
    retry:     false,
  });
}

/** شرح القرار بلغة طبيعيّة (GET /api/v1/decision/explain) — نفس معاملات
 *  for-location؛ الشرح يُعرَض حرفيّاً (explanation_ar) مع مصدره وتنويهه. */
export function useDecisionExplainDeep(
  params: ForLocationParams | null,
): UseQueryResult<DecisionExplainDeepResult> {
  return useQuery<DecisionExplainDeepResult>({
    queryKey: ['decision-explain-deep', params ?? 'none'],
    queryFn:  () => kongApi
      .get('/api/v1/decision/explain', { params: params ?? {} })
      .then(r => r.data as DecisionExplainDeepResult),
    staleTime: 10 * 60_000,
    enabled:   !!params,
    retry:     false,
  });
}

/** الترجمة الاقتصاديّة للأثر (GET /api/v1/decision/economics — خلف
 *  SAHOOL_DECISION_DISPATCH: 404 ⇒ {disabled:true} صادقة). الحجم/القيمة
 *  يحسبهما الخادم فقط مع المساحة/التكلفة — وإلّا null + notes_ar صريحة. */
export function useDecisionEconomics(
  opts: { areaHa?: number; waterCostPerM3?: number; currency?: string; fieldId?: string } = {},
  enabled = true,
): UseQueryResult<DecisionEconomicsResult> {
  const { areaHa, waterCostPerM3, currency, fieldId } = opts;
  return useQuery<DecisionEconomicsResult>({
    queryKey: ['decision-economics', fieldId ?? 'all', areaHa ?? 'none', waterCostPerM3 ?? 'none', currency ?? 'YER'],
    queryFn:  () => kongApi
      .get('/api/v1/decision/economics', {
        params: {
          field_id: fieldId || undefined,
          area_ha: areaHa,
          water_cost_per_m3: waterCostPerM3,
          currency: currency || undefined,
        },
      })
      .then(r => r.data as DecisionEconomicsResult)
      .catch((e) => {
        if (isFeatureDisabled404(e)) {
          // العلم مُطفأ ⇒ حالة صادقة لا اختلاق أرقام (نفس نمط useDispatchQueue).
          return {
            currency: currency ?? 'YER', executed_decisions: 0, success_rate: 0,
            water_saved_mm: 0, water_saved_m3: null, water_cost_avoided: null,
            notes_ar: null, disabled: true,
          } satisfies DecisionEconomicsResult;
        }
        throw e;
      }),
    staleTime: 60_000,
    enabled,
    retry:     false,
  });
}

/** المصالحة الموحّدة (POST /api/v1/decision/unified) — dry-run من الخادم
 *  (dry_run=true)، لا تنفيذ ولا كتابة. 404 ⇒ العلم مُطفأ (يفحصه المكوّن). */
export function useUnifiedDecision(): ReturnType<typeof useMutation<UnifiedDecisionResult, Error, UnifiedDecisionInput>> {
  return useMutation<UnifiedDecisionResult, Error, UnifiedDecisionInput>({
    mutationFn: (input) => kongApi.post('/api/v1/decision/unified', input).then(r => r.data),
  });
}

/** استشارة السياسات (POST /api/v1/decision/policies/resolve) — نقيّة (dry-run):
 *  أيّ أثر حوكمة ينطبق على السياق؟ لا كتابة. 404 ⇒ العلم مُطفأ. */
export function useResolveDecisionPolicies(): ReturnType<typeof useMutation<PolicyResolveResult, Error, PolicyResolveInput>> {
  return useMutation<PolicyResolveResult, Error, PolicyResolveInput>({
    mutationFn: (input) => kongApi.post('/api/v1/decision/policies/resolve', input).then(r => r.data),
  });
}

/** إدامة رأس قرار (POST /api/v1/decision/record) — تسجيل للتدقيق/النَّسَب فقط،
 *  لا تنفيذ ولا نتيجة مُختلقة. يُبطل كاش سجلّ القرارات ليظهر المُدام حيّاً. */
export function useRecordDecision(): ReturnType<typeof useMutation<DecisionRecordResult, Error, DecisionRecordInput>> {
  const qc = useQueryClient();
  return useMutation<DecisionRecordResult, Error, DecisionRecordInput>({
    mutationFn: (input) => kongApi.post('/api/v1/decision/record', input).then(r => r.data),
    onSuccess: () => {
      // سجلّ القرارات المُدامة (DecisionInsightPanel) يقرأ decision-records.
      qc.invalidateQueries({ queryKey: ['decision-records'] });
    },
  });
}

/** التنفيذ المحروس (POST /api/v1/decision/dispatch/execute): حواجز ← تقييم ←
 *  إدامة (تدقيق) + إدراج READY فقط في طابور المُشغِّل — لا إطلاق MQTT من هنا.
 *  BLOCKED/PENDING يُسجَّل not_executed ولا يُنفَّذ (حكم الخادم يُعرَض حرفيّاً).
 *  يُبطل كاش الطابور/القرارات ليعكس الإدراج فوراً. */
export function useExecuteDispatch(): ReturnType<typeof useMutation<DispatchExecuteResult, Error, DispatchExecuteInput>> {
  const qc = useQueryClient();
  return useMutation<DispatchExecuteResult, Error, DispatchExecuteInput>({
    mutationFn: (input) => kongApi.post('/api/v1/decision/dispatch/execute', input).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dispatch-queue'] });
      qc.invalidateQueries({ queryKey: ['dispatch-decisions'] });
    },
  });
}
