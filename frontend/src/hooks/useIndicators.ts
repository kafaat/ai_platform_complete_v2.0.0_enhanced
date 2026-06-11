import { useQuery } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import { useAuthStore } from './useAuth';

// ── useDashboardKPIs ───────────────────────────────────────────────────────
// لقطة لوحة المؤشّرات المُجمَّعة للمستأجِر — ربط حيّ واحد عبر البوّابة:
//   GET /api/v1/indicators/dashboard  (sahool-platform، tenant-scoped + FIELD_VIEW)
//   data.kpis            – عدّادات حيّة من جداولك (حقول/مساحة/مواسم/تنبيهات)
//   data.alerts          – التنبيهات النشطة (لا تلفيق)
//   data.fields_summary  – صفّ لكلّ حقل (+ has_active_season)
//
// FIX (ربط حيّ): كان يستدعي ثلاث نقاط على indicators-service الـstub (بلا خلفيّة)
// ويبتلع كلّ الأخطاء بصمت ⇒ مصفوفات فارغة دائماً (mock زائف). الآن نقطة حقيقيّة
// واحدة، وأيّ خطأ (503 DB / 403) يُرفع ليعرض المُستهلك حالة صادقة (Loading/Error).
export function useDashboardKPIs() {
  const tid = useAuthStore(s => s.user?.tenant_id ?? 'default');

  return useQuery<{ kpis: unknown[]; alerts: unknown[]; fields_summary: unknown[] }>({
    queryKey: ['dashboard-kpis', tid],
    queryFn: async () => {
      const data = (await kongApi.get('/api/v1/indicators/dashboard')).data ?? {};
      return {
        kpis:           Array.isArray(data.kpis) ? data.kpis : [],
        alerts:         Array.isArray(data.alerts) ? data.alerts : [],
        fields_summary: Array.isArray(data.fields_summary) ? data.fields_summary : [],
      };
    },
    refetchInterval: 30_000,
    staleTime:       10_000,
    retry: 1,
  });
}
