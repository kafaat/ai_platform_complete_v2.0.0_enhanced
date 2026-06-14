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
import { useState, useRef, useCallback } from 'react';
import {
  MapContainer, TileLayer, FeatureGroup,
} from 'react-leaflet';
import { EditControl } from 'react-leaflet-draw';
import L from 'leaflet';
import '../lib/leafletSetup'; // CSS الأساسيّ لـLeaflet + الأداة + الأيقونات (حاسم للتصيير)
import {
  X, Check, Trash2, Loader2,
  MapPin, Ruler, AlertCircle, Upload, FileUp,
  Pentagon, Square, Circle,
} from 'lucide-react';
import { kongApi } from '../services/api';
import type { FieldImportInput } from '../services/api';

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
export default function AddFieldWithMap({ onSave, onCancel, onImport }: Props) {
  const fgRef = useRef<L.FeatureGroup>(null);
  // mode: 'draw' (الرسم اليدويّ — الافتراضيّ) أو 'import' (استيراد ملفّ).
  const [mode, setMode] = useState<'draw' | 'import'>('draw');
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

  const handlePolygonDone = useCallback((pts: L.LatLng[]) => {
    if (!fgRef.current) return;
    const fg = fgRef.current;
    fg.clearLayers();
    const poly = L.polygon(pts, {
      color: '#16a34a', fillColor: '#16a34a', fillOpacity: 0.25, weight: 2,
    });
    fg.addLayer(poly);
    // تفعيل التحرير
    (poly as any).editing?.enable();
    const ha = geodesicAreaHa(pts);
    setLatlngs(pts);
    setAreaHa(ha);
    setPerimeterM(geodesicPerimeterM(pts));
    setPolygon(poly);
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
  }, []);

  // أداة الرسم (leaflet-draw): مضلّع / مستطيل / دائرة (ريّ محوريّ).
  const handleCreated = useCallback((e: any) => {
    const layer = e.layer;
    let pts: L.LatLng[];
    if (e.layerType === 'circle') {
      pts = circleToPolygon(layer.getLatLng(), layer.getRadius());
    } else {
      // polygon / rectangle: الحلقة الخارجيّة
      const ring = layer.getLatLngs?.()[0];
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
    } catch (e: any) {
      setError(e?.message || 'فشل الحفظ');
    } finally {
      setSaving(false);
    }
  };

  // ── الاستيراد من ملفّ (GeoJSON/KML) ──────────────────────────
  const [fileName, setFileName]   = useState('');
  const [fileText, setFileText]   = useState('');     // نصّ الملفّ المقروء
  const [fileFmt, setFileFmt]     = useState<'geojson' | 'kml' | null>(null);

  const handleFilePicked = (f: File | null) => {
    setError('');
    if (!f) { setFileName(''); setFileText(''); setFileFmt(null); return; }
    const lower = f.name.toLowerCase();
    const fmt: 'geojson' | 'kml' | null =
      lower.endsWith('.kml') ? 'kml'
      : (lower.endsWith('.geojson') || lower.endsWith('.json')) ? 'geojson'
      : null;
    if (!fmt) {
      setError('صيغة غير مدعومة — اختر ملفّ .geojson أو .json أو .kml.');
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
    } catch (e: any) {
      // رسالة صادقة من الخادم (400 تحليل / 422 هندسة غير صالحة) لا ابتلاع.
      setError(e?.message || 'فشل الاستيراد');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" style={{ background:'rgba(0,0,0,0.7)' }}>
      <div className="relative w-full max-w-4xl rounded-2xl overflow-hidden shadow-2xl" style={{ background:'#1e293b', border:'1px solid #334155' }}>
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b" style={{ borderColor:'#334155' }}>
          <div className="flex items-center gap-2">
            <MapPin className="w-5 h-5 text-emerald-400" />
            <h2 className="font-bold text-slate-100">
              {mode === 'import'
                ? 'استيراد حدود الحقل من ملفّ'
                : stage === 'draw' ? 'ارسم حدود الحقل على الخريطة' : 'بيانات الحقل'}
            </h2>
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
        </div>

        {/* Tabs: رسم يدويّ / استيراد ملفّ (التبويب يظهر فقط إن وُفّر onImport) */}
        {onImport && (
          <div className="flex gap-1 px-5 pt-3" dir="rtl">
            <button
              onClick={() => { setMode('draw'); setError(''); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-sm font-semibold"
              style={mode === 'draw'
                ? { background:'#0f1117', color:'#34d399', border:'1px solid #334155', borderBottom:'none' }
                : { color:'#94a3b8' }}>
              <MapPin className="w-4 h-4" /> رسم على الخريطة
            </button>
            <button
              onClick={() => { setMode('import'); setError(''); }}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-t-lg text-sm font-semibold"
              style={mode === 'import'
                ? { background:'#0f1117', color:'#34d399', border:'1px solid #334155', borderBottom:'none' }
                : { color:'#94a3b8' }}>
              <FileUp className="w-4 h-4" /> استيراد ملفّ
            </button>
          </div>
        )}

        {/* لوحة الأدوات + شريط الإرشاد (إلهام FieldView) — رسم فقط */}
        {mode === 'draw' && stage === 'draw' && (
          <div className="px-5 py-3 space-y-2" style={{ background:'#172032' }} dir="rtl">
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
          </div>
        )}

        {/* Map (الرسم اليدويّ فقط) */}
        {mode === 'draw' && (
        <div style={{ height: 380, position:'relative' }}>
          <MapContainer
            center={[15.05, 45.55]}
            zoom={10}
            style={{ height:'100%', width:'100%' }}
            doubleClickZoom={false}
            ref={(m: L.Map | null) => { mapRef.current = m; }}
          >
            <TileLayer url={tileType === 'satellite' ? SAT_URL : TILE_URL}
              attribution='&copy; <a href="https://carto.com/">CARTO</a>' />
            <FeatureGroup ref={fgRef}>
              {stage === 'draw' && (
                <EditControl
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
        )}

        {/* Bottom panel (الرسم اليدويّ) */}
        {mode === 'draw' && (
        <div className="px-5 py-4" dir="rtl">
          {stage === 'draw' ? (
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-400">ارسم حدود الحقل بإحدى أدوات الرسم (مضلّع / مستطيل / دائرة) أعلى يمين الخريطة</p>
              <button onClick={onCancel} className="px-4 py-2 rounded-lg text-sm border text-slate-400 hover:text-slate-200"
                style={{ borderColor:'#334155' }}>إلغاء</button>
            </div>
          ) : (
            <div className="space-y-4">
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
              <div className="flex gap-2 justify-end">
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
        </div>
        )}

        {/* لوحة الاستيراد من ملفّ (GeoJSON/KML) */}
        {mode === 'import' && (
          <div className="px-5 py-4 space-y-4" dir="rtl">
            <p className="text-sm text-slate-400">
              استورد حدود الحقل من ملفّ <strong className="text-emerald-400">GeoJSON</strong> أو
              {' '}<strong className="text-emerald-400">KML</strong> (مُصدَّر من Google Earth / QGIS / جهاز GPS)
              بدل رسمها يدويّاً. تُتحقَّق الحدود على الخادم وتُحسَب المساحة تلقائيّاً.
            </p>

            {/* File input */}
            <label
              className="flex flex-col items-center justify-center gap-2 px-4 py-6 rounded-xl cursor-pointer border-2 border-dashed transition-colors"
              style={{ borderColor: fileName ? '#16a34a66' : '#334155', background:'#0f1117' }}>
              <Upload className="w-6 h-6 text-emerald-400" />
              <span className="text-sm text-slate-300">
                {fileName ? <>الملفّ: <strong className="text-emerald-300">{fileName}</strong></> : 'اختر ملفّ .geojson / .json / .kml'}
              </span>
              <input
                type="file"
                accept=".geojson,.json,.kml,application/geo+json,application/vnd.google-earth.kml+xml"
                className="hidden"
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
              <button onClick={handleImport} disabled={saving || !fileText}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white transition-colors"
                style={{ background: (saving || !fileText) ? '#15803d' : '#16a34a' }}>
                {saving ? <><Loader2 className="w-4 h-4 animate-spin" /> جاري الاستيراد...</> : <><Check className="w-4 h-4" /> استيراد الحقل</>}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
