// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · محرّك MapLibre GL (WebGL) · إثبات مفهوم المرحلة 2
// ───────────────────────────────────────────────────────────────
// مُصيِّر متّجهيّ بـWebGL (MapLibre GL) لمركز الخرائط — يُثبت مسار العرض المتّجهيّ
// الذي تستعمله FieldView/John Deere، دون نزع مكدّس Leaflet العامل. يُحمَّل فقط
// عند MAP_ENGINE==='maplibre' (مقسوم بالكود عبر React.lazy من MapHub)، فلا
// يُثقِل الحزمة الأساسيّة حين العَلَم مُطفأ (الافتراض leaflet).
//
// صدق البيانات: نفس الحقول الحقيقيّة (FieldOption.geometry)، نفس بلاطات الأساس
// (lib/layerRegistry)، ونفس بلاطات مؤشّر الحقل (raster-service). لا طبقات مُختلَقة.
//
// تنبيه إحداثيّات: مساعِدات lib/geo تُرجِع [lat, lng] (طراز Leaflet)؛ بينما
// MapLibre/GeoJSON يستعملان [lng, lat]. نحوّل بعناية عند كلّ حدّ.
//
// قيود المرحلة 2 (PoC): لا رسم/قياس، لا دبابيس، لا تراكبات (طقس/تنبيهات/أجهزة).
// تبقى هذه في محرّك Leaflet وتُنقَل إلى MapLibre في المرحلة 2ب.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  geomToPolygon, collectFieldBoundsPoints, fieldRepresentativePoint,
} from '../../lib/geo';
import { getLayer } from '../../lib/layerRegistry';
import { rasterBaseUrl } from '../../services/api';
import type { FieldOption } from '../../lib/fields';

const YEMEN_CENTER: [number, number] = [44.0, 15.0]; // [lng, lat] — MapLibre
const SELECTED_COLOR = '#22d3ee';
const FIELD_COLOR = '#34d399';

// معرّفات المصادر/الطبقات (ثوابت لتجنّب التكرار وضمان التنظيف الصحيح).
const SRC_FIELDS = 'sahool-fields';
const SRC_INDICATOR = 'sahool-indicator';
const SRC_BASEMAP = 'sahool-basemap';
const LYR_BASEMAP = 'sahool-basemap-layer';
const LYR_INDICATOR = 'sahool-indicator-layer';
const LYR_FILL = 'sahool-fields-fill';
const LYR_LINE = 'sahool-fields-line';
const LYR_SELECTED = 'sahool-fields-selected';

export interface HubMapGLProps {
  fields: FieldOption[];
  selectedId: string;
  onSelect: (id: string) => void;
  basemapId: string;
  indicatorId: string | null;
  indicatorOpacity: number;
  height?: number | string;
}

// رابط بلاطات مؤشّر الحقل — نفس باني HubMap.indicatorTileUrl (مصدر واحد للصدق).
function indicatorTileUrl(fieldId: string, index: string): string {
  const qs = `index=${encodeURIComponent(index)}&date=latest`;
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
}

// مصدر بلاطات الأساس مُكيَّف لـMapLibre (tiles: [url]):
//   • Esri World Imagery يستعمل …/tile/{z}/{y}/{x} — يعمل كما هو.
//   • CARTO light يستعمل {s} (نطاق فرعيّ) + {r} (دقّة retina) — لا يدعمهما MapLibre،
//     فنستبدل {s} بنطاق ملموس (a) ونُسقِط {r}.
function basemapTileSpec(basemapId: string): { url: string; attribution: string } {
  const layer = getLayer(basemapId);
  const raw = layer?.source
    ?? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const url = raw
    .replace('{s}', 'a')   // نطاق فرعيّ ملموس (MapLibre لا يدعم {s})
    .replace('{r}', '');   // إسقاط لاحقة retina (MapLibre لا يدعم {r})
  const attribution = basemapId === 'light'
    ? '© <a href="https://carto.com/">CARTO</a>'
    : '© <a href="https://www.esri.com/">Esri</a> — World Imagery';
  return { url, attribution };
}

// FeatureCollection من مضلّعات الحقول ([lng, lat]) — يتخطّى ما بلا مضلّع صالح
// (لا هندسة مُختلَقة). كلّ ميزة تحمل id/name للنقر والتلميح.
function fieldsToGeoJSON(fields: FieldOption[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const f of fields) {
    const poly = geomToPolygon(f.geometry); // [lat, lng]
    if (!poly || poly.length < 3) continue; // لا نخترع هندسة لحقل بلا مضلّع
    const ring = poly.map(([lat, lng]) => [lng, lat]); // → [lng, lat] لـGeoJSON
    // إغلاق الحلقة إن لزم (GeoJSON يتطلّب أوّل=آخر).
    const first = ring[0];
    const last = ring[ring.length - 1];
    if (first[0] !== last[0] || first[1] !== last[1]) ring.push([first[0], first[1]]);
    features.push({
      type: 'Feature',
      id: f.id,
      properties: { id: f.id, name: `${f.name}${f.crop && f.crop !== '—' ? ` · ${f.crop}` : ''}` },
      geometry: { type: 'Polygon', coordinates: [ring] },
    });
  }
  return { type: 'FeatureCollection', features };
}

// حدود [[lngW, latS], [lngE, latN]] من نقاط الحقول، أو null إن لا نقاط.
function boundsFromPoints(points: [number, number][]): maplibregl.LngLatBoundsLike | null {
  if (!points.length) return null;
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const [lat, lng] of points) { // النقاط [lat, lng] من lib/geo
    if (lat < minLat) minLat = lat;
    if (lat > maxLat) maxLat = lat;
    if (lng < minLng) minLng = lng;
    if (lng > maxLng) maxLng = lng;
  }
  if (!Number.isFinite(minLat) || !Number.isFinite(minLng)) return null;
  return [[minLng, minLat], [maxLng, maxLat]];
}

// فحص دعم WebGL (maplibregl v5 لا يصدّر supported()). نتحقّق بإنشاء سياق webgl.
// نُبقي حارس maplibregl.supported إن وُجد مستقبلاً (التوافق مع نصّ المرحلة).
function webglSupported(): boolean {
  const sup = (maplibregl as unknown as { supported?: () => boolean }).supported;
  if (typeof sup === 'function') return sup();
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl') || canvas.getContext('experimental-webgl'));
  } catch {
    return false;
  }
}

export default function HubMapGL({
  fields, selectedId, onSelect, basemapId, indicatorId, indicatorOpacity, height = 520,
}: HubMapGLProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const loadedRef = useRef(false);
  const [failed, setFailed] = useState(false);

  // مراجع حيّة للـprops كي تقرأها مُعالِجات الأحداث دون إعادة الربط.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // ── إنشاء الخريطة مرّة واحدة (حارس double-init لـStrictMode) ──────────
  useEffect(() => {
    if (mapRef.current || !containerRef.current) return;
    if (!webglSupported()) { setFailed(true); return; }

    const { url, attribution } = basemapTileSpec(basemapId);
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: {
          version: 8,
          glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
          sources: {
            [SRC_BASEMAP]: {
              type: 'raster',
              tiles: [url],
              tileSize: 256,
              attribution,
            },
          },
          layers: [
            { id: LYR_BASEMAP, type: 'raster', source: SRC_BASEMAP },
          ],
        },
        center: YEMEN_CENTER,
        zoom: 5,
        attributionControl: { compact: true },
      });
    } catch {
      setFailed(true);
      return;
    }
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');

    const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 8 });
    popupRef.current = popup;

    map.on('error', () => { /* بلاطات فارغة/مفقودة لا تُسقِط الخريطة — نتجاهل بهدوء */ });

    map.on('load', () => {
      if (!mapRef.current) return;
      loadedRef.current = true;
      syncFieldsLayers(map);
      syncIndicator(map);
      fitView(map);

      // النقر على مضلّع حقل ⇒ اختيار.
      map.on('click', LYR_FILL, (e) => {
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === 'string') onSelectRef.current(id);
      });
      // تلميح بالاسم على المرور.
      map.on('mousemove', LYR_FILL, (e) => {
        map.getCanvas().style.cursor = 'pointer';
        const feat = e.features?.[0];
        const name = feat?.properties?.name;
        if (name) popup.setLngLat(e.lngLat).setText(String(name)).addTo(map);
      });
      map.on('mouseleave', LYR_FILL, () => {
        map.getCanvas().style.cursor = '';
        popup.remove();
      });
    });

    return () => {
      loadedRef.current = false;
      popupRef.current?.remove();
      popupRef.current = null;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // إنشاء مرّة واحدة؛ التحديثات في useEffects التفاعليّة أدناه.

  // ── الحقول + الإبراز يتفاعلان مع fields/selectedId ──────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    syncFieldsLayers(map);
    fitView(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fields, selectedId]);

  // ── خريطة الأساس تتفاعل مع basemapId ────────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    const src = map.getSource(SRC_BASEMAP) as maplibregl.RasterTileSource | undefined;
    const { url } = basemapTileSpec(basemapId);
    if (src && typeof src.setTiles === 'function') src.setTiles([url]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basemapId]);

  // ── طبقة المؤشّر تتفاعل مع indicatorId/selectedId/opacity ────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    syncIndicator(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indicatorId, selectedId, indicatorOpacity, fields]);

  // ── مُزامِنات داخليّة (تقرأ أحدث props عبر الإغلاق) ────────────────────

  // يُحدّث/يُنشئ مصدر الحقول وطبقات fill/line + طبقة الإبراز المفلترة.
  function syncFieldsLayers(map: maplibregl.Map) {
    const data = fieldsToGeoJSON(fields);
    const existing = map.getSource(SRC_FIELDS) as maplibregl.GeoJSONSource | undefined;
    if (existing) {
      existing.setData(data);
    } else {
      map.addSource(SRC_FIELDS, { type: 'geojson', data, promoteId: 'id' });
      // تعبئة منخفضة الشفّافيّة (تحت الخطوط).
      map.addLayer({
        id: LYR_FILL, type: 'fill', source: SRC_FIELDS,
        paint: { 'fill-color': FIELD_COLOR, 'fill-opacity': 0.12 },
      });
      // خطّ حدّ كلّ الحقول.
      map.addLayer({
        id: LYR_LINE, type: 'line', source: SRC_FIELDS,
        paint: { 'line-color': FIELD_COLOR, 'line-width': 1.5 },
      });
      // طبقة إبراز المختار (مفلترة على id == selectedId).
      map.addLayer({
        id: LYR_SELECTED, type: 'line', source: SRC_FIELDS,
        paint: { 'line-color': SELECTED_COLOR, 'line-width': 3 },
        filter: ['==', ['get', 'id'], ''],
      });
    }
    if (map.getLayer(LYR_SELECTED)) {
      map.setFilter(LYR_SELECTED, ['==', ['get', 'id'], selectedId || ' ']);
    }
    // إبقاء طبقة المؤشّر (إن وُجدت) أسفل خطوط الحقول.
    orderIndicatorBelowLines(map);
  }

  // يُنشئ/يُحدّث/يُزيل مصدر بلاطات المؤشّر للحقل المختار. يُوضَع فوق الأساس وتحت
  // خطوط الحقول. يُزال حين لا مؤشّر/لا حقل مختار صالح.
  function syncIndicator(map: maplibregl.Map) {
    const selected = fields.find((f) => f.id === selectedId);
    const active = indicatorId && selected;
    // إزالة أيّ طبقة/مصدر مؤشّر قائم أوّلاً (تبسيط التحديث؛ يتجنّب التسريب).
    if (map.getLayer(LYR_INDICATOR)) map.removeLayer(LYR_INDICATOR);
    if (map.getSource(SRC_INDICATOR)) map.removeSource(SRC_INDICATOR);
    if (!active) return;
    map.addSource(SRC_INDICATOR, {
      type: 'raster',
      tiles: [indicatorTileUrl(selected.id, indicatorId)],
      tileSize: 256,
    });
    // أدرِج فوق الأساس وتحت أوّل طبقة خطّ حقول (إن وُجدت).
    const beforeId = map.getLayer(LYR_LINE) ? LYR_LINE : undefined;
    map.addLayer({
      id: LYR_INDICATOR, type: 'raster', source: SRC_INDICATOR,
      paint: { 'raster-opacity': indicatorOpacity },
    }, beforeId);
  }

  // يضمن بقاء طبقة المؤشّر أسفل خطوط الحقول بعد إعادة إضافة الطبقات.
  function orderIndicatorBelowLines(map: maplibregl.Map) {
    if (map.getLayer(LYR_INDICATOR) && map.getLayer(LYR_LINE)) {
      try { map.moveLayer(LYR_INDICATOR, LYR_LINE); } catch { /* الترتيب أفضل-جهد */ }
    }
  }

  // يضبط الإطار على الحقل المختار إن وُجد، وإلّا على كلّ الحقول، وإلّا مركز اليمن.
  function fitView(map: maplibregl.Map) {
    const selected = fields.find((f) => f.id === selectedId);
    if (selected) {
      const poly = geomToPolygon(selected.geometry);
      if (poly && poly.length >= 3) {
        const b = boundsFromPoints(poly);
        if (b) { map.fitBounds(b, { padding: 40, maxZoom: 17, duration: 0 }); return; }
      }
      const pt = fieldRepresentativePoint(selected); // [lat, lng]
      if (pt) { map.jumpTo({ center: [pt[1], pt[0]], zoom: 15 }); return; }
    }
    const b = boundsFromPoints(collectFieldBoundsPoints(fields));
    if (b) { map.fitBounds(b, { padding: 30, maxZoom: 16, duration: 0 }); return; }
    map.jumpTo({ center: YEMEN_CENTER, zoom: 5 });
  }

  // ── احتياطيّ أمين حين WebGL غير مدعوم/فشل الإنشاء ────────────────────
  if (failed) {
    return (
      <div
        dir="rtl"
        style={{
          height, borderRadius: 14, border: '1px solid #2d4a37', display: 'flex',
          alignItems: 'center', justifyContent: 'center', textAlign: 'center', padding: 24,
          background: '#0d1611', color: '#fca5a5', fontSize: 13, lineHeight: 1.7,
        }}
      >
        محرّك WebGL غير مدعوم في هذا المتصفّح — استخدم محرّك Leaflet.
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', borderRadius: 14, overflow: 'hidden', border: '1px solid #2d4a37' }}>
      <div ref={containerRef} style={{ height, width: '100%' }} />
      {/* شارة إثبات المفهوم (PoC) */}
      <div
        dir="rtl"
        style={{
          position: 'absolute', top: 12, right: 12, zIndex: 5,
          background: 'rgba(13,22,17,.92)', borderRadius: 10, padding: '6px 12px',
          fontSize: 12, color: '#7dd3fc', border: '1px solid #2d4a37',
          backdropFilter: 'blur(6px)', pointerEvents: 'none', whiteSpace: 'nowrap',
        }}
      >
        MapLibre GL · تجريبيّ (المرحلة 2)
      </div>
    </div>
  );
}
