// ═══════════════════════════════════════════════════════════════
// SAHOOL — التقاويم اليمنيّة التراثيّة (Yemeni Calendars)
// ───────────────────────────────────────────────────────────────
// يربط /api/v1/calendars/* (٤ مسارات GET) بالواجهة: المنازل القمريّة الـ٢٨،
// الشهور الحميريّة، الملفّات الإقليميّة، والجسر الزمنيّ (context). معرفة تراثيّة
// (عرض فقط، لا تدخل القرار). يُنهي دَين high×button لمجال calendars.
// ═══════════════════════════════════════════════════════════════
import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';

export interface LunarMansion {
  index?: number;
  name_ar?: string;
  season_ar?: string;
  agricultural_note_ar?: string;
  [k: string]: unknown;
}

export interface HimyariteMonth {
  index?: number;
  name_ar?: string;
  gregorian_approx?: string;
  note_ar?: string;
  [k: string]: unknown;
}

export interface RegionalProfile {
  governorate?: string;
  region_ar?: string;
  [k: string]: unknown;
}

export interface CalendarContext {
  date_iso: string;
  active_mansion?: LunarMansion;
  himyarite_month?: HimyariteMonth;
  regional_profile?: RegionalProfile;
  [k: string]: unknown;
}

const STALE = 60 * 60_000; // مرجع تراثيّ شبه ثابت — تخبئة ساعة.

/** GET /api/v1/calendars/lunar-mansions — المنازل القمريّة الـ٢٨. */
export function useLunarMansions(enabled = true): UseQueryResult<LunarMansion[]> {
  return useQuery<LunarMansion[]>({
    queryKey: ['calendars', 'lunar-mansions'],
    queryFn: () => kongApi.get('/api/v1/calendars/lunar-mansions').then((r) => r.data),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/calendars/himyarite-months — الشهور الحميريّة الـ١٢. */
export function useHimyariteMonths(enabled = true): UseQueryResult<HimyariteMonth[]> {
  return useQuery<HimyariteMonth[]>({
    queryKey: ['calendars', 'himyarite-months'],
    queryFn: () => kongApi.get('/api/v1/calendars/himyarite-months').then((r) => r.data),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/calendars/regional-profiles?governorate= — الملفّات الإقليميّة. */
export function useRegionalProfiles(
  governorate?: string,
  enabled = true,
): UseQueryResult<RegionalProfile[]> {
  return useQuery<RegionalProfile[]>({
    queryKey: ['calendars', 'regional-profiles', governorate ?? 'all'],
    queryFn: () =>
      kongApi
        .get('/api/v1/calendars/regional-profiles', {
          params: governorate ? { governorate } : {},
        })
        .then((r) => r.data),
    staleTime: STALE,
    enabled,
    retry: false,
  });
}

/** GET /api/v1/calendars/context?date_iso=&governorate= — الجسر الزمنيّ. */
export function useCalendarContext(
  dateIso: string,
  governorate?: string,
  enabled = true,
): UseQueryResult<CalendarContext> {
  return useQuery<CalendarContext>({
    queryKey: ['calendars', 'context', dateIso, governorate ?? 'none'],
    queryFn: () =>
      kongApi
        .get('/api/v1/calendars/context', {
          params: { date_iso: dateIso, ...(governorate ? { governorate } : {}) },
        })
        .then((r) => r.data),
    staleTime: STALE,
    enabled: enabled && !!dateIso,
    retry: false,
  });
}
