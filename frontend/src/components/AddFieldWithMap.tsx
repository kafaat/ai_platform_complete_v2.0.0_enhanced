// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — AddFieldWithMap.tsx
// رسم حدود الحقل على الخريطة:
//   ✅ مضلع بالرؤوس + رسم حر
//   ✅ قياس المساحة تلقائياً (هكتار)
//   ✅ تراجع (Undo) + إلغاء (Cancel)
//   ✅ تعديل الرؤوس بعد الرسم
//   ✅ نموذج اسم + مسؤول يظهر بعد الرسم فقط
//   ✅ حفظ GeoJSON → API
// ═══════════════════════════════════════════════════════════════
import { useState, useRef, useCallback, useMemo, useEffect } from 'react';
import {
  MapContainer, TileLayer, FeatureGroup, useMap,
} from 'react-leaflet';
import DrawControl from './maphub/DrawControl'; // أداة رسم على leaflet-draw خام (بديل EditControl — توافق React 19)
import L from 'leaflet';
import '../lib/leafletSetup'; // CSS الأساسيّ لـLeaflet + الأداة + الأيقونات (حاسم للتصيير)
import {
  X, Check, Trash2, Loader2,
  MapPin, Ruler, AlertCircle, Upload, FileUp,
  Pentagon, Square, Circle, Magnet,
  Undo2, Redo2,
} from 'lucide-react';
import shp from 'shpjs';
import { kongApi, asApiError, segmentField, classifySegmentationError, apiErrorMessage } from '../services/api';
import type { FieldImportInput, SegmentationMode } from '../services/api';
import { geomToPolygon, snapRing, type SnapTarget } from '../lib/geo';
import AutoSegmentControl, { type SegmentNotice } from './maphub/AutoSegmentControl';

// الطبقة المرسومة من leaflet-draw: circle يحمل getLatLng/getRadius؛
// polygon/rectangle يحملان getLatLngs. نستخدمه لتضييق layer داخل المعالِج.
interface DrawnLayer extends L.Layer {
  getLatLng?: () => L.LatLng;
  getRadius?: () => number;
  getLatLngs?: () => L.LatLng[] | L.LatLng[][];
}

// تُعيد حساب أبعاد الخريطة بعد فتح المودال: عند التركيب قد لا يكون حجم الحاوية
// نهائيّاً (انتقال/تخطيط المودال) فيحتفظ Leaflet بحجم قديم ⇒ انحراف بين موضع
// النقر وموضع الرسم. نطلب invalidateSize مرّتين (بعد التركيب وبعد استقرار التخطيط).
function InvalidateMapSize() {
  const map = useMap();
  useEffect(() => {
    const t1 = setTimeout(() => map.invalidateSize(true), 50);
    const t2 = setTimeout(() => map.invalidateSize(true), 250);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [map]);
  return null;
}

interface FieldData {
  name:          string;
  manager:       string;
  crop:          string;
  soil_type:     string;
  area_ha:       number;
  field_code?:   string;
  water_source?: string;
  country?:      string;
  region?:       string;
  geometry:      { type: string; coordinates: number[][][] };
}

interface Props {
  onSave:    (data: FieldData) => Promise<void>;
  onCancel:  () => void;
  // استيراد حدّ حقل من ملفّ (GeoJSON/KML). اختياريّ: إن لم يُمرَّر يبقى تبويب
  // الاستيراد مخفيّاً ويعمل الرسم اليدويّ كما هو (توافق خلفيّ).
  onImport?: (payload: FieldImportInput) => Promise<void>;
  // حدود الحقول القائمة (هندسات GeoJSON) لالتقاط الرؤوس إليها أثناء الرسم.
  // اختياريّة وتوافقيّة خلفيّاً: إن غابت يبقى الالتقاط مقتصراً على إغلاق رأس البداية.
  existingFields?: ReadonlyArray<{ geometry: unknown }>;
}

const CROPS = ['قمح صلب','شعير','ذرة صفراء','طماطم','بطاطس','خضروات','برسيم'];
// قيم نوع التربة تطابق جدول fields (loam/clay_loam/...) — التسمية عربيّة فقط.
const SOIL_TYPES = [
  { value:'loam',       label:'مزيجية (Loam)' },
  { value:'clay_loam',  label:'طينية مزيجية' },
  { value:'sandy_loam', label:'رملية مزيجية' },
  { value:'silt_loam',  label:'طمية مزيجية' },
  { value:'clay',       label:'طينية' },
  { value:'sandy',      label:'رملية' },
];
// مصدر الماء — يطابق عمود fields.water_source (well/canal/...)؛ التسمية عربيّة.
const WATER_SOURCES = [
  { value:'well',    label:'بئر' },
  { value:'canal',   label:'قناة' },
  { value:'river',   label:'نهر' },
  { value:'rainfed', label:'بعليّ (مطري)' },
  { value:'tank',    label:'خزّان' },
  { value:'mixed',   label:'مختلط' },
];
const TILE_URL = 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png';
const SAT_URL  = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// ── Geodesic area (الصيغة الكرويّة الصحيحة — تطابق Leaflet/Mapbox) ──
// إصلاح: الصيغة السابقة كانت تُرجع نصف المساحة الصحيحة (خطأ في خلط الحدود)،
// ما يعني نصف توصيات البذور/الأسمدة/الريّ. الصيغة أدناه مُتحقّق منها عدديّاً.
function geodesicAreaHa(latlngs: L.LatLng[]): number {
  const R = 6378137; // نصف قطر WGS84 (متر)
  if (latlngs.length < 3) return 0;
  let area = 0;
  const n = latlngs.length;
  for (let i = 0; i < n; i++) {
    const p1 = latlngs[i];
    const p2 = latlngs[(i + 1) % n];
    area += ((p2.lng - p1.lng) * Math.PI / 180) *
            (2 + Math.sin(p1.lat * Math.PI / 180) + Math.sin(p2.lat * Math.PI / 180));
  }
  const sqm = Math.abs(area * R * R / 2);
  return sqm / 10000;
}

// ── محيط جيوديسي (متر) — مجموع المسافات بين الرؤوس المتتالية ─────
// يُستخدم نفس نصف قطر WGS84 (R = 6378137) ومعادلة هافرسين على القوس الأكبر.
// الحلقة مُغلقة: نضيف الضلع من آخر رأس إلى الأوّل تلقائيّاً عبر (i+1)%n.
function geodesicPerimeterM(latlngs: L.LatLng[]): number {
  const R = 6378137; // نصف قطر WGS84 (متر) — نفس ثابت المساحة
  if (!Array.isArray(latlngs) || latlngs.length < 2) return 0;
  const rad = Math.PI / 180;
  let perim = 0;
  const n = latlngs.length;
  for (let i = 0; i < n; i++) {
    const p1 = latlngs[i];
    const p2 = latlngs[(i + 1) % n];
    if (!p1 || !p2) continue;
    const dLat = (p2.lat - p1.lat) * rad;
    const dLng = (p2.lng - p1.lng) * rad;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(p1.lat * rad) * Math.cos(p2.lat * rad) * Math.sin(dLng / 2) ** 2;
    perim += 2 * R * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return perim;
}

// تنسيق طول بالمتر: < 10000 م يُعرَض بالمتر (رقمان)، وإلّا بالكيلومتر للقراءة.
// الوحدة تبقى المتر كأساس؛ هذا تنسيق عرض فقط (لا تحويل لأقدام/فدّان أبداً).
function formatLengthM(m: number): string {
  if (!isFinite(m) || m <= 0) return '0 م';
  if (m >= 10000) return `${(m / 1000).toFixed(2)} كم`;
  return `${Math.round(m)} م`;
}

// ── دائرة (ريّ محوريّ) → مضلّع مُقرَّب ──────────────────────────
// الخلفيّة تتوقّع GeoJSON Polygon؛ نحوّل (مركز + نصف قطر م) إلى حلقة رؤوس.
function circleToPolygon(center: L.LatLng, radiusM: number, n = 48): L.LatLng[] {
  const latPerM = 1 / 111320; // متر → درجة عرض
  // تثبيت cosLat بحدّ أدنى: قرب القطبين cos≈0 ⇒ Infinity/NaN يكسر التوليد.
  const cosLat = Math.max(Math.cos((center.lat * Math.PI) / 180), 1e-6);
  const lonPerM = 1 / (111320 * cosLat);
  const pts: L.LatLng[] = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * 2 * Math.PI;
    pts.push(
      L.latLng(
        center.lat + radiusM * latPerM * Math.sin(a),
        center.lng + radiusM * lonPerM * Math.cos(a),
      ),
    );
  }
  return pts;
}

// ── Main component ─────────────────────────────────────────────
export default function AddFieldWithMap({ onSave, onCancel, onImport, existingFields }: Props) {
  const fgRef = useRef<L.FeatureGroup>(null);
  // mode: 'draw' (الرسم اليدويّ — الافتراضيّ) أو 'import' (استيراد ملفّ).
  const [mode, setMode] = useState<'draw' | 'import'>('draw');
  // G — الالتقاط للحدود أثناء الرسم (افتراضيّ مُفعَّل). يُلصِق الرؤوس بحدود الحقول
  // القائمة وبرأس بداية الرسم (إغلاق نظيف) ضمن تسامح صغير بالمتر — هندسة جهة-العميل.
  const [snapEnabled, setSnapEnabled] = useState(true);
  // H — حالة التقطيع المُساعَد: الوضع قيد الطلب + رسالة صادقة (نموذج غير مُهيَّأ/غير متاح).
  const [segLoading, setSegLoading] = useState(false);
  const [segMode, setSegMode] = useState<SegmentationMode | null>(null);
  const [segNotice, setSegNotice] = useState<SegmentNotice | null>(null);
  const [stage, setStage] = useState<'draw' | 'form'>('draw');
  const [latlngs, setLatlngs] = useState<L.LatLng[]>([]);
  const [areaHa, setAreaHa] = useState(0);
  // المحيط الجيوديسي للحدّ المرسوم (متر) — يُعرَض مع المساحة بعد الرسم/التحرير.
  const [perimeterM, setPerimeterM] = useState(0);
  const [polygon, setPolygon] = useState<L.Polygon | null>(null);
  // مدخل "دائرة بنصف قطر" (إلهام FieldView): نصف القطر بالمتر (م) فقط — لا أقدام.
  const [radiusInput, setRadiusInput] = useState('');
  const [name, setName]   = useState('');
  const [mgr,  setMgr]    = useState('');
  const [crop, setCrop]   = useState(CROPS[0]);
  const [soil, setSoil]   = useState(SOIL_TYPES[0].value);
  const [fieldCode, setFieldCode]     = useState('');
  const [waterSource, setWaterSource] = useState(WATER_SOURCES[0].value);
  // الموقع المكتشف آليّاً من مركز المضلّع (دولة + إقليم/محافظة) — للعرض فقط.
  const [autoCountry, setAutoCountry] = useState<string | null>(null);
  const [autoRegion, setAutoRegion]   = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const [tileType, setTileType] = useState<'street'|'satellite'>('satellite');
  const mapRef = useRef<L.Map | null>(null);
  // حارس تسلسل لطلب الكشف العكسي: يمنع ردّ طلب قديم من الكتابة فوق الأحدث
  // (إعادة رسم سريعة قد تُظهر موقعاً لا يطابق المضلّع الحاليّ).
  const geoReqRef = useRef(0);

  // ── تاريخ تراجع/إعادة (Undo/Redo) لحدّ الحقل ───────────────────────────────
  // كلّ لقطة = حلقة رؤوس كأزواج [lat,lng] أرقام صرفة (غير قابلة للتغيّر ورخيصة، لا L.LatLng).
  // history: قائمة لقطات؛ pointer: مؤشّر اللقطة الحاليّة. الحدّ الحاليّ = history[pointer].
  // الدفع يقتطع أيّ «مستقبل» بعد pointer ثمّ يُلحِق ويُقدّم المؤشّر (دلالات Undo/Redo القياسيّة).
  const [history, setHistory] = useState<number[][][]>([]);
  const [pointer, setPointer] = useState(-1);
  // علم حارس: حين نُعيد تطبيق لقطة (Undo/Redo)، لا يجوز لمسار الدفع أن يُعيد الدخول.
  const applyingRef = useRef(false);
  // مرآة للمؤشّر الحاليّ كي يقرأها مستمع Leaflet طويل العمر بلا إغلاق قديم.
  const pointerRef = useRef(-1);

  // G — أهداف الالتقاط: حلقات حدود الحقول القائمة كـ[lat,lng] (مصدر الالتقاط).
  // نشتقّها مرّة عبر geomToPolygon (المصدر الموحّد للهندسة) ونُحدّثها فقط عند تغيّر
  // المُدخَل. رأس بداية الرسم يُضاف داخل snapRing نفسها (إغلاق نظيف).
  const snapTargets = useMemo<SnapTarget[]>(() => {
    if (!Array.isArray(existingFields)) return [];
    const rings: SnapTarget[] = [];
    for (const f of existingFields) {
      const ring = geomToPolygon(f?.geometry);
      if (ring && ring.length >= 2) rings.push(ring);
    }
    return rings;
  }, [existingFields]);

  // يطبّق الالتقاط على حلقة رؤوس Leaflet إن كان مُفعَّلاً (وإلّا يُعيدها كما هي).
  // تسامح ~8م مناسب لحدود الحقول؛ snapRing نقيّة ومُختبَرة offline (lib/geo).
  const maybeSnap = useCallback((pts: L.LatLng[]): L.LatLng[] => {
    if (!snapEnabled || pts.length < 3) return pts;
    const ring = pts.map(p => [p.lat, p.lng] as [number, number]);
    const snapped = snapRing(ring, snapTargets, 8);
    return snapped.map(([lat, lng]) => L.latLng(lat, lng));
  }, [snapEnabled, snapTargets]);

  // يدفع لقطة حلقة (أزواج [lat,lng]) إلى التاريخ: يقتطع أيّ «مستقبل» بعد المؤشّر
  // الحاليّ ثمّ يُلحِق ويُقدّم المؤشّر. يُتجاهَل أثناء إعادة تطبيق لقطة (حارس applyingRef)
  // أو إن كانت الحلقة أقصر من مثلّث. يقرأ المؤشّر من pointerRef (مرآة محدّثة فوراً)
  // كي يعمل بأمان من مستمع Leaflet طويل العمر بلا إغلاق قديم على pointer.
  const pushSnapshot = useCallback((pts: L.LatLng[]) => {
    if (applyingRef.current) return;
    if (!Array.isArray(pts) || pts.length < 3) return;
    const ring: number[][] = pts.map(p => [p.lat, p.lng]);
    setHistory(prev => {
      const trimmed = prev.slice(0, pointerRef.current + 1);
      trimmed.push(ring);
      pointerRef.current = trimmed.length - 1;
      setPointer(pointerRef.current);
      return trimmed;
    });
  }, []);

  // يبني مضلّعاً قابلاً للتحرير في fgRef بنفس النمط/التفعيل، ويعيد حساب
  // latlngs/areaHa/perimeterM، ويربط مستمع 'edit' (يلتقط سحب الرؤوس → لقطة جديدة).
  // pushOnDone=true ⇒ يدفع لقطة لهذا الحدّ (مسار الالتزام)؛ false ⇒ إعادة تطبيق
  // لقطة موجودة (Undo/Redo) بلا دفع. يُعيد الطبقة المبنيّة.
  const buildEditablePolygon = useCallback((pts: L.LatLng[], pushOnDone: boolean): L.Polygon | null => {
    if (!fgRef.current) return null;
    const fg = fgRef.current;
    fg.clearLayers();
    const poly = L.polygon(pts, {
      color: '#16a34a', fillColor: '#16a34a', fillOpacity: 0.25, weight: 2,
    });
    fg.addLayer(poly);
    // تفعيل التحرير
    (poly as any).editing?.enable();
    setLatlngs(pts);
    setAreaHa(geodesicAreaHa(pts));
    setPerimeterM(geodesicPerimeterM(pts));
    setPolygon(poly);
    // التقاط تعديل الرؤوس اليدويّ: leaflet-draw يُطلق 'edit' على الطبقة بعد سحب رأس.
    // نقرأ الحلقة المحدّثة، نُحدّث القياسات، ونُسجّل لقطة (محروسة بـapplyingRef).
    poly.on('edit', () => {
      const edited = (poly.getLatLngs()[0] as L.LatLng[]) ?? [];
      if (edited.length < 3) return;
      setLatlngs(edited);
      setAreaHa(geodesicAreaHa(edited));
      setPerimeterM(geodesicPerimeterM(edited));
      pushSnapshot(edited);
    });
    if (pushOnDone) pushSnapshot(pts);
    return poly;
  }, [pushSnapshot]);

  const handlePolygonDone = useCallback((rawPts: L.LatLng[]) => {
    const pts = maybeSnap(rawPts);
    if (!fgRef.current) return;
    buildEditablePolygon(pts, true);
    setStage('form');
    // كشف عكسي للموقع (دولة + إقليم) من مركز bbox المضلّع — عرض تلقائي قبل الحفظ.
    const lats = pts.map(p => p.lat);
    const lngs = pts.map(p => p.lng);
    const lat = (Math.min(...lats) + Math.max(...lats)) / 2;
    const lon = (Math.min(...lngs) + Math.max(...lngs)) / 2;
    setAutoCountry(null);
    setAutoRegion(null);
    const myReq = ++geoReqRef.current;
    kongApi
      .get('/api/v1/geo/reverse', { params: { lat, lon } })
      .then(r => {
        if (myReq !== geoReqRef.current) return; // ردّ قديم — تجاهله
        setAutoCountry(r.data?.country ?? null);
        setAutoRegion(r.data?.region ?? null);
      })
      .catch(() => { /* الكشف التلقائي اختياري — لا يُفشل الإضافة */ });
  }, [maybeSnap, buildEditablePolygon]);

  // يُعيد تطبيق لقطة عند مؤشّر هدف: يُعيد بناء المضلّع القابل للتحرير ويعيد حساب
  // القياسات بلا دفع لقطة جديدة (حارس applyingRef) وبلا كشف عكسي (إبقاء سريع).
  const applySnapshot = useCallback((targetPtr: number) => {
    const ring = history[targetPtr];
    if (!Array.isArray(ring) || ring.length < 3) return;
    applyingRef.current = true;
    try {
      const pts = ring.map(([lat, lng]) => L.latLng(lat, lng));
      buildEditablePolygon(pts, false);
      pointerRef.current = targetPtr;
      setPointer(targetPtr);
    } finally {
      applyingRef.current = false;
    }
  }, [history, buildEditablePolygon]);

  const handleUndo = useCallback(() => {
    if (pointer <= 0) return;
    applySnapshot(pointer - 1);
  }, [pointer, applySnapshot]);

  const handleRedo = useCallback(() => {
    if (pointer >= history.length - 1) return;
    applySnapshot(pointer + 1);
  }, [pointer, history.length, applySnapshot]);

  // أداة الرسم (leaflet-draw): مضلّع / مستطيل / دائرة (ريّ محوريّ).
  const handleCreated = useCallback((e: L.DrawEvents.Created) => {
    const layer = e.layer as DrawnLayer;
    let pts: L.LatLng[];
    if (e.layerType === 'circle') {
      pts = circleToPolygon(layer.getLatLng!(), layer.getRadius!());
    } else {
      // polygon / rectangle: الحلقة الخارجيّة
      const ring = (layer.getLatLngs?.() as L.LatLng[][] | undefined)?.[0];
      pts = Array.isArray(ring) ? (ring as L.LatLng[]) : [];
    }
    if (pts.length >= 3) handlePolygonDone(pts);
  }, [handlePolygonDone]);

  // إنشاء دائرة بنصف قطر مُدخَل بالمتر (م) — إلهام FieldView (حوار نصف القطر).
  // يُكمّل السحب-للرسم القائم: نأخذ مركز الخريطة الحاليّ ونحوّله لمضلّع عبر
  // circleToPolygon (يستقبل نصف القطر بالمتر مباشرةً). تحقّق دفاعيّ من القيمة.
  const handleCreateCircleByRadius = useCallback(() => {
    setError('');
    const r = Number(radiusInput);
    if (!isFinite(r) || r <= 0) {
      setError('أدخل نصف قطر صالحاً بالمتر (م).');
      return;
    }
    const map = mapRef.current;
    if (!map) { setError('الخريطة غير جاهزة بعد.'); return; }
    const center = map.getCenter();
    const pts = circleToPolygon(center, r);
    if (pts.length >= 3) handlePolygonDone(pts);
  }, [radiusInput, handlePolygonDone]);

  // ── H-UI — تقطيع مُساعَد (تلقائيّ/هجين) عبر خدمة التقطيع المُوكَّلة ─────────────
  // يأخذ النطاق الظاهر للخريطة (bbox) والوضع فيطلب اقتراح حدّ، ثمّ يُحمّل المضلّع
  // المُقترَح في طبقة الرسم القابلة للتحرير (handlePolygonDone) ليؤكّده المستخدم أو
  // يعدّله. صدق صارم: 503 model_not_configured ⇒ رسالة صريحة «استخدم الرسم اليدويّ»
  // (لا مضلّع مُفبرَك)؛ 404 (غير منشورة) ⇒ «غير متاح» بلطف؛ غيرهما ⇒ نصّ الخطأ.
  const handleSegment = useCallback(async (segReqMode: SegmentationMode) => {
    const map = mapRef.current;
    if (!map) { setSegNotice({ tone: 'error', text: 'الخريطة غير جاهزة بعد.' }); return; }
    setSegLoading(true);
    setSegMode(segReqMode);
    setSegNotice(null);
    const b = map.getBounds();
    // bbox بترتيب GeoJSON: [minLon, minLat, maxLon, maxLat].
    const bbox: [number, number, number, number] = [
      b.getWest(), b.getSouth(), b.getEast(), b.getNorth(),
    ];
    // للوضع الهجين: نمرّر مركز الخريطة كتلميح بذرة [lon, lat] (سياق بشريّ خفيف).
    const c = map.getCenter();
    const hints: Array<[number, number]> | undefined =
      segReqMode === 'hybrid' ? [[c.lng, c.lat]] : undefined;
    try {
      const res = await segmentField({ mode: segReqMode, bbox, ...(hints ? { hints } : {}) });
      const ring = geomToPolygon(res?.geometry);
      if (!ring || ring.length < 3) {
        // ردّ بلا هندسة صالحة — لا نُلفّق مضلّعاً، نُبقي الرسم اليدويّ.
        setSegNotice({
          tone: 'warning',
          text: 'لم تُرجِع الخدمة مضلّعاً صالحاً — استخدم الرسم اليدويّ.',
        });
        return;
      }
      // نُحمّل الاقتراح في طبقة التحرير (الالتقاط يبقى مُحترَماً عبر handlePolygonDone).
      const pts = ring.map(([lat, lng]) => L.latLng(lat, lng));
      handlePolygonDone(pts);
      const conf = typeof res?.confidence === 'number' ? ` (ثقة ${(res.confidence * 100).toFixed(0)}٪)` : '';
      setSegNotice({
        tone: 'info',
        text: `حُمِّل اقتراح ${segReqMode === 'auto' ? 'تلقائيّ' : 'هجين'} للحدّ${conf} — راجِعه وعدّله قبل الحفظ.`,
      });
    } catch (e: unknown) {
      const kind = classifySegmentationError(e);
      if (kind === 'model_not_configured') {
        // صدق: لا مضلّع مزيّف. رسالة صريحة بأنّ النموذج غير مُهيَّأ + بديل يدويّ.
        setSegNotice({
          tone: 'warning',
          text: 'التقطيع التلقائيّ يتطلّب تهيئة نموذج (SAM2/GeoSAM) — استخدم الرسم اليدويّ.',
        });
      } else if (kind === 'unavailable') {
        setSegNotice({
          tone: 'warning',
          text: 'خدمة التقطيع التلقائيّ غير متاحة حاليّاً — استخدم الرسم اليدويّ.',
        });
      } else {
        setSegNotice({ tone: 'error', text: apiErrorMessage(e, 'تعذّر التقطيع التلقائيّ.') });
      }
    } finally {
      setSegLoading(false);
      setSegMode(null);
    }
  }, [handlePolygonDone]);

  const handleReset = () => {
    if (fgRef.current) fgRef.current.clearLayers();
    setStage('draw');
    setLatlngs([]);
    setAreaHa(0);
    setPerimeterM(0);
    setPolygon(null);
    setAutoCountry(null);
    setAutoRegion(null);
    setError('');
    setSegNotice(null);
    // تفريغ تاريخ التراجع/الإعادة مع بقيّة الحالة.
    setHistory([]);
    setPointer(-1);
    pointerRef.current = -1;
  };

  const handleSave = async () => {
    if (!name.trim()) { setError('اسم الحقل مطلوب'); return; }
    if (!mgr.trim())  { setError('اسم المسؤول مطلوب'); return; }
    if (latlngs.length < 3) { setError('يرجى رسم الحقل أولاً'); return; }
    setSaving(true); setError('');
    try {
      // إذا تم تعديل الرؤوس، نأخذ الإحداثيات المحدّثة
      let finalPts = latlngs;
      if (polygon) {
        const edited = (polygon.getLatLngs()[0] as L.LatLng[]);
        if (edited?.length >= 3) finalPts = edited;
      }
      const coords = [...finalPts.map(p => [p.lng, p.lat]), [finalPts[0].lng, finalPts[0].lat]];
      await onSave({
        name, manager: mgr, crop, soil_type: soil,
        field_code: fieldCode.trim() || undefined,
        water_source: waterSource,
        country: autoCountry ?? undefined,
        region: autoRegion ?? undefined,
        area_ha: +(geodesicAreaHa(finalPts).toFixed(2)),
        geometry: { type: 'Polygon', coordinates: [coords] },
      });
    } catch (e: unknown) {
      setError(asApiError(e).message || 'فشل الحفظ');
    } finally {
      setSaving(false);
    }
  };

  // ── الاستيراد من ملفّ (GeoJSON/KML/Shapefile) ────────────────
  const [fileName, setFileName]   = useState('');
  const [fileText, setFileText]   = useState('');     // نصّ الملفّ المقروء (أو GeoJSON محوّل من Shapefile)
  const [fileFmt, setFileFmt]     = useState<'geojson' | 'kml' | null>(null);
  // حالة تحليل ملفّ Shapefile في المتصفّح (shpjs) — تحليل غير متزامن يتطلّب مؤشّر تحميل.
  const [parsing, setParsing]     = useState(false);

  // ── استخراج أوّل حلقة مضلّع من نتيجة shpjs ────────────────────
  // الخلفيّة تقبل format:'geojson' فقط (لا 'shp')، لذا نحوّل Shapefile → GeoJSON
  // Polygon في المتصفّح ثمّ نرسله كنصّ GeoJSON. لا نُلفّق هندسة: إن لم نجد مضلّعاً
  // صالحاً نرفع خطأً واضحاً بدل إرسال شيء فارغ.
  const firstPolygonFeature = (
    fc: GeoJSON.FeatureCollection | GeoJSON.FeatureCollection[],
  ): GeoJSON.Feature<GeoJSON.Polygon> => {
    // shpjs قد يُرجع مجموعة واحدة أو مصفوفة مجموعات (إذا حوى الـ.zip عدّة طبقات).
    const collections = Array.isArray(fc) ? fc : [fc];
    for (const coll of collections) {
      const feats = coll?.features ?? [];
      for (const feat of feats) {
        const g = feat?.geometry;
        if (!g) continue;
        if (g.type === 'Polygon' && Array.isArray(g.coordinates) && g.coordinates.length > 0) {
          return { type: 'Feature', properties: feat.properties ?? {}, geometry: g };
        }
        // MultiPolygon: نأخذ أوّل مضلّع (أوّل حلقة خارجيّة) — اختيار صريح، لا تلفيق.
        if (g.type === 'MultiPolygon' && Array.isArray(g.coordinates) && g.coordinates.length > 0) {
          const first = g.coordinates[0];
          if (Array.isArray(first) && first.length > 0) {
            return {
              type: 'Feature',
              properties: feat.properties ?? {},
              geometry: { type: 'Polygon', coordinates: first },
            };
          }
        }
      }
    }
    throw new Error('لم يُعثَر على مضلّع حدود صالح داخل ملفّ Shapefile.');
  };

  const handleFilePicked = (f: File | null) => {
    setError('');
    if (!f) { setFileName(''); setFileText(''); setFileFmt(null); return; }
    const lower = f.name.toLowerCase();
    // Shapefile (.zip مضغوط أو .shp مفرد) → نحلّله في المتصفّح إلى GeoJSON.
    if (lower.endsWith('.zip') || lower.endsWith('.shp')) {
      setFileName(''); setFileText(''); setFileFmt(null);
      setParsing(true);
      const reader = new FileReader();
      reader.onload = async () => {
        try {
          const buf = reader.result;
          if (!(buf instanceof ArrayBuffer) || buf.byteLength === 0) {
            throw new Error('ملفّ Shapefile فارغ أو تعذّرت قراءته.');
          }
          const parsed = await shp(buf);
          const feature = firstPolygonFeature(parsed);
          const geojson: GeoJSON.FeatureCollection = {
            type: 'FeatureCollection',
            features: [feature],
          };
          setFileName(f.name);
          setFileText(JSON.stringify(geojson));
          setFileFmt('geojson'); // الخلفيّة تستقبله كـGeoJSON بعد التحويل
        } catch (e: unknown) {
          setError(asApiError(e).message || 'تعذّر تحليل ملفّ Shapefile — تأكّد أنّه ملفّ .shp/.zip صالح.');
          setFileName(''); setFileText(''); setFileFmt(null);
        } finally {
          setParsing(false);
        }
      };
      reader.onerror = () => { setError('تعذّرت قراءة ملفّ Shapefile.'); setParsing(false); };
      reader.readAsArrayBuffer(f);
      return;
    }
    const fmt: 'geojson' | 'kml' | null =
      lower.endsWith('.kml') ? 'kml'
      : (lower.endsWith('.geojson') || lower.endsWith('.json')) ? 'geojson'
      : null;
    if (!fmt) {
      setError('صيغة غير مدعومة — اختر ملفّ .geojson أو .json أو .kml أو .shp/.zip.');
      setFileName(''); setFileText(''); setFileFmt(null);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setFileName(f.name);
      setFileText(String(reader.result ?? ''));
      setFileFmt(fmt);
    };
    reader.onerror = () => setError('تعذّرت قراءة الملفّ.');
    reader.readAsText(f);
  };

  const handleImport = async () => {
    if (!onImport) return;
    if (!name.trim()) { setError('اسم الحقل مطلوب'); return; }
    if (!mgr.trim())  { setError('اسم المسؤول مطلوب'); return; }
    if (!fileText || !fileFmt) { setError('اختر ملفّ الحدود أولاً (.geojson/.json/.kml).'); return; }
    setSaving(true); setError('');
    try {
      await onImport({
        format: fileFmt,
        content: fileText,
        name, manager: mgr, crop, soil_type: soil,
        field_code: fieldCode.trim() || undefined,
        water_source: waterSource,
      });
    } catch (e: unknown) {
      // رسالة صادقة من الخادم (400 تحليل / 422 هندسة غير صالحة) لا ابتلاع.
      setError(asApiError(e).message || 'فشل الاستيراد');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col" dir="rtl" style={{ background:'#0b1220' }}>
      {/* Top bar (ملء العرض): العنوان + التبويبات على جهة البداية، تبديل الطبقة + الإغلاق على جهة النهاية */}
      <header className="flex items-center justify-between px-5 py-3 border-b shrink-0" style={{ borderColor:'#334155', background:'#1e293b' }}>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <MapPin className="w-5 h-5 text-emerald-400" />
            <h2 className="font-bold text-slate-100">
              {mode === 'import'
                ? 'استيراد حدود الحقل من ملفّ'
                : stage === 'draw' ? 'ارسم حدود الحقل على الخريطة' : 'بيانات الحقل'}
            </h2>
          </div>
          {/* Tabs: رسم يدويّ / استيراد ملفّ (التبويب يظهر فقط إن وُفّر onImport) */}
          {onImport && (
            <div className="flex gap-1">
              <button
                onClick={() => { setMode('draw'); setError(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold"
                style={mode === 'draw'
                  ? { background:'#0f1117', color:'#34d399', border:'1px solid #334155' }
                  : { color:'#94a3b8' }}>
                <MapPin className="w-4 h-4" /> رسم على الخريطة
              </button>
              <button
                onClick={() => { setMode('import'); setError(''); }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-semibold"
                style={mode === 'import'
                  ? { background:'#0f1117', color:'#34d399', border:'1px solid #334155' }
                  : { color:'#94a3b8' }}>
                <FileUp className="w-4 h-4" /> استيراد ملفّ
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          {/* Layer toggle (الرسم فقط) */}
          {mode === 'draw' && (
            <button onClick={() => setTileType(t => t === 'street' ? 'satellite' : 'street')}
              className="px-2 py-1 rounded text-xs border" style={{ borderColor:'#334155', color:'#94a3b8' }}>
              {tileType === 'satellite' ? '🗺 خريطة' : '🛰 قمر صناعي'}
            </button>
          )}
          <button onClick={onCancel} className="p-1 rounded hover:bg-slate-700 text-slate-400">
            <X className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* صفّ العمل: درج التحكّم (البداية) + خريطة ملء الشاشة (flex-1) */}
      <div className="flex-1 flex min-h-0">
        {mode === 'draw' ? (
          <>
            <aside className="w-full sm:w-[400px] shrink-0 overflow-y-auto border-l" style={{ borderColor:'#334155', background:'#1e293b' }} dir="rtl">
              {stage === 'draw' ? (
                /* لوحة الأدوات + شريط الإرشاد (إلهام FieldView) */
                <div className="px-5 py-3 space-y-2" dir="rtl">
                  {/* سطر الإرشاد العربيّ الأصليّ — يبقى كما هو */}
                  <p className="text-sm" style={{ color:'#94a3b8' }}>
                    💡 <strong className="text-emerald-400">ارسم حدود الحقل على الخريطة</strong> — اختر أداة الرسم من أعلى يسار الخريطة.
                  </p>
                  {/* لوحة أدوات مرتّبة: المضلّع/المستطيل/الدائرة من شريط Leaflet (أعلى الخريطة) */}
                  <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color:'#cbd5e1' }}>
                    <span className="px-2 py-1 rounded-lg inline-flex items-center gap-1"
                      style={{ background:'#0f1117', border:'1px solid #334155' }}>
                      <Pentagon className="w-3.5 h-3.5 text-emerald-400" /> مضلّع
                    </span>
                    <span className="px-2 py-1 rounded-lg inline-flex items-center gap-1"
                      style={{ background:'#0f1117', border:'1px solid #334155' }}>
                      <Square className="w-3.5 h-3.5 text-emerald-400" /> مستطيل
                    </span>
                    <span className="px-2 py-1 rounded-lg inline-flex items-center gap-1"
                      style={{ background:'#0f1117', border:'1px solid #334155' }}>
                      <Circle className="w-3.5 h-3.5 text-emerald-400" /> دائرة (ريّ محوريّ)
                    </span>
                    {onImport && (
                      <span className="px-2 py-1 rounded-lg inline-flex items-center gap-1"
                        style={{ background:'#0f1117', border:'1px solid #334155' }}>
                        <FileUp className="w-3.5 h-3.5 text-emerald-400" /> أو استيراد ملفّ
                      </span>
                    )}
                  </div>
                  {/* مدخل: دائرة بنصف قطر بالمتر (م) — يُنشئ حقلاً دائريّاً عند مركز الخريطة */}
                  <div className="flex flex-wrap items-center gap-2">
                    <label className="text-xs" style={{ color:'#94a3b8' }}>
                      دائرة بنصف قطر:
                    </label>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={1}
                        inputMode="numeric"
                        value={radiusInput}
                        onChange={e => setRadiusInput(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleCreateCircleByRadius(); } }}
                        placeholder="مثال: 250"
                        className="w-28 px-2 py-1 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}
                      />
                      <span className="text-xs font-semibold text-emerald-400">م</span>
                    </div>
                    <button
                      type="button"
                      onClick={handleCreateCircleByRadius}
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold text-white"
                      style={{ background:'#16a34a' }}>
                      <Circle className="w-3.5 h-3.5" /> إنشاء دائرة
                    </button>
                    <span className="text-[11px]" style={{ color:'#64748b' }}>
                      (تُنشأ عند مركز الخريطة — نصف القطر بالمتر)
                    </span>
                  </div>

                  {/* G — تبديل الالتقاط للحدود (افتراضيّ مُفعَّل) */}
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setSnapEnabled(s => !s)}
                      aria-pressed={snapEnabled}
                      title="إلصاق رؤوس الرسم بحدود الحقول القائمة وبرأس البداية ضمن تسامح صغير"
                      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-semibold"
                      style={snapEnabled
                        ? { background:'#16a34a22', color:'#34d399', border:'1px solid #16a34a66' }
                        : { background:'#0f1117', color:'#94a3b8', border:'1px solid #334155' }}>
                      <Magnet className="w-3.5 h-3.5" />
                      التقاط للحدود{snapEnabled ? ' · مُفعَّل' : ' · مُعطَّل'}
                    </button>
                    <span className="text-[11px]" style={{ color:'#64748b' }}>
                      (يُلصِق الرؤوس بأقرب حدّ قائم ويُغلق البداية بنظافة)
                    </span>
                  </div>

                  {/* H-UI — أزرار التقطيع المُساعَد (تلقائيّ/هجين) — تعامل صادق عند غياب النموذج */}
                  <AutoSegmentControl
                    onSegment={handleSegment}
                    loading={segLoading}
                    pendingMode={segMode}
                    notice={segNotice}
                  />
                </div>
              ) : (
                <div className="px-5 py-4 space-y-4" dir="rtl">
                  {/* Form */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">اسم الحقل *</label>
                      <input value={name} onChange={e => setName(e.target.value)}
                        placeholder="مثال: حقل وادي سبأ"
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">المسؤول *</label>
                      <input value={mgr} onChange={e => setMgr(e.target.value)}
                        placeholder="اسم المسؤول"
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">المحصول</label>
                      <select value={crop} onChange={e => setCrop(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                        {CROPS.map(c => <option key={c}>{c}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">نوع التربة</label>
                      <select value={soil} onChange={e => setSoil(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                        {SOIL_TYPES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">كود الحقل</label>
                      <input value={fieldCode} onChange={e => setFieldCode(e.target.value)}
                        placeholder="مثال: F-01"
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">مصدر الماء</label>
                      <select value={waterSource} onChange={e => setWaterSource(e.target.value)}
                        className="w-full px-3 py-2 rounded-lg text-sm"
                        style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                        {WATER_SOURCES.map(w => <option key={w.value} value={w.value}>{w.label}</option>)}
                      </select>
                    </div>
                  </div>

                  {/* الموقع المكتشف آليّاً (دولة + إقليم) — للعرض فقط */}
                  {(autoCountry || autoRegion) && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                      style={{ background:'#0f1117', border:'1px solid #334155', color:'#94a3b8' }}>
                      <MapPin className="w-4 h-4 text-emerald-400" />
                      <span>
                        الموقع: <strong className="text-slate-200">{autoCountry || '—'}</strong>
                        {autoRegion ? <> · <strong className="text-slate-200">{autoRegion}</strong></> : null}
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[10px]"
                        style={{ background:'#16a34a22', color:'#34d399', border:'1px solid #16a34a44' }}>
                        تلقائيّ
                      </span>
                    </div>
                  )}

                  {error && (
                    <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                      style={{ background:'#1a000022', border:'1px solid #dc262633', color:'#f87171' }}>
                      <AlertCircle className="w-4 h-4" /> {error}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex flex-wrap gap-2 justify-end">
                    <button onClick={handleUndo} disabled={pointer <= 0}
                      title="تراجع عن آخر تعديل للحدّ"
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-slate-400"
                      style={{ borderColor:'#334155' }}>
                      <Undo2 className="w-4 h-4" /> تراجع
                    </button>
                    <button onClick={handleRedo} disabled={pointer >= history.length - 1}
                      title="إعادة تطبيق التعديل المُتراجَع عنه"
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-slate-400"
                      style={{ borderColor:'#334155' }}>
                      <Redo2 className="w-4 h-4" /> إعادة
                    </button>
                    <button onClick={handleReset}
                      className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200"
                      style={{ borderColor:'#334155' }}>
                      <Trash2 className="w-4 h-4" /> إعادة الرسم
                    </button>
                    <button onClick={onCancel}
                      className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 border"
                      style={{ borderColor:'#334155' }}>
                      إلغاء
                    </button>
                    <button onClick={handleSave} disabled={saving}
                      className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors"
                      style={{ background: saving ? '#15803d' : '#16a34a' }}>
                      {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الحفظ...</> : <><Check className="w-4 h-4" /> حفظ الحقل</>}
                    </button>
                  </div>
                </div>
              )}
            </aside>

            {/* Map (الرسم اليدويّ فقط) — تملأ العمود الطويل */}
            <div className="flex-1 relative min-w-0">
              <MapContainer
                center={[15.05, 45.55]}
                zoom={10}
                style={{ height:'100%', width:'100%' }}
                doubleClickZoom={false}
                ref={(m: L.Map | null) => { mapRef.current = m; }}
              >
                <InvalidateMapSize />
                <TileLayer url={tileType === 'satellite' ? SAT_URL : TILE_URL}
                  attribution='&copy; <a href="https://carto.com/">CARTO</a>' />
                <FeatureGroup ref={fgRef}>
                  {stage === 'draw' && (
                    <DrawControl
                      position="topright"
                      onCreated={handleCreated}
                      draw={{
                        // showArea:false — يتفادى عطل leaflet-draw المعروف (readableArea)
                        // مع Leaflet 1.9؛ المساحة تُحسَب وتُعرَض من geodesicAreaHa لدينا.
                        polygon: { allowIntersection: false, showArea: false, shapeOptions: { color: '#16a34a' } },
                        rectangle: { shapeOptions: { color: '#16a34a' } },
                        circle: { shapeOptions: { color: '#16a34a' } },
                        polyline: false,
                        marker: false,
                        circlemarker: false,
                      }}
                      edit={{ edit: false, remove: false }}
                    />
                  )}
                </FeatureGroup>
              </MapContainer>

              {/* شارة القياسات: المساحة (هكتار + متر مربّع) + المحيط (متر) — الطول دائماً بالمتر */}
              {areaHa > 0 && (
                <div className="absolute top-3 left-3 z-20 px-3 py-1.5 rounded-xl text-sm font-bold"
                  style={{ background:'#16a34acc', color:'white', backdropFilter:'blur(8px)' }}>
                  <Ruler className="w-3.5 h-3.5 inline mr-1" />
                  {areaHa.toFixed(2)} هكتار
                  {/* م² مفيد للحقول الصغيرة/الريّ المحوريّ — تحويل بسيط (1 هكتار = 10000 م²) */}
                  {areaHa < 10 && (
                    <span className="font-semibold"> ({Math.round(areaHa * 10000).toLocaleString('en-US')} م²)</span>
                  )}
                  {perimeterM > 0 && (
                    <span className="font-semibold"> · المحيط: {formatLengthM(perimeterM)}</span>
                  )}
                </div>
              )}

              {/* Draw status */}
              {stage === 'draw' && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-1.5 rounded-xl text-xs"
                  style={{ background:'#0f1117cc', color:'#94a3b8', backdropFilter:'blur(8px)' }}>
                  اختر أداة من أعلى يمين الخريطة: مضلّع · مستطيل · دائرة
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-2xl mx-auto px-5 py-4 space-y-4" dir="rtl">
            <p className="text-sm text-slate-400">
              استورد حدود الحقل من ملفّ <strong className="text-emerald-400">GeoJSON</strong> أو
              {' '}<strong className="text-emerald-400">KML</strong> أو
              {' '}<strong className="text-emerald-400">Shapefile</strong> (.shp أو .zip مضغوط)
              مُصدَّر من Google Earth / QGIS / جهاز GPS بدل رسمها يدويّاً.
              تُحلَّل ملفّات Shapefile داخل المتصفّح وتُحوَّل إلى GeoJSON،
              ثمّ تُتحقَّق الحدود على الخادم وتُحسَب المساحة تلقائيّاً.
            </p>

            {/* File input */}
            <label
              className="flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-xl cursor-pointer border-2 border-dashed transition-colors"
              style={{ borderColor: fileName ? '#16a34a66' : '#334155', background:'#0f1117' }}>
              {parsing
                ? <Loader2 className="w-6 h-6 text-emerald-400 animate-spin" />
                : <Upload className="w-6 h-6 text-emerald-400" />}
              <span className="text-sm text-slate-300">
                {parsing
                  ? 'جاري تحليل ملفّ Shapefile...'
                  : fileName
                    ? <>الملفّ: <strong className="text-emerald-300">{fileName}</strong></>
                    : 'اختر ملفّ .geojson / .json / .kml / .shp / .zip'}
              </span>
              <input
                type="file"
                accept=".geojson,.json,.kml,.shp,.zip,application/geo+json,application/vnd.google-earth.kml+xml,application/zip,application/x-zip-compressed,x-gis/x-shapefile"
                className="hidden"
                disabled={parsing}
                onChange={e => handleFilePicked(e.target.files?.[0] ?? null)}
              />
            </label>

            {/* نموذج البيانات (اسم/مسؤول/محصول/تربة/كود/ماء) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">اسم الحقل *</label>
                <input value={name} onChange={e => setName(e.target.value)}
                  placeholder="مثال: حقل وادي سبأ"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">المسؤول *</label>
                <input value={mgr} onChange={e => setMgr(e.target.value)}
                  placeholder="اسم المسؤول"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">المحصول</label>
                <select value={crop} onChange={e => setCrop(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                  {CROPS.map(c => <option key={c}>{c}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">نوع التربة</label>
                <select value={soil} onChange={e => setSoil(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                  {SOIL_TYPES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">كود الحقل</label>
                <input value={fieldCode} onChange={e => setFieldCode(e.target.value)}
                  placeholder="مثال: F-01"
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }} />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">مصدر الماء</label>
                <select value={waterSource} onChange={e => setWaterSource(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg text-sm"
                  style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                  {WATER_SOURCES.map(w => <option key={w.value} value={w.value}>{w.label}</option>)}
                </select>
              </div>
            </div>

            {error && (
              <div className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
                style={{ background:'#1a000022', border:'1px solid #dc262633', color:'#f87171' }}>
                <AlertCircle className="w-4 h-4" /> {error}
              </div>
            )}

            {/* Actions */}
            <div className="flex gap-2 justify-end">
              <button onClick={onCancel}
                className="px-4 py-2 rounded-lg text-sm text-slate-400 hover:text-slate-200 border"
                style={{ borderColor:'#334155' }}>
                إلغاء
              </button>
              <button onClick={handleImport} disabled={saving || parsing || !fileText}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors"
                style={{ background: (saving || parsing || !fileText) ? '#15803d' : '#16a34a' }}>
                {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الاستيراد...</> : <><Check className="w-4 h-4" /> استيراد الحقل</>}
              </button>
            </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
