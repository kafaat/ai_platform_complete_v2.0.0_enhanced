import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../hooks/useAuth';
import { kongApi } from '../services/api';
import { readEquipmentReadiness } from '../lib/equipmentReadiness';
import { Card, SectionLabel } from './ds/atoms';
import { T } from './ds/tokens';

const verdictLabels = {
  due: 'صيانة مستحقة',
  not_due: 'غير مستحقة وفق الدليل المتاح',
  not_evaluated: 'لم تُقيّم',
} as const;
const fleetLabels = {
  unknown: 'الجاهزية غير محسومة',
  attention_required: 'توجد صيانة مستحقة',
  degraded: 'توجد معدات غير متاحة',
  ready: 'لا استحقاق مثبت في الأصول المقيّمة',
} as const;
const constraintLabels: Record<string, string> = {
  maintenance_policy_missing: 'سياسة الصيانة غير مسجلة',
  service_meter_baseline_missing: 'قراءة العداد عند آخر صيانة غير مسجلة',
  current_meter_reading_missing: 'قراءة العداد الحالية غير متاحة',
  invalid_next_service_date: 'تاريخ الصيانة التالي غير صالح',
  service_meter_not_evaluable: 'لا يمكن تقييم الصيانة وفق العداد',
};

/** Read the existing tenant-wide fleet assessment. Do not infer per-farm readiness. */
export function EquipmentReadinessCard() {
  const tenant = useAuthStore(s => s.tenantId);
  const principal = useAuthStore(s => s.user?.id ?? s.user?.email);
  const role = useAuthStore(s => s.user?.role);
  const authenticated = useAuthStore(s => s.isAuthenticated && !s.isDemoMode);
  const enabled = authenticated && !!tenant && principal != null;
  const query = useQuery({
    // Existing equipment mutations invalidate this tenant prefix too.
    queryKey: ['equipment', tenant, 'intelligence', principal, role],
    enabled,
    staleTime: 0,
    gcTime: 0,
    retry: false,
    queryFn: async ({ signal }) => {
      const initial = useAuthStore.getState();
      const sessionMatches = () => {
        const state = useAuthStore.getState();
        return state.isAuthenticated && !state.isDemoMode && !!initial.token &&
          state.token === initial.token && state.tenantId === tenant &&
          (state.user?.id ?? state.user?.email) === principal && state.user?.role === role;
      };
      if (!sessionMatches()) throw new Error('Equipment session changed');
      const response = await kongApi.get<unknown>('/api/v1/equipment', { params: { summary: true }, signal });
      if (!sessionMatches()) throw new Error('Equipment session changed');
      return readEquipmentReadiness(response.data);
    },
  });
  if (!enabled) return null;

  return (
    <Card>
      <SectionLabel>جاهزية أسطول المستأجر وأدلة الصيانة</SectionLabel>
      {query.isPending ? (
        <p className="text-sm">جارٍ تحميل التقييم من الخادم…</p>
      ) : query.isError || !query.data ? (
        <p className="text-sm" style={{ color: T.warn }} role="alert">
          تعذّر جلب تقييم الصيانة الموثوق؛ لا توجد نتيجة معتمدة للعرض.
          <button type="button" className="underline mx-2" onClick={() => void query.refetch()}>إعادة المحاولة</button>
        </p>
      ) : (
        <div className="space-y-2" dir="rtl">
          <p className="font-semibold" style={{ color: T.ink }}>{fleetLabels[query.data.readiness]}</p>
          <p className="text-sm" style={{ color: T.muted }}>
            المعدات: {query.data.total} · غير المتاحة: {query.data.unavailable} · تغطية تقييم الصيانة: {Math.round(query.data.coverage * 100)}%
          </p>
          <p className="text-xs" style={{ color: T.muted }}>
            هذا تقييم لأسطول المستأجر، وليس إثبات جاهزية مزرعة أو إذن تشغيل. غياب الدليل لا يعني أن الصيانة غير مستحقة.
          </p>
          <ul className="space-y-1 text-sm">
            {query.data.assets.map(asset => (
              <li key={asset.id} className="py-1" style={{ color: T.ink }}>
                <span className="font-semibold">{asset.name}</span> — {verdictLabels[asset.status]}
                {asset.basis && <span className="text-xs"> · {asset.basis === 'service_meter' ? 'وفق العداد' : 'وفق الجدولة المسجلة'}</span>}
                {asset.constraints.length > 0 && <p className="text-xs" style={{ color: T.muted }}>{asset.constraints.map(c => constraintLabels[c] ?? c).join(' · ')}</p>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
