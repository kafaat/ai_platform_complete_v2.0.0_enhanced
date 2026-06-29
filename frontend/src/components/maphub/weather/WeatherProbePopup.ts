// ═══════════════════════════════════════════════════════════════
// SAHOOL Weather Probe Popup
// Handles map-click agricultural weather probe, operation window, and operation plan.
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import {
  type WeatherLayerKey,
  type WeatherTimeKey,
  isOperationLayer,
  operationFromLayer,
  weatherFetchHeaders,
} from './weatherLayerDefinitions';

export function registerWeatherProbePopup(
  map: L.Map,
  layer: WeatherLayerKey,
  time: WeatherTimeKey,
  model: string,
): () => void {
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
}
