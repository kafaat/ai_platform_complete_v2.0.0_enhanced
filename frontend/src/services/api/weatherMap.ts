// SAHOOL — Map-hub weather API (probe · operation window/plan · action bridge · tiles)
//
// FRONTEND-FETCH-OUTSIDE-API-LAYER-01: كانت وحدةُ الطقس على الخريطة تستدعي `fetch` مباشرةً
// في ٨ مواضع موزّعة على ٣ ملفّات مكوّنات، كلٌّ منها يُركّب ترويسةَ المصادقة
// بنفسه (`weatherFetchHeaders()`). فكان تغييرُ ترويسةٍ أو مسارٍ يحتاج مسحاً لا تعديلاً في
// مكانٍ واحد (#993)، والمواضعُ الثمانية تُفلت من اعتراضات `kongApi` كلِّها: فحصِ انتهاء
// التوكن جهةَ العميل، و`X-Tenant-ID`، وحارسِ ردّ HTML حين يسقط المسارُ إلى SPA.
// الآن كلُّ نداءٍ للطقس من الخريطة يمرّ من هنا عبر `kongApi` — الترويسةُ تُرفَق في موضعٍ
// واحد، والروابطُ تُبنى في موضعٍ واحد بالبايت نفسه الذي كانت تُبنى به في المكوّنات.

import { kongApi } from './client';

const HOURS = '0,1,3,6,12,24,48';
export const WEATHER_PLAN_OPERATIONS = 'spraying,irrigation,harvesting,sowing';

const coord = (value: number) => value.toFixed(5);

export function weatherProbeUrl(lat: number, lon: number, time: string, model: string): string {
  return `/api/v1/weather/probe?lat=${coord(lat)}&lon=${coord(lon)}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}`;
}

export function weatherOperationWindowUrl(lat: number, lon: number, operation: string, model: string): string {
  return `/api/v1/weather/operation-window?lat=${coord(lat)}&lon=${coord(lon)}&operation=${encodeURIComponent(operation)}&hours=${HOURS}&model=${encodeURIComponent(model)}`;
}

export function weatherOperationPlanUrl(lat: number, lon: number, model: string): string {
  return `/api/v1/weather/operation-plan?lat=${coord(lat)}&lon=${coord(lon)}&operations=${WEATHER_PLAN_OPERATIONS}&hours=${HOURS}&model=${encodeURIComponent(model)}`;
}

export function weatherActionRecommendationUrl(lat: number, lon: number, fieldRef: string, model: string): string {
  return `/api/v1/weather/action-recommendation?lat=${coord(lat)}&lon=${coord(lon)}&client_field_ref=${encodeURIComponent(fieldRef)}&operations=${WEATHER_PLAN_OPERATIONS}&hours=${HOURS}&model=${encodeURIComponent(model)}`;
}

/** بلاطةُ بيانات: طبقةُ قياسٍ (`layer`) أو طبقةُ عمليّةٍ زراعيّة (`operation`) — لا كلاهما. */
export type WeatherTileTarget = { layer: string } | { operation: string };

export function weatherTileDataUrl(
  tile: { z: number; x: number; y: number },
  target: WeatherTileTarget,
  time: string,
  model: string,
): string {
  const tail = `time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}&interpolation=grid`;
  if ('operation' in target) {
    return `/api/v1/weather/operation-tile-data/${tile.z}/${tile.x}/${tile.y}?operation=${encodeURIComponent(target.operation)}&${tail}`;
  }
  return `/api/v1/weather/tile-data/${tile.z}/${tile.x}/${tile.y}?layer=${encodeURIComponent(target.layer)}&${tail}`;
}

// الأجوبةُ تُعاد كما وصلت (`unknown` مُضيَّقاً عند المستهلك): كلُّ عرضٍ يقرأ حقولاً مختلفة
// ويقصّ كلَّ غيابٍ إلى «—»، فلا يَعِد هذا الملفّ بشكلٍ لا يفرضه الخادم.
const getJson = <T>(url: string): Promise<T> => kongApi.get<T>(url).then((r) => r.data);

export const getWeatherProbe = <T = unknown>(lat: number, lon: number, time: string, model: string) =>
  getJson<T>(weatherProbeUrl(lat, lon, time, model));

export const getWeatherOperationWindow = <T = unknown>(lat: number, lon: number, operation: string, model: string) =>
  getJson<T>(weatherOperationWindowUrl(lat, lon, operation, model));

export const getWeatherOperationPlan = <T = unknown>(lat: number, lon: number, model: string) =>
  getJson<T>(weatherOperationPlanUrl(lat, lon, model));

export const getWeatherActionRecommendation = <T = unknown>(lat: number, lon: number, fieldRef: string, model: string) =>
  getJson<T>(weatherActionRecommendationUrl(lat, lon, fieldRef, model));

export const getWeatherTileData = <T = unknown>(
  tile: { z: number; x: number; y: number },
  target: WeatherTileTarget,
  time: string,
  model: string,
) => getJson<T>(weatherTileDataUrl(tile, target, time, model));

export interface WeatherTaskFromPlanRequest {
  field_id: string;
  lat: number;
  lon: number;
  operation: string;
  model: string;
  dry_run: boolean;
}

export interface WeatherRecommendationFromPlanRequest {
  field_id: string;
  lat: number;
  lon: number;
  operations: string;
  model: string;
  dry_run: boolean;
}

// مفتاحُ idempotency يُشتقّ عند المُستدعي من مدخلات الإجراء (F5-08) ويُمرَّر هنا حرفيّاً:
// إعادةُ فتح النافذة أو المحاولةُ بعد مهلة تُنتِج المفتاحَ ذاته فيمنع الخادمُ التكرار.
export const createWeatherTaskFromOperationPlan = (body: WeatherTaskFromPlanRequest, idempotencyKey: string) =>
  kongApi
    .post('/api/v1/weather/tasks/from-operation-plan', body, { headers: { 'Idempotency-Key': idempotencyKey } })
    .then((r) => r.data);

export const createWeatherRecommendationFromOperationPlan = (
  body: WeatherRecommendationFromPlanRequest,
  idempotencyKey: string,
) =>
  kongApi
    .post('/api/v1/weather/recommendations/from-operation-plan', body, { headers: { 'Idempotency-Key': idempotencyKey } })
    .then((r) => r.data);
