// ═══════════════════════════════════════════════════════════════
// SAHOOL — صحّة الحقل (Field Health) · خريطة الاستطلاع (Scouting)
// ───────────────────────────────────────────────────────────────
// خريطة Leaflet حقيقيّة بنمط «Scouting Pins» (FieldView): خريطة أساس
// (صور جوّيّة) + طبقة بلاطات المؤشّر (variability المنطقيّة) فوق حدود
// الحقل + دبابيس مشاهدات (pins) يُسقطها المستخدم بالنقر.
//
// ✅ الدبابيس دائمة الآن (v94): تُجلَب من GET /api/v1/scouting/pins?field_id=…
// وتُنشأ عبر POST /api/v1/fields/{id}/pins (راجع hooks/useScouting.ts). تنجو من
// إعادة التحميل (مُخزَّنة في القاعدة، معزولة بالمستأجِر RLS). صدق: القاعدة غير
// مفعّلة ⇒ حالة فارغة صريحة (لا اختراع مشاهدات) — يتولّاها المستهلِك (SatellitePage).
//
// ترميز العرض: اللون من الفئة (category)، والشكل من الدوام (persistence): الموسميّ
// دائرة ممتلئة، والدائم حلقة مزدوجة (إشارة بصريّة لمشكلة بنيويّة تبقى عبر المواسم).
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { MapContainer, TileLayer, Polygon, CircleMarker, Popup, useMapEvents } from 'react-leaflet';
import type { LatLngExpression } from 'leaflet';
import '../../lib/leafletSetup'; // CSS + أيقونات Leaflet (side-effect حاسم)
import { fieldIndicatorTileUrl, normalizeIndicatorIndex } from '../../services/api';
import { getTenantId } from '../../lib/authStorage';
import type { FieldPolygonLatLng } from '../FieldIndicatorMap';

const BASEMAP_SAT =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// فئة مشاهدة (مطابقة لـ IssueCategory في scouting_pins.py — للعرض/اللون).
export type PinCategory = 'disease' | 'pest' | 'weed' | 'nutrient' | 'water_stress' | 'abiotic' | 'other';

// دوام المشاهدة (مطابق لـ Persistence في scouting_pins.py): موسميّ vs دائم.
export type PinPersistence = 'seasonal' | 'permanent';

// شدّة المشاهدة (مطابقة لـ Severity في scouting_pins.py).
export type PinSeverity = 'low' | 'medium' | 'high';

// دبّوس مشاهدة. ``pin_id`` معرّف العميل (idempotency للخادم). ``persisted`` يُميّز
// الدبّوس المُثبَّت في القاعدة عن التفاؤليّ ريثما تكتمل إعادة الجلب (false مؤقّتاً).
export interface ScoutPin {
  id: string;                      // = pin_id (معرّف العميل المُرسَل للخادم)
  lat: number;
  lon: number;
  category: PinCategory;
  note: string;
  createdAt: string;               // ISO — وقت الإنشاء
  persistence: PinPersistence;     // موسميّ | دائم
  severity?: PinSeverity;          // الشدّة (افتراضيّاً medium)
  issueCode?: string | null;       // رمز من الـtaxonomy (مثل tomato.tuta)
  persisted?: boolean;             // هل ثُبِّت في القاعدة؟ (false = تفاؤليّ/غير محفوظ)
}

export const PIN_PERSISTENCE_AR: Record<PinPersistence, string> = {
  seasonal: 'موسميّة',
  permanent: 'دائمة',
};

export const PIN_SEVERITY_AR: Record<PinSeverity, string> = {
  low: 'خفيفة',
  medium: 'متوسّطة',
  high: 'شديدة',
};

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

// رابط قالب بلاطات المؤشّر — {z}/{x}/{y} حرفيّ ليفسّره Leaflet.
// نستخدم helper موحّد كي يحمل tid مثل باقي خرائط المؤشرات؛ وإلا ستفشل
// إعادة الترطيب tenant-scoped بعد إعادة تشغيل raster-service.
function indicatorTileUrl(fieldId: string, index: string, date: string, tenantId?: string | null): string {
  return fieldIndicatorTileUrl(fieldId, normalizeIndicatorIndex(index), date, tenantId);
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
  const tenantId = getTenantId();
  const tilesUrl = indicatorTileUrl(fieldId, index, date, tenantId);

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
          errorTileUrl="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
        />

        {/* حدود الحقل */}
        {fieldPolygon && fieldPolygon.length >= 3 && (
          <Polygon positions={fieldPolygon} pathOptions={{ color: '#5cbf6e', weight: 2, fill: false }} />
        )}

        {/* دبابيس المشاهدات (مُخزَّنة) — اللون من الفئة، الشكل من الدوام */}
        {pins.map((p) => {
          const col = pinColor(p.category);
          const isPermanent = p.persistence === 'permanent';
          return (
            <CircleMarker
              key={p.id}
              center={[p.lat, p.lon]}
              // الدائم: حلقة مزدوجة (حدّ أعرض شفّاف + لبّ ممتلئ) — إشارة بنيويّة.
              radius={isPermanent ? 9 : 8}
              pathOptions={{
                color: col,
                fillColor: col,
                fillOpacity: isPermanent ? 0.35 : 0.9,
                weight: isPermanent ? 4 : 2,
                // التفاؤليّ (لم يُثبَّت بعد) — خطّ متقطّع حتى تكتمل إعادة الجلب.
                dashArray: p.persisted === false ? '4 3' : undefined,
              }}
            >
              <Popup>
                <div dir="rtl" style={{ minWidth: 170 }}>
                  <div style={{ fontWeight: 700, color: col }}>
                    {PIN_CATEGORY_AR[p.category]}
                    {p.severity ? ` · ${PIN_SEVERITY_AR[p.severity]}` : ''}
                  </div>
                  <div style={{ fontSize: 11, color: '#475569', marginTop: 2 }}>
                    {PIN_PERSISTENCE_AR[p.persistence]}
                    {p.issueCode ? ` · ${p.issueCode}` : ''}
                  </div>
                  {p.note && <div style={{ fontSize: 12, marginTop: 4, color: '#334155' }}>{p.note}</div>}
                  <div style={{ fontSize: 11, color: '#64748b', marginTop: 4 }}>
                    📍 {p.lat.toFixed(5)}، {p.lon.toFixed(5)}
                  </div>
                  {p.persisted === false && (
                    <div style={{ fontSize: 10, color: '#b45309', marginTop: 3 }}>
                      لم يُحفَظ بعد (بانتظار التزامن)
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => onRemovePin(p.id)}
                    style={{
                      marginTop: 6, fontSize: 11, color: '#dc2626', background: 'transparent',
                      border: '1px solid #fca5a5', borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
                    }}
                  >
                    إخفاء من العرض
                  </button>
                </div>
              </Popup>
            </CircleMarker>
          );
        })}

        <ClickToDrop onDrop={onDropPin} />
      </MapContainer>

      {/* تلميح الإسقاط (RTL) */}
      <div
        dir="rtl"
        style={{
          position: 'absolute', bottom: 12, insetInlineEnd: 12, zIndex: 1000,
          background: 'rgba(13,22,17,.88)', borderRadius: 10, padding: '6px 10px',
          fontSize: 11, color: '#cdddd2', border: '1px solid #2d4a37', backdropFilter: 'blur(6px)',
          maxWidth: 240,
        }}
      >
        انقر الخريطة لإسقاط دبّوس مشاهدة — يُحفَظ على الخادم ويبقى عبر الجلسات.
      </div>
    </div>
  );
}
