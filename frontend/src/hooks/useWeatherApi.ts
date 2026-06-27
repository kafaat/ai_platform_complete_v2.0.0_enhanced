// SAHOOL v9.0 — src/hooks/useWeatherApi.ts — هوكات الطقس (مقتطعة من useApi.ts)
import { useQuery } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import { QK } from './useApiKeys';

// ── Weather ───────────────────────────────────────────────────
// توحيد بيانات الطقس على المنصّة (sahool-platform/api/routers/weather.py):
//   GET /api/v1/weather/current  → {temperature_c, humidity_pct, wind_speed_ms, …}
//   GET /api/v1/weather/forecast → {location, days:[{date, temp_max_c, temp_min_c,
//                                    et0_mm, daylight_hours, sunrise/sunset, …}]}
//   GET /api/v1/weather/historical (start_date/end_date) → {days:[…]}
// المنطق الحقيقيّ (Open-Meteo + ET₀ FAO-56) يعيش في المنصّة؛ خدمة weather-service
// جذعيّة تردّ 501 لأيّ مسار طقس. لذا نُمرّر كلّ طلبات الطقس عبر kongApi (مسارات
// /api/v1/weather النسبيّة عبر البوّابة) بدل weatherApi المعطوبة، ونُطبّع الردّ إلى
// الشكل الذي تقرؤه المكوّنات بثبات: {current:{tmean,humidity_pct,wind_speed_kmh,
// et0_mm}, forecast:[{date,tmean,tmax,tmin,…}], daily:[…]}. لا تلفيق: أيّ حقل غائب
// يبقى null والمكوّنات تعرض «—». فشل المصدر (502/503) يُرفع لتعرض الواجهة حالة خطأ.

interface PlatformForecastDay {
  date?: string;
  temp_max_c?: number | null;
  temp_min_c?: number | null;
  precipitation_mm?: number | null;
  et0_mm?: number | null;
  sunshine_hours?: number | null;
  sunrise?: string | null;
  sunset?: string | null;
  daylight_hours?: number | null;
  solar_radiation_mj_m2?: number | null;
  wind_max_ms?: number | null;
  weather_code?: number | null;
  weather_ar?: string | null;
}
interface PlatformCurrent {
  temperature_c?: number | null;
  humidity_pct?: number | null;
  wind_speed_ms?: number | null;
  wind_direction_deg?: number | null;
  wind_dir_deg?: number | null;
  precipitation_mm?: number | null;
  weather_code?: number | null;
  weather_ar?: string | null;
  is_day?: number | null;
  timestamp?: string | null;
}
/** يُطبّع يوماً من المنصّة إلى شكل المكوّنات (tmean/tmax/tmin + حقول الشمس/ET₀). */
function normForecastDay(d: PlatformForecastDay) {
  const tmax = d.temp_max_c ?? null;
  const tmin = d.temp_min_c ?? null;
  const tmean = tmax != null && tmin != null ? (tmax + tmin) / 2 : null;
  return {
    date: d.date ?? null,
    tmean, tmax, tmin,
    rain: d.precipitation_mm ?? null,
    et0_mm: d.et0_mm ?? null,
    sunrise: d.sunrise ?? undefined,
    sunset: d.sunset ?? undefined,
    daylight_hours: d.daylight_hours ?? undefined,
    solar_radiation_mj_m2: d.solar_radiation_mj_m2 ?? undefined,
    weather_ar: d.weather_ar ?? undefined,
  };
}
/** يجلب الطقس الحاليّ + التوقّعات من المنصّة ويُطبّعهما لشكل المكوّنات الموحّد.
 *  current.wind_speed_kmh مُحوّلة من m/s (×3.6). et0_mm للحاضر من أوّل يوم توقّع. */
async function fetchPlatformWeather(lat: number, lon: number, days: number) {
  const [cur, fc] = await Promise.all([
    kongApi.get<PlatformCurrent>('/api/v1/weather/current', { params: { lat, lon } }).then(r => r.data),
    kongApi.get<{ days?: PlatformForecastDay[] }>('/api/v1/weather/forecast', { params: { lat, lon, days } }).then(r => r.data),
  ]);
  const rawDays = Array.isArray(fc?.days) ? fc.days : [];
  const forecast = rawDays.map(normForecastDay);
  const windKmh = cur?.wind_speed_ms != null ? Math.round(cur.wind_speed_ms * 3.6 * 10) / 10 : undefined;
  return {
    current: {
      tmean: cur?.temperature_c ?? undefined,
      humidity_pct: cur?.humidity_pct ?? undefined,
      wind_speed_kmh: windKmh,
      wind_direction_deg: cur?.wind_direction_deg ?? cur?.wind_dir_deg ?? undefined,
      et0_mm: forecast[0]?.et0_mm ?? null,
      weather_ar: cur?.weather_ar ?? undefined,
    },
    forecast,
    daily: forecast,
    location: { lat, lon },
    source: 'sahool-platform',
  };
}

export function useWeatherForecast(lat = 15.05, lon = 45.55, days = 7) {
  return useQuery({
    queryKey:        QK.weatherForecast(lat, lon),
    queryFn:         () => fetchPlatformWeather(lat, lon, days),
    staleTime:       30 * 60_000,
    refetchInterval: 60 * 60_000,
    retry:           false,
  });
}

export function useWeatherWofost(lat = 15.05, lon = 45.55, days = 14) {
  // لا نقطة wofost_format على المنصّة؛ نشتقّ مدخلات بنمط WOFOST من توقّعات المنصّة
  // الحقيقيّة (نفس مصدر Open-Meteo) بدل ضرب خدمة weather-service الجذعيّة (501).
  return useQuery({
    queryKey: QK.weatherWofost(lat, lon, days),
    queryFn:  async () => {
      const fc = await kongApi
        .get<{ days?: PlatformForecastDay[] }>('/api/v1/weather/forecast', { params: { lat, lon, days } })
        .then(r => r.data);
      const rawDays = Array.isArray(fc?.days) ? fc.days : [];
      return {
        wofost_input: rawDays.map(d => ({
          date: d.date ?? null,
          tmax: d.temp_max_c ?? null,
          tmin: d.temp_min_c ?? null,
          radiation_mj: d.solar_radiation_mj_m2 ?? null,
          et0: d.et0_mm ?? null,
          precipitation: d.precipitation_mm ?? null,
        })),
        total_days: rawDays.length,
        source: 'sahool-platform',
      };
    },
    staleTime:60 * 60_000,
    retry:    false,
  });
}

export function useWeatherHistory(lat = 15.05, lon = 45.55, days = 30) {
  // المنصّة تتطلّب نطاق تاريخ صريح (start_date/end_date) لا عدد أيّام — نُحوّله هنا.
  return useQuery({
    queryKey: QK.weatherHistory(lat, lon, days),
    queryFn:  () => {
      const end = new Date();
      const start = new Date(end.getTime() - days * 86_400_000);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      return kongApi
        .get('/api/v1/weather/historical', {
          params: { lat, lon, start_date: iso(start), end_date: iso(end) },
        })
        .then(r => r.data);
    },
    staleTime:30 * 60_000,
    retry:    false,
  });
}
