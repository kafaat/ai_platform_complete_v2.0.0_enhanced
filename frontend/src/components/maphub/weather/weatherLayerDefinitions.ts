import type { WeatherMarker } from '../OverlayMarkers';
import { getAccessToken } from '../../../lib/authStorage';

export const WEATHER_TILE_SIZE = 256;

// ترويسات طلبات الطقس: تُرفِق رمز الوصول (Bearer) حين توفّره الجلسة. حاسم خلف بوّابة
// الإنتاج (auth_request على /api/v1/) — وبالأخصّ نقاط POST (إنشاء مهمّة/توصية) المحميّة
// بـrequire_permission: بدون الترويسة تُرجِع 401/403. الطلبات هنا عبر fetch فتقبلها مباشرةً.
export function weatherFetchHeaders(): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json' };
  const tok = getAccessToken();
  if (tok) h.Authorization = `Bearer ${tok}`;
  return h;
}

// ترويسات JSON لطلبات POST (تُضيف Content-Type فوق ترويسات المصادقة).
export function weatherJsonHeaders(): Record<string, string> {
  return { ...weatherFetchHeaders(), 'Content-Type': 'application/json' };
}

export type WeatherLayerKey =
  | 'temperature'
  | 'wind'
  | 'precipitation'
  | 'et0'
  | 'vpd'
  | 'soil_temperature'
  | 'soil_temperature_10_40cm'
  | 'spraying_drift_risk'
  | 'soil_trafficability'
  | 'heat_stress'
  | 'disease_late_blight'
  | 'disease_downy_mildew'
  | 'disease_stripe_rust'
  | 'soil_moisture'
  | 'pressure'
  | 'clouds'
  | 'operation_spraying'
  | 'operation_harvesting'
  | 'operation_sowing'
  | 'operation_irrigation';

export interface WeatherInterpolationPoint {
  id: string;
  u: number;
  v: number;
  lat?: number;
  lon?: number;
  value: number | null;
  cache_state?: string;
}

export interface WeatherInterpolationPayload {
  mode: string;
  quality: 'smooth' | 'partial' | string;
  point_count: number;
  average_value?: number | null;
  points: WeatherInterpolationPoint[];
}

export interface WeatherTilePayload {
  layer: WeatherLayerKey;
  value: number | null;
  unit: string;
  source?: string;
  sample?: Record<string, unknown>;
  operation?: { score: number; suitability: string; limiting_factors: string[] };
  interpolation?: WeatherInterpolationPayload | null;
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

// مخطط الألوان (palette) للطبقة النشطة: 'coldwarm' هو السلّم الافتراضيّ لكلّ طبقة (cfg.stops)،
// و'rainbow' سلّم طيفيّ موحّد (أزرق→سماوي→أخضر→أصفر→برتقالي→أحمر) يُطبَّق على نطاق القيمة كاملاً.
export type WeatherPalette = 'coldwarm' | 'rainbow';

// سلّم قوس قزح المشترك: يُستعمل لكلّ الطبقات عند اختيار 'rainbow'.
const RAINBOW_STOPS: string[] = ['#2563eb', '#22d3ee', '#22c55e', '#eab308', '#f97316', '#ef4444'];

export const WEATHER_PALETTES: Array<{ key: WeatherPalette; label: string }> = [
  { key: 'coldwarm', label: 'بارد/دافئ' },
  { key: 'rainbow', label: 'قوس قزح' },
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
  { key: 'soil_temperature_10_40cm', labelAr: 'حرارة التربة 10-40 سم', shortAr: '10-40سم', unit: '°C', min: 0, max: 45, stops: ['#1e3a8a', '#2563eb', '#38bdf8', '#22c55e', '#eab308', '#f97316', '#dc2626'] },
  { key: 'spraying_drift_risk', labelAr: 'خطر انجراف الرش', shortAr: 'انجراف', unit: '0..1', min: 0, max: 1, stops: ['#22c55e', '#a3e635', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] },
  { key: 'soil_trafficability', labelAr: 'صلاحية مرور الآليات', shortAr: 'مرور', unit: '0..1', min: 0, max: 1, stops: ['#7f1d1d', '#ef4444', '#f97316', '#eab308', '#a3e635', '#22c55e'] },
  { key: 'heat_stress', labelAr: 'الإجهاد الحراري', shortAr: 'إجهاد', unit: '0..1', min: 0, max: 1, stops: ['#22c55e', '#a3e635', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] },
  { key: 'disease_late_blight', labelAr: 'نافذة اللفحة المتأخّرة (البطاطس)', shortAr: 'لفحة', unit: '%', min: 0, max: 1, stops: ['#22c55e', '#a3e635', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] },
  { key: 'disease_downy_mildew', labelAr: 'نافذة البياض الزغبيّ (العنب)', shortAr: 'بياض', unit: '%', min: 0, max: 1, stops: ['#22c55e', '#a3e635', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] },
  { key: 'disease_stripe_rust', labelAr: 'نافذة الصدأ المخطّط (القمح)', shortAr: 'صدأ', unit: '%', min: 0, max: 1, stops: ['#22c55e', '#a3e635', '#eab308', '#f97316', '#ef4444', '#7f1d1d'] },
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
  { label: 'تربة 10-40 سم', layer: 'soil_temperature_10_40cm', note: 'مطابق بصرياً لوضع 10-40 cm down' },
  { label: 'خطر انجراف الرش', layer: 'spraying_drift_risk', note: 'رياح + هبّات + VPD + مطر' },
  { label: 'مرور الآليات', layer: 'soil_trafficability', note: 'رطوبة التربة + مطر حديث' },
  { label: 'الإجهاد الحراري', layer: 'heat_stress', note: 'حرارة + رطوبة نسبية' },
  { label: 'نافذة اللفحة المتأخّرة', layer: 'disease_late_blight', note: 'حرارة 10-24° + رطوبة عالية + بلل' },
  { label: 'نافذة البياض الزغبيّ', layer: 'disease_downy_mildew', note: 'حرارة 18-25° + مطر ≈10مم + رطوبة' },
  { label: 'نافذة الصدأ المخطّط', layer: 'disease_stripe_rust', note: 'حرارة 7-15° + ندى/رطوبة عالية' },
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

// يختار سلسلة الألوان حسب المخطط المحدّد: coldwarm = سلّم الطبقة الأصليّ، rainbow = السلّم الطيفيّ الموحّد.
export function paletteStops(cfg: WeatherLayerConfig, palette: WeatherPalette = 'coldwarm'): string[] {
  return palette === 'rainbow' ? RAINBOW_STOPS : cfg.stops;
}

export function colorAt(value: number | null | undefined, cfg: WeatherLayerConfig, offset = 0, palette: WeatherPalette = 'coldwarm'): string {
  const stops = paletteStops(cfg, palette);
  const f = clamp01(layerFactor(value, cfg) + offset);
  const scaled = f * (stops.length - 1);
  const i = Math.max(0, Math.min(stops.length - 2, Math.floor(scaled)));
  return lerpHex(stops[i], stops[i + 1], scaled - i);
}

export function sampleNum(sample: Record<string, unknown> | undefined, key: string): number | null {
  const value = sample?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

// رمب خطّي 0..1 يطابق _ramp في الواجهة الخلفية.
function ramp(value: number, low: number, high: number): number {
  if (high <= low) return value >= high ? 1 : 0;
  return clamp01((value - low) / (high - low));
}

// خطر انجراف الرش 0..1 (يطابق _spraying_drift_risk_value الخلفي): رياح + هبّات + VPD،
// مع مطر فعّال (>0.1مم) يرفعه إلى 1.0.
function sprayingDriftRisk(sample: Record<string, unknown> | undefined): number | null {
  const wind = sampleNum(sample, 'wind_speed_10m_kmh');
  const gust = sampleNum(sample, 'wind_gusts_10m_kmh');
  const vpd = sampleNum(sample, 'vapour_pressure_deficit_kpa');
  const rain = sampleNum(sample, 'precipitation_mm');
  if (wind == null && gust == null && vpd == null) return null;
  if (rain != null && rain > 0.1) return 1;
  const parts: Array<[number, number]> = [];
  if (wind != null) parts.push([ramp(wind, 6, 22), 0.5]);
  if (gust != null) parts.push([ramp(gust, 15, 35), 0.3]);
  if (vpd != null) parts.push([ramp(vpd, 1.2, 3.5), 0.2]);
  const total = parts.reduce((s, [, w]) => s + w, 0);
  if (total <= 0) return null;
  return Math.min(1, parts.reduce((s, [v, w]) => s + v * w, 0) / total);
}

// صلاحية مرور الآليات 0..1 (يطابق _soil_trafficability_value): الأعلى = أكثر أماناً.
function soilTrafficability(sample: Record<string, unknown> | undefined): number | null {
  const soilM =
    sampleNum(sample, 'soil_moisture_1_to_3cm_m3m3') ?? sampleNum(sample, 'soil_moisture_0_to_1cm_m3m3');
  if (soilM == null) return null;
  let score = 1 - ramp(soilM, 0.22, 0.4);
  const rain = sampleNum(sample, 'precipitation_mm');
  if (rain != null && rain > 5) score = Math.min(score, 0.5);
  return clamp01(score);
}

// الإجهاد الحراري 0..1 (يطابق _heat_stress_value): حرارة + تعزيز رطوبة نسبية.
function heatStress(sample: Record<string, unknown> | undefined): number | null {
  const temp = sampleNum(sample, 'temperature_2m_c');
  if (temp == null) return null;
  const rh = sampleNum(sample, 'relative_humidity_2m_pct');
  const base = ramp(temp, 28, 42);
  const humidityBoost = rh != null && rh > 60 ? ramp(rh, 60, 100) * 0.25 : 0;
  return clamp01(base + humidityBoost);
}

// نطاق حرارة هضبيّ 0..1 يطابق _temp_band الخلفي: 0 خارج [loOff,hiOff]، 1 داخل [loOn,hiOn].
function tempBand(temp: number, loOff: number, loOn: number, hiOn: number, hiOff: number): number {
  return Math.min(ramp(temp, loOff, loOn), 1 - ramp(temp, hiOn, hiOff));
}

// نافذة اللفحة المتأخّرة (Phytophthora infestans) 0..1، يطابق _disease_late_blight_value الخلفي.
function diseaseLateBlight(sample: Record<string, unknown> | undefined): number | null {
  const temp = sampleNum(sample, 'temperature_2m_c');
  if (temp == null) return null;
  const rh = sampleNum(sample, 'relative_humidity_2m_pct');
  const vpd = sampleNum(sample, 'vapour_pressure_deficit_kpa');
  if (rh == null && vpd == null) return null;
  const band = tempBand(temp, 10, 14, 20, 24);
  const humidity = rh != null ? ramp(rh, 88, 96) : 1 - ramp(vpd as number, 0.1, 0.6);
  const rain = sampleNum(sample, 'precipitation_mm');
  const wetness = rain != null && rain > 0.1 ? 1 : 0;
  return clamp01(band * (0.7 * humidity + 0.3 * wetness));
}

// نافذة البياض الزغبيّ (Plasmopara viticola) 0..1، يطابق _disease_downy_mildew_value الخلفي.
function diseaseDownyMildew(sample: Record<string, unknown> | undefined): number | null {
  const temp = sampleNum(sample, 'temperature_2m_c');
  if (temp == null) return null;
  const rh = sampleNum(sample, 'relative_humidity_2m_pct');
  const rain = sampleNum(sample, 'precipitation_mm');
  if (rh == null && rain == null) return null;
  const band = tempBand(temp, 13, 18, 25, 30);
  const rainMoisture = rain != null ? ramp(rain, 2, 10) : 0;
  const humidity = rh != null ? ramp(rh, 80, 95) : 0;
  return clamp01(band * Math.max(rainMoisture, 0.6 * humidity));
}

// نافذة الصدأ المخطّط (Puccinia striiformis) 0..1، يطابق _disease_stripe_rust_value الخلفي.
function diseaseStripeRust(sample: Record<string, unknown> | undefined): number | null {
  const temp = sampleNum(sample, 'temperature_2m_c');
  if (temp == null) return null;
  const rh = sampleNum(sample, 'relative_humidity_2m_pct');
  const vpd = sampleNum(sample, 'vapour_pressure_deficit_kpa');
  if (rh == null && vpd == null) return null;
  const band = tempBand(temp, 2, 7, 13, 22);
  const wetness = rh != null ? ramp(rh, 85, 95) : 1 - ramp(vpd as number, 0.1, 0.5);
  return clamp01(band * wetness);
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
    case 'soil_temperature_10_40cm': return sampleNum(sample, 'soil_temperature_10_40cm_c') ?? sampleNum(sample, 'soil_temperature_18cm_c') ?? sampleNum(sample, 'soil_temperature_6cm_c');
    case 'spraying_drift_risk': return sprayingDriftRisk(sample);
    case 'soil_trafficability': return soilTrafficability(sample);
    case 'heat_stress': return heatStress(sample);
    case 'disease_late_blight': return diseaseLateBlight(sample);
    case 'disease_downy_mildew': return diseaseDownyMildew(sample);
    case 'disease_stripe_rust': return diseaseStripeRust(sample);
    case 'soil_moisture': return sampleNum(sample, 'soil_moisture_1_to_3cm_m3m3') ?? sampleNum(sample, 'soil_moisture_0_to_1cm_m3m3');
    case 'pressure': return sampleNum(sample, 'pressure_msl_hpa');
    case 'clouds': return sampleNum(sample, 'cloud_cover_pct');
    default: return fallback.tempC;
  }
}

export function windDirection(sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number | null {
  // صادق: لا قيمة وهميّة. اتّجاه حقيقيّ (Open-Meteo، أو MET.no احتياطاً خادميّاً) ⇒
  // اتّجاه الحقل الحاليّ ⇒ null (فلا تُرسَم أسهم بدل اتّجاه مُلفَّق 315°).
  return sampleNum(sample, 'wind_direction_10m_deg') ?? fallback.windDirectionDeg ?? null;
}

export function windSpeed(sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number {
  return sampleNum(sample, 'wind_speed_10m_kmh') ?? fallback.windSpeedKmh ?? 12;
}

export function safeMod(value: number, modulo: number): number {
  return ((value % modulo) + modulo) % modulo;
}

