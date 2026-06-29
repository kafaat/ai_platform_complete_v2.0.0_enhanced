import type { WeatherMarker } from '../OverlayMarkers';
import { getAccessToken } from '../../../lib/authStorage';

export const WEATHER_TILE_SIZE = 256;

// ترويسات طلبات الطقس: تُرفِق رمز الوصول (Bearer) حين توفّره الجلسة. حاسم خلف
// بوّابة الإنتاج (auth_request على /api/v1/) — بدونه تُرجِع نقاط الطقس 401 ولا
// تظهر الطبقة. الطلبات هنا عبر fetch (لا <img>) فتقبل الترويسة مباشرةً.
export function weatherFetchHeaders(): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json' };
  const tok = getAccessToken();
  if (tok) h.Authorization = `Bearer ${tok}`;
  return h;
}

export type WeatherLayerKey =
  | 'temperature'
  | 'wind'
  | 'precipitation'
  | 'et0'
  | 'vpd'
  | 'soil_temperature'
  | 'soil_moisture'
  | 'pressure'
  | 'clouds'
  | 'operation_spraying'
  | 'operation_harvesting'
  | 'operation_sowing'
  | 'operation_irrigation';

export interface WeatherTilePayload {
  layer: WeatherLayerKey;
  value: number | null;
  unit: string;
  source?: string;
  sample?: Record<string, unknown>;
  operation?: { score: number; suitability: string; limiting_factors: string[] };
  cache_state?: string;
  cache_age_s?: number | null;
  upstream_error?: string | null;
}

export type WeatherTimeKey = 'now' | '+1h' | '+3h' | '+6h' | '+12h' | '+24h' | '+48h';
export type WindDensity = 'auto' | 'low' | 'medium' | 'high';
export const WEATHER_TIMES: Array<{ key: WeatherTimeKey; label: string }> = [
  { key: 'now', label: 'الآن' },
  { key: '+1h', label: '+1س' },
  { key: '+3h', label: '+3س' },
  { key: '+6h', label: '+6س' },
  { key: '+12h', label: '+12س' },
  { key: '+24h', label: '+24س' },
  { key: '+48h', label: '+48س' },
];

export const WEATHER_MODELS: Array<{ key: string; label: string }> = [
  { key: 'best_match', label: 'الأفضل تلقائياً' },
  { key: 'gfs_seamless', label: 'GFS' },
  { key: 'ecmwf_ifs04', label: 'ECMWF IFS' },
];

export const WIND_DENSITIES: Array<{ key: WindDensity; label: string; detail: string }> = [
  { key: 'auto', label: 'تلقائي', detail: 'يضبط الكثافة حسب الجهاز' },
  { key: 'low', label: 'منخفض', detail: 'أخف للجوال' },
  { key: 'medium', label: 'متوسط', detail: 'توازن جودة/أداء' },
  { key: 'high', label: 'عالي', detail: 'أقرب للصورة المرجعية' },
];

export interface WeatherLayerConfig {
  key: WeatherLayerKey;
  labelAr: string;
  shortAr: string;
  unit: string;
  min: number;
  max: number;
  stops: string[];
}

export const WEATHER_LAYERS: WeatherLayerConfig[] = [
  { key: 'temperature', labelAr: 'حرارة السطح', shortAr: 'حرارة', unit: '°C', min: -10, max: 50, stops: ['#12d7f7', '#2563eb', '#7c3aed', '#22c55e', '#eab308', '#f97316', '#ef4444', '#e11d48', '#ec4899'] },
  { key: 'wind', labelAr: 'سرعة واتجاه الرياح', shortAr: 'رياح', unit: 'كم/س', min: 0, max: 70, stops: ['#dbeafe', '#93c5fd', '#38bdf8', '#22c55e', '#eab308', '#f97316', '#ef4444'] },
  { key: 'precipitation', labelAr: 'الهطول', shortAr: 'مطر', unit: 'مم', min: 0, max: 30, stops: ['#f8fafc', '#bfdbfe', '#60a5fa', '#2563eb', '#7c3aed'] },
  { key: 'et0', labelAr: 'البخر-نتح المرجعي ET₀', shortAr: 'ET₀', unit: 'مم', min: 0, max: 10, stops: ['#dcfce7', '#bef264', '#facc15', '#fb923c', '#ef4444'] },
  { key: 'vpd', labelAr: 'عجز ضغط البخار VPD', shortAr: 'VPD', unit: 'kPa', min: 0, max: 5, stops: ['#38bdf8', '#22c55e', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] },
  { key: 'soil_temperature', labelAr: 'حرارة التربة', shortAr: 'تربة °', unit: '°C', min: 0, max: 45, stops: ['#2563eb', '#38bdf8', '#22c55e', '#eab308', '#f97316', '#dc2626'] },
  { key: 'soil_moisture', labelAr: 'رطوبة التربة', shortAr: 'رطوبة تربة', unit: 'm³/m³', min: 0, max: 0.55, stops: ['#92400e', '#f59e0b', '#a3e635', '#22c55e', '#0ea5e9', '#1d4ed8'] },
  { key: 'pressure', labelAr: 'ضغط مستوى البحر', shortAr: 'ضغط', unit: 'hPa', min: 980, max: 1040, stops: ['#7c3aed', '#2563eb', '#22c55e', '#eab308', '#ef4444'] },
  { key: 'clouds', labelAr: 'الغيوم', shortAr: 'غيوم', unit: '%', min: 0, max: 100, stops: ['#0f172a', '#475569', '#94a3b8', '#e2e8f0', '#ffffff'] },
  { key: 'operation_spraying', labelAr: 'صلاحية الرش', shortAr: 'رش', unit: '%', min: 0, max: 1, stops: ['#7f1d1d', '#ef4444', '#f97316', '#eab308', '#22c55e'] },
  { key: 'operation_harvesting', labelAr: 'صلاحية الحصاد', shortAr: 'حصاد', unit: '%', min: 0, max: 1, stops: ['#7f1d1d', '#ef4444', '#f97316', '#eab308', '#22c55e'] },
  { key: 'operation_sowing', labelAr: 'صلاحية البذار', shortAr: 'بذار', unit: '%', min: 0, max: 1, stops: ['#7f1d1d', '#ef4444', '#f97316', '#eab308', '#22c55e'] },
  { key: 'operation_irrigation', labelAr: 'أولوية الري', shortAr: 'ري', unit: '%', min: 0, max: 1, stops: ['#0ea5e9', '#22c55e', '#eab308', '#f97316', '#ef4444'] },
];

export const WEATHER_PRESETS: Array<{ label: string; layer: WeatherLayerKey; note: string }> = [
  { label: 'وضع الرش', layer: 'operation_spraying', note: 'رياح + مطر + حرارة + رطوبة' },
  { label: 'وضع الري', layer: 'operation_irrigation', note: 'VPD + رطوبة التربة + المطر' },
  { label: 'وضع الحصاد', layer: 'operation_harvesting', note: 'رطوبة + مطر + رياح' },
  { label: 'وضع البذار', layer: 'operation_sowing', note: 'حرارة ورطوبة التربة' },
];

export const DEFAULT_LAYER: WeatherLayerKey = 'temperature';

export function layerConfig(key: WeatherLayerKey): WeatherLayerConfig {
  return WEATHER_LAYERS.find((l) => l.key === key) ?? WEATHER_LAYERS[0];
}

export function isOperationLayer(layer: WeatherLayerKey): boolean {
  return layer.startsWith('operation_');
}

export function operationFromLayer(layer: WeatherLayerKey): string {
  return layer.replace('operation_', '');
}

export function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function layerFactor(value: number | null | undefined, cfg: WeatherLayerConfig): number {
  if (value == null || Number.isNaN(value)) return 0.55;
  return clamp01((value - cfg.min) / (cfg.max - cfg.min));
}

function lerpHex(a: string, b: string, t: number): string {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ar = (pa >> 16) & 255; const ag = (pa >> 8) & 255; const ab = pa & 255;
  const br = (pb >> 16) & 255; const bg = (pb >> 8) & 255; const bb = pb & 255;
  const rr = Math.round(ar + (br - ar) * t);
  const rg = Math.round(ag + (bg - ag) * t);
  const rb = Math.round(ab + (bb - ab) * t);
  return `#${((1 << 24) + (rr << 16) + (rg << 8) + rb).toString(16).slice(1)}`;
}

export function colorAt(value: number | null | undefined, cfg: WeatherLayerConfig, offset = 0): string {
  const stops = cfg.stops;
  const f = clamp01(layerFactor(value, cfg) + offset);
  const scaled = f * (stops.length - 1);
  const i = Math.max(0, Math.min(stops.length - 2, Math.floor(scaled)));
  return lerpHex(stops[i], stops[i + 1], scaled - i);
}

export function sampleNum(sample: Record<string, unknown> | undefined, key: string): number | null {
  const value = sample?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function getLayerValue(layer: WeatherLayerKey, sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number | null {
  if (isOperationLayer(layer)) return null;
  switch (layer) {
    case 'temperature': return sampleNum(sample, 'temperature_2m_c') ?? fallback.tempC;
    case 'wind': return sampleNum(sample, 'wind_speed_10m_kmh') ?? fallback.windSpeedKmh ?? null;
    case 'precipitation': return sampleNum(sample, 'precipitation_mm');
    case 'et0': return sampleNum(sample, 'et0_fao_evapotranspiration_mm');
    case 'vpd': return sampleNum(sample, 'vapour_pressure_deficit_kpa');
    case 'soil_temperature': return sampleNum(sample, 'soil_temperature_6cm_c') ?? sampleNum(sample, 'soil_temperature_0cm_c');
    case 'soil_moisture': return sampleNum(sample, 'soil_moisture_1_to_3cm_m3m3') ?? sampleNum(sample, 'soil_moisture_0_to_1cm_m3m3');
    case 'pressure': return sampleNum(sample, 'pressure_msl_hpa');
    case 'clouds': return sampleNum(sample, 'cloud_cover_pct');
    default: return fallback.tempC;
  }
}

export function windDirection(sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number {
  return sampleNum(sample, 'wind_direction_10m_deg') ?? fallback.windDirectionDeg ?? 315;
}

export function windSpeed(sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number {
  return sampleNum(sample, 'wind_speed_10m_kmh') ?? fallback.windSpeedKmh ?? 12;
}

export function safeMod(value: number, modulo: number): number {
  return ((value % modulo) + modulo) % modulo;
}

