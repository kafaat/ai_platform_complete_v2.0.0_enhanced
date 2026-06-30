// ═══════════════════════════════════════════════════════════════
// SAHOOL Weather Tile Layer
// Renders Open-Meteo-backed weather/agronomic data as Leaflet GridLayer SVG tiles.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import type { WeatherMarker } from '../OverlayMarkers';
import {
  WEATHER_TILE_SIZE,
  type WeatherLayerKey,
  type WeatherTilePayload,
  type WeatherTimeKey,
  type WindDensity,
  type WeatherPalette,
  layerConfig,
  isOperationLayer,
  operationFromLayer,
  clamp01,
  colorAt,
  getLayerValue,
  windDirection,
  windSpeed,
  safeMod,
  weatherFetchHeaders,
} from './weatherLayerDefinitions';


function interpolationColor(payload: WeatherTilePayload | undefined, cfg: ReturnType<typeof layerConfig>, id: string, fallback: number | null, palette: WeatherPalette = 'coldwarm'): string {
  const point = payload?.interpolation?.points?.find((p) => p.id === id);
  return colorAt(typeof point?.value === 'number' ? point.value : fallback, cfg, 0, palette);
}

function interpolationValue(payload: WeatherTilePayload | undefined, fallback: number | null): number | null {
  const avg = payload?.interpolation?.average_value;
  return typeof avg === 'number' && Number.isFinite(avg) ? avg : fallback;
}

export function weatherTileSvg(
  marker: WeatherMarker,
  coords: L.Coords,
  layer: WeatherLayerKey,
  payload?: WeatherTilePayload,
  showWind = true,
  windDensity: WindDensity = 'auto',
  palette: WeatherPalette = 'coldwarm',
): string {
  const cfg = layerConfig(layer);
  const sample = payload?.sample;
  const rawValue = payload?.operation?.score ?? payload?.value ?? getLayerValue(layer, sample, marker);
  const value = interpolationValue(payload, rawValue);
  const speed = windSpeed(sample, marker);
  const dir = windDirection(sample, marker);
  const seedA = safeMod(coords.x * 19 + coords.y * 37 + coords.z * 11, 100) / 100;
  const seedB = safeMod(coords.x * 43 - coords.y * 13 + coords.z * 29, 100) / 100;
  const o0 = -0.30 + seedA * 0.12;
  const o1 = -0.09 + seedB * 0.10;
  const o2 = 0.12 + seedA * 0.10;
  const o3 = 0.30;
  const c0 = colorAt(value, cfg, o0, palette);
  const c1 = colorAt(value, cfg, o1, palette);
  const c2 = colorAt(value, cfg, o2, palette);
  const c3 = colorAt(value, cfg, o3, palette);
  // ألوان وسطيّة على نفس منحنى الطبقة لتنعيم القفزات بين المراحل (تقليل الخطوات الصلبة).
  const cMid01 = colorAt(value, cfg, (o0 + o1) / 2, palette);
  const cMid12 = colorAt(value, cfg, (o1 + o2) / 2, palette);
  const cMid23 = colorAt(value, cfg, (o2 + o3) / 2, palette);
  const cNW = interpolationColor(payload, cfg, 'nw', value, palette);
  const cNE = interpolationColor(payload, cfg, 'ne', value, palette);
  const cSW = interpolationColor(payload, cfg, 'sw', value, palette);
  const cSE = interpolationColor(payload, cfg, 'se', value, palette);
  const hasInterpolation = !!payload?.interpolation?.points?.length;
  const gradId = `sahool-weather-${layer}-${coords.x}-${coords.y}-${coords.z}`;
  const heatId = `sahool-heat-${layer}-${coords.x}-${coords.y}-${coords.z}`;
  const noiseId = `sahool-noise-${layer}-${coords.x}-${coords.y}-${coords.z}`;
  const speedFactor = clamp01(speed / 55);
  // الجوال (low/medium) يرسم جسيمات أقل وأخفّ لتقليل حمل الـGPU؛ high/auto أقرب للمرجع.
  const particleOpacity = (layer === 'wind' ? 0.92 : 0.70) * (windDensity === 'low' ? 0.60 : windDensity === 'medium' ? 0.78 : 1);
  const strokeW = Math.max(1.05, Math.min(3.8, 1.25 + speed / 28));
  const dash = Math.max(15, Math.min(38, 17 + speed * 0.34));
  const gap = Math.max(13, Math.min(32, 23 - speed * 0.10));
  const duration = Math.max(1.0, 3.8 - speed / 18).toFixed(2);
  const phase = safeMod(coords.x * 17 + coords.y * 31 + coords.z * 7, 97);
  // لون الجسيمات مشتقّ من لون قيمة الطبقة (بارد→أزرق، دافئ→أحمر لطبقة الرياح حسب السرعة)
  // ممزوجاً مع الأبيض لرفع الإضاءة/التباين فوق صور الأقمار. fallback محايد فاتح إذا value=null.
  const particleHex = value == null ? '#dbeafe' : colorAt(value, cfg, 0, palette);
  const pm = /^#([0-9a-f]{6})$/i.exec(particleHex);
  const pInt = pm ? parseInt(pm[1], 16) : 0xdbeafe;
  // ~62% لون الطبقة + 38% أبيض: يبقى ملوّناً مع إضاءة كافية للوضوح فوق صور الأقمار.
  const whiteMix = 0.38;
  const pr = Math.round(((pInt >> 16) & 255) * (1 - whiteMix) + 255 * whiteMix);
  const pg = Math.round(((pInt >> 8) & 255) * (1 - whiteMix) + 255 * whiteMix);
  const pb = Math.round((pInt & 255) * (1 - whiteMix) + 255 * whiteMix);
  const particleRgb = `${pr},${pg},${pb}`;
  const windLines: string[] = [];
  // densityProfile: low/medium (الجوال) أقل صفوف/أعمدة بوضوح لتخفيف الرسم؛ high أكثف.
  const densityProfile = windDensity === 'low'
    ? { rows: layer === 'wind' ? 6 : 4, cols: layer === 'wind' ? 3 : 2 }
    : windDensity === 'medium'
      ? { rows: layer === 'wind' ? 10 : 8, cols: layer === 'wind' ? 5 : 4 }
      : { rows: layer === 'wind' ? 19 : 15, cols: layer === 'wind' ? 9 : 7 };
  const rows = densityProfile.rows;
  const cols = densityProfile.cols;
  for (let r = 0; r < rows; r += 1) {
    const y = -34 + r * (322 / rows);
    for (let c = 0; c < cols; c += 1) {
      const baseX = -74 + c * (404 / cols);
      const jitterX = safeMod(r * 23 + c * 31 + phase * 3, 34) - 17;
      const jitterY = safeMod(r * 17 - c * 19 + phase * 5, 24) - 12;
      const length = 34 + safeMod(r * 7 + c * 11 + phase, 34) + speedFactor * 26;
      const curve = safeMod(r * 13 + c * 17 + phase, 22) - 11;
      const alpha = 0.50 + safeMod(r * 11 + c * 7 + phase, 35) / 100;
      const x = baseX + jitterX;
      const yy = y + jitterY;
      const d = `M ${x.toFixed(1)} ${yy.toFixed(1)} C ${(x + length * 0.30).toFixed(1)} ${(yy + curve * 0.16).toFixed(1)}, ${(x + length * 0.68).toFixed(1)} ${(yy + 9 + curve * 0.12).toFixed(1)}, ${(x + length).toFixed(1)} ${(yy - 2).toFixed(1)}`;
      const dashOff = safeMod(r * 37 + c * 19 + phase, 80);
      const anim = `<animate attributeName="stroke-dashoffset" from="${(80 + speed).toFixed(1)}" to="0" dur="${duration}s" repeatCount="indefinite" />`;
      // الجسم: لون الطبقة الممزوج بالأبيض مع تباين شفافيّة لكلّ خطّ كما كان.
      windLines.push(`<path d="${d}" fill="none" stroke="rgba(${particleRgb},${alpha.toFixed(2)})" stroke-width="${strokeW.toFixed(2)}" stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${gap.toFixed(1)}" stroke-dashoffset="${dashOff}">${anim}</path>`);
      // نواة بيضاء رفيعة على ثلث الخطوط فقط (تكلفة منخفضة) لإبراز التدفّق فوق الصور الداكنة.
      if ((r + c) % 3 === 0) {
        windLines.push(`<path d="${d}" fill="none" stroke="rgba(255,255,255,${(alpha * 0.55).toFixed(2)})" stroke-width="${(strokeW * 0.42).toFixed(2)}" stroke-linecap="round" stroke-dasharray="${dash.toFixed(1)} ${gap.toFixed(1)}" stroke-dashoffset="${dashOff}">${anim}</path>`);
      }
    }
  }
  const shown = value == null ? '—' : (isOperationLayer(layer) ? `${Math.round(Number(value) * 100)}` : Number(value).toFixed(layer === 'soil_moisture' ? 2 : 1));
  const cacheState = payload?.cache_state || 'client_fallback';
  const isStale = cacheState === 'stale_fallback' || cacheState === 'stale';
  const statusLabel = isStale ? 'بيانات مخزنة' : cacheState === 'client_fallback' ? 'تقديري' : (hasInterpolation ? 'ناعم' : '');
  const unit = isOperationLayer(layer) ? '%' : cfg.unit;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${WEATHER_TILE_SIZE}" height="${WEATHER_TILE_SIZE}" viewBox="0 0 256 256" preserveAspectRatio="none" role="img" aria-label="${cfg.labelAr}: ${shown} ${unit}">
    <defs>
      <radialGradient id="${heatId}" cx="${30 + seedA * 48}%" cy="${26 + seedB * 56}%" r="104%">
        <stop offset="0%" stop-color="${c3}" stop-opacity="0.70"/>
        <stop offset="24%" stop-color="${cMid23}" stop-opacity="0.64"/>
        <stop offset="46%" stop-color="${c2}" stop-opacity="0.58"/>
        <stop offset="66%" stop-color="${cMid12}" stop-opacity="0.54"/>
        <stop offset="84%" stop-color="${c1}" stop-opacity="0.50"/>
        <stop offset="100%" stop-color="${c0}" stop-opacity="0.44"/>
      </radialGradient>
      <linearGradient id="${gradId}" x1="-0.08" y1="-0.08" x2="1.08" y2="1.08">
        <stop offset="0%" stop-color="${c0}" stop-opacity="0.48"/>
        <stop offset="20%" stop-color="${cMid01}" stop-opacity="0.52"/>
        <stop offset="38%" stop-color="${c1}" stop-opacity="0.56"/>
        <stop offset="54%" stop-color="${cMid12}" stop-opacity="0.55"/>
        <stop offset="72%" stop-color="${c2}" stop-opacity="0.54"/>
        <stop offset="86%" stop-color="${cMid23}" stop-opacity="0.51"/>
        <stop offset="100%" stop-color="${c3}" stop-opacity="0.48"/>
      </linearGradient>
      <radialGradient id="${gradId}-nw" cx="-6%" cy="-6%" r="118%"><stop offset="0%" stop-color="${cNW}" stop-opacity="0.74"/><stop offset="52%" stop-color="${cNW}" stop-opacity="0.34"/><stop offset="100%" stop-color="${cNW}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${gradId}-ne" cx="106%" cy="-6%" r="118%"><stop offset="0%" stop-color="${cNE}" stop-opacity="0.74"/><stop offset="52%" stop-color="${cNE}" stop-opacity="0.34"/><stop offset="100%" stop-color="${cNE}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${gradId}-sw" cx="-6%" cy="106%" r="118%"><stop offset="0%" stop-color="${cSW}" stop-opacity="0.74"/><stop offset="52%" stop-color="${cSW}" stop-opacity="0.34"/><stop offset="100%" stop-color="${cSW}" stop-opacity="0"/></radialGradient>
      <radialGradient id="${gradId}-se" cx="106%" cy="106%" r="118%"><stop offset="0%" stop-color="${cSE}" stop-opacity="0.74"/><stop offset="52%" stop-color="${cSE}" stop-opacity="0.34"/><stop offset="100%" stop-color="${cSE}" stop-opacity="0"/></radialGradient>
      <filter id="${noiseId}"><feTurbulence type="fractalNoise" baseFrequency="0.020 0.046" numOctaves="3" seed="${Math.round(seedA * 80 + 1)}"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="table" tableValues="0 0.12"/></feComponentTransfer></filter>
      <filter id="sahool-wind-glow"><feGaussianBlur stdDeviation="0.65" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <rect width="256" height="256" fill="url(#${gradId})"/>
    <rect width="256" height="256" fill="url(#${heatId})" style="mix-blend-mode:${layer === 'wind' ? 'screen' : 'normal'}"/>
    ${hasInterpolation ? `<g opacity="0.70" style="mix-blend-mode:soft-light"><rect x="-12" y="-12" width="280" height="280" fill="url(#${gradId}-nw)"/><rect x="-12" y="-12" width="280" height="280" fill="url(#${gradId}-ne)"/><rect x="-12" y="-12" width="280" height="280" fill="url(#${gradId}-sw)"/><rect x="-12" y="-12" width="280" height="280" fill="url(#${gradId}-se)"/></g>` : ''}
    <rect width="256" height="256" filter="url(#${noiseId})" opacity="0.42"/>
    <g opacity="0.18"><path d="M-24 204 C 42 166, 98 226, 164 186 S 266 154, 294 184" fill="none" stroke="rgba(10,18,16,0.52)" stroke-width="10"/><path d="M-18 84 C 46 114, 92 50, 144 76 S 234 124, 294 78" fill="none" stroke="rgba(255,255,255,0.27)" stroke-width="5"/></g>
    ${showWind && dir != null ? `<g transform="rotate(${dir} 128 128)" opacity="${particleOpacity}" filter="url(#sahool-wind-glow)">${windLines.join('')}</g>` : ''}
    <text x="246" y="236" text-anchor="end" fill="rgba(255,255,255,.82)" font-family="system-ui" font-size="13" font-weight="900" paint-order="stroke" stroke="rgba(15,23,42,.55)" stroke-width="3">${cfg.shortAr} ${shown}${unit}</text>
    ${statusLabel ? `<rect x="8" y="10" rx="8" ry="8" width="82" height="23" fill="rgba(15,23,42,.70)"/><text x="49" y="26" text-anchor="middle" fill="rgba(255,255,255,.88)" font-family="system-ui" font-size="11" font-weight="900">${statusLabel}</text>` : ''}
  </svg>`;
}

export function loadingTileSvg(layer: WeatherLayerKey): string {
  const cfg = layerConfig(layer);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect width="256" height="256" fill="rgba(15,23,42,.20)"/><text x="128" y="128" text-anchor="middle" fill="rgba(255,255,255,.75)" font-family="system-ui" font-size="14">${cfg.shortAr}…</text></svg>`;
}

export function tileDataUrl(coords: L.Coords, layer: WeatherLayerKey, time: WeatherTimeKey, model: string): string {
  if (isOperationLayer(layer)) {
    return `/api/v1/weather/operation-tile-data/${coords.z}/${coords.x}/${coords.y}?operation=${encodeURIComponent(operationFromLayer(layer))}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}&interpolation=grid`;
  }
  return `/api/v1/weather/tile-data/${coords.z}/${coords.x}/${coords.y}?layer=${encodeURIComponent(layer)}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}&interpolation=grid`;
}

export function createWeatherWindGridLayer(
  marker: WeatherMarker,
  layer: WeatherLayerKey,
  time: WeatherTimeKey,
  model: string,
  opacity: number,
  showWind: boolean,
  windDensity: WindDensity,
  palette: WeatherPalette = 'coldwarm',
): L.GridLayer {
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
        .then((payload: WeatherTilePayload) => { tile.innerHTML = weatherTileSvg(marker, coords, layer, payload, showWind, windDensity, palette); })
        .catch(() => { tile.innerHTML = weatherTileSvg(marker, coords, layer, undefined, showWind, windDensity, palette); });
      return tile;
    },
  });
  return new (WeatherWindGrid as unknown as { new(options?: L.GridLayerOptions): L.GridLayer })({
    tileSize: WEATHER_TILE_SIZE,
    opacity,
    pane: 'overlayPane',
    updateWhenIdle: false,
    updateWhenZooming: true,
    keepBuffer: 3,
  });
}
