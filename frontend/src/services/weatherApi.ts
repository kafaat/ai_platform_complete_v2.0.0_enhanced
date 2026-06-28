// ═══════════════════════════════════════════════════════════════
// weatherApi.ts — دوالّ مجال الطقس (مُستخرَجة من api.ts)
// موحّدة على المنصّة عبر kongApi (لا عميل weatherApi المعطوب). تعتمد على
// kongApi/tryReal من apiClients وبيانات mock من apiMocks. api.ts يعيد التصدير
// عبر `export *` فيبقى كلّ import من '.../services/api' يعمل دون تغيير.
// السلوك محفوظ: نسخ حرفيّ للدوالّ/المسارات.
// ═══════════════════════════════════════════════════════════════

import { kongApi, tryReal } from './apiClients';
import { MOCK_WEATHER_TODAY, mockWeatherDays } from './apiMocks';

// ══════════════════════════════════════════════════════════════════
// WEATHER — موحّد على المنصّة (sahool-platform/api/routers/weather.py)
// ══════════════════════════════════════════════════════════════════
// المنطق الحقيقيّ للطقس (Open-Meteo + ET₀ FAO-56) يعيش في المنصّة عبر
// /api/v1/weather/{current,forecast,historical}. خدمة weather-service جذعيّة تردّ
// 501 لأيّ مسار طقس، لذا نُمرّر هذه الدوالّ عبر kongApi (مسارات /api/v1/weather عبر
// البوّابة) لا weatherApi المعطوبة. الردّ بشكل المنصّة الخام (days[].temp_max_c …).

export const fetchCurrentWeather = (lat = 15.05, lon = 45.55) =>
  tryReal(
    () => kongApi.get('/api/v1/weather/current', { params:{ lat, lon } }).then(r => r.data),
    () => ({ current: MOCK_WEATHER_TODAY, location:{ lat, lon, region:'البيضاء، اليمن' } })
  );

export const fetchWeatherForecast = (days = 7, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => kongApi.get('/api/v1/weather/forecast', { params:{ days, lat, lon } }).then(r => r.data),
    () => ({ forecast:mockWeatherDays(days), days, summary:{ total_gdd:85, total_et0_mm:31, avg_tmax_c:31 } })
  );

export const fetchWeatherHistorical = (days = 30, lat = 15.05, lon = 45.55) =>
  tryReal(
    () => {
      // المنصّة تتطلّب نطاق تاريخ صريح (start_date/end_date) لا عدد أيّام.
      const end = new Date();
      const start = new Date(end.getTime() - days * 86_400_000);
      const iso = (d: Date) => d.toISOString().slice(0, 10);
      return kongApi
        .get('/api/v1/weather/historical', { params:{ lat, lon, start_date: iso(start), end_date: iso(end) } })
        .then(r => r.data);
    },
    () => ({ period_days:days, data:mockWeatherDays(days), summary:{ total_gdd:300, water_deficit_mm:45, total_et0_mm:130, total_rainfall_mm:85 } })
  );

export const fetchWofostFormat = (days = 30, lat = 15.05, lon = 45.55) =>
  // لا نقطة wofost_format على المنصّة؛ نشتقّ مدخلات WOFOST من توقّعات المنصّة الحقيقيّة.
  tryReal(
    () => kongApi.get('/api/v1/weather/forecast', { params:{ days, lat, lon } }).then(r => {
      const rawDays = Array.isArray(r.data?.days) ? r.data.days : [];
      return {
        wofost_input: rawDays.map((d: { date?: string; temp_max_c?: number; temp_min_c?: number; solar_radiation_mj_m2?: number; et0_mm?: number; precipitation_mm?: number }) => ({
          date: d.date ?? null, tmax: d.temp_max_c ?? null, tmin: d.temp_min_c ?? null,
          radiation_mj: d.solar_radiation_mj_m2 ?? null, et0: d.et0_mm ?? null,
          precipitation: d.precipitation_mm ?? null,
        })),
        total_days: rawDays.length,
        source: 'sahool-platform',
      };
    }),
    () => ({ wofost_input:mockWeatherDays(days).map(d => ({ date:d.date, tmax:d.tmax, tmin:d.tmin, radiation_mj:18, et0:d.et0, precipitation:d.rain, soil_moisture_pct:35 })), total_days:days, source:'mock' })
  );

// ملاحظة صدق: لا نقطة agro-indicators مكافئة على المنصّة (كانت تستهدف weather-service
// الجذعيّة ⇒ 501). غير مُستهلَكة في أيّ واجهة. مُبقاة للـMOCK_MODE فقط؛ خارجه ترمي
// بصدق (لا تلفيق) حتى تُبنى نقطة مكافئة على المنصّة.
export const fetchAgroIndicators = (_days = 30) =>
  tryReal(
    () => Promise.reject(new Error('agro-indicators: لا نقطة مكافئة على المنصّة بعد')),
    () => ({ gdd_accumulated:305, et0_accumulated_mm:132, rainfall_accumulated_mm:87, water_deficit_mm:45, drought_stress_days:5 })
  );
