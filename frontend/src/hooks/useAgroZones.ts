// ═══════════════════════════════════════════════════════════════
// SAHOOL — الأقاليم المناخيّة-الزراعيّة (Agro-Climatic Zones)
// ───────────────────────────────────────────────────────────────
// يربط نقاط /api/v1/agro-zones/* (٦ مسارات GET) بالواجهة عبر React Query.
// نمط مطابق لبقيّة hooks (kongApi + useQuery). كلّها قراءة (لا طفرات).
// يُنهي دَين واجهة high×button للمجال agro-zones (خطّة UI_DEBT_MAP).
// ═══════════════════════════════════════════════════════════════
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';

// ── الأنواع (شكل استجابة الخادم؛ مرنة حيث المخطّط الخلفيّ حرّ) ──
export interface AgroZoneSummary {
  zone: string;
  name_ar?: string;
  elevation_range_m?: [number, number] | string;
  rainfall_mm?: string | number;
  summary_ar?: string;
  [k: string]: unknown;
}

export interface AgroZoneProfile {
  zone: string;
  name_ar?: string;
  temperature?: unknown;
  rainfall?: unknown;
  suited_crops?: string[];
  avoid_crops?: string[];
  [k: string]: unknown;
}

export interface SuitedCropsResult {
  zone: string;
  supported?: boolean;
  // أسماء الخادم الفعليّة (agro_climate_zones.suited_for_zone).
  suited_crops_ar?: string[];
  avoid_ar?: string[];
  rainfed_possible?: boolean;
  water_note_ar?: string;
  [k: string]: unknown;
}

const QK = {
  list: ['agro-zones', 'list'] as const,
  profile: (zone: string) => ['agro-zones', 'profile', zone] as const,
  identify: (loc: string) => ['agro-zones', 'identify', loc] as const,
  suited: (zone: string, irr: boolean) => ['agro-zones', 'suited', zone, irr] as const,
  byElev: (alt: number, west: boolean) => ['agro-zones', 'elev', alt, west] as const,
  smart: (loc: string, alt: number | null, west: boolean) =>
    ['agro-zones', 'smart', loc, alt ?? 'none', west] as const,
};

const STALE = 30 * 60_000; // الأقاليم مرجع شبه ثابت — تخبئة طويلة.

/** GET /api/v1/agro-zones/list — الأقاليم الستّة مع ملخّصها.
 *  الخادم يغلّف القائمة: `{zones: [...], count, principle_ar}` — يجب فكّ `zones`
 *  وإلّا انهارت الواجهة بـ`.map is not a function` (علّة مُبلَّغة 2026-07-11). */
export function useAgroZonesList(enabled = true): UseQueryResult<AgroZoneSummary[]> {
  return useQuery<AgroZoneSummary[]>({
    queryKey: QK.list,
    queryFn: () =>
      kongApi.get('/api/v1/agro-zones/list').then((r) =>
        Array.isArray(r.data) ? r.data : ((r.data?.zones ?? []) as AgroZoneSummary[]),
      ),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/agro-zones/profile?zone= — الملفّ الكامل لإقليم. */
export function useAgroZoneProfile(
  zone: string,
  enabled = true,
): UseQueryResult<AgroZoneProfile> {
  return useQuery<AgroZoneProfile>({
    queryKey: QK.profile(zone),
    queryFn: () =>
      kongApi.get('/api/v1/agro-zones/profile', { params: { zone } }).then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && !!zone,
    retry: false,
  });
}

/** GET /api/v1/agro-zones/identify?location= — الإقليم من اسم محافظة/منطقة. */
export function useAgroZoneIdentify(
  location: string,
  enabled = true,
): UseQueryResult<AgroZoneProfile> {
  return useQuery<AgroZoneProfile>({
    queryKey: QK.identify(location),
    queryFn: () =>
      kongApi
        .get('/api/v1/agro-zones/identify', { params: { location } })
        .then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && !!location,
    retry: false,
  });
}

/** GET /api/v1/agro-zones/suited-crops?zone=&irrigated= — المحاصيل الملائمة. */
export function useAgroZoneSuitedCrops(
  zone: string,
  irrigated = true,
  enabled = true,
): UseQueryResult<SuitedCropsResult> {
  return useQuery<SuitedCropsResult>({
    queryKey: QK.suited(zone, irrigated),
    queryFn: () =>
      kongApi
        .get('/api/v1/agro-zones/suited-crops', { params: { zone, irrigated } })
        .then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && !!zone,
    retry: false,
  });
}

/** GET /api/v1/agro-zones/by-elevation?altitude_m=&is_western= — الأصدق مناخيّاً. */
export function useAgroZoneByElevation(
  altitudeM: number,
  isWestern = true,
  enabled = true,
): UseQueryResult<AgroZoneProfile> {
  return useQuery<AgroZoneProfile>({
    queryKey: QK.byElev(altitudeM, isWestern),
    queryFn: () =>
      kongApi
        .get('/api/v1/agro-zones/by-elevation', {
          params: { altitude_m: altitudeM, is_western: isWestern },
        })
        .then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && Number.isFinite(altitudeM),
    retry: false,
  });
}

/** GET /api/v1/agro-zones/identify-smart — تحديد ذكيّ (محافظات متعدّدة الأقاليم). */
export function useAgroZoneIdentifySmart(
  location: string,
  altitudeM: number | null = null,
  isWestern = true,
  enabled = true,
): UseQueryResult<AgroZoneProfile> {
  return useQuery<AgroZoneProfile>({
    queryKey: QK.smart(location, altitudeM, isWestern),
    queryFn: () =>
      kongApi
        .get('/api/v1/agro-zones/identify-smart', {
          params: {
            location,
            ...(altitudeM != null ? { altitude_m: altitudeM } : {}),
            is_western: isWestern,
          },
        })
        .then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && !!location,
    retry: false,
  });
}
