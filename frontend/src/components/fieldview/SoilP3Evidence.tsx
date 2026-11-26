import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../hooks/useAuth';
import { getAuthScope } from '../../lib/authStorage';
import { soilApi } from '../../services/api/client';
import { T } from '../ds';

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as RecordValue : {};
const text = (value: unknown): string => typeof value === 'string' && value.trim() ? value : 'غير متاح';
const strings = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [];

export function scopedP3Evidence(value: unknown, tenant: string, field: string): RecordValue | null {
  const data = record(value);
  return data.tenant_id === tenant && data.field_id === field &&
    typeof data.product_id === 'string' && data.product_id.length > 0 ? data : null;
}

export default function SoilP3Evidence({ fieldId }: { fieldId?: string | null }) {
  const tenant = useAuthStore(s => s.tenantId);
  const user = useAuthStore(s => s.user);
  const authenticated = useAuthStore(s => s.isAuthenticated && !s.isDemoMode);
  const identity = user?.id ?? user?.email;
  const scope = authenticated && tenant && identity != null && String(identity)
    ? JSON.stringify([tenant, String(identity)]) : null;
  const enabled = Boolean(scope && fieldId);
  const load = async (product: string) => {
    if (!scope || !tenant || !fieldId || getAuthScope() !== scope) throw new Error('session changed');
    const response = await soilApi.get(
      `/v1/fields/${encodeURIComponent(fieldId)}/soil/${product}`,
      { expectedAuthScope: scope },
    );
    if (getAuthScope() !== scope) throw new Error('session changed');
    const data = scopedP3Evidence(response.data, tenant, fieldId);
    if (!data) throw new Error('assessment scope mismatch');
    return data;
  };
  const drainage = useQuery({
    queryKey: ['soil-p3-drainage', scope, fieldId], queryFn: () => load('drainage-assessment'),
    enabled, retry: false, staleTime: 0, gcTime: 0,
  });
  const reclamation = useQuery({
    queryKey: ['soil-p3-reclamation', scope, fieldId], queryFn: () => load('reclamation-assessment'),
    enabled, retry: false, staleTime: 0, gcTime: 0,
  });
  if (!enabled || getAuthScope() !== scope) return null;
  const d = !drainage.isError && !drainage.isFetching ? drainage.data : undefined;
  const r = !reclamation.isError && !reclamation.isFetching ? reclamation.data : undefined;
  const provenance = record(r?.provenance);
  const gypsum = record(provenance.gypsum_scenario);
  const rate = record(gypsum.estimate).gypsum_t_per_ha;
  const capability = record(provenance.land_capability_scenario);
  const result = record(capability.result);
  return (
    <div className="mt-2 rounded-xl border p-2 text-[11px]" style={{ borderColor: T.line, color: T.muted }}
      data-testid="soil-p3-evidence">
      <div className="font-bold" style={{ color: T.ink }}>أدلة الصرف والاستصلاح المحفوظة — قراءة فقط</div>
      <div>الصرف: {drainage.isFetching ? 'جارٍ القراءة' : d ? text(d.drainage_need) : 'لا تقييم متاح أو تعذرت قراءته'}</div>
      {d && <div>مرجع المنتج: {text(d.product_id)} · الإصدار: {text(d.assessment_version)}</div>}
      {d && strings(d.limitations).length > 0 && <div>قيود: {strings(d.limitations).join('، ')}</div>}
      <div>الاستصلاح: {reclamation.isFetching ? 'جارٍ القراءة' : r ? text(r.reclamation_priority) : 'لا تقييم متاح أو تعذرت قراءته'}</div>
      {r && <div>مرجع المنتج: {text(r.product_id)} · الإصدار: {text(r.assessment_version)}</div>}
      {r && strings(r.blocked_actions).length > 0 && <div>محجوب: {strings(r.blocked_actions).join('، ')}</div>}
      {r && gypsum.status === 'estimated' && gypsum.execution_authorized === false &&
        gypsum.local_compliance_evaluated === false && typeof rate === 'number' && Number.isFinite(rate) && rate >= 0 &&
        <div>تقدير نظري للجبس: {rate} طن/هكتار · {text(gypsum.input_basis)} · {text(gypsum.source_ref)}</div>}
      {r && gypsum.status === 'not_evaluated' && <div>الجبس غير مقيم: {text(gypsum.reason)}</div>}
      {r && capability.status === 'estimated' && capability.execution_authorized === false &&
        capability.local_compliance_evaluated === false && result.complete === true &&
        <div>تصنيف إرشادي: {text(result.capability_class)} · {text(result.standard)}</div>}
      {r && capability.status === 'incomplete' && <div>تصنيف القدرة الزراعية غير مكتمل</div>}
      <div>لا اعتماد محلي أو إذن بتنفيذ الاستصلاح من هذه البطاقة.</div>
    </div>
  );
}
