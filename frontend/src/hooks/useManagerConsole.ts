// useManagerConsole — هوكات react-query لنقاط backend اليتيمة الموجَّهة للإدارة
// (P3). الأعراف مطابقة لـuseApi.ts وuseIrrigationDecisionAids.ts: kongApi عبر
// البوّابة (/api/v1/*)، retry:false لحالة صادقة عند الفشل، و404 ⇒ {disabled:true}
// (عرف isDisabled404) فتعرض الواجهة «غير مُفعَّل» بدل خطأ مُفزِع.
//
// القراءات useQuery (مُعطَّلة حتى تكتمل مدخلاتها — لا استدعاء بلا معطى)، والكتابات
// (POST) useMutation. الأذونات تُفرَض خادميّاً (ANALYTICS_VIEW/AUDIT_VIEW/
// SETTINGS_MANAGE/USER_INVITE/DEVICE_MANAGE…)؛ canManage في الصفحة تلميح صادق.

import { useMutation, useQuery, type UseMutationResult, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type {
  CostCategoriesResult,
  FeasibilityResult,
  FieldCostRow,
  RoleChangePreview,
  SettingRow,
  WhoCanResult,
} from '../lib/managerConsole';

/** نسخة محليّة من عرف useApi.ts (الدالّة هناك غير مُصدَّرة — لا نعدّل ملفّاً قائماً). */
function isDisabled404(e: unknown): boolean {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return status === 404;
}

// كائن «مُعطَّل» موحَّد يُعاد عند 404 (ميزة خلف علم/راوتر غير مُركَّب) — حالة صادقة.
type Disabled = { disabled: true };

// ─── قراءات (useQuery) — الاقتصاد ─────────────────────────────────────────────

/** بنود التكلفة القياسيّة — GET /api/v1/economics/cost-categories (مرجعيّة ثابتة). */
export function useCostCategories(enabled = true): UseQueryResult<CostCategoriesResult> {
  return useQuery<CostCategoriesResult>({
    queryKey: ['mc-cost-categories'],
    queryFn: () => kongApi
      .get('/api/v1/economics/cost-categories')
      .then((r) => r.data as CostCategoriesResult)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60 * 60_000,
    enabled,
    retry: false,
  });
}

/** تكلفة المهامّ لكلّ حقل — GET /api/v1/analytics/costs/by-field (ANALYTICS_VIEW). */
export function useCostsByField(enabled = true): UseQueryResult<FieldCostRow[] | Disabled> {
  return useQuery<FieldCostRow[] | Disabled>({
    queryKey: ['mc-costs-by-field'],
    queryFn: () => kongApi
      .get('/api/v1/analytics/costs/by-field')
      .then((r) => (Array.isArray(r.data) ? (r.data as FieldCostRow[]) : []))
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 5 * 60_000,
    enabled,
    retry: false,
  });
}

// ─── قراءات — إسقاطات دفتر العمليّات (خلف FEATURE flag ⇒ 404 عند التعطيل) ──────

/** إسقاط ERP قابل للترحيل — GET /api/v1/farm-ledger/erp-projection/{season_id}.
 *  لا يُرسِل شيئاً إلى ERP (synced=false دائماً) — معاينة فقط. */
export function useErpProjection(seasonId: string | null, enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['mc-erp-projection', seasonId ?? 'none'],
    queryFn: () => kongApi
      .get(`/api/v1/farm-ledger/erp-projection/${encodeURIComponent(seasonId!)}`)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled: enabled && !!seasonId,
    retry: false,
  });
}

/** إسقاط خصم المخزون — GET /api/v1/farm-ledger/inventory-projection/{season_id}.
 *  لا يكتب في inventory-service (معاينة فقط). */
export function useInventoryProjection(seasonId: string | null, enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['mc-inventory-projection', seasonId ?? 'none'],
    queryFn: () => kongApi
      .get(`/api/v1/farm-ledger/inventory-projection/${encodeURIComponent(seasonId!)}`)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled: enabled && !!seasonId,
    retry: false,
  });
}

// ─── قراءات — حوكمة الصلاحيّات (استبطان قراءة فقط فوق core.rbac_governance) ─────

/** مصفوفة الصلاحيّات الكاملة — GET /api/v1/rbac/permission-matrix (AUDIT_VIEW). */
export function usePermissionMatrix(enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['mc-permission-matrix'],
    queryFn: () => kongApi
      .get('/api/v1/rbac/permission-matrix')
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 30 * 60_000,
    enabled,
    retry: false,
  });
}

/** الاستعلام العكسي «من يقدر على صلاحيّة؟» — GET /api/v1/rbac/who-can (AUDIT_VIEW). */
export function useWhoCan(permission: string | null, enabled = true): UseQueryResult<WhoCanResult> {
  return useQuery<WhoCanResult>({
    queryKey: ['mc-who-can', permission ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/rbac/who-can', { params: { permission } })
      .then((r) => r.data as WhoCanResult)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 10 * 60_000,
    enabled: enabled && !!permission,
    retry: false,
  });
}

/** معاينة أثر تغيير دور قبل تطبيقه — GET /api/v1/rbac/preview-role-change
 *  (USER_CHANGE_ROLE). استبطان قراءة فقط: لا يُطبّق التغيير. */
export function usePreviewRoleChange(
  currentRole: string | null,
  newRole: string | null,
  enabled = true,
): UseQueryResult<RoleChangePreview> {
  return useQuery<RoleChangePreview>({
    queryKey: ['mc-preview-role-change', currentRole ?? 'none', newRole ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/rbac/preview-role-change', { params: { current_role: currentRole, new_role: newRole } })
      .then((r) => r.data as RoleChangePreview)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 10 * 60_000,
    enabled: enabled && !!currentRole && !!newRole,
    retry: false,
  });
}

// ─── قراءات — السوق (RECOMMENDATION_VIEW) ─────────────────────────────────────

/** فجوة السوق وتركّز المحاصيل لمنطقة — GET /api/v1/market/crop-gap. */
export function useCropGap(zoneKey: string | null, enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['mc-crop-gap', zoneKey ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/market/crop-gap', { params: { zone_key: zoneKey } })
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 10 * 60_000,
    enabled: enabled && !!zoneKey,
    retry: false,
  });
}

/** جاهزيّة تصنيف المحاصيل بالأقمار لمنطقة — GET /api/v1/market/crop-classification-readiness. */
export function useCropClassificationReadiness(zoneKey: string | null, enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['mc-crop-classification-readiness', zoneKey ?? 'none'],
    queryFn: () => kongApi
      .get('/api/v1/market/crop-classification-readiness', { params: { zone_key: zoneKey } })
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 10 * 60_000,
    enabled: enabled && !!zoneKey,
    retry: false,
  });
}

// ─── قراءات — الإعدادات (SETTINGS_VIEW) ───────────────────────────────────────

/** إعدادات المستأجِر (مُرشَّحة اختياريّاً بالنطاق) — GET /api/v1/settings. */
export function useSettings(scope: string | null, enabled = true): UseQueryResult<SettingRow[] | Disabled> {
  return useQuery<SettingRow[] | Disabled>({
    queryKey: ['mc-settings', scope ?? 'all'],
    queryFn: () => kongApi
      .get('/api/v1/settings', { params: scope ? { scope } : undefined })
      .then((r) => (Array.isArray(r.data) ? (r.data as SettingRow[]) : []))
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
    staleTime: 60_000,
    enabled,
    retry: false,
  });
}

// ─── كتابات/حسابات (POST) كـuseMutation ──────────────────────────────────────
// 404 ⇒ {disabled:true} داخل النتيجة (اتّساقاً مع القراءات)؛ بقيّة الأخطاء تُرفَع.

/** جدوى المحصول — POST /api/v1/economics/feasibility (حساب نقيّ، لا كتابة قاعدة). */
export function useFeasibility(): UseMutationResult<FeasibilityResult, unknown, Record<string, unknown>> {
  return useMutation<FeasibilityResult, unknown, Record<string, unknown>>({
    mutationFn: (body) => kongApi
      .post('/api/v1/economics/feasibility', body)
      .then((r) => r.data as FeasibilityResult)
      .catch((e) => { if (isDisabled404(e)) return { supported: false, disabled: true }; throw e; }),
  });
}

/** معاينة الكتابة التلقائيّة للسجلّ الرقابي — POST /api/v1/farm-ledger/autowrite-preview.
 *  لا يحفظ شيئاً (would_persist علَم فقط). */
export function useAutowritePreview(): UseMutationResult<Record<string, unknown>, unknown, Record<string, unknown>> {
  return useMutation<Record<string, unknown>, unknown, Record<string, unknown>>({
    mutationFn: (body) => kongApi
      .post('/api/v1/farm-ledger/autowrite-preview', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}

/** بناء مواصفة تقرير مُتحقَّق منها — POST /api/v1/reports/build (مواصفة فقط لا بيانات). */
export function useReportBuild(): UseMutationResult<Record<string, unknown>, unknown, Record<string, unknown>> {
  return useMutation<Record<string, unknown>, unknown, Record<string, unknown>>({
    mutationFn: (body) => kongApi
      .post('/api/v1/reports/build', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}

/** تحويل توصية إلى أمر عمل (FOES) — POST /api/v1/work-orders/from-recommendation.
 *  كتابة فعليّة (persist-first ثمّ حدث): persisted=true فقط حين أُدرِج صفّ. */
export function useWorkOrderFromRecommendation(): UseMutationResult<Record<string, unknown>, unknown, { field_id: string; recommendation: Record<string, unknown> }> {
  return useMutation<Record<string, unknown>, unknown, { field_id: string; recommendation: Record<string, unknown> }>({
    mutationFn: (body) => kongApi
      .post('/api/v1/work-orders/from-recommendation', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}

/** توليد مفتاح مشاركة — POST /api/v1/sharing/generate-key (USER_INVITE). يُعرَض
 *  الـplaintext مرّة واحدة فقط (الحفظ في DB يحتاج تفعيل الخادم). */
export function useGenerateShareKey(): UseMutationResult<Record<string, unknown>, unknown, Record<string, unknown>> {
  return useMutation<Record<string, unknown>, unknown, Record<string, unknown>>({
    mutationFn: (body) => kongApi
      .post('/api/v1/sharing/generate-key', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}

/** تحويل لقطة كاميرا إلى قرينة ميدانيّة — POST /api/v1/cameras/snapshot-evidence
 *  (DEVICE_MANAGE). قرينة بصريّة منخفضة الوزن — لا تشخيص آليّ. */
export function useSnapshotEvidence(): UseMutationResult<Record<string, unknown>, unknown, Record<string, unknown>> {
  return useMutation<Record<string, unknown>, unknown, Record<string, unknown>>({
    mutationFn: (body) => kongApi
      .post('/api/v1/cameras/snapshot-evidence', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}

/** تقييم اكتمال البيانات — POST /api/v1/data-readiness (ما المتاح/المحجوب/التالي). */
export function useDataReadiness(): UseMutationResult<Record<string, unknown>, unknown, { provided_fields: string[] }> {
  return useMutation<Record<string, unknown>, unknown, { provided_fields: string[] }>({
    mutationFn: (body) => kongApi
      .post('/api/v1/data-readiness', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}

/** فحص أنماط الفشل المعروفة (سحب/طقس قديم/تربة) — POST /api/v1/failures/check. */
export function useFailuresCheck(): UseMutationResult<Record<string, unknown>, unknown, Record<string, unknown>> {
  return useMutation<Record<string, unknown>, unknown, Record<string, unknown>>({
    mutationFn: (body) => kongApi
      .post('/api/v1/failures/check', body)
      .then((r) => r.data as Record<string, unknown>)
      .catch((e) => { if (isDisabled404(e)) return { disabled: true }; throw e; }),
  });
}
