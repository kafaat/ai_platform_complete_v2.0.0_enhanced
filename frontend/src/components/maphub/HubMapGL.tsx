// ═══════════════════════════════════════════════════════════════
// SAHOOL — Map Hub · محرّك MapLibre GL (WebGL) · المرحلة 3 (التقاط حيّ أثناء الرسم)
// ───────────────────────────────────────────────────────────────
// مُصيِّر متّجهيّ بـWebGL (MapLibre GL) لمركز الخرائط — يُثبت مسار العرض المتّجهيّ
// الذي تستعمله FieldView/John Deere، دون نزع مكدّس Leaflet العامل. يُحمَّل فقط
// عند MAP_ENGINE==='maplibre' (مقسوم بالكود عبر React.lazy من MapHub)، فلا
// يُثقِل الحزمة الأساسيّة حين العَلَم مُطفأ (الافتراض leaflet).
//
// المرحلة 2ب: تكافؤ مزايا محرّك Leaflet — رسم/قياس (Terra Draw، محرّك-محايد MIT)،
// دبابيس استكشاف، وتراكبات (طقس/تنبيهات/أجهزة) عبر علامات MapLibre أصليّة بعناصر
// DOM بسيطة (لا Leaflet يدخل هذه الحزمة المقسومة).
//
// المرحلة 3: الالتقاط المغناطيسيّ الحيّ أثناء الرسم. حدود الحقول القائمة ليست في
// مخزن Terra Draw (هي مصدر MapLibre منفصل SRC_FIELDS)، لذا لا يكفي toLine/
// toCoordinate المدمجان — نستعمل toCustom في وضعَي المضلّع والخطّ، فنُحوّل المؤشّر
// إلى [lat, lng] ونمرّره عبر snapPoint من lib/geo (نفس محرّك الالتقاط المُختبَر
// الذي يستعمله محرّر Leaflet)، مع أهداف = حدود الحقول + حلقة الرسم الجاري (إغلاق
// نظيف ذاتيّ). تبديل تشغيل/إيقاف في الشريط (افتراضيّاً مُفعَّل).
//
// صدق البيانات: نفس الحقول الحقيقيّة (FieldOption.geometry)، نفس بلاطات الأساس
// (lib/layerRegistry)، ونفس بلاطات مؤشّر الحقل (raster-service). لا طبقات مُختلَقة.
//
// تنبيه إحداثيّات: مساعِدات lib/geo تُرجِع [lat, lng] (طراز Leaflet)؛ بينما
// MapLibre/GeoJSON/Terra Draw تستعمل [lng, lat]. نحوّل بعناية عند كلّ حدّ.
//
// قيود لاحقة (أمانة): التقطيع التلقائيّ للقطاعات (SAM2) يبقى للمرحلة 4 — لا ندّعيه
// هنا. كما أنّ محرّر Leaflet (AddFieldWithMap) يحتفظ بالتقاطه بعد-الإتمام (snapRing)
// دون تغيير؛ الالتقاط الحيّ هنا يخصّ أداة رسم محرّك GL وحدها.
// ═══════════════════════════════════════════════════════════════
import { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  geomToPolygon, collectFieldBoundsPoints, fieldRepresentativePoint,
  areaSqMeters, lengthMeters, snapPoint,
} from '../../lib/geo';
import type { SnapTarget } from '../../lib/geo';
import { getLayer, resolveLayerSource, toMapLibreRasterUrl } from '../../lib/layerRegistry';
import { rasterBaseUrl } from '../../services/api';
import { getAccessToken } from '../../lib/authStorage';
import type { FieldOption } from '../../lib/fields';
import type { DrawFeature } from './drawing';
// أنواع فقط (تُمحى وقت الترجمة) — لا يدخل Leaflet هذه الحزمة المقسومة.
import type { ScoutPin } from './HubMap';
import type { AlertMarker, DeviceMarker, WeatherMarker, OperationalMarker } from './OverlayMarkers';

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
// طبقات التضاريس/التربة (تكافؤ Leaflet في وضع GL) — بلاطات raster + كنتور vector.
const SRC_HILLSHADE = 'sahool-hillshade';
const LYR_HILLSHADE = 'sahool-hillshade-layer';
const SRC_SLOPE = 'sahool-slope';
const LYR_SLOPE = 'sahool-slope-layer';
const SRC_SOIL = 'sahool-soil';
const LYR_SOIL = 'sahool-soil-layer';
const SRC_CONTOURS = 'sahool-contours';
const LYR_CONTOURS = 'sahool-contours-layer';

// أسماء أوضاع Terra Draw القياسيّة (من getters .mode في الحزمة).
type DrawMode = 'polygon' | 'linestring' | 'select';

// تسامح الالتقاط الحيّ بالمتر. يوازي قصد محرّر Leaflet (~8 م في snapRing) مع هامش
// طفيف ليُسهّل الالتصاق بالحدود على شاشات اللمس/التكبير المتوسّط.
const SNAP_TOLERANCE_M = 10;

// لون/عرض نقطة الالتقاط التي يرسمها Terra Draw حين يلتقط toCustom (تلميح بصريّ).
const SNAP_POINT_COLOR = '#22d3ee';
const SNAP_POINT_WIDTH = 6;

export interface HubMapGLProps {
  fields: FieldOption[];
  selectedId: string;
  onSelect: (id: string) => void;
  basemapId: string;
  indicatorId: string | null;
  indicatorOpacity: number;
  height?: number | string;
  // ── المرحلة 2ب: أدوات/دبابيس/تراكبات (افتراضيّاً مُطفأة/فارغة) ──
  drawTools?: boolean;
  pinMode?: boolean;
  pins?: ScoutPin[];
  onAddPin?: (lat: number, lng: number) => void;
  alertMarkers?: AlertMarker[];
  deviceMarkers?: DeviceMarker[];
  weatherMarker?: WeatherMarker | null;
  operationalMarkers?: OperationalMarker[];
  pivotDesignerEnabled?: boolean;
  onAddPivotDraft?: (lat: number, lng: number) => void;
  pivotDrafts?: DrawFeature[];
  imageryTs?: number;
  imageryDate?: string | null;
  preferPersistedCog?: boolean;  // التاريخ has_cog ⇒ /tiles المحفوظ بدل /cdse-tiles الحيّ
  tenantId?: string | null;
  // ── طبقات التضاريس/التربة (تكافؤ Leaflet) — روابط بلاطات + كنتور + نقاط عيّنات ──
  hillshadeTilesUrl?: string | null;
  slopeTilesUrl?: string | null;
  soilTilesUrl?: string | null;
  contours?: { type: string; features: unknown[] } | null;
  soilSamplePoints?: Array<{ id: string; lat: number; lng: number; label: string; reason?: string }>;
  // ── v2: التقاط/استعادة عرض الخريطة (مركز + تكبير) ──
  // لقطة عرض مُستعادة تبدأ منها الخريطة وتُلغي الملاءمة التلقائيّة عند أوّل تحميل.
  initialView?: { centerLat: number; centerLng: number; zoom: number } | null;
  // يُستدعى عند استقرار حركة المستخدم (moveend) بالمركز [lat,lng] والتكبير.
  onViewChange?: (center: [number, number], zoom: number) => void;
}

// رابط بلاطات مؤشّر الحقل — نفس باني HubMap.indicatorTileUrl (مصدر واحد للصدق).
// CDSE الحيّ: المسار المحلّيّ `tiles` يحتاج COG مُسبق-التوليد ⇒ 404 لحقل بلا معالجة
// (MAPHUB-CDSE)؛ `cdse-tiles` يجلب المشهد حيّاً ويقصّه على المضلّع (قناع rasterio).
function indicatorTileUrl(field: FieldOption, index: string, tenantId?: string | null, imageryTs = 0, imageryDate?: string | null, preferPersistedCog = false): string {
  const params = new URLSearchParams({ index });
  if (imageryDate && imageryDate !== 'latest') params.set('date', imageryDate);
  // المستأجِر كـ`tenant_id` (لا `tid`): بوّابة nginx تقرأ `$arg_tenant_id` فتحقن X-Tenant-Id
  // الموثوق لبلاطات <img> بلا ترويسات (المسار الآمن، مطابق بوّابة 3003/الإنتاج).
  if (tenantId) params.set('tenant_id', tenantId);
  if (imageryTs) params.set('v', String(imageryTs));
  // مصادقة بلاطة <img> خلف بوّابة auth_request: JWT كـ`access_token` تقرأه البوّابة.
  const _tok = getAccessToken();
  if (_tok) params.set('access_token', _tok);
  // القصّ (poly/bbox) لمسار CDSE الحيّ فقط؛ /tiles المحفوظ يقرأ COG مقصوصاً مسبقاً.
  if (!preferPersistedCog) {
  const poly = geomToPolygon(field.geometry);
  if (poly && poly.length >= 3) {
    let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity;
    for (const [lat, lng] of poly) {
      if (lng < w) w = lng;
      if (lng > e) e = lng;
      if (lat < s) s = lat;
      if (lat > n) n = lat;
    }
    params.set('bbox_w', String(w)); params.set('bbox_s', String(s));
    params.set('bbox_e', String(e)); params.set('bbox_n', String(n));
    params.set('poly', poly.map(([lat, lng]) => `${lng},${lat}`).join(';'));
  }
  }
  const qs = params.toString();
  // preferPersistedCog (has_cog) ⇒ COG المحفوظ /tiles؛ وإلّا CDSE الحيّ /cdse-tiles (يُصلِح الطبقة الورديّة).
  const segment = preferPersistedCog ? 'tiles' : 'cdse-tiles';
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${field.id}/${segment}/{z}/{x}/{y}.png?${qs}`;
}

// مصدر بلاطات الأساس مُكيَّف لـMapLibre (tiles: [url]):
//   • Esri World Imagery يستعمل …/tile/{z}/{y}/{x} — يعمل كما هو.
//   • CARTO light يستعمل {s} (نطاق فرعيّ) + {r} (دقّة retina) — لا يدعمهما MapLibre،
//     فنستبدل {s} بنطاق ملموس (a) ونُسقِط {r}.
function basemapTileSpec(basemapId: string): { url: string; attribution: string } {
  const layer = getLayer(basemapId);
  const raw = resolveLayerSource(layer, import.meta.env as Record<string, string | undefined>)
    ?? 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const url = toMapLibreRasterUrl(raw);
  const attribution = layer?.attribution ?? (basemapId === 'light'
    ? '© <a href="https://carto.com/">CARTO</a>'
    : '© <a href="https://www.esri.com/">Esri</a> — World Imagery');
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

// أهداف الالتقاط = حلقة [lat, lng] لكلّ حقل ذي مضلّع صالح (يتخطّى ما بلا حلقة —
// لا هندسة مُختلَقة). تُمرَّر إلى snapPoint من lib/geo كما يفعل محرّر Leaflet.
function buildSnapTargets(fields: FieldOption[]): SnapTarget[] {
  const targets: SnapTarget[] = [];
  for (const f of fields) {
    const poly = geomToPolygon(f.geometry); // [lat, lng]
    if (poly && poly.length >= 2) targets.push(poly);
  }
  return targets;
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

// ── علامات التراكب (DOM بسيط — نُحاكي قصد OverlayMarkers بصريّاً بلا Leaflet) ──
const onlineAr = (online: boolean) => (online ? 'متصل' : 'غير متصل');

function alertColor(severity: string): string {
  const s = severity.toLowerCase();
  if (s === 'critical') return '#ef4444';
  if (s === 'warning') return '#f59e0b';
  return '#38bdf8'; // info / غيره
}

function alertEl(m: AlertMarker): HTMLElement {
  const el = document.createElement('div');
  el.title = `${m.title}${m.fieldName ? ` · ${m.fieldName}` : ''}`;
  el.style.cssText =
    `width:18px;height:18px;border-radius:50%;background:${alertColor(m.severity)};`
    + 'border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);'
    + 'display:flex;align-items:center;justify-content:center;'
    + 'color:#0d1611;font-size:12px;font-weight:800;line-height:1;cursor:default';
  el.textContent = '!';
  return el;
}

function deviceEl(m: DeviceMarker): HTMLElement {
  const el = document.createElement('div');
  el.title = `${m.name} · ${m.dtype} · ${onlineAr(m.online)}`;
  el.style.cssText =
    `width:14px;height:14px;border-radius:50%;background:${m.online ? '#22c55e' : '#94a3b8'};`
    + 'border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);cursor:default';
  return el;
}

function weatherEl(m: WeatherMarker): HTMLElement {
  const temp = m.tempC != null ? `${Math.round(m.tempC)}°م` : '—';
  const cond = m.conditionAr ? ` · ${m.conditionAr}` : '';
  const parts: string[] = [];
  if (m.conditionAr) parts.push(m.conditionAr);
  if (m.humidityPct != null) parts.push(`رطوبة ${Math.round(m.humidityPct)}%`);
  const el = document.createElement('div');
  el.dir = 'rtl';
  el.title = parts.length ? parts.join(' · ') : 'طقس الحقل المختار';
  el.style.cssText =
    'display:flex;align-items:center;gap:4px;white-space:nowrap;'
    + 'background:rgba(13,22,17,.92);border:1px solid #2d4a37;border-radius:8px;'
    + 'padding:3px 7px;color:#e2e8f0;font-size:12px;font-weight:700;'
    + 'box-shadow:0 1px 4px rgba(0,0,0,.5);cursor:default';
  el.textContent = `☀️ ${temp}${cond}`;
  return el;
}


function operationalEl(m: OperationalMarker): HTMLElement {
  const el = document.createElement('div');
  el.title = `${m.title}${m.subtitle ? ` · ${m.subtitle}` : ''}`;
  const s = (m.status ?? '').toLowerCase();
  const bg = m.kind === 'pivot'
    ? '#38bdf8'
    : m.kind === 'task'
      ? (s === 'completed' ? '#22c55e' : s === 'in_progress' ? '#f59e0b' : '#a3e635')
      : (['broken', 'maintenance', 'down'].includes(s) ? '#ef4444' : '#84cc16');
  const glyph = m.kind === 'pivot' ? '◔' : m.kind === 'task' ? '✓' : '⚙';
  el.style.cssText =
    `width:20px;height:20px;border-radius:7px;background:${bg};` +
    'border:2px solid #0d1611;box-shadow:0 1px 3px rgba(0,0,0,.6);' +
    'display:flex;align-items:center;justify-content:center;' +
    'color:#0d1611;font-size:13px;font-weight:900;line-height:1;cursor:default';
  el.textContent = glyph;
  return el;
}

function weatherHeatCss(marker: WeatherMarker | null): string {
  const t = marker?.tempC ?? 30;
  const h = marker?.humidityPct ?? 45;
  if (t >= 38) return 'rgba(239,68,68,.32)';
  if (t >= 32) return 'rgba(249,115,22,.28)';
  if (h >= 75) return 'rgba(14,165,233,.23)';
  return 'rgba(245,158,11,.20)';
}


function pinEl(p: ScoutPin): HTMLElement {
  const el = document.createElement('div');
  el.title = p.note || p.category;
  el.style.cssText = 'font-size:22px;line-height:1;filter:drop-shadow(0 1px 2px rgba(0,0,0,.6));cursor:default';
  el.textContent = '📍';
  return el;
}

// تنسيق عرض القياسات (نفس HubMap.fmtArea/fmtLength).
function fmtArea(m2: number): string {
  const ha = m2 / 10000;
  return `${Math.round(m2).toLocaleString('en-US')} م² · ${ha.toFixed(2)} هكتار`;
}
function fmtLength(m: number): string {
  const km = m / 1000;
  return `${Math.round(m).toLocaleString('en-US')} م · ${km.toFixed(2)} كم`;
}

interface MeasureState { polys: number; lines: number; areaM2: number; lengthM: number }
const EMPTY_MEASURE: MeasureState = { polys: 0, lines: 0, areaM2: 0, lengthM: 0 };

export default function HubMapGL({
  fields, selectedId, onSelect, basemapId, indicatorId, indicatorOpacity, height = 520,
  drawTools = false, pinMode = false, pins = [], onAddPin,
  alertMarkers = [], deviceMarkers = [], weatherMarker = null, operationalMarkers = [],
  initialView = null, onViewChange, imageryTs = 0, imageryDate = null, tenantId = null, preferPersistedCog = false,
  hillshadeTilesUrl = null, slopeTilesUrl = null, soilTilesUrl = null,
  contours = null, soilSamplePoints = [],
}: HubMapGLProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const loadedRef = useRef(false);
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false); // يُعاد الرسم بعد load كي تُزامِن التراكبات

  // مراجع حيّة للـprops كي تقرأها مُعالِجات الأحداث دون إعادة الربط.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onAddPinRef = useRef(onAddPin);
  onAddPinRef.current = onAddPin;
  const pinModeRef = useRef(pinMode);
  pinModeRef.current = pinMode;
  const onViewChangeRef = useRef(onViewChange);
  onViewChangeRef.current = onViewChange;

  // ── v2: لقطة العرض المُستعادة (تُؤخذ مرّة عند أوّل تركيب) ──
  // إن وُجدت، تُستعمل كمركز/تكبير ابتدائيّ وتُلغي الملاءمة التلقائيّة في fitView.
  // hasRestoredViewRef حارس يُستهلَك بعد أوّل ملاءمة كي تعمل الملاءمات اللاحقة.
  const initialViewRef = useRef(initialView);
  const hasRestoredViewRef = useRef(initialView != null);

  // مراجع علامات التراكب/الدبابيس (إزالة كلّ شيء عند كلّ مزامنة/تفكيك — لا تسريب).
  const overlayMarkersRef = useRef<maplibregl.Marker[]>([]);
  const pinMarkersRef = useRef<maplibregl.Marker[]>([]);
  const soilMarkersRef = useRef<maplibregl.Marker[]>([]);

  // ── Terra Draw (رسم/قياس) ──────────────────────────────────────────
  // نُبقي نسخة الرسم ومراجعها خارج React (لا إعادة إنشاء عند كلّ render).
  // نوع فضفاض (TerraDraw مُحمَّل ديناميكيّاً) — نتفادى استيراد النوع في الحزمة.
  const drawRef = useRef<{ stop: () => void; setMode: (m: string) => void; clear: () => void; getSnapshot: () => GeoJSON.Feature[] } | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>('polygon');
  const drawModeRef = useRef<DrawMode>('polygon');
  drawModeRef.current = drawMode;
  const [measure, setMeasure] = useState<MeasureState>(EMPTY_MEASURE);
  // يُشير لاكتمال تهيئة Terra Draw (الاستيراد الديناميكيّ + draw.start()) — للاختبارات.
  const [drawReady, setDrawReady] = useState(false);

  // ── الالتقاط الحيّ (المرحلة 3) ──────────────────────────────────────
  // أهداف الالتقاط (حدود الحقول) في مرجع حيّ كي تقرأ إغلاقة toCustom — المُنشأة
  // مرّة واحدة عند بناء Terra Draw — أحدثها دائماً بعد تغيّر fields بلا إعادة بناء.
  const snapTargetsRef = useRef<SnapTarget[]>(buildSnapTargets(fields));
  snapTargetsRef.current = buildSnapTargets(fields);
  // تبديل الالتقاط (افتراضيّاً مُفعَّل) + مرجع حيّ تقرأه الإغلاقة.
  const [snapOn, setSnapOn] = useState(true);
  const snapOnRef = useRef(true);
  snapOnRef.current = snapOn;

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
        // v2: ابدأ من العرض المُستعاد إن وُجد ([lng,lat] لـMapLibre)، وإلّا اليمن.
        center: initialViewRef.current
          ? [initialViewRef.current.centerLng, initialViewRef.current.centerLat]
          : YEMEN_CENTER,
        zoom: initialViewRef.current?.zoom ?? 5,
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
      setReady(true); // يُشغّل useEffectات التراكب/الدبابيس/الرسم بعد جهوز الخريطة

      // النقر على مضلّع حقل ⇒ اختيار (يُقمَع في وضع الدبابيس — الدبّوس له الأولويّة).
      map.on('click', LYR_FILL, (e) => {
        if (pinModeRef.current) return; // في وضع الدبابيس لا نُغيّر الاختيار
        const id = e.features?.[0]?.properties?.id;
        if (typeof id === 'string') onSelectRef.current(id);
      });
      // النقر العامّ على الخريطة في وضع الدبابيس ⇒ إضافة دبّوس.
      map.on('click', (e) => {
        if (pinModeRef.current) onAddPinRef.current?.(e.lngLat.lat, e.lngLat.lng);
      });
      // تلميح بالاسم على المرور.
      map.on('mousemove', LYR_FILL, (e) => {
        if (pinModeRef.current) return;
        map.getCanvas().style.cursor = 'pointer';
        const feat = e.features?.[0];
        const name = feat?.properties?.name;
        if (name) popup.setLngLat(e.lngLat).setText(String(name)).addTo(map);
      });
      map.on('mouseleave', LYR_FILL, () => {
        if (!pinModeRef.current) map.getCanvas().style.cursor = '';
        popup.remove();
      });

      // v2: التقاط استقرار الحركة (moveend) ⇒ إبلاغ المركز [lat,lng] والتكبير.
      // يشمل moveend البرمجيّ (fitBounds/jumpTo) والمستخدم؛ الكتابة في MapHub
      // مُتسامِحة (idempotent) فلا تُحدث حلقة استعادة↔حركة.
      map.on('moveend', () => {
        const c = map.getCenter();
        onViewChangeRef.current?.([c.lat, c.lng], map.getZoom());
      });
    });

    return () => {
      loadedRef.current = false;
      setReady(false);
      // تفكيك الرسم أوّلاً (يعتمد على map).
      try { drawRef.current?.stop(); } catch { /* أفضل-جهد */ }
      drawRef.current = null;
      overlayMarkersRef.current.forEach((mk) => mk.remove());
      overlayMarkersRef.current = [];
      pinMarkersRef.current.forEach((mk) => mk.remove());
      pinMarkersRef.current = [];
      soilMarkersRef.current.forEach((mk) => mk.remove());
      soilMarkersRef.current = [];
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
    const { url, attribution } = basemapTileSpec(basemapId);

    // لا نستخدم إعادة ضبط tiles على المصدر القائم: في MapLibre قد تبقى بلاطات قديمة في الذاكرة
    // أو تختلط مع المصدر الجديد عند تبديل الأساس/التاريخ. إعادة إنشاء المصدر
    // تغلق سبباً جنائياً محتملاً لـ stale raster tiles.
    const dependentLayers = [LYR_INDICATOR, LYR_FILL, LYR_LINE, LYR_SELECTED];
    const hadIndicator = Boolean(map.getLayer(LYR_INDICATOR));
    for (const layerId of dependentLayers) {
      if (map.getLayer(layerId)) map.removeLayer(layerId);
    }
    for (const sourceId of [SRC_INDICATOR, SRC_FIELDS, SRC_BASEMAP]) {
      if (map.getSource(sourceId)) map.removeSource(sourceId);
    }
    map.addSource(SRC_BASEMAP, {
      type: 'raster',
      tiles: [url],
      tileSize: 256,
      attribution,
    });
    map.addLayer({ id: LYR_BASEMAP, type: 'raster', source: SRC_BASEMAP });
    syncFieldsLayers(map);
    if (hadIndicator) syncIndicator(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [basemapId]);

  // ── طبقة المؤشّر تتفاعل مع indicatorId/selectedId/opacity ────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    syncIndicator(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [indicatorId, selectedId, indicatorOpacity, fields, tenantId, imageryTs, imageryDate]);

  // ── طبقات التضاريس/التربة (تكافؤ Leaflet): بلاطات hillshade/slope/soil + كنتور +
  // نقاط عيّنات 🧪. يعتمد على basemapId كي يُعاد بناؤها بعد إعادة تحميل الأساس (لا تختفي).
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const beforeId = map.getLayer(LYR_LINE) ? LYR_LINE : undefined;
    // مساعِد: أضِف/أزِل طبقة بلاطات raster حسب توفّر الرابط (fail-closed: بلا رابط ⇒ إزالة).
    const syncRaster = (src: string, lyr: string, url: string | null, opacity: number) => {
      if (map.getLayer(lyr)) map.removeLayer(lyr);
      if (map.getSource(src)) map.removeSource(src);
      if (!url) return;
      map.addSource(src, { type: 'raster', tiles: [url], tileSize: 256 });
      map.addLayer({ id: lyr, type: 'raster', source: src, paint: { 'raster-opacity': opacity } }, beforeId);
    };
    syncRaster(SRC_HILLSHADE, LYR_HILLSHADE, hillshadeTilesUrl, 0.7);
    syncRaster(SRC_SLOPE, LYR_SLOPE, slopeTilesUrl, 0.65);
    syncRaster(SRC_SOIL, LYR_SOIL, soilTilesUrl, 0.7);
    // كنتور (GeoJSON خطّيّ) فوق البلاطات.
    if (map.getLayer(LYR_CONTOURS)) map.removeLayer(LYR_CONTOURS);
    if (map.getSource(SRC_CONTOURS)) map.removeSource(SRC_CONTOURS);
    if (contours && Array.isArray(contours.features) && contours.features.length > 0) {
      map.addSource(SRC_CONTOURS, { type: 'geojson', data: contours as unknown as GeoJSON.FeatureCollection });
      map.addLayer({
        id: LYR_CONTOURS, type: 'line', source: SRC_CONTOURS,
        paint: { 'line-color': '#8b5a2b', 'line-width': 1, 'line-opacity': 0.8 },
      });
    }
    // نقاط عيّنات التربة (علامات DOM 🧪) — إزالة الكلّ ثمّ إعادة بناء.
    soilMarkersRef.current.forEach((mk) => mk.remove());
    soilMarkersRef.current = [];
    for (const p of soilSamplePoints) {
      const el = document.createElement('div');
      el.textContent = '🧪';
      el.title = p.reason || p.label;
      el.style.cssText = 'font-size:18px;cursor:default;filter:drop-shadow(0 1px 1px rgba(0,0,0,.5))';
      const mk = new maplibregl.Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(map);
      soilMarkersRef.current.push(mk);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hillshadeTilesUrl, slopeTilesUrl, soilTilesUrl, contours, soilSamplePoints, basemapId, ready]);

  // ── علامات التراكب (تنبيهات/أجهزة/طقس) — إزالة الكلّ ثمّ إعادة بناء ──
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    overlayMarkersRef.current.forEach((mk) => mk.remove());
    overlayMarkersRef.current = [];
    const add = (el: HTMLElement, lat: number, lng: number) => {
      const mk = new maplibregl.Marker({ element: el }).setLngLat([lng, lat]).addTo(map);
      overlayMarkersRef.current.push(mk);
    };
    for (const a of alertMarkers) add(alertEl(a), a.lat, a.lng);
    for (const d of deviceMarkers) add(deviceEl(d), d.lat, d.lng);
    for (const o of operationalMarkers) add(operationalEl(o), o.lat, o.lng);
    if (weatherMarker) add(weatherEl(weatherMarker), weatherMarker.lat, weatherMarker.lng);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [alertMarkers, deviceMarkers, operationalMarkers, weatherMarker, ready]);

  // ── دبابيس الاستكشاف — إزالة الكلّ ثمّ إعادة بناء ──────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    pinMarkersRef.current.forEach((mk) => mk.remove());
    pinMarkersRef.current = [];
    for (const p of pins) {
      const mk = new maplibregl.Marker({ element: pinEl(p), anchor: 'bottom' })
        .setLngLat([p.lng, p.lat]).addTo(map);
      pinMarkersRef.current.push(mk);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pins, ready]);

  // ── مؤشّر الفأرة (crosshair) في وضع الدبابيس ─────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.getCanvas().style.cursor = pinMode ? 'crosshair' : '';
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pinMode, ready]);

  // ── Terra Draw: تهيئة/تفكيك مع drawTools ────────────────────────────
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    let cancelled = false;

    if (drawTools) {
      if (drawRef.current) return; // حارس إعادة التهيئة
      // تحميل ديناميكيّ (يبقى داخل هذه الحزمة المقسومة، خارج index الأساسيّة).
      Promise.all([
        import('terra-draw'),
        import('terra-draw-maplibre-gl-adapter'),
      ]).then(([td, adapterMod]) => {
        if (cancelled || !mapRef.current) return;
        const {
          TerraDraw, TerraDrawPolygonMode, TerraDrawLineStringMode, TerraDrawSelectMode,
        } = td;
        const { TerraDrawMapLibreGLAdapter } = adapterMod;

        // ── إغلاقة الالتقاط الحيّ (toCustom) ──────────────────────────
        // Terra Draw يُمرّر الحدث بإحداثيّات جغرافيّة (lng/lat) وبكسلات الحاوية،
        // ويُتيح لقطة الهندسة الجارية. نُحوّل المؤشّر إلى [lat, lng] ونلتقط عبر
        // snapPoint (lib/geo) مقابل: حدود الحقول القائمة + رؤوس الرسم الجاري
        // (لإغلاق نظيف على رأس البداية). نُعيد [lng, lat] إن التُقِط، وإلّا
        // undefined (رسم حرّ). إيقاف التبديل ⇒ undefined دائماً.
        type TDEvent = { lng: number; lat: number };
        type TDContext = {
          getCurrentGeometrySnapshot: () => GeoJSON.Polygon | GeoJSON.LineString | null;
        };
        const snapToCustom = (event: TDEvent, context: TDContext): GeoJSON.Position | undefined => {
          if (!snapOnRef.current) return undefined;
          const cursor: [number, number] = [event.lat, event.lng]; // [lat, lng] لـlib/geo
          // أهداف = حدود الحقول + حلقة الرسم الجاري (إغلاق ذاتيّ نظيف).
          const targets: SnapTarget[] = [...snapTargetsRef.current];
          const snap = context.getCurrentGeometrySnapshot?.();
          if (snap) {
            const coords = snap.type === 'Polygon' ? snap.coordinates[0] : snap.coordinates;
            if (Array.isArray(coords) && coords.length >= 1) {
              // إحداثيّات GeoJSON [lng, lat] → [lat, lng].
              const ring = coords
                .filter((c): c is GeoJSON.Position => Array.isArray(c) && c.length >= 2)
                .map((c) => [c[1], c[0]] as [number, number]);
              if (ring.length) targets.push(ring);
            }
          }
          const res = snapPoint(cursor, targets, SNAP_TOLERANCE_M);
          if (!res.snapped) return undefined;
          return [res.point[1], res.point[0]]; // [lat, lng] → [lng, lat] = Position
        };

        const snapping = { toCustom: snapToCustom } as unknown as Record<string, unknown>;
        const snapStyles = {
          snappingPointColor: SNAP_POINT_COLOR,
          snappingPointWidth: SNAP_POINT_WIDTH,
        };

        const draw = new TerraDraw({
          adapter: new TerraDrawMapLibreGLAdapter({ map }),
          modes: [
            new TerraDrawPolygonMode({ snapping, styles: snapStyles } as never),
            new TerraDrawLineStringMode({ snapping, styles: snapStyles } as never),
            new TerraDrawSelectMode(),
          ],
        });
        draw.start();
        draw.setMode(drawModeRef.current);
        setDrawReady(true);
        // عند كلّ تغيير/إنهاء: أعِد حساب الإجماليّات من اللقطة (GeoJSON حقيقيّ).
        const recompute = () => {
          const feats = draw.getSnapshot() as GeoJSON.Feature[];
          let polys = 0, lines = 0, areaM2 = 0, lengthM = 0;
          for (const f of feats) {
            const t = f.geometry?.type;
            if (t === 'Polygon' || t === 'MultiPolygon') { polys += 1; areaM2 += areaSqMeters(f); }
            else if (t === 'LineString' || t === 'MultiLineString') { lines += 1; lengthM += lengthMeters(f); }
          }
          setMeasure({ polys, lines, areaM2, lengthM });
        };
        draw.on('change', recompute);
        draw.on('finish', recompute);
        drawRef.current = draw as unknown as typeof drawRef.current;
        setMeasure(EMPTY_MEASURE);
      }).catch(() => { /* فشل تحميل الرسم لا يُسقِط الخريطة */ });
    } else if (drawRef.current) {
      // إيقاف الرسم وتنظيف اللوحة.
      try { drawRef.current.stop(); } catch { /* أفضل-جهد */ }
      drawRef.current = null;
      setMeasure(EMPTY_MEASURE);
      setDrawReady(false);
    }

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drawTools, ready]);

  // ── تبديل وضع الرسم (polygon/linestring/select) ─────────────────────
  useEffect(() => {
    if (drawRef.current) {
      try { drawRef.current.setMode(drawMode); } catch { /* أفضل-جهد */ }
    }
  }, [drawMode]);

  const handleClearDraw = () => {
    if (drawRef.current) {
      try { drawRef.current.clear(); } catch { /* أفضل-جهد */ }
      setMeasure(EMPTY_MEASURE);
    }
  };

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
      map.setFilter(LYR_SELECTED, ['==', ['get', 'id'], selectedId || ' ']);
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
      tiles: [indicatorTileUrl(selected, indicatorId, tenantId, imageryTs, imageryDate, preferPersistedCog)],
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
  // v2: حين عرض مُستعاد، نتخطّى أوّل ملاءمة فقط (احترام مركز/تكبير المستخدم)؛
  // يُستهلَك الحارس فتعمل الملاءمات اللاحقة (تغيّر الاختيار/الحقول) كالمعتاد.
  function fitView(map: maplibregl.Map) {
    if (hasRestoredViewRef.current) {
      hasRestoredViewRef.current = false;
      return;
    }
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
    <div data-testid="hubmapgl-wrapper" style={{ position: 'relative', borderRadius: 14, overflow: 'hidden', border: '1px solid #2d4a37' }}>
      <div data-testid="hubmapgl-container" ref={containerRef} style={{ height, width: '100%' }} />
      {weatherMarker && (
        <div
          aria-label="طبقة الطقس والرياح فوق الخريطة"
          style={{
            position: 'absolute', inset: 0, zIndex: 2, pointerEvents: 'none',
            background: weatherHeatCss(weatherMarker), overflow: 'hidden',
          }}
        >
          <style>{`@keyframes sahoolWindDrift{from{transform:translateX(-80px)}to{transform:translateX(80px)}}`}</style>
          {/* صادق: نرسم تدفّق الرياح الاتّجاهيّ فقط عند توفّر اتّجاه حقيقيّ — لا اتّجاه
              مُلفَّق (315° سابقاً). غياب الاتّجاه ⇒ تبقى خلفيّة السرعة فقط بلا أسهم. */}
          {weatherMarker.windDirectionDeg != null && (
          <div style={{ position: 'absolute', inset: '-12%', transform: `rotate(${weatherMarker.windDirectionDeg}deg)`, opacity: .68 }}>
            {Array.from({ length: 56 }).map((_, i) => (
              <span
                key={i}
                style={{
                  position: 'absolute', width: 74 + (i % 4) * 16, height: 3, borderRadius: 999,
                  background: 'rgba(255,255,255,.70)', top: `${(i * 17) % 104}%`, left: `${(i * 23) % 108 - 8}%`,
                  animation: `sahoolWindDrift ${2.2 + (i % 5) * .25}s linear infinite`,
                  animationDelay: `${-(i % 7) * .25}s`,
                }}
              />
            ))}
          </div>
          )}
        </div>
      )}

      {/* شارة المحرّك — المرحلة 3: التقاط حيّ للحدود مُفعَّل في محرّك GL.
          أمانة: التقطيع التلقائيّ (SAM2) للمرحلة 4، ومحرّر Leaflet يلتقط بعد-الإتمام. */}
      <div
        dir="rtl"
        title="التقاط حيّ للحدود أثناء الرسم (المرحلة 3). التقطيع التلقائيّ SAM2 لاحقاً (المرحلة 4)."
        style={{
          position: 'absolute', top: 12, right: 12, zIndex: 5,
          background: 'rgba(13,22,17,.92)', borderRadius: 10, padding: '6px 12px',
          fontSize: 12, color: '#7dd3fc', border: '1px solid #2d4a37',
          backdropFilter: 'blur(6px)', pointerEvents: 'none', whiteSpace: 'nowrap',
        }}
      >
        MapLibre GL · المرحلة 3 · التقاط حيّ
      </div>

      {/* لوحة الرسم/القياس (Terra Draw) — تظهر فقط حين drawTools */}
      {drawTools && (
        <div
          dir="rtl"
          data-testid="draw-panel"
          data-draw-ready={drawReady ? 'true' : 'false'}
          style={{
            position: 'absolute', top: 12, left: 12, zIndex: 6,
            background: 'rgba(13,22,17,.92)', borderRadius: 10, padding: '10px 12px',
            fontSize: 12, color: '#e2e8f0', border: '1px solid #2d4a37',
            backdropFilter: 'blur(6px)', maxWidth: 260,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
            <span style={{ fontWeight: 700, color: '#5cbf6e' }}>الرسم/القياس</span>
            <button
              type="button" onClick={handleClearDraw} data-testid="btn-clear-draw"
              style={{
                marginRight: 'auto', fontSize: 11, color: '#fca5a5', background: 'transparent',
                border: '1px solid #7a2a2a', borderRadius: 6, padding: '2px 8px', cursor: 'pointer',
              }}
            >مسح</button>
          </div>
          {/* مبدّل الوضع: مضلّع / خطّ / تحديد */}
          <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
            {([
              ['polygon', 'مضلّع', 'btn-mode-polygon'],
              ['linestring', 'خطّ', 'btn-mode-line'],
              ['select', 'تحديد', 'btn-mode-select'],
            ] as [DrawMode, string, string][]).map(([m, label, tid]) => (
              <button
                key={m} type="button" onClick={() => setDrawMode(m)} data-testid={tid}
                style={{
                  flex: 1, fontSize: 11, fontWeight: 600, padding: '4px 6px', borderRadius: 6,
                  cursor: 'pointer',
                  background: drawMode === m ? '#16a34a' : 'transparent',
                  color: drawMode === m ? '#fff' : '#cdddd2',
                  border: `1px solid ${drawMode === m ? '#16a34a' : '#2d4a37'}`,
                }}
              >{label}</button>
            ))}
          </div>
          {/* تبديل الالتقاط الحيّ للحدود (المرحلة 3) — يظهر في وضعَي الرسم فقط */}
          {drawMode !== 'select' && (
            <button
              type="button"
              onClick={() => setSnapOn((v) => !v)}
              aria-pressed={snapOn}
              data-testid="btn-snap-toggle"
              title="التقاط مغناطيسيّ لحدود الحقول القائمة أثناء الرسم"
              style={{
                display: 'flex', alignItems: 'center', gap: 6, width: '100%',
                marginBottom: 8, fontSize: 11, fontWeight: 600, padding: '5px 8px',
                borderRadius: 6, cursor: 'pointer', textAlign: 'right',
                background: snapOn ? 'rgba(34,211,238,.12)' : 'transparent',
                color: snapOn ? '#7dd3fc' : '#9fb3a6',
                border: `1px solid ${snapOn ? '#22d3ee' : '#2d4a37'}`,
              }}
            >
              <span style={{
                width: 8, height: 8, borderRadius: '50%',
                background: snapOn ? '#22d3ee' : '#5a6b60',
              }} />
              التقاط للحدود · {snapOn ? 'مُفعَّل' : 'مُعطَّل'}
            </button>
          )}
          {measure.polys === 0 && measure.lines === 0 ? (
            <p style={{ color: '#9fb3a6', lineHeight: 1.6, margin: 0 }}>
              اختر «مضلّع» للمساحة أو «خطّ» للطول ثمّ ارسم على الخريطة. «تحديد» لتعديل المرسوم.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {measure.polys > 0 && (
                <div>
                  <div style={{ color: '#7dd3fc', fontWeight: 600 }}>المساحة ({measure.polys})</div>
                  <div data-testid="measure-area" style={{ color: '#cdddd2' }}>{fmtArea(measure.areaM2)}</div>
                </div>
              )}
              {measure.lines > 0 && (
                <div>
                  <div style={{ color: '#fcd34d', fontWeight: 600 }}>الطول ({measure.lines})</div>
                  <div data-testid="measure-length" style={{ color: '#cdddd2' }}>{fmtLength(measure.lengthM)}</div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* إرشاد وضع الدبابيس */}
      {pinMode && (
        <div
          dir="rtl"
          style={{
            position: 'absolute', bottom: 12, left: 12, zIndex: 6,
            background: 'rgba(13,22,17,.9)', borderRadius: 10, padding: '6px 12px',
            fontSize: 12, color: '#fcd34d', border: '1px solid #5a4a1f', pointerEvents: 'none',
          }}
        >
          انقر على الخريطة لإضافة دبّوس استكشاف
        </div>
      )}
    </div>
  );
}
