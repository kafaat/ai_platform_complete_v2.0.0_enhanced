// ═══════════════════════════════════════════════════════════════
// SAHOOL — النظائر المناخيّة (Climate Analogs)
// ───────────────────────────────────────────────────────────────
// يربط /api/v1/climate-analogs/* بالواجهة: قائمة المناطق النظيرة، تفصيل منطقة،
// محاصيل صحراويّة، الطبقات الاستراتيجيّة، والاستراتيجيّة. يفيد سياق الجوف الصحراويّ
// (مناطق عالميّة مشابهة مناخيّاً ⇒ محاصيل مُجرّبة). يُنهي دَين climate-analogs.
// ═══════════════════════════════════════════════════════════════
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import {
  parseClimateAnalogRegions,
  parseDesertCrops,
  type ClimateAnalogRegion,
  type DesertCrop,
} from '../lib/referenceContracts';

export type { ClimateAnalogRegion, DesertCrop };

/** ``supported=false`` يحمل ``message_ar`` بالمناطق المتاحة بدل حقول المنطقة. */
export interface ClimateAnalogDetail {
  supported?: boolean;
  region_ar?: string;
  message_ar?: string;
  [k: string]: unknown;
}

const STALE = 60 * 60_000;

/** GET /api/v1/climate-analogs/list — المناطق النظيرة مناخيّاً. */
export function useClimateAnalogsList(enabled = true): UseQueryResult<ClimateAnalogRegion[]> {
  return useQuery<ClimateAnalogRegion[]>({
    queryKey: ['climate-analogs', 'list'],
    queryFn: () => kongApi.get('/api/v1/climate-analogs/list').then((r) => parseClimateAnalogRegions(r.data)),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/climate-analogs/detail?region= — تفصيل منطقة نظيرة. */
export function useClimateAnalogDetail(
  region: string,
  enabled = true,
): UseQueryResult<ClimateAnalogDetail> {
  return useQuery<ClimateAnalogDetail>({
    queryKey: ['climate-analogs', 'detail', region],
    queryFn: () =>
      kongApi
        .get('/api/v1/climate-analogs/detail', { params: { region } })
        .then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && !!region,
    retry: false,
  });
}

/** GET /api/v1/climate-analogs/desert-crops?category= — محاصيل صحراويّة. */
export function useDesertCrops(
  category?: string,
  enabled = true,
): UseQueryResult<DesertCrop[]> {
  return useQuery<DesertCrop[]>({
    queryKey: ['climate-analogs', 'desert-crops', category ?? 'all'],
    queryFn: () =>
      kongApi
        .get('/api/v1/climate-analogs/desert-crops', {
          params: category ? { category } : {},
        })
        .then((r) => parseDesertCrops(r.data)),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/climate-analogs/strategic-tiers?tier= — الطبقات الاستراتيجيّة. */
export function useStrategicTiers(
  tier?: string,
  enabled = true,
): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['climate-analogs', 'strategic-tiers', tier ?? 'all'],
    queryFn: () =>
      kongApi
        .get('/api/v1/climate-analogs/strategic-tiers', {
          params: tier ? { tier } : {},
        })
        .then((r) => r.data),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/climate-analogs/strategy — الاستراتيجيّة العامّة. */
export function useClimateStrategy(enabled = true): UseQueryResult<Record<string, unknown>> {
  return useQuery<Record<string, unknown>>({
    queryKey: ['climate-analogs', 'strategy'],
    queryFn: () => kongApi.get('/api/v1/climate-analogs/strategy').then((r) => r.data),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}
