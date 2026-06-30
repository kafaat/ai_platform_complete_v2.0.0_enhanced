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
import { useEffect, useState, useCallback } from 'react';
import { MapContainer, TileLayer, Polygon, FeatureGroup, useMap } from 'react-leaflet';
import DrawControl from './maphub/DrawControl'; // أداة رسم على leaflet-draw خام (بديل EditControl — توافق React 19)
import L from 'leaflet';
import '../lib/leafletSetup'; // CSS الأساسيّ + أيقونات Leaflet + أداة الرسم (side-effect) — حاسم للتصيير
import { fieldCdseTileUrl, fieldIndicatorTileUrl, normalizeIndicatorIndex, rasterApi } from '../services/api';
import { getTenantId } from '../lib/authStorage';
import { areaSqMeters, lengthMeters } from '../lib/geo';
import { readFieldMapView, consumeDefaultViewOnce } from '../lib/fieldMapView';

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
  available?: boolean;
  note?: string | null;
  reason?: string | null;
  user_message?: string | null;
  legend?: { index: string; vmin: number; vmax: number; invert?: boolean; palette?: string; nodata_alpha?: number };
  resolved_date?: string | null;
  cache_version?: string | number | null;
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
  // أدوات الرسم/القياس على الخريطة (مضلّع→مساحة · خطّ→طول). افتراضيّاً off
  // فلا يتأثّر أيّ مستهلك حاليّ (توافق خلفيّ — الزرّ يظهر فقط حين tools=true).
  tools?: boolean;
  // مقطع مسار البلاطة (توحيد main↔cert): 'tiles' (COG محلّي، افتراضيّ) أو 'cdse-tiles'
  // (Sentinel Hub حيّ مع قصّ المضلّع). bbox/geometry تُمرَّر لبلاطات cdse-tiles للقصّ.
  tileSegment?: string;
  fieldBbox?: [number, number, number, number];
  fieldGeometry?: { type?: string; coordinates?: unknown } | null;
}

// ── أدوات القياس (overlay) ──────────────────────────────────────────
// تُدار طبقات الرسم في حالة React عبر ردود EditControl (created/edited/deleted)
// ثمّ تُحسَب المساحة/الطول من هندسة GeoJSON الفعليّة (turf) — لا أرقام مُفبركة.
interface Measurement {
  id: number;            // L.stamp(layer) — مفتاح ثابت للطبقة
  kind: 'polygon' | 'polyline';
  areaM2?: number;       // للمضلّع: المساحة بالمتر المربّع
  lengthM?: number;      // للخطّ: الطول بالمتر
}

// تنسيق المساحة: م² دائماً، مع هكتار للقراءة (1 هكتار = 10000 م²). عرض فقط.
function fmtArea(m2: number): string {
  const ha = m2 / 10000;
  return `${Math.round(m2).toLocaleString('en-US')} م² · ${ha.toFixed(2)} هكتار`;
}
// تنسيق الطول: م دائماً، مع كم للأطوال الكبيرة (1 كم = 1000 م). عرض فقط.
function fmtLength(m: number): string {
  const km = m / 1000;
  return `${Math.round(m).toLocaleString('en-US')} م · ${km.toFixed(2)} كم`;
}

// يستخرج قياساً من طبقة leaflet-draw بالاعتماد على هندسة GeoJSON الحقيقيّة.
function measureLayer(layer: L.Layer): Measurement | null {
  const id = L.stamp(layer);
  // toGeoJSON موجودة على طبقات الأشكال (Path/FeatureGroup) لا على L.Layer الأساس.
  const toGeoJSON = (layer as { toGeoJSON?: () => GeoJSON.Feature }).toGeoJSON;
  let gj: GeoJSON.Feature | null;
  try { gj = toGeoJSON?.() ?? null; } catch { gj = null; }
  const type = gj?.geometry?.type;
  if (type === 'Polygon' || type === 'MultiPolygon') {
    return { id, kind: 'polygon', areaM2: areaSqMeters(gj) };
  }
  if (type === 'LineString' || type === 'MultiLineString') {
    return { id, kind: 'polyline', lengthM: lengthMeters(gj) };
  }
  return null;
}

// لوحة أدوات القياس: شريط Leaflet-draw للرسم + شارة نتائج RTL + «مسح».
function MeasureTools() {
  // مرجع مجموعة الطبقات المرسومة — مصدر الحقيقة الهندسيّة (نُعيد المسح منها).
  const [fg, setFg] = useState<L.FeatureGroup | null>(null);
  const [items, setItems] = useState<Measurement[]>([]);

  // إعادة حساب كلّ القياسات من الطبقات الحاليّة (يستوعب created/edited/deleted).
  const recompute = useCallback((group: L.FeatureGroup | null) => {
    if (!group) { setItems([]); return; }
    const next: Measurement[] = [];
    group.eachLayer((layer) => {
      const m = measureLayer(layer);
      if (m) next.push(m);
    });
    setItems(next);
  }, []);

  const handleCreated = useCallback(() => recompute(fg), [fg, recompute]);
  const handleEdited = useCallback(() => recompute(fg), [fg, recompute]);
  const handleDeleted = useCallback(() => recompute(fg), [fg, recompute]);

  const handleClear = useCallback(() => {
    if (fg) fg.clearLayers();
    setItems([]);
  }, [fg]);

  const totalArea = items.reduce((s, m) => s + (m.areaM2 ?? 0), 0);
  const totalLen = items.reduce((s, m) => s + (m.lengthM ?? 0), 0);
  const polys = items.filter((m) => m.kind === 'polygon');
  const lines = items.filter((m) => m.kind === 'polyline');

  return (
    <>
      <FeatureGroup ref={(r: L.FeatureGroup | null) => setFg(r)}>
        <DrawControl
          position="topright"
          onCreated={handleCreated}
          onEdited={handleEdited}
          onDeleted={handleDeleted}
          draw={{
            // قياس فقط: مضلّع (مساحة) + خطّ (طول). لا علامات/دوائر/مستطيل.
            // showArea:false — يتفادى عطل readableArea في leaflet-draw مع Leaflet 1.9؛
            // المساحة تُحسَب وتُعرَض من turf (areaSqMeters) في الشارة أدناه.
            polygon: { allowIntersection: false, showArea: false, shapeOptions: { color: '#38bdf8' } },
            polyline: { shapeOptions: { color: '#fbbf24' } },
            rectangle: false,
            circle: false,
            marker: false,
            circlemarker: false,
          }}
          edit={{ edit: {}, remove: {} }}
        />
      </FeatureGroup>

      {/* شارة نتائج القياس (RTL · عربيّ) — أعلى يسار الخريطة */}
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
              type="button"
              onClick={handleClear}
              style={{
                marginRight: 'auto', fontSize: 11, color: '#fca5a5',
                background: 'transparent', border: '1px solid #7a2a2a',
                borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
              }}
            >
              مسح
            </button>
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
                <div style={{ color: '#7dd3fc', fontWeight: 600 }}>
                  المساحة ({polys.length})
                </div>
                <div style={{ color: '#cdddd2' }}>{fmtArea(totalArea)}</div>
              </div>
            )}
            {lines.length > 0 && (
              <div>
                <div style={{ color: '#fcd34d', fontWeight: 600 }}>
                  الطول ({lines.length})
                </div>
                <div style={{ color: '#cdddd2' }}>{fmtLength(totalLen)}</div>
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
}

// مكوّن داخلي: يضبط إطار الخريطة على الحدود المتاحة (مضلع → TileJSON → fallback)
function FitBounds({
  polygon,
  tileBounds,
  fallbackBounds,
  fieldId,
}: {
  polygon?: FieldPolygonLatLng;
  tileBounds?: [number, number, number, number];
  fallbackBounds?: [number, number, number, number];
  fieldId?: string;
}) {
  const map = useMap();
  useEffect(() => {
    // حقل أُنشئ للتوّ ⇒ الإطار الافتراضيّ (تخطَّ المشهد المحفوظ مرّةً). غير ذلك:
    // أولويّة المشهد المحفوظ (zoom + مركز عند الإنشاء) ⇒ نطير إليه عند الفتح اللاحق.
    const saved = consumeDefaultViewOnce(fieldId) ? null : readFieldMapView(fieldId);
    if (saved) {
      map.flyTo([saved.lat, saved.lng], saved.zoom, { duration: 0.8 });
      return;
    }
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
  }, [map, polygon, tileBounds, fallbackBounds, fieldId]);
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
  tools = false,
  tileSegment = 'tiles',
  fieldBbox,
  fieldGeometry,
}: FieldIndicatorMapProps) {
  const [opacity, setOpacity] = useState(initialOpacity);
  const [tileBounds, setTileBounds] = useState<[number, number, number, number] | undefined>();
  const [tileAvailable, setTileAvailable] = useState<boolean | null>(null);
  const [legend, setLegend] = useState<TileJSON['legend'] | undefined>();
  const [tileUnavailableMessage, setTileUnavailableMessage] = useState<string | null>(null);
  const [tileCacheVersion, setTileCacheVersion] = useState<string | number | null>(null);

  const baseUrl = basemap === 'satellite' ? BASEMAP_SAT : BASEMAP_LIGHT;
  // البلاطات تُحمَّل كصور Leaflet، لذلك لا تمر عبر Axios ولا تحمل X-Tenant-ID.
  // نمرّر tid في الاستعلام كما يفعل HubMap/HubMapGL حتى يعمل العزل بعد تشديده.
  const tenantId = getTenantId();
  const normalizedIndex = normalizeIndicatorIndex(index);
  // توحيد main↔cert: بلاطات CDSE الحيّة (قصّ poly) عند tileSegment='cdse-tiles'، وإلّا COG محلّي.
  const tilesUrl = tileSegment === 'cdse-tiles'
    ? fieldCdseTileUrl(fieldId, normalizedIndex, date, tenantId, tileCacheVersion, fieldGeometry, fieldBbox)
    : fieldIndicatorTileUrl(fieldId, normalizedIndex, date, tenantId, tileCacheVersion);

  // جلب TileJSON لضبط الإطار وفحص التوفّر.
  // CDSE: يستخدم cdse-tilejson (يعكس توفّر CDSE_CLIENT_ID لا COG محلّيّ).
  // COG:  يستخدم tilejson العاديّ (يعكس وجود ملف COG فعليّ).
  useEffect(() => {
    let cancelled = false;
    setTileBounds(undefined);
    setTileAvailable(null);
    setLegend(undefined);
    setTileUnavailableMessage(null);
    setTileCacheVersion(null);
    // توحيد main↔cert: في وضع CDSE الحيّ نفحص cdse-tilejson (available=is_configured)
    // لا tilejson المحلّيّ (COG) — وإلّا حُجبت طبقة المؤشّر دائماً لحقل بلا COG رغم توفّر CDSE.
    const isCdse = tileSegment === 'cdse-tiles';
    const tilejsonEndpoint = isCdse
      ? `/v1/fields/${fieldId}/cdse-tilejson`
      : `/v1/fields/${fieldId}/tilejson`;
    const params = {
      index: normalizedIndex,
      ...(date && date !== 'latest' ? { date } : {}),
      ...(tenantId ? { tid: tenantId } : {}),
    };
    rasterApi
      .get<TileJSON>(tilejsonEndpoint, { params })
      .then((r) => {
        if (cancelled) return;
        if (r.data?.available === false) {
          setTileAvailable(false);
          setTileUnavailableMessage(
            isCdse
              ? 'CDSE غير مُهيّأ — تحقّق من CDSE_CLIENT_ID/CDSE_CLIENT_SECRET في الخادم.'
              : (r.data?.user_message || r.data?.note || r.data?.reason || null),
          );
          return;
        }
        setTileAvailable(true);
        if (!isCdse) {
          setLegend(r.data?.legend);
          setTileCacheVersion(r.data?.cache_version ?? r.data?.resolved_date ?? null);
        }
        const b = r.data?.bounds;
        if (Array.isArray(b) && b.length === 4) {
          setTileBounds([b[0], b[1], b[2], b[3]]);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTileAvailable(false);
          setTileUnavailableMessage(
            isCdse
              ? 'تعذّر التحقّق من إعداد CDSE. راجع اتصال خدمة الراستر.'
              : 'تعذر التحقق من توفر طبقة المؤشر. راجع اتصال خدمة الراستر أو اختر تاريخاً آخر.',
          );
        }
      });
    return () => { cancelled = true; };
  }, [fieldId, normalizedIndex, date, tenantId, tileSegment]);

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

        {/* طبقة بلاطات المؤشر (شفّافة خارج الحقل) — {z}/{x}/{y} حرفيّ.
            لا تُركّب عند available=false كي لا يبدو غياب COG كتراكب صحيح. */}
        {tileAvailable === true && (
          <TileLayer
            key={`${fieldId}-${normalizedIndex}-${date}-${tileCacheVersion ?? 'default'}`}
            url={tilesUrl}
            opacity={opacity}
            // المؤشر مقصوص بالفعل على الحقل من الـ backend؛ نتجنّب أخطاء 404 صاخبة
            errorTileUrl="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
          />
        )}

        {/* حدود الحقل إن توفّرت */}
        {fieldPolygon && fieldPolygon.length >= 3 && (
          <Polygon
            positions={fieldPolygon}
            pathOptions={{ color: '#5cbf6e', weight: 2, fill: false }}
          />
        )}

        {/* أدوات الرسم/القياس (اختياريّة) — مضلّع→مساحة · خطّ→طول (turf) */}
        {tools && <MeasureTools />}

        <FitBounds polygon={fieldPolygon} tileBounds={tileBounds} fallbackBounds={fallbackBounds} fieldId={fieldId} />
      </MapContainer>

      {tileAvailable === false && (
        <div
          dir="rtl"
          style={{
            position: 'absolute', top: 12, right: 12, zIndex: 1000,
            background: 'rgba(13,22,17,.88)', borderRadius: 10, padding: '8px 12px',
            fontSize: 12, color: '#fcd34d', border: '1px solid #5c4a1f',
            backdropFilter: 'blur(6px)', maxWidth: 280,
          }}
        >
          <strong>{normalizedIndex.toUpperCase()}</strong>: {tileUnavailableMessage || 'لا توجد طبقة متاحة لهذا التاريخ. اختر تاريخاً آخر أو شغّل معالجة الصور.'}
        </div>
      )}

      {tileAvailable === true && legend && (
        <div
          dir="rtl"
          style={{
            position: 'absolute', top: 12, left: 12, zIndex: 1000,
            background: 'rgba(13,22,17,.88)', borderRadius: 10, padding: '8px 12px',
            fontSize: 12, color: '#cdddd2', border: '1px solid #2d4a37',
            backdropFilter: 'blur(6px)', minWidth: 190,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, marginBottom: 6 }}>
            <strong style={{ color: '#e2e8f0' }}>{legend.index.toUpperCase()}</strong>
            <span style={{ color: '#9fb3a6' }}>{legend.palette || 'RdYlGn'}</span>
          </div>
          <div
            aria-label={`legend ${legend.index}`}
            style={{
              height: 10, borderRadius: 999, border: '1px solid rgba(255,255,255,.2)',
              background: legend.invert
                ? 'linear-gradient(90deg, #1a9850, #d9ef8b, #fee08b, #f46d43, #a50026)'
                : 'linear-gradient(90deg, #a50026, #f46d43, #fee08b, #d9ef8b, #1a9850)',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4, color: '#9fb3a6' }}>
            <span>{legend.vmin}</span>
            <span>{legend.vmax}</span>
          </div>
        </div>
      )}


      <div
        dir="rtl"
        aria-label="indicator availability status"
        style={{
          position: 'absolute', bottom: 12, left: 12, zIndex: 1000,
          background: tileAvailable === true ? 'rgba(20,83,45,.88)' : tileAvailable === false ? 'rgba(92,64,18,.88)' : 'rgba(15,23,42,.82)',
          borderRadius: 10, padding: '7px 10px', fontSize: 12, color: '#e2e8f0',
          border: '1px solid rgba(255,255,255,.18)', backdropFilter: 'blur(6px)',
        }}
      >
        {tileAvailable === true ? `متاح: ${normalizedIndex.toUpperCase()}` : tileAvailable === false ? `غير متاح: ${normalizedIndex.toUpperCase()}` : `جاري التحقق: ${normalizedIndex.toUpperCase()}`}
      </div>

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
