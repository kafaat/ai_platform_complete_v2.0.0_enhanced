// ═══════════════════════════════════════════════════════════════
// SAHOOL — صحّة الحقل (Field Health) · خريطة الاستطلاع (Scouting)
// ───────────────────────────────────────────────────────────────
// خريطة Leaflet حقيقيّة بنمط «Scouting Pins» (FieldView): خريطة أساس
// (صور جوّيّة) + طبقة بلاطات المؤشّر (variability المنطقيّة) فوق حدود
// الحقل + دبابيس مشاهدات (pins) يُسقطها المستخدم بالنقر.
//
// ⚠️ صدق المصدر (TODO موثّق): الخادم لا يوفّر نقطة قراءة (GET) لدبابيس
// المشاهدات — نقطتا /api/v1/scouting/pins و/timeline في الخادم POST فقط
// (إنشاء/تجميع من حمولة الطلب) ولا تُرجِعان قائمة مُخزَّنة تُقرأ بـGET
// (راجع hooks/useScouting.ts و scouting_pins.py). لذا الدبابيس هنا
// **محلّيّة للجلسة فقط** (state في الذاكرة): لا تُحفَظ ولا تُجلَب من الخادم،
// وتختفي بإعادة التحميل. لا نخترع endpoint قراءة ولا نُلفّق مشاهدات مُخزَّنة.
// عند توفّر GET /scouting/pins?field_id=… مستقبلاً تُربَط هنا (نقطة تمديد).
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { MapContainer, TileLayer, Polygon, CircleMarker, Popup, useMapEvents } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';
import '../../lib/leafletSetup'; // CSS + أيقونات Leaflet (side-effect حاسم)
import { rasterApi } from '../../services/api';
import type { FieldPolygonLatLng } from '../FieldIndicatorMap';

const RASTER = (rasterApi.defaults.baseURL || '').replace(/\/+$/, '');
const BASEMAP_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// فئة مشاهدة (مطابقة لـ IssueCategory في scouting_pins.py — للعرض/اللون).
export type PinCategory = 'disease' | 'pest' | 'weed' | 'nutrient' | 'water_stress' | 'abiotic' | 'other';

// دبّوس مشاهدة محلّيّ للجلسة (لا مُعرّف خادم — مُعرّف محلّيّ فقط).
export interface ScoutPin {
  id: string;
  lat: number;
  lon: number;
  category: PinCategory;
  note: string;
  createdAt: string; // ISO محلّيّ — وقت الإسقاط في المتصفّح
}

export const PIN_CATEGORY_AR: Record<PinCategory, string> = {
  disease: 'مرض',
  pest: 'آفة',
  weed: 'أعشاب ضارّة',
  nutrient: 'نقص عنصر',
  water_stress: 'إجهاد مائي',
  abiotic: 'غير حيوي',
  other: 'أخرى',
};

const PIN_COLOR: Record<PinCategory, string> = {
  disease: '#dc2626',
  pest: '#ea580c',
  weed: '#a16207',
  nutrient: '#a855f7',
  water_stress: '#0ea5e9',
  abiotic: '#64748b',
  other: '#16a34a',
};

export function pinColor(c: PinCategory): string {
  return PIN_COLOR[c] ?? PIN_COLOR.other;
}

// رابط قالب بلاطات المؤشّر — {z}/{x}/{y} حرفيّ ليفسّرها Leaflet.
function indicatorTileUrl(fieldId: string, index: string, date: string): string {
  const qs = `index=${encodeURIComponent(index)}&date=${encodeURIComponent(date)}`;
  // eslint-disable-next-line no-template-curly-in-string
  return `${RASTER}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
}

// مُستمِع نقر الخريطة لإسقاط دبّوس عند الإحداثيّات المنقورة.
function ClickToDrop({ onDrop }: { onDrop: (lat: number, lon: number) => void }) {
  useMapEvents({
    click(e) {
      onDrop(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export interface ScoutingMapProps {
  fieldId: string;
  index: string;
  date: string;
  fieldPolygon?: FieldPolygonLatLng;
  fallbackBounds?: [number, number, number, number]; // [w, s, e, n]
  pins: ScoutPin[];
  onDropPin: (lat: number, lon: number) => void;
  onRemovePin: (id: string) => void;
  opacity?: number;
  height?: number | string;
}

export default function ScoutingMap({
  fieldId,
  index,
  date,
  fieldPolygon,
  fallbackBounds,
  pins,
  onDropPin,
  onRemovePin,
  opacity = 0.7,
  height = 400,
}: ScoutingMapProps) {
  const tilesUrl = indicatorTileUrl(fieldId, index, date);

  // مركز افتراضيّ من المضلّع/الإطار الاحتياطيّ (نفس منطق FieldIndicatorMap).
  const center: LatLngExpression = useMemo(() => {
    if (fieldPolygon && fieldPolygon.length) return fieldPolygon[0];
    if (fallbackBounds) {
      return [(fallbackBounds[1] + fallbackBounds[3]) / 2, (fallbackBounds[0] + fallbackBounds[2]) / 2];
    }
    return [16.153, 45.303];
  }, [fieldPolygon, fallbackBounds]);

  return (
    <div style={{ position: 'relative', borderRadius: 14, overflow: 'hidden', border: '1px solid #2d4a37' }}>
      <MapContainer center={center} zoom={15} style={{ height, width: '100%' }} scrollWheelZoom>
        <TileLayer url={BASEMAP_SAT} attribution='&copy; <a href="https://www.esri.com/">Esri</a>' />

        {/* طبقة بلاطات المؤشّر (التباين المكانيّ) — شفّافة خارج الحقل */}
        <TileLayer
          key={`${fieldId}-${index}-${date}`}
          url={tilesUrl}
          opacity={opacity}
          errorTileUrl="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ/pLvAAAAAElFTkSuQmCC"
        />

        {/* حدود الحقل */}
        {fieldPolygon && fieldPolygon.length >= 3 && (
          <Polygon positions={fieldPolygon} pathOptions={{ color: '#5cbf6e', weight: 2, fill: false }} />
        )}

        {/* دبابيس المشاهدات (محلّيّة للجلسة) */}
        {pins.map((p) => (
          <CircleMarker
            key={p.id}
            center={[p.lat, p.lon]}
            radius={8}
            pathOptions={{ color: pinColor(p.category), fillColor: pinColor(p.category), fillOpacity: 0.9, weight: 2 }}
          >
            <Popup>
              <div dir="rtl" style={{ minWidth: 160 }}>
                <div style={{ fontWeight: 700, color: pinColor(p.category) }}>
                  {PIN_CATEGORY_AR[p.category]}
                </div>
                {p.note && <div style={{ fontSize: 12, marginTop: 4, color: '#334155' }}>{p.note}</div>}
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                  📍 {p.lat.toFixed(5)}، {p.lon.toFixed(5)}
                </div>
                <button
                  type="button"
                  onClick={() => onRemovePin(p.id)}
                  style={{
                    marginTop: 6, fontSize: 11, color: '#dc2626', background: 'transparent',
                    border: '1px solid #fca5a5', borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
                  }}
                >
                  حذف الدبّوس
                </button>
              </div>
            </Popup>
          </CircleMarker>
        ))}

        <ClickToDrop onDrop={onDropPin} />
      </MapContainer>

      {/* تلميح الإسقاط (RTL) */}
      <div
        dir="rtl"
        style={{
          position: 'absolute', bottom: 12, insetInlineEnd: 12, zIndex: 1000,
          background: 'rgba(13,22,17,.88)', borderRadius: 10, padding: '6px 10px',
          fontSize: 11, color: '#cdddd2', border: '1px solid #2d4a37', backdropFilter: 'blur(6px)',
          maxWidth: 230,
        }}
      >
        انقر الخريطة لإسقاط دبّوس مشاهدة (محلّيّ للجلسة — لا يُحفَظ على الخادم).
      </div>
    </div>
  );
}
