// ═══════════════════════════════════════════════════════════════
// SAHOOL — FieldIndicatorMap.tsx
// عرض خريطة حقيقية (Leaflet) مع طبقة بلاطات المؤشر (XYZ tiles) من
// raster-service مقصوصة فوق حدود الحقل:
//   • خريطة أساس (CARTO / ArcGIS satellite) — نفس روابط AddFieldWithMap
//   • حدود الحقل (مضلع) إن توفّرت
//   • طبقة بلاطات المؤشر colormapped PNG (شفّافة خارج الحقل) فوق الأساس
//   • ضبط الإطار (fitBounds) على حدود الحقل / TileJSON
//   • شريط تحكّم بالشفافية (opacity)
//
// ملاحظة مهمّة: قالب رابط Leaflet `{z}/{x}/{y}` يُمرَّر حرفيّاً إلى
// TileLayer.url (Leaflet هو من يستبدلها)، فلا نستخدم استبدال JS داخل
// هذا الجزء — فقط نُمرّر index/date عبر استعلام مُرمَّز.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useState } from 'react';
import { MapContainer, TileLayer, Polygon, useMap } from 'react-leaflet';
import L from 'leaflet';
import { rasterApi } from '../services/api';

// قاعدة خدمة الراستر (نفس الأساس المستخدم في useIndicatorGrid / VITE_RASTER_URL)
const RASTER = (rasterApi.defaults.baseURL || '').replace(/\/+$/, '');

// روابط خرائط الأساس (نفس AddFieldWithMap.tsx)
const BASEMAP_LIGHT = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const BASEMAP_SAT   = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// عقد TileJSON القادمة من raster-service
export interface TileJSON {
  tilejson: string;
  tiles: string[];
  bounds: [number, number, number, number]; // [w, s, e, n]
  minzoom?: number;
  maxzoom?: number;
  center?: [number, number, number] | [number, number];
}

// حدود الحقل كـ [lat, lng] لكل رأس (مناسبة مباشرة لـ Leaflet Polygon)
export type FieldPolygonLatLng = [number, number][];

export interface FieldIndicatorMapProps {
  fieldId: string;
  index: string;            // ndvi | ndmi | ndwi | salinity
  date: string;             // latest | YYYY-MM-DD
  // حدود الحقل (مضلع) إن توفّرت — مصفوفة [lat, lng]
  fieldPolygon?: FieldPolygonLatLng;
  // إطار افتراضي [w, s, e, n] للضبط حين لا يتوفّر مضلع ولا TileJSON بعد
  fallbackBounds?: [number, number, number, number];
  basemap?: 'light' | 'satellite';
  initialOpacity?: number;
  height?: number | string;
}

// رابط قالب بلاطات المؤشر — نُبقي {z}/{x}/{y} حرفيّاً ليفسّرها Leaflet.
function indicatorTileUrl(fieldId: string, index: string, date: string): string {
  const qs = `index=${encodeURIComponent(index)}&date=${encodeURIComponent(date)}`;
  // eslint-disable-next-line no-template-curly-in-string
  return `${RASTER}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
}

// مكوّن داخلي: يضبط إطار الخريطة على الحدود المتاحة (مضلع → TileJSON → fallback)
function FitBounds({
  polygon,
  tileBounds,
  fallbackBounds,
}: {
  polygon?: FieldPolygonLatLng;
  tileBounds?: [number, number, number, number];
  fallbackBounds?: [number, number, number, number];
}) {
  const map = useMap();
  useEffect(() => {
    let bounds: L.LatLngBounds | null = null;
    if (polygon && polygon.length >= 3) {
      bounds = L.latLngBounds(polygon.map(([lat, lng]) => L.latLng(lat, lng)));
    } else if (tileBounds) {
      const [w, s, e, n] = tileBounds;
      bounds = L.latLngBounds(L.latLng(s, w), L.latLng(n, e));
    } else if (fallbackBounds) {
      const [w, s, e, n] = fallbackBounds;
      bounds = L.latLngBounds(L.latLng(s, w), L.latLng(n, e));
    }
    if (bounds && bounds.isValid()) {
      map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
    }
  }, [map, polygon, tileBounds, fallbackBounds]);
  return null;
}

export default function FieldIndicatorMap({
  fieldId,
  index,
  date,
  fieldPolygon,
  fallbackBounds,
  basemap = 'satellite',
  initialOpacity = 0.75,
  height = 420,
}: FieldIndicatorMapProps) {
  const [opacity, setOpacity] = useState(initialOpacity);
  const [tileBounds, setTileBounds] = useState<[number, number, number, number] | undefined>();

  const baseUrl = basemap === 'satellite' ? BASEMAP_SAT : BASEMAP_LIGHT;
  const tilesUrl = indicatorTileUrl(fieldId, index, date);

  // جلب TileJSON لضبط الإطار حين لا يتوفّر مضلع (اختياري — الفشل غير حرج)
  useEffect(() => {
    let cancelled = false;
    setTileBounds(undefined);
    rasterApi
      .get<TileJSON>(`/v1/fields/${fieldId}/tilejson`, { params: { index, date } })
      .then((r) => {
        if (cancelled) return;
        const b = r.data?.bounds;
        if (Array.isArray(b) && b.length === 4) {
          setTileBounds([b[0], b[1], b[2], b[3]]);
        }
      })
      .catch(() => { /* TileJSON غير متاح — نعتمد على المضلع/الإطار الاحتياطي */ });
    return () => { cancelled = true; };
  }, [fieldId, index, date]);

  // مركز افتراضي قبل ضبط fitBounds
  const center: [number, number] = fieldPolygon && fieldPolygon.length
    ? fieldPolygon[0]
    : fallbackBounds
      ? [(fallbackBounds[1] + fallbackBounds[3]) / 2, (fallbackBounds[0] + fallbackBounds[2]) / 2]
      : [16.153, 45.303];

  return (
    <div style={{ position: 'relative', borderRadius: 14, overflow: 'hidden', border: '1px solid #2d4a37' }}>
      <MapContainer
        center={center}
        zoom={15}
        style={{ height, width: '100%' }}
        scrollWheelZoom
      >
        {/* خريطة الأساس */}
        <TileLayer
          url={baseUrl}
          attribution={basemap === 'satellite'
            ? '&copy; <a href="https://www.esri.com/">Esri</a>'
            : '&copy; <a href="https://carto.com/">CARTO</a>'}
        />

        {/* طبقة بلاطات المؤشر (شفّافة خارج الحقل) — {z}/{x}/{y} حرفيّ */}
        <TileLayer
          key={`${fieldId}-${index}-${date}`}
          url={tilesUrl}
          opacity={opacity}
          // المؤشر مقصوص بالفعل على الحقل من الـ backend؛ نتجنّب أخطاء 404 صاخبة
          errorTileUrl="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
        />

        {/* حدود الحقل إن توفّرت */}
        {fieldPolygon && fieldPolygon.length >= 3 && (
          <Polygon
            positions={fieldPolygon}
            pathOptions={{ color: '#5cbf6e', weight: 2, fill: false }}
          />
        )}

        <FitBounds polygon={fieldPolygon} tileBounds={tileBounds} fallbackBounds={fallbackBounds} />
      </MapContainer>

      {/* شريط التحكّم بالشفافية */}
      <div
        dir="rtl"
        style={{
          position: 'absolute', bottom: 12, right: 12, zIndex: 1000,
          background: 'rgba(13,22,17,.88)', borderRadius: 10, padding: '8px 12px',
          display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#cdddd2',
          border: '1px solid #2d4a37', backdropFilter: 'blur(6px)',
        }}
      >
        <span style={{ whiteSpace: 'nowrap' }}>شفافية المؤشر</span>
        <input
          type="range" min={0} max={1} step={0.05} value={opacity}
          onChange={(e) => setOpacity(parseFloat(e.target.value))}
          style={{ width: 110, accentColor: '#5cbf6e' }}
          aria-label="indicator opacity"
        />
        <span style={{ width: 34, textAlign: 'left', fontVariantNumeric: 'tabular-nums' }}>
          {Math.round(opacity * 100)}%
        </span>
      </div>
    </div>
  );
}
