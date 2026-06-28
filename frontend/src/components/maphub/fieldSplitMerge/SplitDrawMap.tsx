// ═══════════════════════════════════════════════════════════════
// SAHOOL — maphub/fieldSplitMerge/SplitDrawMap.tsx
// شريحة مستخرَجة من FieldSplitMergeTool (تفكيك محفوظ السلوك): خريطة التقسيم.
// ───────────────────────────────────────────────────────────────
// تعرض حدّ الحقل الأصليّ + أداة رسم مضلّع القصّ + معاينة الجزأين (أ/ب). النقل
// حرفيّ 1:1؛ العقد عبر props صريحة، ولا تغيير في منطق الرسم/القصّ أو أسماء DOM.
//
// تُصدَّر أيضاً المساعِدتان layerToGeometry وgeomToLeafletRings لأنّهما تُستعمَلان
// هنا (وgeomToLeafletRings يُعيد استعمالها الأصل لمعاينة الدمج).
// ═══════════════════════════════════════════════════════════════
import { useCallback } from 'react';
import { MapContainer, TileLayer, Polygon, FeatureGroup } from 'react-leaflet';
import L from 'leaflet';
import DrawControl from '../DrawControl';
import { geomToPolygon } from '../../../lib/geo';
import { type ArealGeometry } from '../../../lib/fieldGeometryOps';
import type { FieldOption } from '../../../lib/fields';
import { T, RADIUS, Card } from '../../ds';
import { LoadingState } from '../../StateViews';

// هندسة GeoJSON Polygon المرسومة من leaflet-draw → شكل {type,coordinates}.
export function layerToGeometry(layer: L.Layer): ArealGeometry | null {
  const toGeoJSON = (layer as { toGeoJSON?: () => GeoJSON.Feature }).toGeoJSON;
  let gj: GeoJSON.Feature | null;
  try { gj = toGeoJSON?.() ?? null; } catch { gj = null; }
  const g = gj?.geometry;
  if (g && (g.type === 'Polygon' || g.type === 'MultiPolygon')) {
    return g as ArealGeometry;
  }
  return null;
}

// يحوّل هندسة مساحيّة (Polygon/MultiPolygon) إلى حلقات Leaflet للمعاينة.
export function geomToLeafletRings(geom: ArealGeometry | null): [number, number][][] {
  if (!geom) return [];
  if (geom.type === 'Polygon') {
    const ring = geomToPolygon(geom);
    return ring ? [ring] : [];
  }
  // MultiPolygon: حلقة خارجيّة لكلّ جزء.
  const out: [number, number][][] = [];
  for (const part of geom.coordinates) {
    const ring = geomToPolygon({ type: 'Polygon', coordinates: part });
    if (ring) out.push(ring);
  }
  return out;
}

// ── خريطة التقسيم: حدّ الحقل + أداة رسم القصّ + معاينة الجزأين ──
export default function SplitDrawMap({
  field, preview, onCut,
}: {
  field: FieldOption | undefined;
  preview: { partA: ArealGeometry; partB: ArealGeometry } | null;
  onCut: (geom: ArealGeometry | null) => void;
}) {
  if (!field) {
    return (
      <Card pad={12}>
        <div style={{ color: T.muted, fontSize: 13, textAlign: 'center', padding: '24px 0' }}>
          اختَر حقلاً لرسم مضلّع القصّ عليه.
        </div>
      </Card>
    );
  }
  const ring = geomToPolygon(field.geometry);
  const partARings = geomToLeafletRings(preview?.partA ?? null);
  const partBRings = geomToLeafletRings(preview?.partB ?? null);

  return (
    <SplitDrawInner
      key={field.id}
      fieldRing={ring}
      partARings={partARings}
      partBRings={partBRings}
      onCut={onCut}
    />
  );
}

// مكوّن داخليّ يحمل أداة الرسم (يُعاد إنشاؤه عند تبديل الحقل عبر key من الأب).
function SplitDrawInner({
  fieldRing, partARings, partBRings, onCut,
}: {
  fieldRing: [number, number][] | undefined;
  partARings: [number, number][][];
  partBRings: [number, number][][];
  onCut: (geom: ArealGeometry | null) => void;
}) {
  const points = fieldRing && fieldRing.length >= 3 ? fieldRing : null;
  // عند فقدان الحدّ لا خريطة (لا يُفترَض أن يحدث — arealFields مفروزة).
  const handleCreated = useCallback((e: L.DrawEvents.Created) => {
    onCut(layerToGeometry(e.layer));
  }, [onCut]);
  const handleDeleted = useCallback(() => onCut(null), [onCut]);

  if (!points) {
    return <Card pad={12}><LoadingState message="جارٍ تجهيز الخريطة…" /></Card>;
  }

  return (
    <div style={{ borderRadius: RADIUS.md, overflow: 'hidden', border: `1px solid ${T.line}` }}>
      <MapContainer
        bounds={L.latLngBounds(points.map(([la, ln]) => L.latLng(la, ln)))}
        boundsOptions={{ padding: [30, 30] }}
        style={{ height: 360, width: '100%' }}
        scrollWheelZoom
      >
        <TileLayer
          url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          attribution='&copy; <a href="https://www.esri.com/">Esri</a>'
        />
        {/* حدّ الحقل الأصليّ */}
        <Polygon positions={points} pathOptions={{ color: '#34d399', weight: 2, fillOpacity: 0.08 }} />
        {/* معاينة الجزأين (إن رُسم قصّ صالح) */}
        {partARings.map((r, i) => (
          <Polygon key={`a-${i}`} positions={r} pathOptions={{ color: '#22d3ee', weight: 3, fillOpacity: 0.25 }} />
        ))}
        {partBRings.map((r, i) => (
          <Polygon key={`b-${i}`} positions={r} pathOptions={{ color: '#fbbf24', weight: 3, fillOpacity: 0.18 }} />
        ))}
        {/* أداة رسم مضلّع القصّ (مضلّع فقط) */}
        <FeatureGroup>
          <DrawControl
            position="topright"
            onCreated={handleCreated}
            onDeleted={handleDeleted}
            draw={{
              polygon: { allowIntersection: false, showArea: false, shapeOptions: { color: '#f87171' } },
              polyline: false, rectangle: { shapeOptions: { color: '#f87171' } },
              circle: false, marker: false, circlemarker: false,
            }}
            edit={{ edit: {}, remove: {} }}
          />
        </FeatureGroup>
      </MapContainer>
    </div>
  );
}
