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
  WEATHER_TIMES,
  WEATHER_MODELS,
  WIND_DENSITIES,
  WEATHER_LAYERS,
  WEATHER_PRESETS,
  layerConfig,
} from './weatherLayerDefinitions';

function gradientCss(cfg: WeatherLayerConfig): string {
  return cfg.stops.map((c, i) => `${c} ${Math.round((i / Math.max(1, cfg.stops.length - 1)) * 100)}%`).join(',');
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
): string {
  const cfg = layerConfig(layer);
  const temp = marker.tempC != null ? `${Math.round(marker.tempC)}°م` : '—';
  const wind = marker.windSpeedKmh != null ? `${Math.round(marker.windSpeedKmh)} كم/س` : '—';
  const dir = marker.windDirectionDeg != null ? `${Math.round(marker.windDirectionDeg)}°` : '—';
  if (!panelOpen) {
    return `<div dir="rtl" class="sahool-weather-layer-control" style="display:flex;align-items:center;gap:9px;background:rgba(88,20,78,.86);border:1px solid rgba(255,255,255,.22);border-radius:999px;color:#f8fafc;font:12px system-ui;box-shadow:0 12px 32px rgba(0,0,0,.35);backdrop-filter:blur(10px);padding:8px 10px;">
      <button type="button" data-panel-toggle="1" title="فتح طبقات الطقس" style="width:34px;height:34px;border-radius:999px;border:1px solid rgba(255,255,255,.25);background:rgba(15,23,42,.52);color:white;font-size:19px;cursor:pointer">☰</button>
      <span style="font-weight:900">${cfg.shortAr}</span><span>${temp}</span><span>💨 ${wind}</span>
    </div>`;
  }
  const layerRows = WEATHER_LAYERS.map((l) => {
    const active = l.key === layer;
    return `<button type="button" data-layer="${l.key}" class="sahool-weather-layer-row" style="display:flex;align-items:center;justify-content:space-between;gap:10px;width:100%;border:0;border-radius:0;background:${active ? 'rgba(14,85,142,.78)' : 'transparent'};color:#f8fafc;padding:9px 12px;font-weight:${active ? '900' : '700'};cursor:pointer;text-align:right">
      <span>${l.labelAr}</span><span style="font-size:11px;color:${active ? '#dbeafe' : '#cbd5e1'}">${l.unit}</span>
    </button>`;
  }).join('');
  return `<div dir="rtl" class="sahool-weather-layer-control" style="width:min(330px,calc(100vw - 24px));max-height:calc(100vh - 116px);overflow:auto;background:linear-gradient(180deg,rgba(91,19,74,.86),rgba(58,16,55,.78) 46%,rgba(17,24,39,.82));border:1px solid rgba(255,255,255,.18);border-radius:18px;color:#e2e8f0;font:13px/1.35 system-ui,-apple-system,Segoe UI,sans-serif;box-shadow:0 18px 46px rgba(0,0,0,.42);backdrop-filter:blur(10px);">
    <div style="display:flex;align-items:center;gap:8px;padding:12px 12px 9px;border-bottom:1px solid rgba(255,255,255,.13)">
      <button type="button" data-panel-toggle="1" title="تصغير" style="width:34px;height:34px;border-radius:10px;border:1px solid rgba(255,255,255,.22);background:rgba(15,23,42,.45);color:#fff;font-weight:900;cursor:pointer">×</button>
      <div style="width:38px;height:38px;border-radius:12px;background:rgba(255,255,255,.12);display:grid;place-items:center;font-size:22px">⌕</div>
      <div style="flex:1;background:rgba(15,23,42,.46);border:1px solid rgba(255,255,255,.15);border-radius:12px;padding:10px 12px;color:#dbeafe;text-align:right">ابحث عن طبقة طقس</div>
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:7px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.13)">
      ${WEATHER_PRESETS.map((preset) => `<button type="button" data-layer="${preset.layer}" title="${preset.note}" style="border:1px solid ${preset.layer === layer ? 'rgba(255,255,255,.72)' : 'rgba(255,255,255,.16)'};border-radius:12px;background:${preset.layer === layer ? 'rgba(37,99,235,.82)' : 'rgba(15,23,42,.46)'};color:#f8fafc;padding:8px 6px;font-weight:900;cursor:pointer">${preset.label}</button>`).join('')}
    </div>
    <div style="padding:9px 0;border-bottom:1px solid rgba(255,255,255,.12)">
      ${layerRows}
    </div>
    <div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.13)">
      ${WEATHER_TIMES.map((t) => `<button type="button" data-time="${t.key}" style="border:1px solid ${t.key === time ? 'rgba(255,255,255,.72)' : 'rgba(255,255,255,.16)'};border-radius:9px;background:${t.key === time ? 'rgba(37,99,235,.86)' : 'rgba(15,23,42,.50)'};color:#f8fafc;padding:6px 2px;font-weight:900;cursor:pointer;font-size:11px">${t.label}</button>`).join('')}
    </div>
    <div style="padding:11px 12px;border-bottom:1px solid rgba(255,255,255,.13);display:grid;gap:8px">
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>شفافية الطبقة</span><b>${Math.round(opacity * 100)}%</b></label>
      <input type="range" min="35" max="100" value="${Math.round(opacity * 100)}" data-opacity="1" style="width:100%;accent-color:#38bdf8"/>
      <label style="display:flex;align-items:center;gap:7px;justify-content:space-between"><span>Wind Animation / تحريك الرياح</span><input type="checkbox" data-wind-toggle="1" ${showWind ? 'checked' : ''}/></label>
      <select data-density="1" title="كثافة مسارات الرياح" style="width:100%;border-radius:10px;border:1px solid rgba(255,255,255,.22);background:rgba(15,23,42,.70);color:#f8fafc;padding:9px">
        ${WIND_DENSITIES.map((d) => `<option value="${d.key}" ${d.key === windDensity ? 'selected' : ''}>كثافة الرياح: ${d.label}</option>`).join('')}
      </select>
      <select data-model="1" style="width:100%;border-radius:10px;border:1px solid rgba(255,255,255,.22);background:rgba(15,23,42,.70);color:#f8fafc;padding:9px">
        ${WEATHER_MODELS.map((m) => `<option value="${m.key}" ${m.key === model ? 'selected' : ''}>${m.label}</option>`).join('')}
      </select>
    </div>
    <div style="display:grid;grid-template-columns:18px 1fr;gap:10px;padding:12px;border-bottom:1px solid rgba(255,255,255,.12)">
      <div style="height:190px;border-radius:999px;border:1px solid rgba(255,255,255,.30);background:linear-gradient(to top,${gradientCss(cfg)});"></div>
      <div style="display:flex;flex-direction:column;justify-content:space-between;color:#f8fafc;font-weight:800">
        <span>${cfg.max}${cfg.unit}</span><span>${((cfg.min + cfg.max) / 2).toFixed(cfg.key === 'soil_moisture' ? 2 : 0)}${cfg.unit}</span><span>${cfg.min}${cfg.unit}</span>
      </div>
    </div>
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
): L.Control {
  const WeatherControl = L.Control.extend({
    onAdd() {
      const div = L.DomUtil.create('div', 'sahool-weather-layer-control-wrap');
      div.innerHTML = weatherControlHtml(layer, marker, time, model, opacity, showWind, windDensity, panelOpen);
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
      const densitySelect = div.querySelector<HTMLSelectElement>('select[data-density]');
      if (densitySelect) densitySelect.onchange = () => onWindDensityChange(densitySelect.value as WindDensity);
      const panelToggle = div.querySelector<HTMLButtonElement>('button[data-panel-toggle]');
      if (panelToggle) panelToggle.onclick = () => onPanelToggle();
      const opacityInput = div.querySelector<HTMLInputElement>('input[data-opacity]');
      if (opacityInput) opacityInput.oninput = () => onOpacityChange(Math.max(0.35, Math.min(1, Number(opacityInput.value) / 100)));
      const windToggle = div.querySelector<HTMLInputElement>('input[data-wind-toggle]');
      if (windToggle) windToggle.onchange = () => onWindToggle(windToggle.checked);
      return div;
    },
  });
  return new WeatherControl({ position: 'topright' });
}
