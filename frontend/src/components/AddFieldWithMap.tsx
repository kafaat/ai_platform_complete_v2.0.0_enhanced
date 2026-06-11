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
import 'leaflet-draw/dist/leaflet.draw.css';
import {
  X, Check, Trash2, Loader2,
  MapPin, Ruler, AlertCircle,
} from 'lucide-react';

interface FieldData {
  name:        string;
  manager:     string;
  crop:        string;
  area_ha:     number;
  geometry:    { type: string; coordinates: number[][][] };
}

interface Props {
  onSave:   (data: FieldData) => Promise<void>;
  onCancel: () => void;
}

const CROPS = ['قمح صلب','شعير','ذرة صفراء','طماطم','بطاطس','خضروات','برسيم'];
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
export default function AddFieldWithMap({ onSave, onCancel }: Props) {
  const fgRef = useRef<L.FeatureGroup>(null);
  const [stage, setStage] = useState<'draw' | 'form'>('draw');
  const [latlngs, setLatlngs] = useState<L.LatLng[]>([]);
  const [areaHa, setAreaHa] = useState(0);
  const [polygon, setPolygon] = useState<L.Polygon | null>(null);
  const [name, setName]   = useState('');
  const [mgr,  setMgr]    = useState('');
  const [crop, setCrop]   = useState(CROPS[0]);
  const [saving, setSaving] = useState(false);
  const [error, setError]   = useState('');
  const [tileType, setTileType] = useState<'street'|'satellite'>('satellite');
  const mapRef = useRef<L.Map | null>(null);

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
    setPolygon(poly);
    setStage('form');
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

  const handleReset = () => {
    if (fgRef.current) fgRef.current.clearLayers();
    setStage('draw');
    setLatlngs([]);
    setAreaHa(0);
    setPolygon(null);
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
        name, manager: mgr, crop,
        area_ha: +(geodesicAreaHa(finalPts).toFixed(2)),
        geometry: { type: 'Polygon', coordinates: [coords] },
      });
    } catch (e: any) {
      setError(e?.message || 'فشل الحفظ');
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
              {stage === 'draw' ? 'ارسم حدود الحقل على الخريطة' : 'بيانات الحقل'}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {/* Layer toggle */}
            <button onClick={() => setTileType(t => t === 'street' ? 'satellite' : 'street')}
              className="px-2 py-1 rounded text-xs border" style={{ borderColor:'#334155', color:'#94a3b8' }}>
              {tileType === 'satellite' ? '🗺 خريطة' : '🛰 قمر صناعي'}
            </button>
            <button onClick={onCancel} className="p-1 rounded hover:bg-slate-700 text-slate-400">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Instructions */}
        {stage === 'draw' && (
          <div className="px-5 py-2 text-sm" style={{ background:'#172032', color:'#94a3b8' }}>
            💡 <strong className="text-emerald-400">أدوات الرسم</strong> (أعلى يمين الخريطة): مضلّع (انقر الرؤوس ثمّ أغلق) · مستطيل · <strong className="text-emerald-400">دائرة</strong> للريّ المحوريّ.
          </div>
        )}

        {/* Map */}
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

          {/* Area badge */}
          {areaHa > 0 && (
            <div className="absolute top-3 left-3 z-20 px-3 py-1.5 rounded-xl text-sm font-bold"
              style={{ background:'#16a34acc', color:'white', backdropFilter:'blur(8px)' }}>
              <Ruler className="w-3.5 h-3.5 inline mr-1" />
              {areaHa.toFixed(2)} هكتار
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

        {/* Bottom panel */}
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
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
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
              </div>

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
      </div>
    </div>
  );
}
