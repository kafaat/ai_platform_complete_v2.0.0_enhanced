// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · الخريطة الأساسيّة (Leaflet 2D)
// ───────────────────────────────────────────────────────────────
// خريطة Leaflet موحّدة لمركز الخرائط: تعرض كلّ الحقول (مضلّع/نقطة) مع إبراز
// الحقل المختار، طبقة أساس قابلة للتبديل (CARTO/Esri من layerRegistry)، طبقة
// بلاطات مؤشّر اختياريّة (raster-service) بشفّافيّة مضبوطة فوق الحقل المختار،
// أدوات رسم/قياس اختياريّة (turf — مطابقة لـFieldIndicatorMap)، ودبابيس استكشاف
// (إضافة بالنقر/عرض). تعيد استخدام أنماط FarmMapOverview + FieldIndicatorMap +
// AddFieldWithMap بلا تكرار للمنطق الهندسيّ (lib/geo).
//
// صدق البيانات: الحقول/الحدود من useFieldOptions الحيّة. بلاطات المؤشّر مقصوصة
// على الحقل من الخلفيّة (errorTileUrl شفّاف يتفادى 404 صاخب). الدبابيس حالة
// محلّيّة (لا نقطة قراءة scouting في الخلفيّة — موثّق في MapHub بـTODO).
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  MapContainer, TileLayer, Polygon, CircleMarker, Marker, Tooltip,
  FeatureGroup, useMap, useMapEvents,
} from 'react-leaflet';
import DrawControl from './DrawControl'; // أداة رسم على leaflet-draw خام (بديل EditControl — توافق React 19)
import L from 'leaflet';
import '../../lib/leafletSetup';
import { geomToPolygon, collectFieldBoundsPoints, fieldRepresentativePoint, areaSqMeters, lengthMeters } from '../../lib/geo';
import { getLayer } from '../../lib/layerRegistry';
import { rasterBaseUrl } from '../../services/api';
import type { FieldOption } from '../../lib/fields';
import {
  AlertOverlay, DeviceOverlay, WeatherOverlay,
  type AlertMarker, type DeviceMarker, type WeatherMarker,
} from './OverlayMarkers';

const YEMEN_CENTER: [number, number] = [15.0, 44.0];
const SELECTED_COLOR = '#22d3ee';
const FIELD_COLOR = '#34d399';

export interface ScoutPin {
  id: string;
  lat: number;
  lng: number;
  note: string;
  category: string;
}

export interface HubMapProps {
  fields: FieldOption[];
  selectedId: string;
  onSelect: (id: string) => void;
  // معرّف خريطة الأساس من layerRegistry (kind:'basemap'): 'satellite' | 'light'.
  basemapId: string;
  // معرّف طبقة المؤشّر النشطة (kind:'index') أو null لإخفاء طبقة المؤشّر.
  indicatorId: string | null;
  indicatorOpacity: number;
  // أدوات الرسم/القياس (مضلّع→مساحة · خطّ→طول).
  drawTools: boolean;
  // وضع إضافة دبابيس الاستكشاف بالنقر على الخريطة.
  pinMode: boolean;
  pins: ScoutPin[];
  onAddPin: (lat: number, lng: number) => void;
  height?: number | string;
  // طبقات تراكب اختياريّة (طقس/تنبيهات/أجهزة) — بيانات حيّة مُبسَّطة من MapHub.
  // كلّها افتراضيّاً فارغة/null (لا تُعرَض في المقارنة). الإحداثيّات محسوبة في
  // MapHub من النقطة الممثِّلة لحقل العنصر — لا اختراع هنا.
  alertMarkers?: AlertMarker[];
  deviceMarkers?: DeviceMarker[];
  weatherMarker?: WeatherMarker | null;
}

export type { AlertMarker, DeviceMarker, WeatherMarker };

// ── تنسيق عرض القياسات (نفس FieldIndicatorMap) ──────────────────
function fmtArea(m2: number): string {
  const ha = m2 / 10000;
  return `${Math.round(m2).toLocaleString('en-US')} م² · ${ha.toFixed(2)} هكتار`;
}
function fmtLength(m: number): string {
  const km = m / 1000;
  return `${Math.round(m).toLocaleString('en-US')} م · ${km.toFixed(2)} كم`;
}

interface Measurement { id: number; kind: 'polygon' | 'polyline'; areaM2?: number; lengthM?: number }

function measureLayer(layer: L.Layer): Measurement | null {
  const id = L.stamp(layer);
  const toGeoJSON = (layer as { toGeoJSON?: () => GeoJSON.Feature }).toGeoJSON;
  let gj: GeoJSON.Feature | null;
  try { gj = toGeoJSON?.() ?? null; } catch { gj = null; }
  const type = gj?.geometry?.type;
  if (type === 'Polygon' || type === 'MultiPolygon') return { id, kind: 'polygon', areaM2: areaSqMeters(gj) };
  if (type === 'LineString' || type === 'MultiLineString') return { id, kind: 'polyline', lengthM: lengthMeters(gj) };
  return null;
}

// لوحة أدوات القياس (مطابقة نمطاً لـFieldIndicatorMap.MeasureTools).
function MeasureTools() {
  const [fg, setFg] = useState<L.FeatureGroup | null>(null);
  const [items, setItems] = useState<Measurement[]>([]);

  const recompute = useCallback((group: L.FeatureGroup | null) => {
    if (!group) { setItems([]); return; }
    const next: Measurement[] = [];
    group.eachLayer((layer) => { const m = measureLayer(layer); if (m) next.push(m); });
    setItems(next);
  }, []);

  const handleChange = useCallback(() => recompute(fg), [fg, recompute]);
  const handleClear = useCallback(() => { if (fg) fg.clearLayers(); setItems([]); }, [fg]);

  const totalArea = items.reduce((s, m) => s + (m.areaM2 ?? 0), 0);
  const totalLen = items.reduce((s, m) => s + (m.lengthM ?? 0), 0);
  const polys = items.filter((m) => m.kind === 'polygon');
  const lines = items.filter((m) => m.kind === 'polyline');

  return (
    <>
      <FeatureGroup ref={(r: L.FeatureGroup | null) => setFg(r)}>
        <DrawControl
          position="topright"
          onCreated={handleChange}
          onEdited={handleChange}
          onDeleted={handleChange}
          draw={{
            polygon: { allowIntersection: false, showArea: false, shapeOptions: { color: '#38bdf8' } },
            polyline: { shapeOptions: { color: '#fbbf24' } },
            rectangle: false, circle: false, marker: false, circlemarker: false,
          }}
          edit={{ edit: {}, remove: {} }}
        />
      </FeatureGroup>
      <div
        dir="rtl"
        style={{
          position: 'absolute', top: 12, left: 12, zIndex: 1000,
          background: 'rgba(13,22,17,.92)', borderRadius: 10, padding: '10px 12px',
          fontSize: 12, color: '#e2e8f0', border: '1px solid #2d4a37',
          backdropFilter: 'blur(6px)', maxWidth: 260,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <span style={{ fontWeight: 700, color: '#5cbf6e' }}>أدوات القياس</span>
          {items.length > 0 && (
            <button
              type="button" onClick={handleClear}
              style={{
                marginRight: 'auto', fontSize: 11, color: '#fca5a5', background: 'transparent',
                border: '1px solid #7a2a2a', borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
              }}
            >مسح</button>
          )}
        </div>
        {items.length === 0 ? (
          <p style={{ color: '#9fb3a6', lineHeight: 1.6, margin: 0 }}>
            ارسم مضلّعاً للمساحة أو خطّاً للطول من شريط الأدوات أعلى يمين الخريطة.
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {polys.length > 0 && (
              <div>
                <div style={{ color: '#7dd3fc', fontWeight: 600 }}>المساحة ({polys.length})</div>
                <div style={{ color: '#cdddd2' }}>{fmtArea(totalArea)}</div>
              </div>
            )}
            {lines.length > 0 && (
              <div>
                <div style={{ color: '#fcd34d', fontWeight: 600 }}>الطول ({lines.length})</div>
                <div style={{ color: '#cdddd2' }}>{fmtLength(totalLen)}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// يضبط إطار الخريطة على الحقل المختار إن وُجد، وإلّا على كلّ الحقول.
function FitToFields({
  fields, selectedId,
}: {
  fields: FieldOption[];
  selectedId: string;
}) {
  const map = useMap();
  useEffect(() => {
    const selected = fields.find((f) => f.id === selectedId);
    if (selected) {
      const poly = geomToPolygon(selected.geometry);
      if (poly && poly.length >= 3) {
        const b = L.latLngBounds(poly.map(([lat, lng]) => L.latLng(lat, lng)));
        if (b.isValid()) { map.fitBounds(b, { padding: [40, 40], maxZoom: 17 }); return; }
      }
      const pt = fieldRepresentativePoint(selected);
      if (pt) { map.setView(pt, 15); return; }
    }
    const points = collectFieldBoundsPoints(fields);
    if (points.length) {
      const b = L.latLngBounds(points.map(([lat, lng]) => L.latLng(lat, lng)));
      if (b.isValid()) map.fitBounds(b, { padding: [30, 30], maxZoom: 16 });
    }
  }, [map, fields, selectedId]);
  return null;
}

// يلتقط النقر على الخريطة لإضافة دبّوس استكشاف حين pinMode مفعّل.
function PinClickHandler({ enabled, onAddPin }: { enabled: boolean; onAddPin: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) { if (enabled) onAddPin(e.latlng.lat, e.latlng.lng); },
  });
  return null;
}

// رابط بلاطات المؤشّر — نُبقي {z}/{x}/{y} حرفيّاً ليفسّرها Leaflet (مطابق api.ts).
function indicatorTileUrl(fieldId: string, index: string): string {
  const qs = `index=${encodeURIComponent(index)}&date=latest`;
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
}

// أيقونة دبّوس استكشاف (divIcon — لا أصل صورة خارجيّ).
const PIN_ICON = L.divIcon({
  className: 'sahool-scout-pin',
  html: '<div style="font-size:22px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))">📍</div>',
  iconSize: [22, 22],
  iconAnchor: [11, 22],
});

export default function HubMap({
  fields, selectedId, onSelect, basemapId, indicatorId, indicatorOpacity,
  drawTools, pinMode, pins, onAddPin, height = 520,
  alertMarkers = [], deviceMarkers = [], weatherMarker = null,
}: HubMapProps) {
  const basemap = getLayer(basemapId);
  const basemapUrl = basemap?.source
    ?? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

  const center = useMemo<[number, number]>(() => {
    const points = collectFieldBoundsPoints(fields);
    if (!points.length) return YEMEN_CENTER;
    const [sumLat, sumLng] = points.reduce(([a, b], [la, ln]) => [a + la, b + ln], [0, 0]);
    return [sumLat / points.length, sumLng / points.length];
  }, [fields]);

  const selected = fields.find((f) => f.id === selectedId);
  const selectedPoly = selected ? geomToPolygon(selected.geometry) : undefined;

  return (
    <div data-testid="leaflet-map" style={{ position: 'relative', borderRadius: 14, overflow: 'hidden', border: '1px solid #2d4a37' }}>
      <MapContainer
        className="leaflet-map"
        center={center}
        zoom={11}
        style={{ height, width: '100%', cursor: pinMode ? 'crosshair' : undefined }}
        scrollWheelZoom
      >
        <TileLayer
          key={basemapId}
          url={basemapUrl}
          attribution={basemapId === 'light'
            ? '&copy; <a href="https://carto.com/">CARTO</a>'
            : '&copy; <a href="https://www.esri.com/">Esri</a> — World Imagery'}
        />

        {/* طبقة بلاطات المؤشّر للحقل المختار (شفّافة خارج الحقل) */}
        {indicatorId && selected && (
          <TileLayer
            key={`${selected.id}-${indicatorId}`}
            url={indicatorTileUrl(selected.id, indicatorId)}
            opacity={indicatorOpacity}
            errorTileUrl="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
          />
        )}

        {/* كلّ الحقول: مضلّع لذي الهندسة، نقطة لما بلا هندسة (نمط FarmMapOverview) */}
        {fields.map((f) => {
          const poly = geomToPolygon(f.geometry);
          const isSel = f.id === selectedId;
          const label = `${f.name}${f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}`;
          if (poly && poly.length >= 3) {
            return (
              <Polygon
                key={f.id}
                positions={poly}
                pathOptions={{
                  color: isSel ? SELECTED_COLOR : FIELD_COLOR,
                  weight: isSel ? 3 : 1.5,
                  fillOpacity: isSel ? 0.25 : 0.12,
                }}
                eventHandlers={{ click: () => onSelect(f.id) }}
              >
                <Tooltip>{label}</Tooltip>
              </Polygon>
            );
          }
          const pt = fieldRepresentativePoint(f);
          if (!pt) return null;
          return (
            <CircleMarker
              key={f.id}
              center={pt}
              radius={isSel ? 9 : 6}
              pathOptions={{
                color: isSel ? SELECTED_COLOR : FIELD_COLOR,
                fillColor: isSel ? SELECTED_COLOR : FIELD_COLOR,
                fillOpacity: 0.8, weight: isSel ? 3 : 1.5,
              }}
              eventHandlers={{ click: () => onSelect(f.id) }}
            >
              <Tooltip>{label}</Tooltip>
            </CircleMarker>
          );
        })}

        {/* حدّ الحقل المختار مُبرَزاً فوق البلاطات (وضوح بصريّ) */}
        {selectedPoly && selectedPoly.length >= 3 && (
          <Polygon
            positions={selectedPoly}
            pathOptions={{ color: SELECTED_COLOR, weight: 3, fill: false }}
          />
        )}

        {/* دبابيس الاستكشاف */}
        {pins.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={PIN_ICON}>
            <Tooltip>{p.note || p.category}</Tooltip>
          </Marker>
        ))}

        {/* طبقات التراكب (طقس/تنبيهات/أجهزة) — تُرسَم فقط عند توفّر عناصر قابلة
            للعرض. الحرّاس داخل المكوّنات تتكفّل بالفراغ/الـnull. */}
        <AlertOverlay markers={alertMarkers} />
        <DeviceOverlay markers={deviceMarkers} />
        <WeatherOverlay marker={weatherMarker} />

        <PinClickHandler enabled={pinMode} onAddPin={onAddPin} />
        {drawTools && <MeasureTools />}
        <FitToFields fields={fields} selectedId={selectedId} />
      </MapContainer>

      {/* شريط التحكّم بشفّافيّة المؤشّر — يظهر فقط حين توجد طبقة مؤشّر نشطة */}
      {indicatorId && selected && (
        <div
          dir="rtl"
          style={{
            position: 'absolute', bottom: 12, right: 12, zIndex: 1000,
            background: 'rgba(13,22,17,.88)', borderRadius: 10, padding: '8px 12px',
            display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: '#cdddd2',
            border: '1px solid #2d4a37', backdropFilter: 'blur(6px)',
          }}
        >
          <span style={{ whiteSpace: 'nowrap' }}>شفافية المؤشّر</span>
          <span style={{ width: 34, textAlign: 'left', fontVariantNumeric: 'tabular-nums' }}>
            {Math.round(indicatorOpacity * 100)}%
          </span>
        </div>
      )}

      {pinMode && (
        <div
          dir="rtl"
          style={{
            position: 'absolute', top: 12, right: 12, zIndex: 1000,
            background: 'rgba(13,22,17,.9)', borderRadius: 10, padding: '6px 12px',
            fontSize: 12, color: '#fcd34d', border: '1px solid #5a4a1f',
          }}
        >
          انقر على الخريطة لإضافة دبّوس استكشاف
        </div>
      )}
    </div>
  );
}
