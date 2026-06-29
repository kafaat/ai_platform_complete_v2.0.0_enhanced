// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · علامات وطبقات تراكبيّة
// ───────────────────────────────────────────────────────────────
// Open-Meteo = مصدر البيانات فقط. SAHOOL يرسم البلاطات والأنيميشن والـlegend
// والـlayer controls داخل Leaflet بدون الاعتماد على بلاطات مزوّد خارجي.
// ═══════════════════════════════════════════════════════════════
import { Marker, Tooltip } from 'react-leaflet';
import L from 'leaflet';
import { WeatherRasterOverlay } from './weather/WeatherRasterOverlay';

export interface AlertMarker {
  id: string;
  lat: number;
  lng: number;
  severity: string;
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
  fieldId?: string | null;
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

const ALERT_Z = 800;
const DEVICE_Z = 750;
const WEATHER_Z = 900;
const OPERATIONAL_Z = 780;
function alertColor(severity: string): string {
  const s = severity.toLowerCase();
  if (s === 'critical') return '#ef4444';
  if (s === 'warning') return '#f59e0b';
  return '#38bdf8';
}

function alertIcon(severity: string): L.DivIcon {
  const color = alertColor(severity);
  return L.divIcon({
    className: 'sahool-alert-marker',
    html: `<div style="width:18px;height:18px;border-radius:50%;background:${color};border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;color:#0d1611;font-size:12px;font-weight:800;line-height:1">!</div>`,
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function deviceIcon(online: boolean): L.DivIcon {
  const color = online ? '#22c55e' : '#94a3b8';
  return L.divIcon({
    className: 'sahool-device-marker',
    html: `<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6)"></div>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function weatherIcon(tempC: number | null, conditionAr: string | null): L.DivIcon {
  const temp = tempC != null ? `${Math.round(tempC)}°م` : '—';
  const cond = conditionAr ? ` · ${conditionAr}` : '';
  return L.divIcon({
    className: 'sahool-weather-marker',
    html: `<div dir="rtl" style="display:flex;align-items:center;gap:4px;white-space:nowrap;background:rgba(13,22,17,.92);border:1px solid #2d4a37;border-radius:8px;padding:3px 7px;color:#e2e8f0;font-size:12px;font-weight:700;box-shadow:0 1px 4px rgba(0,0,0,.5)">☀️ ${temp}${cond}</div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 28],
  });
}


// WeatherRasterOverlay is implemented in ./weather/WeatherRasterOverlay and re-exported here
// so HubMap can keep using the existing OverlayMarkers import surface.
export { WeatherRasterOverlay };

function operationalIcon(kind: OperationalMarker['kind'], status?: string): L.DivIcon {
  const s = (status ?? '').toLowerCase();
  const bg = kind === 'pivot' ? '#38bdf8' : kind === 'task' ? (s === 'completed' ? '#22c55e' : s === 'in_progress' ? '#f59e0b' : '#a3e635') : (['broken', 'maintenance', 'down'].includes(s) ? '#ef4444' : '#84cc16');
  const glyph = kind === 'pivot' ? '◔' : kind === 'task' ? '✓' : '⚙';
  return L.divIcon({ className: `sahool-operational-marker sahool-operational-${kind}`, html: `<div style="width:20px;height:20px;border-radius:7px;background:${bg};border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center;color:#0d1611;font-size:13px;font-weight:900;line-height:1">${glyph}</div>`, iconSize: [20, 20], iconAnchor: [10, 10] });
}

export function OperationalOverlay({ markers }: { markers: OperationalMarker[] }) {
  if (!markers.length) return null;
  return <>{markers.map((m) => <Marker key={`ops-${m.kind}-${m.id}`} position={[m.lat, m.lng]} icon={operationalIcon(m.kind, m.status)} zIndexOffset={OPERATIONAL_Z}><Tooltip direction="top" offset={[0, -8]}><span dir="rtl">{m.title}{m.subtitle ? ` · ${m.subtitle}` : ''}</span></Tooltip></Marker>)}</>;
}

const onlineAr = (online: boolean) => (online ? 'متصل' : 'غير متصل');

export function AlertOverlay({ markers }: { markers: AlertMarker[] }) {
  if (!markers.length) return null;
  return <>{markers.map((m) => <Marker key={`alert-${m.id}`} position={[m.lat, m.lng]} icon={alertIcon(m.severity)} zIndexOffset={ALERT_Z}><Tooltip direction="top" offset={[0, -8]}><span dir="rtl">{m.title}{m.fieldName ? ` · ${m.fieldName}` : ''}</span></Tooltip></Marker>)}</>;
}

export function DeviceOverlay({ markers }: { markers: DeviceMarker[] }) {
  if (!markers.length) return null;
  return <>{markers.map((m) => <Marker key={`device-${m.id}`} position={[m.lat, m.lng]} icon={deviceIcon(m.online)} zIndexOffset={DEVICE_Z}><Tooltip direction="top" offset={[0, -6]}><span dir="rtl">{m.name} · {m.dtype} · {onlineAr(m.online)}</span></Tooltip></Marker>)}</>;
}

export function WeatherOverlay({ marker }: { marker: WeatherMarker | null }) {
  if (!marker) return null;
  const parts: string[] = [];
  if (marker.conditionAr) parts.push(marker.conditionAr);
  if (marker.humidityPct != null) parts.push(`رطوبة ${Math.round(marker.humidityPct)}%`);
  if (marker.windSpeedKmh != null) parts.push(`رياح ${Math.round(marker.windSpeedKmh)} كم/س`);
  const tip = parts.length ? parts.join(' · ') : 'طقس الحقل المختار';
  return <Marker position={[marker.lat, marker.lng]} icon={weatherIcon(marker.tempC, marker.conditionAr)} zIndexOffset={WEATHER_Z}><Tooltip direction="top" offset={[0, -28]}><span dir="rtl">{tip}</span></Tooltip></Marker>;
}
