// ═══════════════════════════════════════════════════════════════
// SAHOOL Weather Hover Readout (inspired by meteoblue)
// Moving the mouse over the map shows the active layer's value at the
// cursor in a subtle floating tooltip. Mirrors WeatherProbePopup auth,
// but is a lightweight DOM element (NOT a Leaflet popup — popups are for click).
// ═══════════════════════════════════════════════════════════════
import L from 'leaflet';
import {
  type WeatherLayerKey,
  type WeatherTimeKey,
  getLayerValue,
  isOperationLayer,
  layerConfig,
  operationFromLayer,
  weatherFetchHeaders,
} from './weatherLayerDefinitions';

const HOVER_DEBOUNCE_MS = 180;
const CACHE_MAX = 256;
// تقريب الإحداثيّات يجمّع التحويمات المتقاربة في خليّة واحدة فلا تتكرّر الطلبات.
const COORD_ROUND = 2; // ~1km grid; matches probe coarseness for hover

function roundCoord(value: number): string {
  return value.toFixed(COORD_ROUND);
}

// قيمة الطبقة النشِطة من عيّنة المسبار + وحدتها (أو نسبة العملية).
function formatReadout(layer: WeatherLayerKey, data: any): string {
  const cfg = layerConfig(layer);
  if (isOperationLayer(layer)) {
    const op = operationFromLayer(layer);
    const o = data?.operations?.[op];
    if (o && typeof o.score === 'number') {
      return `${Math.round(o.score * 100)}% · ${o.suitability ?? ''}`.trim();
    }
    return '—';
  }
  const value = getLayerValue(layer, data?.sample ?? {}, {} as any);
  if (value == null || Number.isNaN(value)) return '—';
  const rounded = Math.abs(value) >= 100 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${cfg.unit}`.trim();
}

export function registerWeatherHoverReadout(
  map: L.Map,
  layer: WeatherLayerKey,
  time: WeatherTimeKey,
  model: string,
): () => void {
  const cache = new Map<string, string>();
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;

  // عنصر DOM خفيف شفّاف (زجاج داكن) يطابق نمط لوحة الطقس — ليس Leaflet popup.
  const tip = L.DomUtil.create('div', 'sahool-weather-hover-readout');
  Object.assign(tip.style, {
    position: 'absolute',
    zIndex: '500',
    pointerEvents: 'none',
    display: 'none',
    direction: 'rtl',
    font: '12px/1.4 system-ui',
    color: '#f8fafc',
    background: 'rgba(15,23,42,0.78)',
    border: '1px solid rgba(148,163,184,0.35)',
    borderRadius: '9px',
    padding: '5px 9px',
    backdropFilter: 'blur(6px)',
    boxShadow: '0 6px 18px rgba(0,0,0,0.35)',
    whiteSpace: 'nowrap',
    transform: 'translate(12px, 12px)',
  } as Partial<CSSStyleDeclaration>);
  const container = map.getContainer();
  container.appendChild(tip);

  const cacheKey = (lat: number, lng: number) =>
    `${roundCoord(lat)}|${roundCoord(lng)}|${layer}|${time}|${model}`;

  const render = (lat: number, lng: number, valueLine: string) => {
    if (disposed) return;
    const cfg = layerConfig(layer);
    tip.innerHTML = `<b>${cfg.shortAr}</b>: <b>${valueLine}</b><br/><span style="opacity:0.7">${lat.toFixed(3)}, ${lng.toFixed(3)}</span>`;
  };

  const position = (point: L.Point) => {
    tip.style.left = `${point.x}px`;
    tip.style.top = `${point.y}px`;
  };

  const fetchValue = (lat: number, lng: number) => {
    const key = cacheKey(lat, lng);
    const cached = cache.get(key);
    if (cached !== undefined) {
      render(lat, lng, cached);
      return;
    }
    const url = `/api/v1/weather/probe?lat=${lat.toFixed(5)}&lon=${lng.toFixed(5)}&time=${encodeURIComponent(time)}&model=${encodeURIComponent(model)}`;
    fetch(url, { headers: weatherFetchHeaders() })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data) => {
        if (disposed) return;
        const line = formatReadout(layer, data);
        // سقف الذاكرة المؤقّتة: نسقط أقدم مفتاح (FIFO) كي لا تنمو بلا حدّ.
        if (cache.size >= CACHE_MAX) {
          const oldest = cache.keys().next().value;
          if (oldest !== undefined) cache.delete(oldest);
        }
        cache.set(key, line);
        render(lat, lng, line);
      })
      .catch(() => {
        // سقوط آمن: تبقى الإحداثيّات ظاهرة، لا نكسر التحويم عند فشل الطلب.
        if (!disposed) render(lat, lng, '…');
      });
  };

  const onMove = (ev: L.LeafletMouseEvent) => {
    if (disposed) return;
    const { lat, lng } = ev.latlng;
    tip.style.display = 'block';
    position(ev.containerPoint);
    render(lat, lng, '…'); // أثناء الانتظار نعرض الإحداثيّات فقط
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      debounceTimer = null;
      fetchValue(lat, lng);
    }, HOVER_DEBOUNCE_MS);
  };

  const onOut = () => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
    tip.style.display = 'none';
  };

  map.on('mousemove', onMove);
  map.on('mouseout', onOut);

  return () => {
    disposed = true;
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; }
    map.off('mousemove', onMove);
    map.off('mouseout', onOut);
    cache.clear();
    tip.remove();
  };
}
