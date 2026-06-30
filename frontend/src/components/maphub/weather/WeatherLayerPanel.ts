// ═══════════════════════════════════════════════════════════════
// SAHOOL Weather Layer Panel
// Leaflet control for layer switching, agricultural presets, timeline, model,
// opacity, wind density, and animation toggles.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import type { WeatherMarker } from '../OverlayMarkers';
import {
  type WeatherLayerKey,
  type WeatherTimeKey,
  type WindDensity,
  type WeatherLayerConfig,
  type WeatherPalette,
  WEATHER_TIMES,
  WEATHER_MODELS,
  WIND_DENSITIES,
  WEATHER_LAYERS,
  WEATHER_PRESETS,
  WEATHER_PALETTES,
  layerConfig,
  layerFactor,
  getLayerValue,
} from './weatherLayerDefinitions';

function gradientCss(cfg: WeatherLayerConfig): string {
  return cfg.stops.map((c, i) => `${c} ${Math.round((i / Math.max(1, cfg.stops.length - 1)) * 100)}%`).join(',');
}

// تنسيق قيمة المقياس حسب الطبقة (رطوبة التربة بمنزلتين، الباقي صحيح).
function fmtLegend(v: number, cfg: WeatherLayerConfig): string {
  return cfg.key === 'soil_moisture' ? v.toFixed(2) : Math.round(v).toString();
}

// أُسطورة ديناميكيّة: علامات (ticks) مشتقّة من نطاق الطبقة الفعليّ (min/max/stops)
// لا قيم ثابتة، مع مؤشّر حيّ لقيمة مركز الحقل الحاليّة على المقياس.
function legendHtml(cfg: WeatherLayerConfig, marker: WeatherMarker): string {
  const stopCount = cfg.stops.length;
  // علامة لكل حدّ لون (stop) — تعكس فعليّاً درجات الطبقة لا 3 قيم ثابتة.
  const ticks: number[] = [];
  for (let i = stopCount - 1; i >= 0; i -= 1) {
    ticks.push(cfg.min + (cfg.max - cfg.min) * (i / Math.max(1, stopCount - 1)));
  }
  const ticksHtml = ticks.map((t) => `<span>${fmtLegend(t, cfg)}${cfg.unit}</span>`).join('');
  // مؤشّر القيمة الحاليّة لمركز الحقل (إن توفّرت لهذه الطبقة) كنسبة من أعلى المقياس.
  const live = getLayerValue(cfg.key, undefined, marker);
  const liveMarker = live == null
    ? ''
    : `<div title="القيمة الحاليّة: ${fmtLegend(live, cfg)}${cfg.unit}" style="position:absolute;left:-3px;right:-3px;height:2px;background:#fff;box-shadow:0 0 0 1px rgba(15,23,42,.7);bottom:calc(${(layerFactor(live, cfg) * 100).toFixed(1)}% - 1px)"></div>`;
  // بطاقة أُسطورة شبه شفّافة: شريط تدرّج عموديّ نحيل + وحدة الطبقة في الأعلى + علامات النطاق.
  return `<div style="padding:12px;border-bottom:1px solid rgba(255,255,255,.12)">
      <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:8px;color:#e2e8f0"><b style="font-size:12px">${cfg.shortAr}</b><span style="font-size:11px;color:#bfdbfe;font-weight:800">${cfg.unit}</span></div>
      <div style="display:grid;grid-template-columns:16px 1fr;gap:10px;background:rgba(15,23,42,.35);border:1px solid rgba(255,255,255,.12);border-radius:12px;padding:10px;backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px)">
        <div style="position:relative;height:180px;border-radius:999px;border:1px solid rgba(255,255,255,.30);background:linear-gradient(to top,${gradientCss(cfg)});">${liveMarker}</div>
        <div style="display:flex;flex-direction:column;justify-content:space-between;color:#f8fafc;font-weight:800;font-size:11px">${ticksHtml}</div>
      </div>
    </div>`;
}

export function weatherControlHtml(
  layer: WeatherLayerKey,
  marker: WeatherMarker,
  time: WeatherTimeKey,
  model: string,
  opacity: number,
  showWind: boolean,
  windDensity: WindDensity,
  panelOpen: boolean,
  palette: WeatherPalette = 'coldwarm',
  playing: boolean = false,
  graticule: boolean = false,
): string {
  const cfg = layerConfig(layer);
  const timeIndex = Math.max(0, WEATHER_TIMES.findIndex((t) => t.key === time));
  const currentTimeLabel = (WEATHER_TIMES[timeIndex] ?? WEATHER_TIMES[0]).label;
  const temp = marker.tempC != null ? `${Math.round(marker.tempC)}°م` : '—';
  const wind = marker.windSpeedKmh != null ? `${Math.round(marker.windSpeedKmh)} كم/س` : '—';
  const dir = marker.windDirectionDeg != null ? `${Math.round(marker.windDirectionDeg)}°` : '—';
  if (!panelOpen) {
    // شريحة مصغّرة شبه شفافة (زجاج داكن) تُظهر الخريطة خلفها بنعومة.
    return `<div dir="rtl" class="sahool-weather-layer-control" style="display:flex;align-items:center;gap:9px;background:rgba(15,23,42,.58);border:1px solid rgba(255,255,255,.18);border-radius:999px;color:#f8fafc;font:12px system-ui;box-shadow:0 12px 32px rgba(0,0,0,.35);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);padding:8px 10px;">
      <button type="button" data-panel-toggle="1" title="فتح طبقات الطقس" style="width:34px;height:34px;border-radius:999px;border:1px solid rgba(255,255,255,.22);background:rgba(15,23,42,.45);color:white;font-size:19px;cursor:pointer">☰</button>
      <span style="font-weight:900">${cfg.shortAr}</span><span>${temp}</span><span>💨 ${wind}</span>
    </div>`;
  }
  // قائمة الطبقات: الطبقة النشطة كبطاقة صلبة بارزة، والبقيّة كقائمة بسيطة.
  const layerRows = WEATHER_LAYERS.map((l) => {
    const active = l.key === layer;
    return `<button type="button" data-layer="${l.key}" class="sahool-weather-layer-row" data-search="${`${l.labelAr} ${l.shortAr} ${l.key}`.toLowerCase()}" style="display:flex;align-items:center;justify-content:space-between;gap:10px;width:calc(100% - 16px);margin:${active ? '3px 8px' : '0 8px'};border:${active ? '1px solid rgba(56,189,248,.55)' : '0'};border-radius:${active ? '12px' : '0'};background:${active ? 'rgba(14,85,142,.92)' : 'transparent'};box-shadow:${active ? '0 6px 16px rgba(2,6,23,.40)' : 'none'};color:#f8fafc;padding:${active ? '11px 12px' : '8px 12px'};font-weight:${active ? '900' : '700'};cursor:pointer;text-align:right">
      <span>${l.labelAr}</span><span style="font-size:11px;color:${active ? '#dbeafe' : '#cbd5e1'}">${l.unit}</span>
    </button>`;
  }).join('');
  // اللوحة المفتوحة: زجاج داكن شبه شفّاف تظهر الخريطة خلفه بدل خلفيّة معتمة.
  return `<div dir="rtl" class="sahool-weather-layer-control" style="width:min(330px,calc(100vw - 24px));max-height:calc(100vh - 116px);overflow:auto;background:rgba(15,23,42,.62);border:1px solid rgba(255,255,255,.16);border-radius:18px;color:#e2e8f0;font:13px/1.35 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 18px 46px rgba(0,0,0,.42);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);">
    <div style="display:flex;align-items:center;gap:8px;padding:12px 12px 9px;border-bottom:1px solid rgba(255,255,255,.13)">
      <button type="button" data-panel-toggle="1" title="تصغير" style="width:34px;height:34px;border-radius:10px;border:1px solid rgba(255,255,255,.22);background:rgba(15,23,42,.40);color:#fff;font-weight:900;cursor:pointer">×</button>
      <div style="width:38px;height:38px;border-radius:12px;background:rgba(255,255,255,.12);display:grid;place-items:center;font-size:22px">⌕</div>
      <input type="search" data-layer-search="1" placeholder="ابحث عن طبقة طقس" autocomplete="off" style="flex:1;min-width:0;background:rgba(15,23,42,.40);border:1px solid rgba(255,255,255,.14);border-radius:12px;padding:10px 12px;color:#f8fafc;text-align:right;outline:none" />
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:7px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.13)">
      ${WEATHER_PRESETS.map((preset) => `<button type="button" data-layer="${preset.layer}" title="${preset.note}" style="border:1px solid ${preset.layer === layer ? 'rgba(255,255,255,.72)' : 'rgba(255,255,255,.16)'};border-radius:12px;background:${preset.layer === layer ? 'rgba(37,99,235,.82)' : 'rgba(15,23,42,.40)'};color:#f8fafc;padding:8px 6px;font-weight:900;cursor:pointer">${preset.label}</button>`).join('')}
    </div>
    <div style="padding:9px 0;border-bottom:1px solid rgba(255,255,255,.12)">
      ${layerRows}
    </div>
    <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;padding:10px 12px 6px">
      ${WEATHER_TIMES.map((t) => `<button type="button" data-time="${t.key}" style="border:1px solid ${t.key === time ? 'rgba(255,255,255,.72)' : 'rgba(255,255,255,.16)'};border-radius:9px;background:${t.key === time ? 'rgba(37,99,235,.86)' : 'rgba(15,23,42,.50)'};color:#f8fafc;padding:6px 2px;font-weight:900;cursor:pointer;font-size:11px">${t.label}</button>`).join('')}
    </div>
    <div style="display:flex;align-items:center;gap:9px;padding:4px 12px 11px;border-bottom:1px solid rgba(255,255,255,.13)">
      <button type="button" data-play="1" title="${playing ? 'إيقاف العرض الزمني' : 'تشغيل العرض الزمني'}" aria-pressed="${playing ? 'true' : 'false'}" style="flex:0 0 auto;width:36px;height:36px;border-radius:999px;border:1px solid rgba(255,255,255,.22);background:${playing ? 'rgba(37,99,235,.86)' : 'rgba(15,23,42,.50)'};color:#f8fafc;font-size:15px;cursor:pointer">${playing ? '⏸' : '▶'}</button>
      <input type="range" min="0" max="${WEATHER_TIMES.length - 1}" step="1" value="${timeIndex}" data-time-slider="1" title="شريط الزمن" style="flex:1;direction:ltr;width:100%;accent-color:#38bdf8"/>
      <b style="flex:0 0 auto;min-width:42px;text-align:center;color:#dbeafe;font-size:12px">${currentTimeLabel}</b>
    </div>
    <style>
      .sahool-ios-toggle{position:relative;display:inline-block;width:44px;height:25px;flex:0 0 auto}
      .sahool-ios-toggle input{position:absolute;opacity:0;width:100%;height:100%;margin:0;cursor:pointer;z-index:2}
      .sahool-ios-toggle .sahool-ios-track{position:absolute;inset:0;border-radius:999px;background:rgba(148,163,184,.45);transition:background .18s ease}
      .sahool-ios-toggle .sahool-ios-track::after{content:"";position:absolute;top:2px;left:2px;width:21px;height:21px;border-radius:999px;background:#fff;box-shadow:0 1px 3px rgba(0,0,0,.4);transition:transform .18s ease}
      .sahool-ios-toggle input:checked + .sahool-ios-track{background:#34c759}
      .sahool-ios-toggle input:checked + .sahool-ios-track::after{transform:translateX(19px)}
    </style>
    <div style="padding:11px 12px;border-bottom:1px solid rgba(255,255,255,.13);display:grid;gap:8px">
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>شفافية الطبقة</span><b>${Math.round(opacity * 100)}%</b></label>
      <input type="range" min="35" max="100" value="${Math.round(opacity * 100)}" data-opacity="1" style="width:100%;accent-color:#38bdf8"/>
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>Wind Animation / تحريك الرياح</span><span class="sahool-ios-toggle"><input type="checkbox" data-wind-toggle="1" ${showWind ? 'checked' : ''}/><span class="sahool-ios-track"></span></span></label>
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>Graticule / شبكة الإحداثيّات</span><span class="sahool-ios-toggle"><input type="checkbox" data-graticule="1" ${graticule ? 'checked' : ''}/><span class="sahool-ios-track"></span></span></label>
      <select data-density="1" title="كثافة مسارات الرياح" style="width:100%;border-radius:10px;border:1px solid rgba(255,255,255,.20);background:rgba(15,23,42,.55);color:#f8fafc;padding:9px">
        ${WIND_DENSITIES.map((d) => `<option value="${d.key}" ${d.key === windDensity ? 'selected' : ''}>كثافة الرياح: ${d.label}</option>`).join('')}
      </select>
      <select data-model="1" style="width:100%;border-radius:10px;border:1px solid rgba(255,255,255,.20);background:rgba(15,23,42,.55);color:#f8fafc;padding:9px">
        ${WEATHER_MODELS.map((m) => `<option value="${m.key}" ${m.key === model ? 'selected' : ''}>${m.label}</option>`).join('')}
      </select>
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>مخطط الألوان</span></label>
      <div style="display:grid;grid-template-columns:repeat(${WEATHER_PALETTES.length},1fr);gap:4px;background:rgba(15,23,42,.45);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:4px">
        ${WEATHER_PALETTES.map((p) => `<button type="button" data-palette="${p.key}" style="border:1px solid ${p.key === palette ? 'rgba(255,255,255,.72)' : 'transparent'};border-radius:9px;background:${p.key === palette ? 'rgba(37,99,235,.86)' : 'transparent'};color:#f8fafc;padding:7px 4px;font-weight:900;cursor:pointer;font-size:12px">${p.label}</button>`).join('')}
      </div>
    </div>
    ${legendHtml(cfg, marker)}
    <div style="padding:10px 12px;color:#cbd5e1;display:grid;gap:3px">
      <div>المصدر: <b>Open‑Meteo</b> · الرسم: <b>SAHOOL</b></div>
      <div>الطبقة: <b>${cfg.labelAr}</b> · الزمن: <b>${time}</b></div>
      <div>النموذج: <b>${model}</b></div>
      <div>حرارة مركز الحقل: <b>${temp}</b></div>
      <div>الرياح: <b>${wind}</b> · اتجاه <b>${dir}</b></div>
      <div style="margin-top:5px;color:#bfdbfe;font-weight:800">انقر على الخريطة لقراءة Probe وخطة العمليات.</div>
      <div style="color:#93c5fd">الأداء: يمكن خفض كثافة الرياح للجوال أو الأجهزة الضعيفة.</div>
    </div>
  </div>`;
}

export function createWeatherControl(
  layer: WeatherLayerKey,
  marker: WeatherMarker,
  time: WeatherTimeKey,
  model: string,
  opacity: number,
  showWind: boolean,
  windDensity: WindDensity,
  panelOpen: boolean,
  onLayerChange: (layer: WeatherLayerKey) => void,
  onTimeChange: (time: WeatherTimeKey) => void,
  onModelChange: (model: string) => void,
  onOpacityChange: (opacity: number) => void,
  onWindToggle: (show: boolean) => void,
  onWindDensityChange: (density: WindDensity) => void,
  onPanelToggle: () => void,
  palette: WeatherPalette = 'coldwarm',
  onPaletteChange: (palette: WeatherPalette) => void = () => {},
  playing: boolean = false,
  onPlayToggle: () => void = () => {},
  graticule: boolean = false,
  onGraticuleToggle: (show: boolean) => void = () => {},
): L.Control {
  const WeatherControl = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create('div', 'sahool-weather-layer-control-wrap');
      div.innerHTML = weatherControlHtml(layer, marker, time, model, opacity, showWind, windDensity, panelOpen, palette, playing, graticule);
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      div.querySelectorAll<HTMLButtonElement>('button[data-layer]').forEach((btn) => {
        btn.onclick = () => onLayerChange(btn.dataset.layer as WeatherLayerKey);
      });
      // بحث/تصفية الطبقات (نمط meteoblue): يُخفي صفوف الطبقات غير المطابقة فوراً (عميل فقط).
      const layerSearch = div.querySelector<HTMLInputElement>('input[data-layer-search]');
      if (layerSearch) {
        layerSearch.oninput = () => {
          const q = layerSearch.value.trim().toLowerCase();
          div.querySelectorAll<HTMLButtonElement>('.sahool-weather-layer-row').forEach((row) => {
            const hay = row.dataset.search || row.textContent?.toLowerCase() || '';
            row.style.display = !q || hay.includes(q) ? '' : 'none';
          });
        };
      }
      div.querySelectorAll<HTMLButtonElement>('button[data-time]').forEach((btn) => {
        btn.onclick = () => onTimeChange(btn.dataset.time as WeatherTimeKey);
      });
      const modelSelect = div.querySelector<HTMLSelectElement>('select[data-model]');
      if (modelSelect) modelSelect.onchange = () => onModelChange(modelSelect.value);
      const densitySelect = div.querySelector<HTMLSelectElement>('select[data-density]');
      if (densitySelect) densitySelect.onchange = () => onWindDensityChange(densitySelect.value as WindDensity);
      const panelToggle = div.querySelector<HTMLButtonElement>('button[data-panel-toggle]');
      if (panelToggle) panelToggle.onclick = () => onPanelToggle();
      const opacityInput = div.querySelector<HTMLInputElement>('input[data-opacity]');
      if (opacityInput) opacityInput.oninput = () => onOpacityChange(Math.max(0.35, Math.min(1, Number(opacityInput.value) / 100)));
      const windToggle = div.querySelector<HTMLInputElement>('input[data-wind-toggle]');
      if (windToggle) windToggle.onchange = () => onWindToggle(windToggle.checked);
      const graticuleToggle = div.querySelector<HTMLInputElement>('input[data-graticule]');
      if (graticuleToggle) graticuleToggle.onchange = () => onGraticuleToggle(graticuleToggle.checked);
      div.querySelectorAll<HTMLButtonElement>('button[data-palette]').forEach((btn) => {
        btn.onclick = () => onPaletteChange(btn.dataset.palette as WeatherPalette);
      });
      const timeSlider = div.querySelector<HTMLInputElement>('input[data-time-slider]');
      if (timeSlider) timeSlider.oninput = () => {
        const idx = Math.max(0, Math.min(WEATHER_TIMES.length - 1, Math.round(Number(timeSlider.value))));
        onTimeChange(WEATHER_TIMES[idx].key);
      };
      const playButton = div.querySelector<HTMLButtonElement>('button[data-play]');
      if (playButton) playButton.onclick = () => onPlayToggle();
      return div;
    },
  });
  return new WeatherControl({ position: 'topright' });
}
