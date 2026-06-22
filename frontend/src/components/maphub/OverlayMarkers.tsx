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
import { Marker, Tooltip } from 'react-leaflet';
import L from 'leaflet';

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
}

// طبقات التراكب تجلس فوق المضلّعات/البلاطات (zIndexOffset موجب كبير).
const ALERT_Z = 800;
const DEVICE_Z = 750;
const WEATHER_Z = 900;

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
