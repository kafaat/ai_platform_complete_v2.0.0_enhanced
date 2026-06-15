// useTenantConfig — يستهلك تكوين المستأجِر (#206) من /api/v1/tenant/config.
// أفضل-جهد: عند أيّ خطأ يُرجِع null فتُبقي الواجهة الافتراضيّات (لا كسر). الكاش
// مُفهرَس بالمستأجِر الفعّال كي يُعاد الجلب عند تبديل المستأجِر، ومُفعَّل فقط بعد
// المصادقة وخارج الوضع التجريبيّ (لا طلب قبل تسجيل الدخول).
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { fetchTenantConfig, type TenantConfig } from '../services/api';
import { useAuthStore } from './useAuth';

export type { TenantConfig, TenantBranding } from '../services/api';

export function useTenantConfig(): UseQueryResult<TenantConfig | null> {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isDemoMode = useAuthStore((s) => s.isDemoMode);
  return useQuery<TenantConfig | null>({
    queryKey: ['tenant', 'config', tid],
    queryFn:  () => fetchTenantConfig(),
    staleTime: 60 * 60_000, // تكوين شبه ثابت — ساعة كافية
    retry:     false,
    enabled:   isAuthenticated && !isDemoMode,
  });
}
