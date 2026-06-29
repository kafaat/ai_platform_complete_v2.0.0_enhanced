// ═══════════════════════════════════════════════════════════════
// SAHOOL — MapHub Weather Engine
// Open-Meteo is the data source; SAHOOL renders GridLayer tiles, animation,
// layer controls, legend, time selector, and agronomic probe popups.
// ═══════════════════════════════════════════════════════════════
import { useMap } from 'react-leaflet';
import L from 'leaflet';
import { useEffect, useMemo, useState } from 'react';
import type { WeatherMarker } from '../OverlayMarkers';
import { getAccessToken } from '../../../lib/authStorage';

// ترويسات طلب الطقس: بوّابة الإنتاج (nginx /api/v1/) خلف auth_request تتطلّب JWT؛
// طلب fetch (لا <img>) يحمل الترويسة، فنُرفِق Authorization كي تعمل الطبقة في الإنتاج.
function weatherFetchHeaders(): Record<string, string> {
  const h: Record<string, string> = { Accept: 'application/json' };
  const tok = getAccessToken();
  if (tok) h.Authorization = `Bearer ${tok}`;
  return h;
}

const WEATHER_TILE_SIZE = 256;

type WeatherLayerKey =
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

interface WeatherTilePayload {
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

type WeatherTimeKey = 'now' | '+1h' | '+3h' | '+6h' | '+12h' | '+24h' | '+48h';
const WEATHER_TIMES: Array<{ key: WeatherTimeKey; label: string }> = [
  { key: 'now', label: 'الآن' },
  { key: '+1h', label: '+1س' },
  { key: '+3h', label: '+3س' },
  { key: '+6h', label: '+6س' },
  { key: '+12h', label: '+12س' },
  { key: '+24h', label: '+24س' },
  { key: '+48h', label: '+48س' },
];

const WEATHER_MODELS: Array<{ key: string; label: string }> = [
  { key: 'best_match', label: 'الأفضل تلقائياً' },
  { key: 'gfs_seamless', label: 'GFS' },
  { key: 'ecmwf_ifs04', label: 'ECMWF IFS' },
];

interface WeatherLayerConfig {
  key: WeatherLayerKey;
  labelAr: string;
  shortAr: string;
  unit: string;
  min: number;
  max: number;
  stops: string[];
}

const WEATHER_LAYERS: WeatherLayerConfig[] = [
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

const WEATHER_PRESETS: Array<{ label: string; layer: WeatherLayerKey; note: string }> = [
  { label: 'وضع الرش', layer: 'operation_spraying', note: 'رياح + مطر + حرارة + رطوبة' },
  { label: 'وضع الري', layer: 'operation_irrigation', note: 'VPD + رطوبة التربة + المطر' },
  { label: 'وضع الحصاد', layer: 'operation_harvesting', note: 'رطوبة + مطر + رياح' },
  { label: 'وضع البذار', layer: 'operation_sowing', note: 'حرارة ورطوبة التربة' },
];

const DEFAULT_LAYER: WeatherLayerKey = 'temperature';

function layerConfig(key: WeatherLayerKey): WeatherLayerConfig {
  return WEATHER_LAYERS.find((l) => l.key === key) ?? WEATHER_LAYERS[0];
}

function isOperationLayer(layer: WeatherLayerKey): boolean {
  return layer.startsWith('operation_');
}

function operationFromLayer(layer: WeatherLayerKey): string {
  return layer.replace('operation_', '');
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function layerFactor(value: number | null | undefined, cfg: WeatherLayerConfig): number {
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

function colorAt(value: number | null | undefined, cfg: WeatherLayerConfig, offset = 0): string {
  const stops = cfg.stops;
  const f = clamp01(layerFactor(value, cfg) + offset);
  const scaled = f * (stops.length - 1);
  const i = Math.max(0, Math.min(stops.length - 2, Math.floor(scaled)));
  return lerpHex(stops[i], stops[i + 1], scaled - i);
}

function sampleNum(sample: Record<string, unknown> | undefined, key: string): number | null {
  const value = sample?.[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function getLayerValue(layer: WeatherLayerKey, sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number | null {
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

function windDirection(sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number {
  return sampleNum(sample, 'wind_direction_10m_deg') ?? fallback.windDirectionDeg ?? 315;
}

function windSpeed(sample: Record<string, unknown> | undefined, fallback: WeatherMarker): number {
  return sampleNum(sample, 'wind_speed_10m_kmh') ?? fallback.windSpeedKmh ?? 12;
}

function weatherTileSvg(marker: WeatherMarker, coords: L.Coords, layer: WeatherLayerKey, payload?: WeatherTilePayload, showWind = true): string {
  const cfg = layerConfig(layer);
  const sample = payload?.sample;
  const value = payload?.operation?.score ?? payload?.value ?? getLayerValue(layer, sample, marker);
  const speed = windSpeed(sample, marker);
  const dir = windDirection(sample, marker);
  const seedA = ((coords.x * 19 + coords.y * 37 + coords.z * 11) % 100) / 100;
  const seedB = ((coords.x * 43 - coords.y * 13 + coords.z * 29) % 100) / 100;
  const c0 = colorAt(value, cfg, -0.26 + seedA * 0.13);
  const c1 = colorAt(value, cfg, -0.07 + seedB * 0.11);
  const c2 = colorAt(value, cfg, 0.10 + seedA * 0.09);
  const c3 = colorAt(value, cfg, 0.25);
  const gradId = `sahool-weather-${layer}-${coords.x}-${coords.y}-${coords.z}`;
  const noiseId = `sahool-noise-${layer}-${coords.x}-${coords.y}-${coords.z}`;
  const strokeW = Math.max(1, Math.min(6, 1.15 + speed / 21));
  const lines: string[] = [];
  const phase = Math.abs((coords.x * 17 + coords.y * 31 + coords.z * 7) % 97);
  for (let row = -40; row <= 296; row += 26) {
    for (let col = -72; col <= 328; col += 54) {
      const wobble = ((row * 3 + col * 5 + phase) % 44) - 22;
      const length = 34 + ((row + col + phase) % 22);
      const mid = length * 0.62;
      lines.push(`<path d="M ${col} ${row} C ${col + mid * 0.45} ${row + wobble * 0.12}, ${col + mid} ${row + 11}, ${col + length} ${row - 2}" fill="none" stroke="rgba(255,255,255,0.82)" stroke-width="${strokeW}" stroke-linecap="round" stroke-dasharray="${18 + speed * 0.45} ${14 + speed * 0.28}"><animate attributeName="stroke-dashoffset" from="64" to="0" dur="${Math.max(1.4, 3.9 - speed / 16).toFixed(1)}s" repeatCount="indefinite" /></path>`);
    }
  }
  const shown = value == null ? '—' : (isOperationLayer(layer) ? `${Math.round(Number(value) * 100)}` : Number(value).toFixed(layer === 'soil_moisture' ? 2 : 1));
  const cacheState = payload?.cache_state || 'client_fallback';
  const isStale = cacheState === 'stale_fallback' || cacheState === 'stale';
  const statusLabel = isStale ? 'بيانات مخزنة' : cacheState === 'client_fallback' ? 'تقديري' : '';
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${WEATHER_TILE_SIZE}" height="${WEATHER_TILE_SIZE}" viewBox="0 0 256 256" preserveAspectRatio="none" role="img" aria-label="${cfg.labelAr}: ${shown} ${cfg.unit}">
    <defs>
      <linearGradient id="${gradId}" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="${c0}" stop-opacity="0.45"/>
        <stop offset="38%" stop-color="${c1}" stop-opacity="0.53"/>
        <stop offset="72%" stop-color="${c2}" stop-opacity="0.49"/>
        <stop offset="100%" stop-color="${c3}" stop-opacity="0.43"/>
      </linearGradient>
      <filter id="${noiseId}"><feTurbulence type="fractalNoise" baseFrequency="0.018 0.042" numOctaves="2" seed="${Math.round(seedA * 50 + 1)}"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 0.10"/></feComponentTransfer></filter>
    </defs>
    <rect width="256" height="256" fill="url(#${gradId})"/>
    <rect width="256" height="256" filter="url(#${noiseId})" opacity="0.55"/>
    <g opacity="0.20"><path d="M-20 202 C 60 170, 110 225, 176 184 S 268 156, 296 184" fill="none" stroke="rgba(13,22,17,0.48)" stroke-width="9"/><path d="M-12 82 C 46 112, 92 52, 144 76 S 234 124, 292 78" fill="none" stroke="rgba(255,255,255,0.26)" stroke-width="5"/></g>
    ${showWind ? `<g transform="rotate(${dir} 128 128)" opacity="${layer === 'wind' ? 0.92 : 0.68}">${lines.join('')}</g>` : ''}
    <text x="246" y="236" text-anchor="end" fill="rgba(255,255,255,.75)" font-family="system-ui" font-size="13" font-weight="700">${cfg.shortAr} ${shown}${isOperationLayer(layer) ? '%' : cfg.unit}</text>
    ${statusLabel ? `<rect x="8" y="10" rx="8" ry="8" width="82" height="23" fill="rgba(15,23,42,.68)"/><text x="49" y="26" text-anchor="middle" fill="rgba(255,255,255,.88)" font-family="system-ui" font-size="11" font-weight="800">${statusLabel}</text>` : ''}
  </svg>`;
}

function loadingTileSvg(layer: WeatherLayerKey): string {
  const cfg = layerConfig(layer);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" fill="rgba(15,23,42,.20)"/><text x="128" y="128" text-anchor="middle" fill="rgba(255,255,255,.75)" font-family="system-ui" font-size="14">${cfg.shortAr}…</text></svg>`;
}

function tileDataUrl(coords: L.Coords, layer: WeatherLayerKey, time: WeatherTimeKey, model: string): string {
  if (isOperationLayer(layer)) {
    return `/api/v1/weather/operation-tile-data/${coords.z}/${coords.x}/${coords.y}?operation=${encodeURIComponent(operationFromLayer(layer))}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}`;
  }
  return `/api/v1/weather/tile-data/${coords.z}/${coords.x}/${coords.y}?layer=${encodeURIComponent(layer)}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}`;
}

function createWeatherWindGridLayer(marker: WeatherMarker, layer: WeatherLayerKey, time: WeatherTimeKey, model: string, opacity: number, showWind: boolean): L.GridLayer {
  const WeatherWindGrid = L.GridLayer.extend({
    createTile(coords: L.Coords) {
      const tile = L.DomUtil.create('div', 'sahool-weather-wind-tile');
      tile.setAttribute('dir', 'rtl');
      tile.style.width = `${WEATHER_TILE_SIZE}px`;
      tile.style.height = `${WEATHER_TILE_SIZE}px`;
      tile.style.pointerEvents = 'none';
      tile.style.overflow = 'hidden';
      tile.style.willChange = 'transform';
      tile.innerHTML = loadingTileSvg(layer);
      fetch(tileDataUrl(coords, layer, time, model), { headers: weatherFetchHeaders() })
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((payload: WeatherTilePayload) => { tile.innerHTML = weatherTileSvg(marker, coords, layer, payload, showWind); })
        .catch(() => { tile.innerHTML = weatherTileSvg(marker, coords, layer, undefined, showWind); });
      return tile;
    },
  });
  return new (WeatherWindGrid as unknown as { new(options?: L.GridLayerOptions): L.GridLayer })({ tileSize: WEATHER_TILE_SIZE, opacity, pane: 'overlayPane', updateWhenIdle: false, updateWhenZooming: true, keepBuffer: 3 });
}

function gradientCss(cfg: WeatherLayerConfig): string {
  return cfg.stops.map((c, i) => `${c} ${Math.round((i / Math.max(1, cfg.stops.length - 1)) * 100)}%`).join(',');
}

function weatherControlHtml(layer: WeatherLayerKey, marker: WeatherMarker, time: WeatherTimeKey, model: string, opacity: number, showWind: boolean): string {
  const cfg = layerConfig(layer);
  const temp = marker.tempC != null ? `${Math.round(marker.tempC)}°م` : '—';
  const wind = marker.windSpeedKmh != null ? `${Math.round(marker.windSpeedKmh)} كم/س` : '—';
  const dir = marker.windDirectionDeg != null ? `${Math.round(marker.windDirectionDeg)}°` : '—';
  const max = cfg.max.toString();
  const mid = ((cfg.min + cfg.max) / 2).toFixed(cfg.key === 'soil_moisture' ? 2 : 0);
  const min = cfg.min.toString();
  return `<div dir="rtl" class="sahool-weather-layer-control" style="background:rgba(13,22,17,.84);border:1px solid rgba(226,232,240,.18);border-radius:14px;color:#e2e8f0;padding:10px 9px;font:12px/1.35 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 8px 22px rgba(0,0,0,.32);backdrop-filter:blur(7px);min-width:168px;max-width:210px;">
    <div style="font-weight:900;margin-bottom:7px;text-align:center">طبقات Open‑Meteo + SAHOOL</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:7px">
      ${WEATHER_PRESETS.map((p) => `<button type="button" data-layer="${p.layer}" title="${p.note}" style="border:1px solid ${p.layer === layer ? 'rgba(255,255,255,.78)' : 'rgba(255,255,255,.18)'};border-radius:9px;background:${p.layer === layer ? 'rgba(22,163,74,.88)' : 'rgba(15,23,42,.62)'};color:#f8fafc;padding:5px 6px;font-weight:800;cursor:pointer">${p.label}</button>`).join('')}
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:4px;margin-bottom:7px">
      ${WEATHER_TIMES.map((t) => `<button type="button" data-time="${t.key}" style="border:1px solid ${t.key === time ? 'rgba(255,255,255,.72)' : 'rgba(255,255,255,.16)'};border-radius:8px;background:${t.key === time ? 'rgba(37,99,235,.86)' : 'rgba(15,23,42,.56)'};color:#f8fafc;padding:4px 5px;font-weight:700;cursor:pointer">${t.label}</button>`).join('')}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:9px;max-height:154px;overflow:auto;padding-left:2px">
      ${WEATHER_LAYERS.map((l) => `<button type="button" data-layer="${l.key}" style="border:1px solid ${l.key === layer ? 'rgba(255,255,255,.70)' : 'rgba(255,255,255,.18)'};border-radius:9px;background:${l.key === layer ? 'rgba(37,99,235,.86)' : 'rgba(15,23,42,.62)'};color:#f8fafc;padding:5px 6px;font-weight:700;cursor:pointer">${l.shortAr}</button>`).join('')}
    </div>

    <div style="display:grid;grid-template-columns:1fr;gap:6px;margin-bottom:8px">
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>شفافية الطبقة</span><b>${Math.round(opacity * 100)}%</b></label>
      <input type="range" min="35" max="100" value="${Math.round(opacity * 100)}" data-opacity="1" style="width:100%"/>
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>تحريك الرياح</span><input type="checkbox" data-wind-toggle="1" ${showWind ? 'checked' : ''}/></label>
      <select data-model="1" style="width:100%;border-radius:8px;border:1px solid rgba(255,255,255,.22);background:rgba(15,23,42,.70);color:#f8fafc;padding:6px">
        ${WEATHER_MODELS.map((m) => `<option value="${m.key}" ${m.key === model ? 'selected' : ''}>${m.label}</option>`).join('')}
      </select>
    </div>
    <div style="display:flex;gap:8px;align-items:stretch;justify-content:center">
      <div style="width:16px;height:142px;border-radius:999px;border:1px solid rgba(255,255,255,.28);background:linear-gradient(to top,${gradientCss(cfg)});"></div>
      <div style="display:flex;flex-direction:column;justify-content:space-between;text-align:right;color:#f8fafc"><span>${max}${cfg.unit}</span><span>${mid}${cfg.unit}</span><span>${min}${cfg.unit}</span></div>
    </div>
    <div style="margin-top:8px;border-top:1px solid rgba(255,255,255,.16);padding-top:7px;color:#cbd5e1">
      <div>المصدر: <b>Open‑Meteo</b></div><div>الرسم/القرار: <b>SAHOOL</b></div><div>الزمن: <b>${time}</b> · النموذج: <b>${model}</b></div><div>حرارة الحقل: <b>${temp}</b></div><div>الرياح: <b>${wind}</b> · <b>${dir}</b></div><div style="margin-top:5px;color:#bfdbfe">انقر على الخريطة لقراءة Probe زراعي.</div>
    </div>
  </div>`;
}

function createWeatherControl(layer: WeatherLayerKey, marker: WeatherMarker, time: WeatherTimeKey, model: string, opacity: number, showWind: boolean, onLayerChange: (layer: WeatherLayerKey) => void, onTimeChange: (time: WeatherTimeKey) => void, onModelChange: (model: string) => void, onOpacityChange: (opacity: number) => void, onWindToggle: (show: boolean) => void): L.Control {
  const WeatherControl = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create('div', 'sahool-weather-layer-control-wrap');
      div.innerHTML = weatherControlHtml(layer, marker, time, model, opacity, showWind);
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelectorAll<HTMLButtonElement>('button[data-layer]').forEach((btn) => {
        btn.onclick = () => onLayerChange(btn.dataset.layer as WeatherLayerKey);
      });
      div.querySelectorAll<HTMLButtonElement>('button[data-time]').forEach((btn) => {
        btn.onclick = () => onTimeChange(btn.dataset.time as WeatherTimeKey);
      });
      const modelSelect = div.querySelector<HTMLSelectElement>('select[data-model]');
      if (modelSelect) modelSelect.onchange = () => onModelChange(modelSelect.value);
      const opacityInput = div.querySelector<HTMLInputElement>('input[data-opacity]');
      if (opacityInput) opacityInput.oninput = () => onOpacityChange(Math.max(0.35, Math.min(1, Number(opacityInput.value) / 100)));
      const windToggle = div.querySelector<HTMLInputElement>('input[data-wind-toggle]');
      if (windToggle) windToggle.onchange = () => onWindToggle(windToggle.checked);
      return div;
    },
  });
  return new WeatherControl({ position: 'topleft' });
}


export function WeatherRasterOverlay({ marker }: { marker: WeatherMarker | null }) {
  const map = useMap();
  const [layer, setLayer] = useState<WeatherLayerKey>(DEFAULT_LAYER);
  const [time, setTime] = useState<WeatherTimeKey>('now');
  const [model, setModel] = useState('best_match');
  const [opacity, setOpacity] = useState(0.86);
  const [showWind, setShowWind] = useState(true);
  const stableMarker = useMemo(() => marker, [marker]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    const grid = createWeatherWindGridLayer(stableMarker, layer, time, model, opacity, showWind).addTo(map);
    const container = grid.getContainer();
    container?.classList.add('sahool-weather-wind-grid-layer');
    if (container) { container.style.mixBlendMode = 'screen'; container.style.pointerEvents = 'none'; container.style.zIndex = '450'; container.style.opacity = String(opacity); }
    return () => { grid.remove(); };
  }, [map, stableMarker, layer, time, model, opacity, showWind]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    const control = createWeatherControl(layer, stableMarker, time, model, opacity, showWind, setLayer, setTime, setModel, setOpacity, setShowWind).addTo(map);
    return () => { control.remove(); };
  }, [map, stableMarker, layer, time, model, opacity, showWind]);

  useEffect(() => {
    if (!stableMarker) return undefined;
    const onClick = (ev: L.LeafletMouseEvent) => {
      const { lat, lng } = ev.latlng;
      const popup = L.popup({ maxWidth: 330 })
        .setLatLng(ev.latlng)
        .setContent('<div dir="rtl" style="min-width:230px;font:13px system-ui">جاري قراءة الطقس الزراعي…</div>')
        .openOn(map);
      const selectedOperation = isOperationLayer(layer) ? operationFromLayer(layer) : 'spraying';
      const probeUrl = `/api/v1/weather/probe?lat=${lat.toFixed(5)}&lon=${lng.toFixed(5)}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}`;
      const windowUrl = `/api/v1/weather/operation-window?lat=${lat.toFixed(5)}&lon=${lng.toFixed(5)}&operation=${encodeURIComponent(selectedOperation)}&hours=0,1,3,6,12,24,48&model=${encodeURIComponent(model)}`;
      const planUrl = `/api/v1/weather/operation-plan?lat=${lat.toFixed(5)}&lon=${lng.toFixed(5)}&operations=spraying,irrigation,harvesting,sowing&hours=0,1,3,6,12,24,48&model=${encodeURIComponent(model)}`;
      Promise.all([
        fetch(probeUrl, { headers: weatherFetchHeaders() }).then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status))))),
        fetch(windowUrl, { headers: weatherFetchHeaders() }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
        fetch(planUrl, { headers: weatherFetchHeaders() }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
      ])
        .then(([data, windowData, planData]) => {
          const s = data.sample || {};
          const ops = data.operations || {};
          const opLine = (name: string, ar: string) => {
            const o = ops[name];
            if (!o) return '';
            return `<div><b>${ar}:</b> ${Math.round((o.score ?? 0) * 100)}% · ${o.suitability}</div>`;
          };
          const best = windowData?.best;
          const bestLine = best?.operation ? `<hr/><div><b>أفضل نافذة ${selectedOperation}:</b> ${best.time} · ${Math.round((best.operation.score ?? 0) * 100)}% · ${best.operation.suitability}</div><div style="color:#475569">${windowData.advice_ar ?? ''}</div>` : '';
          const planOps = Array.isArray(planData?.operations) ? planData.operations.slice(0, 4) : [];
          const planLine = planOps.length ? `<hr/><div><b>خطة العمليات حسب الطقس</b></div>${planOps.map((item: any) => `<div style="display:flex;justify-content:space-between;gap:8px"><span>${item.label_ar ?? item.operation}</span><b>${item.best?.time ?? '—'} · ${item.priority ?? 0}%</b></div>`).join('')}${planData?.alerts_ar?.length ? `<div style="margin-top:5px;color:#b45309">${planData.alerts_ar.slice(0, 2).join(' · ')}</div>` : ''}` : '';
          popup.setContent(`<div dir="rtl" style="min-width:285px;font:13px/1.55 system-ui;color:#0f172a">
            <b>قراءة طقس زراعية</b><br/>
            الحرارة: <b>${s.temperature_2m_c ?? '—'}°م</b><br/>
            الرياح: <b>${s.wind_speed_10m_kmh ?? '—'} كم/س</b> · اتجاه <b>${s.wind_direction_10m_deg ?? '—'}°</b><br/>
            المطر: <b>${s.precipitation_mm ?? '—'} مم</b> · VPD: <b>${s.vapour_pressure_deficit_kpa ?? '—'} kPa</b><br/>
            ET₀: <b>${s.et0_fao_evapotranspiration_mm ?? '—'} مم</b> · رطوبة التربة: <b>${s.soil_moisture_1_to_3cm_m3m3 ?? '—'}</b><hr/>
            ${opLine('spraying', 'الرش')}
            ${opLine('irrigation', 'الري')}
            ${opLine('harvesting', 'الحصاد')}
            ${opLine('sowing', 'البذار')}
            ${bestLine}
            ${planLine}
            <hr/>
            حالة البيانات: <b>${data.cache_state ?? 'live'}</b>${data.cache_age_s ? ` · عمرها ${data.cache_age_s}ث` : ''}
          </div>`);
        })
        .catch(() => { popup.setContent('<div dir="rtl">تعذر جلب قراءة Open‑Meteo لهذه النقطة.</div>'); });
    };
    map.on('click', onClick);
    return () => { map.off('click', onClick); };
  }, [map, stableMarker, time, model, layer]);

  return null;
}

