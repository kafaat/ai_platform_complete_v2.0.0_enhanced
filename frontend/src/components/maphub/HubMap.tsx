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
// دبابيس دائمة (v94): GET /api/v1/scouting/pins + POST /fields/{id}/pins — تُجلَب وتُحفَظ.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  MapContainer, TileLayer, Polygon, CircleMarker, Marker, Tooltip,
  GeoJSON, useMap, useMapEvents,
} from 'react-leaflet';
import MeasureTools from './MeasureTools';
import L from 'leaflet';
import '../../lib/leafletSetup';
import { geomToPolygon, collectFieldBoundsPoints, fieldRepresentativePoint } from '../../lib/geo';
import { readFieldMapView, consumeDefaultViewOnce } from '../../lib/fieldMapView';
import { drawFeatureStyle } from './drawFeatureStyle';
import { PivotPlacementControl } from './PivotPlacementControl';
import type { DrawFeature } from './drawing';
import { getLayer, resolveLayerSource } from '../../lib/layerRegistry';
import { type FieldContours } from '../../services/api';
import type { FieldOption } from '../../lib/fields';
import { indicatorTileUrl } from './indicatorTileUrl';
import {
  AlertOverlay, DeviceOverlay, WeatherOverlay, WeatherRasterOverlay, OperationalOverlay,
  type AlertMarker, type DeviceMarker, type WeatherMarker, type OperationalMarker,
} from './OverlayMarkers';

const YEMEN_CENTER: [number, number] = [15.0, 44.0];
const SELECTED_COLOR = '#22d3ee';
const FIELD_COLOR = '#34d399';
// بلاطة PNG شفّافة 1×1 — تُستعمَل كـerrorTileUrl فتُبتلَع بلاطات 404/شفّافة (لا DEM)
// بلا ضجيج بصريّ، بدل مربّع «بلاطة مفقودة».
const TRANSPARENT_TILE = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg==';

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
  // معرّف خريطة الأساس من layerRegistry (kind:'basemap'): satellite/light/mapbox-satellite عند توفر token.
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
  operationalMarkers?: OperationalMarker[];
  // v36-v40: Pivot Designer + zones — طبقات رسم محفوظة/محلية فوق الخريطة.
  pivotDesignerEnabled?: boolean;
  onAddPivotDraft?: (lat: number, lng: number) => void;
  pivotDrafts?: DrawFeature[]; // اسم تاريخي: يمرّر الآن كل DrawFeature polygonal overlays.
  // يغيّر مفتاح/رابط طبقة المؤشّر بعد معالجة Sentinel لإجبار المتصفّح/Leaflet على جلب البلاطات الجديدة.
  imageryTs?: number;
  // تاريخ مشهد Sentinel/CDSE المختار من الواجهة. 'latest' يبقى صريحاً فقط عند عدم اختيار تاريخ.
  imageryDate?: string | null;
  // preferPersistedCog: التاريخ has_cog ⇒ اقرأ COG المحفوظ (/tiles) بدل CDSE الحيّ (/cdse-tiles).
  preferPersistedCog?: boolean;
  // يُمرَّر في رابط البلاطات لعزل الكاش/التتبّع حسب المستأجِر. لا يستخدم للقرار.
  tenantId?: string | null;
  // ── طبقات التضاريس (DEM حقيقيّ من raster-service) — مستقلّة عن طبقة المؤشّر ──
  // روابط قوالب بلاطات ({z}/{x}/{y}) للتظليل/الانحدار، أو null لإخفائها. تُبنى في
  // MapHub من fetchTerrainTileJson (available:true) + hillshadeTileUrl/slopeTileUrl؛
  // البلاطة شفّافة حيث لا DEM (لا اختراع تضاريس). contours خطوط كنتور الحقل المختار
  // (GeoJSON MultiLineString) من fetchFieldContours (computed:true) أو null.
  hillshadeTilesUrl?: string | null;
  slopeTilesUrl?: string | null;
  terrainOpacity?: number;
  contours?: FieldContours | null;
  // ── طبقة التربة (SoilGrids) من raster-service — مستقلّة عن المؤشّر/التضاريس ──
  // رابط قالب بلاطات ({z}/{x}/{y}) لخاصّيّة/عمق تربة، أو null لإخفائها. تُبنى في
  // MapHub من fetchSoilTileJson (available:true) + soilTileUrl؛ البلاطة نصف-شفّافة،
  // وشفّافة تماماً حيث لا مصدر (لا اختراع قيم تربة).
  soilTilesUrl?: string | null;
  soilOpacity?: number;
  // ── نقاط أخذ العيّنات المقترَحة (soil sampling plan) — مستقلّة عن طبقة التربة ──
  // نقاط 🧪 من fetchSoilSamplingPlan (computed:true) للحقل المختار، تُبنى في MapHub؛
  // فارغة/غياب ⇒ لا تُرسَم (لا اختراع نقاط عند غياب المصدر). label نصّ التلميح،
  // reason شرح اختياريّ (reason_ar من الخادم).
  soilSamplePoints?: Array<{ id: string; lat: number; lng: number; label: string; reason?: string }>;
  // ── v2: التقاط/استعادة عرض الخريطة (مركز + تكبير) ──
  // لقطة عرض مُستعادة (مركز lat/lng + تكبير) تبدأ منها الخريطة وتُلغي الملاءمة
  // التلقائيّة عند أوّل تركيب. null/غياب ⇒ سلوك v1 (ملاءمة للحقول).
  initialView?: { centerLat: number; centerLng: number; zoom: number } | null;
  // يُستدعى عند استقرار حركة المستخدم (moveend) بالمركز [lat,lng] والتكبير.
  onViewChange?: (center: [number, number], zoom: number) => void;
}

export type { AlertMarker, DeviceMarker, WeatherMarker, OperationalMarker };

// ── تنسيق عرض القياسات: fmtArea/fmtLength مُستورَدان من lib/geo (مصدر واحد) ──



// يضبط إطار الخريطة على الحقل المختار إن وُجد، وإلّا على كلّ الحقول.
// v2: حين hasRestoredView، نتخطّى الملاءمة عند أوّل تركيب فقط كي لا نطمس عرضاً
// مُستعاداً (مركز+تكبير المستخدم)؛ تغيّرات الاختيار/الحقول لاحقاً تُلائم كالمعتاد.
function FitToFields({
  fields, selectedId, hasRestoredView = false,
}: {
  fields: FieldOption[];
  selectedId: string;
  hasRestoredView?: boolean;
}) {
  const map = useMap();
  const firstFitSkippedRef = useRef(false);
  useEffect(() => {
    if (hasRestoredView && !firstFitSkippedRef.current) {
      // أوّل تركيب مع عرض مُستعاد ⇒ لا تُلائم (احترم العرض المُستعاد). التغيّرات
      // اللاحقة (اختيار/حقول) تُلائم عادةً لأنّ الحارس يُستهلَك بعد أوّل تشغيل.
      firstFitSkippedRef.current = true;
      return;
    }
    const selected = fields.find((f) => f.id === selectedId);
    if (selected) {
      // حقل أُنشئ للتوّ ⇒ اعرضه بالإطار الافتراضيّ (تخطَّ المشهد المحفوظ مرّةً).
      const forceDefault = consumeDefaultViewOnce(selectedId);
      // مشهد محفوظ للحقل (zoom + مركز عند الإنشاء) ⇒ طِر إليه عند الفتح اللاحق.
      const saved = forceDefault ? null : readFieldMapView(selectedId);
      if (saved) { map.flyTo([saved.lat, saved.lng], saved.zoom, { duration: 0.8 }); return; }
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
  }, [map, fields, selectedId, hasRestoredView]);
  return null;
}

// يُعيد حساب أبعاد الخريطة عند تغيّر حجم حاويتها. المشكلة: حين تظهر كتل الصور
// (بطاقة الجاهزيّة، شريط الصور التاريخيّ، محدّد التاريخ) *فوق* الخريطة داخل نفس العمود،
// يتغيّر صندوق الخريطة لكن Leaflet يحتفظ بأصل بكسليّ قديم ⇒ تظهر الخريطة رماديّة/فارغة
// (البلاطات بإزاحة خاطئة). لا يُعاد تركيب الخريطة عند تبديل الصور، ولا مُراقِب أبعاد —
// فنُضيف invalidateSize عند التركيب + ResizeObserver على حاوية الخريطة (نمط
// AddFieldWithMap.InvalidateMapSize) لاستعادة العرض تلقائيّاً.
function InvalidateOnResize() {
  const map = useMap();
  useEffect(() => {
    const t1 = setTimeout(() => map.invalidateSize(false), 60);
    const t2 = setTimeout(() => map.invalidateSize(false), 260);
    const el = map.getContainer();
    let raf = 0;
    const ro =
      typeof ResizeObserver !== 'undefined'
        ? new ResizeObserver(() => {
            // خفّف: اجمع دفعات تغيّر الأبعاد في إطار واحد قبل إعادة الحساب.
            if (raf) cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => map.invalidateSize(false));
          })
        : null;
    ro?.observe(el);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      if (raf) cancelAnimationFrame(raf);
      ro?.disconnect();
    };
  }, [map]);
  return null;
}

// يلتقط استقرار حركة المستخدم (moveend) فيُبلّغ المركز [lat,lng] والتكبير لأعلى.
// خفيف بلا حالة؛ الكتابة في MapHub مُتسامِحة (نفس القيمة لا تُحدث حلقة).
function ViewCapture({ onViewChange }: { onViewChange?: (center: [number, number], zoom: number) => void }) {
  const map = useMapEvents({
    moveend() {
      if (!onViewChange) return;
      const c = map.getCenter();
      onViewChange([c.lat, c.lng], map.getZoom());
    },
  });
  return null;
}

// يلتقط النقر على الخريطة لإضافة دبّوس استكشاف حين pinMode مفعّل.
function PinClickHandler({ enabled, onAddPin }: { enabled: boolean; onAddPin: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) { if (enabled) onAddPin(e.latlng.lat, e.latlng.lng); },
  });
  return null;
}

function PivotDesignerClickHandler({ enabled, onAddPivotDraft }: { enabled: boolean; onAddPivotDraft?: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(e) { if (enabled && onAddPivotDraft) onAddPivotDraft(e.latlng.lat, e.latlng.wrap().lng); },
  });
  return null;
}

function drawFeaturePolygonPositions(feature: DrawFeature): [number, number][] | null {
  if (feature.geometry.type !== 'Polygon') return null;
  const rings = feature.geometry.coordinates as unknown;
  if (!Array.isArray(rings) || !Array.isArray(rings[0])) return null;
  const outer = rings[0] as unknown[];
  const positions: [number, number][] = [];
  for (const pt of outer) {
    if (!Array.isArray(pt) || typeof pt[0] !== 'number' || typeof pt[1] !== 'number') return null;
    positions.push([pt[1], pt[0]]);
  }
  return positions.length >= 3 ? positions : null;
}

function drawFeatureLabel(feature: DrawFeature): string {
  const name = feature.properties.name || (feature.kind === 'pivot' ? 'Pivot' : feature.kind);
  const area = feature.measurements?.areaHa;
  const rate = feature.properties.rate as number | undefined;
  const rateUnit = feature.properties.rateUnit as string | undefined;
  const rateText = typeof rate === 'number' ? ` · ${rate}${rateUnit ? ` ${rateUnit}` : ''}` : '';
  return `${name}${typeof area === 'number' ? ` · ${area.toFixed(2)} هـ` : ''}${rateText}`;
}

// رابط بلاطات المؤشّر — نُبقي {z}/{x}/{y} حرفيّاً ليفسّرها Leaflet (مطابق api.ts).
// بلاطات CDSE الحيّة (Sentinel Hub): المسار المحلّيّ `tiles` يحتاج COG مُسبق-التوليد غير
// موجود لحقل بلا معالجة ⇒ 404 ⇒ لا يظهر المؤشّر (MAPHUB-CDSE). `cdse-tiles` يجلب المشهد
// حيّاً ويقصّه على مضلّع الحقل (قناع rasterio بكسليّ) ⇒ شفّافيّة دقيقة خارج الحدّ.
// باني رابط بلاطة المؤشّر انتقل إلى وحدة مُشترَكة قابلة للاختبار (indicatorTileUrl.ts)
// — مصدر واحد للصدق بدل نسخة مُكرَّرة هنا وفي HubMapGL (تفكيك المكوّن العملاق).

// أيقونة دبّوس استكشاف (divIcon — لا أصل صورة خارجيّ).
const PIN_ICON = L.divIcon({
  className: 'sahool-scout-pin',
  html: '<div style="font-size:22px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))">📍</div>',
  iconSize: [22, 22],
  iconAnchor: [11, 22],
});

// أيقونة نقطة عيّنة تربة (divIcon — لا أصل صورة خارجيّ). 🧪
const SOIL_SAMPLE_ICON = L.divIcon({
  className: 'sahool-soil-sample-pin',
  html: '<div style="font-size:20px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6))">🧪</div>',
  iconSize: [20, 20],
  iconAnchor: [10, 20],
});

export default function HubMap({
  fields, selectedId, onSelect, basemapId, indicatorId, indicatorOpacity,
  drawTools, pinMode, pins, onAddPin, height = 520,
  alertMarkers = [], deviceMarkers = [], weatherMarker = null, operationalMarkers = [],
  pivotDesignerEnabled = false, onAddPivotDraft, pivotDrafts = [],
  imageryTs = 0, imageryDate = null, tenantId = null, preferPersistedCog = false,
  hillshadeTilesUrl = null, slopeTilesUrl = null, terrainOpacity = 0.7, contours = null,
  soilTilesUrl = null, soilOpacity = 0.6,
  soilSamplePoints = [],
  initialView = null, onViewChange,
}: HubMapProps) {
  const mapRef = useRef<L.Map | null>(null);
  const [dock, setDock] = useState<HTMLDivElement | null>(null);
  const basemap = getLayer(basemapId);
  const basemapUrl = resolveLayerSource(basemap, import.meta.env as Record<string, string | undefined>)
    ?? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const basemapAttribution = basemap?.attribution
    ?? '&copy; <a href="https://www.esri.com/">Esri</a> — World Imagery';
  const basemapMaxZoom = basemap?.maxZoom ?? 19;

  // v2: لقطة العرض المُستعادة تُؤخذ مرّة واحدة عند أوّل تركيب (المركز/التكبير
  // الابتدائيّان لـMapContainer غير تفاعليّين بعد التركيب). نُثبّتها بـref كي لا
  // تتغيّر مرجعيّاً، وكي يتّسق حارس تخطّي الملاءمة الأوّليّة معها.
  const initialViewRef = useRef(initialView);
  const hasRestoredView = initialViewRef.current != null;

  const center = useMemo<[number, number]>(() => {
    const iv = initialViewRef.current;
    if (iv) return [iv.centerLat, iv.centerLng];
    const points = collectFieldBoundsPoints(fields);
    if (!points.length) return YEMEN_CENTER;
    const [sumLat, sumLng] = points.reduce(([a, b], [la, ln]) => [a + la, b + ln], [0, 0]);
    return [sumLat / points.length, sumLng / points.length];
  }, [fields]);
  const initialZoom = initialViewRef.current?.zoom ?? 11;

  const selected = fields.find((f) => f.id === selectedId);
  const selectedPoly = selected ? geomToPolygon(selected.geometry) : undefined;

  return (
    <>
    <div ref={setDock} />
    <div data-testid="leaflet-map" style={{ position: 'relative', borderRadius: 14, overflow: 'hidden', border: '1px solid #2d4a37' }}>
      <MapContainer
        ref={mapRef}
        className="leaflet-map"
        center={center}
        zoom={initialZoom}
        style={{ height, width: '100%', cursor: pinMode || pivotDesignerEnabled ? 'crosshair' : undefined }}
        scrollWheelZoom
      >
        <TileLayer
          key={basemapId}
          url={basemapUrl}
          attribution={basemapAttribution}
          maxZoom={basemapMaxZoom}
        />

        {/* طبقات التضاريس (DEM من raster-service) — مستقلّة عن المؤشّر، تُرسَم فوق
            الأساس وتحت المؤشّر/الحدود. البلاطة شفّافة حيث لا DEM (errorTileUrl) —
            لا اختراع تضاريس. تظهر فقط حين available:true (يبني MapHub الرابط عندئذ). */}
        {hillshadeTilesUrl && (
          <TileLayer
            key={`hillshade-${tenantId ?? 'tenant'}`}
            url={hillshadeTilesUrl}
            opacity={terrainOpacity}
            errorTileUrl={TRANSPARENT_TILE}
          />
        )}
        {slopeTilesUrl && (
          <TileLayer
            key={`slope-${tenantId ?? 'tenant'}`}
            url={slopeTilesUrl}
            opacity={terrainOpacity}
            errorTileUrl={TRANSPARENT_TILE}
          />
        )}

        {/* طبقة التربة (SoilGrids) — تُرسَم فوق الأساس/التضاريس وتحت المؤشّر/الحدود.
            البلاطة نصف-شفّافة، وشفّافة تماماً حيث لا مصدر (errorTileUrl) — لا اختراع
            قيم تربة. تظهر فقط حين available:true (يبني MapHub الرابط عندئذ). */}
        {soilTilesUrl && (
          <TileLayer
            key={`soil-${tenantId ?? 'tenant'}`}
            url={soilTilesUrl}
            opacity={soilOpacity}
            errorTileUrl={TRANSPARENT_TILE}
          />
        )}

        {/* طبقة بلاطات المؤشّر للحقل المختار (شفّافة خارج الحقل). تُخفى عند تفعيل الطقس
            ليحلّ محلّها العرض الحراريّ للطقس (المقصوص على حدّ الحقل) بدل صورة CDSE. */}
        {indicatorId && selected && !weatherMarker && (
          <TileLayer
            key={`${selected.id}-${indicatorId}-${imageryDate || 'latest'}-${tenantId ?? 'tenant'}-${imageryTs}`}
            className="sahool-indicator-pixels"
            url={indicatorTileUrl(selected, indicatorId, tenantId, imageryTs, imageryDate, preferPersistedCog)}
            opacity={indicatorOpacity}
            errorTileUrl="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQABpfZFQAAAAABJRU5ErkJggg=="
          />
        )}

        {/* كلّ الحقول: مضلّع لذي الهندسة، نقطة لما بلا هندسة (نمط FarmMapOverview) */}
        {fields.map((f) => {
          const poly = geomToPolygon(f.geometry);
          const isSel = f.id === selectedId;
          const label = `${f.name}${f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}`;
          // UI-G3: في وضع الدبابيس تنتشر نقرة الحقل إلى الخريطة فتُضيف الدبّوس؛ لا نُغيّر
          // الاختيار معها (وإلّا تتحرّك الكاميرا عبر FitToFields) — مطابقةً لحارس HubMapGL.
          const selectField = () => { if (!drawTools && !pinMode && !pivotDesignerEnabled) onSelect(f.id); };
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
                eventHandlers={{ click: selectField }}
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
              eventHandlers={{ click: selectField }}
            >
              <Tooltip>{label}</Tooltip>
            </CircleMarker>
          );
        })}

        {/* خطوط كنتور الحقل المختار (MultiLineString من DEM حقيقيّ). تُعرَض فقط حين
            توجد عناصر فعليّة (computed:true) — الحالة الفارغة تُعرَض كملاحظة في MapHub. */}
        {contours && contours.features.length > 0 && (
          <GeoJSON
            key={`contours-${contours.field_id ?? 'field'}-${contours.features.length}`}
            data={contours}
            style={() => ({ color: '#b45309', weight: 1, opacity: 0.9 })}
            onEachFeature={(feature, layer) => {
              const el = feature.properties?.elevation_m;
              if (typeof el === 'number') layer.bindTooltip(`${el} م`, { sticky: true });
            }}
          />
        )}

        {/* حدّ الحقل المختار مُبرَزاً فوق البلاطات (وضوح بصريّ) */}
        {selectedPoly && selectedPoly.length >= 3 && (
          <Polygon
            positions={selectedPoly}
            pathOptions={{ color: SELECTED_COLOR, weight: 3, fill: false }}
          />
        )}

        {/* v36-v40: تصاميم Pivot ومناطق الإدارة/الوصفات المحفوظة أو المحلية. */}
        {pivotDrafts.map((feature) => {
          const positions = drawFeaturePolygonPositions(feature);
          if (!positions) return null;
          return (
            <Polygon
              key={`pivot-draft-${feature.id}`}
              positions={positions}
              pathOptions={drawFeatureStyle(feature)}
            >
              <Tooltip>{drawFeatureLabel(feature)}</Tooltip>
            </Polygon>
          );
        })}

        {/* دبابيس الاستكشاف */}
        {pins.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={PIN_ICON}>
            <Tooltip>{p.note || p.category}</Tooltip>
          </Marker>
        ))}

        {/* نقاط أخذ العيّنات المقترَحة (🧪) — من خطّة أخذ العيّنات للحقل المختار.
            لا تُرسَم حين تكون القائمة فارغة (لا اختراع نقاط عند غياب المصدر). */}
        {soilSamplePoints.map((p) => (
          <Marker key={p.id} position={[p.lat, p.lng]} icon={SOIL_SAMPLE_ICON}>
            <Tooltip>
              <div>{p.label}</div>
              {p.reason ? <div style={{ opacity: 0.8 }}>{p.reason}</div> : null}
            </Tooltip>
          </Marker>
        ))}

        {/* طبقات التراكب (طقس/تنبيهات/أجهزة) — تُرسَم فقط عند توفّر عناصر قابلة
            للعرض. الحرّاس داخل المكوّنات تتكفّل بالفراغ/الـnull. */}
        <WeatherRasterOverlay marker={weatherMarker} fieldPolygon={selectedPoly} />
        <AlertOverlay markers={alertMarkers} />
        <DeviceOverlay markers={deviceMarkers} />
        <OperationalOverlay markers={operationalMarkers} />
        <WeatherOverlay marker={weatherMarker} />

        <PinClickHandler enabled={pinMode} onAddPin={onAddPin} />
        <PivotDesignerClickHandler enabled={pivotDesignerEnabled} onAddPivotDraft={onAddPivotDraft} />
        {drawTools && <MeasureTools dock={dock} />}
        <FitToFields fields={fields} selectedId={selectedId} hasRestoredView={hasRestoredView} />
        <InvalidateOnResize />
        <ViewCapture onViewChange={onViewChange} />
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

      {pivotDesignerEnabled && onAddPivotDraft && (
        <PivotPlacementControl getCenter={() => mapRef.current?.getCenter().wrap()} onPlace={onAddPivotDraft} />
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
    </>
  );
}
