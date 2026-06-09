import { useQuery } from '@tanstack/react-query';
import { indicatorsApi, vegetationApi } from '../services/api';
import { useAuthStore } from './useAuth';

// ── useDashboardKPIs ───────────────────────────────────────────────────────
// Fetches a full KPI snapshot for the dashboard:
//   data.kpis            – array of indicator objects
//   data.alerts          – array of active alerts
//   data.fields_summary  – per-field summary rows
export function useDashboardKPIs(fieldId = 'field_01') {
  const tid = useAuthStore(s => s.user?.tenant_id ?? 'default');

  return useQuery({
    queryKey: ['dashboard-kpis', tid, fieldId],
    queryFn: async () => {
      const [indRes, ndviRes, alertsRes] = await Promise.allSettled([
        indicatorsApi.get(`/v1/indicators/${fieldId}`),
        vegetationApi.get('/v1/ndvi/all', { params: { tenant_id: tid } }),
        indicatorsApi.get('/v1/alerts',   { params: { tenant_id: tid } }),
      ]);

      const indicators  = indRes.status    === 'fulfilled' ? indRes.value.data    : null;
      const ndviAll     = ndviRes.status   === 'fulfilled' ? ndviRes.value.data   : null;
      const alertsData  = alertsRes.status === 'fulfilled' ? alertsRes.value.data : null;

      const kpis: unknown[] = indicators?.kpis ?? indicators?.indicators ?? [];
      const alerts: unknown[] = alertsData?.alerts ?? [];
      const fields_summary: unknown[] = ndviAll?.fields ?? ndviAll?.features ?? [];

      return { kpis, alerts, fields_summary };
    },
    refetchInterval: 30_000,
    staleTime:       10_000,
    retry: 1,
  });
}
