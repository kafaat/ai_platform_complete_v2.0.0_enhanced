// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · علامات الطبقات التراكبيّة (Overlay Markers)
// ───────────────────────────────────────────────────────────────
// علامات Leaflet خفيفة لطبقات «طقس/تنبيهات/أجهزة» فوق طبقة الحقول. تُبقي
// HubMap نظيفاً: كلّ علامة divIcon (لا أصل صورة خارجيّ) مع Tooltip عربيّ.
//
// صدق البيانات: لا إحداثيّات مُخترَعة. الأشكال المُمرَّرة من MapHub مبسّطة
// (lat/lng محسوبة من النقطة الممثِّلة لحقل العنصر فقط)؛ ما لا نقطة له يُسقَط
// في MapHub قبل الوصول هنا ويُحتسَب في ملاحظة «غير قابل للعرض».
// ═══════════════════════════════════════════════════════════════
import { Marker, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import { useEffect } from 'react';

// ── الأشكال المبسّطة (لا أنواع خام من api.ts داخل طبقة العرض) ──────
export interface AlertMarker {
  id: string;
  lat: number;
  lng: number;
  severity: string; // 'critical' | 'warning' | 'info' | ...
  title: string;
  fieldName: string;
}

export interface DeviceMarker {
  id: string;
  lat: number;
  lng: number;
  name: string;
  dtype: string;
  online: boolean;
}

export interface WeatherMarker {
  lat: number;
  lng: number;
  tempC: number | null;
  humidityPct: number | null;
  conditionAr: string | null;
  windSpeedKmh?: number | null;
  windDirectionDeg?: number | null;
}

export interface OperationalMarker {
  id: string;
  lat: number;
  lng: number;
  kind: 'equipment' | 'task' | 'pivot';
  title: string;
  subtitle?: string;
  status?: string;
}

// طبقات التراكب تجلس فوق المضلّعات/البلاطات (zIndexOffset موجب كبير).
const ALERT_Z = 800;
const DEVICE_Z = 750;
const WEATHER_Z = 900;
const OPERATIONAL_Z = 780;

// لون التنبيه بحسب الخطورة (أحمر/كهرمانيّ/أزرق) — افتراضيّ أزرق للمجهول.
function alertColor(severity: string): string {
  const s = severity.toLowerCase();
  if (s === 'critical') return '#ef4444';
  if (s === 'warning') return '#f59e0b';
  return '#38bdf8'; // info / غيره
}

// أيقونة تنبيه: قرص مُلوَّن بحدّ داكن + علامة تعجّب (divIcon — لا صورة).
function alertIcon(severity: string): L.DivIcon {
  const color = alertColor(severity);
  return L.divIcon({
    className: 'sahool-alert-marker',
    html:
      `<div style="width:18px;height:18px;border-radius:50%;background:${color};` +
      `border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);` +
      `display:flex;align-items:center;justify-content:center;` +
      `color:#0d1611;font-size:12px;font-weight:800;line-height:1">!</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

// أيقونة جهاز: نقطة خضراء (متّصل) أو رماديّة (غير متّصل) بحلقة داكنة.
function deviceIcon(online: boolean): L.DivIcon {
  const color = online ? '#22c55e' : '#94a3b8';
  return L.divIcon({
    className: 'sahool-device-marker',
    html:
      `<div style="width:14px;height:14px;border-radius:50%;background:${color};` +
      `border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

// شارة طقس: بطاقة صغيرة تُظهر الحرارة °م (والحالة إن وُجدت).
function weatherIcon(tempC: number | null, conditionAr: string | null): L.DivIcon {
  const temp = tempC != null ? `${Math.round(tempC)}°م` : '—';
  const cond = conditionAr ? ` · ${conditionAr}` : '';
  return L.divIcon({
    className: 'sahool-weather-marker',
    html:
      `<div dir="rtl" style="display:flex;align-items:center;gap:4px;white-space:nowrap;` +
      `background:rgba(13,22,17,.92);border:1px solid #2d4a37;border-radius:8px;` +
      `padding:3px 7px;color:#e2e8f0;font-size:12px;font-weight:700;` +
      `box-shadow:0 1px 4px rgba(0,0,0,.5)">☀️ ${temp}${cond}</div>`,
    iconSize: [0, 0], // الحجم تلقائيّ من المحتوى
    iconAnchor: [0, 28],
  });
}



// ── طبقة طقس مرئيّة فوق الخريطة: حرارة/رطوبة + مسارات رياح ─────────────
// هذه ليست شارة فقط؛ تُضاف كـSVG overlay داخل Leaflet فوق basemap وتحت العلامات.
// تعتمد على بيانات الطقس الحالية للحقل المختار. إن غاب اتجاه الرياح من الـAPI
// نعرض خطوطاً قطرية محايدة مع وسم «اتجاه غير متاح» بدل اختراع قيمة دقيقة.
function heatFill(tempC: number | null, humidityPct: number | null): string {
  const t = tempC ?? 30;
  const h = humidityPct ?? 45;
  if (t >= 38) return 'rgba(239,68,68,0.34)';
  if (t >= 32) return 'rgba(249,115,22,0.30)';
  if (h >= 75) return 'rgba(14,165,233,0.24)';
  return 'rgba(245,158,11,0.22)';
}

function windStroke(width: number): string {
  const safe = Math.max(1, Math.min(5, width));
  return String(safe);
}

function weatherOverlaySvg(marker: WeatherMarker): SVGSVGElement {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 1000 1000');
  svg.setAttribute('preserveAspectRatio', 'none');
  svg.setAttribute('role', 'img');
  const temp = marker.tempC != null ? `${Math.round(marker.tempC)}°م` : 'حرارة غير متاحة';
  const wind = marker.windSpeedKmh != null ? `${Math.round(marker.windSpeedKmh)} كم/س` : 'سرعة الرياح غير متاحة';
  svg.setAttribute('aria-label', `طبقة الطقس فوق الخريطة: ${temp}، ${wind}`);

  const bg = document.createElementNS(ns, 'rect');
  bg.setAttribute('x', '0'); bg.setAttribute('y', '0');
  bg.setAttribute('width', '1000'); bg.setAttribute('height', '1000');
  bg.setAttribute('fill', heatFill(marker.tempC, marker.humidityPct));
  svg.appendChild(bg);

  const dir = marker.windDirectionDeg ?? 315;
  const speed = marker.windSpeedKmh ?? 12;
  const strokeW = windStroke(1.4 + speed / 18);
  const g = document.createElementNS(ns, 'g');
  g.setAttribute('transform', `rotate(${dir} 500 500)`);
  g.setAttribute('opacity', marker.windDirectionDeg == null ? '0.42' : '0.68');
  for (let row = -80; row <= 1080; row += 115) {
    for (let col = -120; col <= 1120; col += 170) {
      const path = document.createElementNS(ns, 'path');
      const wobble = ((row + col) % 90) - 45;
      path.setAttribute('d', `M ${col} ${row} C ${col + 52} ${row + wobble * 0.16}, ${col + 94} ${row + 20}, ${col + 142} ${row - 4}`);
      path.setAttribute('fill', 'none');
      path.setAttribute('stroke', 'rgba(255,255,255,0.72)');
      path.setAttribute('stroke-width', strokeW);
      path.setAttribute('stroke-linecap', 'round');
      path.setAttribute('stroke-dasharray', '58 34');
      path.innerHTML = '<animate attributeName="stroke-dashoffset" from="92" to="0" dur="2.8s" repeatCount="indefinite" />';
      g.appendChild(path);
    }
  }
  svg.appendChild(g);
  return svg;
}

export function WeatherRasterOverlay({ marker }: { marker: WeatherMarker | null }) {
  const map = useMap();
  useEffect(() => {
    if (!marker) return undefined;

    // تُعامل كطبقة بلاط/راستر مرئية: تغطي كامل نافذة الخريطة وتتحدّث مع pan/zoom
    // بدلاً من شارة ثابتة فقط. البيانات نفسها صادقة: حرارة/رطوبة/رياح الحقل المختار.
    const overlay = L.svgOverlay(weatherOverlaySvg(marker), map.getBounds().pad(1.25), {
      opacity: 1,
      interactive: false,
      pane: 'overlayPane',
    }).addTo(map);
    overlay.getElement()?.classList.add('sahool-weather-raster-overlay');

    const syncBounds = () => overlay.setBounds(map.getBounds().pad(1.25));
    map.on('moveend zoomend resize', syncBounds);
    syncBounds();

    return () => {
      map.off('moveend zoomend resize', syncBounds);
      overlay.remove();
    };
  }, [map, marker]);
  return null;
}


function operationalIcon(kind: OperationalMarker['kind'], status?: string): L.DivIcon {
  const s = (status ?? '').toLowerCase();
  const bg = kind === 'pivot'
    ? '#38bdf8'
    : kind === 'task'
      ? (s === 'completed' ? '#22c55e' : s === 'in_progress' ? '#f59e0b' : '#a3e635')
      : (['broken', 'maintenance', 'down'].includes(s) ? '#ef4444' : '#84cc16');
  const glyph = kind === 'pivot' ? '◔' : kind === 'task' ? '✓' : '⚙';
  return L.divIcon({
    className: `sahool-operational-marker sahool-operational-${kind}`,
    html:
      `<div style="width:20px;height:20px;border-radius:7px;background:${bg};` +
      `border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);` +
      `display:flex;align-items:center;justify-content:center;` +
      `color:#0d1611;font-size:13px;font-weight:900;line-height:1">${glyph}</div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
}

export function OperationalOverlay({ markers }: { markers: OperationalMarker[] }) {
  if (!markers.length) return null;
  return (
    <>
      {markers.map((m) => (
        <Marker
          key={`ops-${m.kind}-${m.id}`}
          position={[m.lat, m.lng]}
          icon={operationalIcon(m.kind, m.status)}
          zIndexOffset={OPERATIONAL_Z}
        >
          <Tooltip direction="top" offset={[0, -8]}>
            <span dir="rtl">{m.title}{m.subtitle ? ` · ${m.subtitle}` : ''}</span>
          </Tooltip>
        </Marker>
      ))}
    </>
  );
}

const onlineAr = (online: boolean) => (online ? 'متصل' : 'غير متصل');

// ── طبقة علامات التنبيهات ────────────────────────────────────────
export function AlertOverlay({ markers }: { markers: AlertMarker[] }) {
  if (!markers.length) return null;
  return (
    <>
      {markers.map((m) => (
        <Marker
          key={`alert-${m.id}`}
          position={[m.lat, m.lng]}
          icon={alertIcon(m.severity)}
          zIndexOffset={ALERT_Z}
        >
          <Tooltip direction="top" offset={[0, -8]}>
            <span dir="rtl">{m.title}{m.fieldName ? ` · ${m.fieldName}` : ''}</span>
          </Tooltip>
        </Marker>
      ))}
    </>
  );
}

// ── طبقة علامات الأجهزة ──────────────────────────────────────────
export function DeviceOverlay({ markers }: { markers: DeviceMarker[] }) {
  if (!markers.length) return null;
  return (
    <>
      {markers.map((m) => (
        <Marker
          key={`device-${m.id}`}
          position={[m.lat, m.lng]}
          icon={deviceIcon(m.online)}
          zIndexOffset={DEVICE_Z}
        >
          <Tooltip direction="top" offset={[0, -6]}>
            <span dir="rtl">{m.name} · {m.dtype} · {onlineAr(m.online)}</span>
          </Tooltip>
        </Marker>
      ))}
    </>
  );
}

// ── شارة الطقس (نقطة واحدة للحقل المختار) ────────────────────────
export function WeatherOverlay({ marker }: { marker: WeatherMarker | null }) {
  if (!marker) return null;
  const parts: string[] = [];
  if (marker.conditionAr) parts.push(marker.conditionAr);
  if (marker.humidityPct != null) parts.push(`رطوبة ${Math.round(marker.humidityPct)}%`);
  const tip = parts.length ? parts.join(' · ') : 'طقس الحقل المختار';
  return (
    <Marker
      position={[marker.lat, marker.lng]}
      icon={weatherIcon(marker.tempC, marker.conditionAr)}
      zIndexOffset={WEATHER_Z}
    >
      <Tooltip direction="top" offset={[0, -28]}>
        <span dir="rtl">{tip}</span>
      </Tooltip>
    </Marker>
  );
}
