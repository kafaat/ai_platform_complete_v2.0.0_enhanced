// SAHOOL v9 — SatellitePage.tsx (v3)
// ✅ خريطة Leaflet حقيقيّة (FieldIndicatorMap) ببلاطات مؤشّر من raster-service
//    بدل الشبكة المتدرّجة + NDVI الجيبيّ الوهميّ السابق.
// ✅ الحقول من القاعدة (useFields) بدل قائمة مُبرمَجة.
import { useState, useEffect, useMemo } from 'react';
import { Satellite, Layers, Calendar, RefreshCw, Loader2, Wifi, Map as MapIcon, GitCompareArrows } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import {
  useVegetationTimeseries, useAnalyzeVegetation, useCurrentNDVI,
  useIndicatorGrid, useFieldTimeseries, useFieldChange, useFields, type GridIndex,
} from '../hooks/useApi';
import FieldIndicatorMap from '../components/FieldIndicatorMap';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { geomToPolygon } from '../lib/geo';

// أيّ مؤشّر من طبقات الواجهة يملك بلاطات/شبكة حقيقيّة في raster-service؟
// غير المدعوم يسقط إلى ndvi (الخدمة تُرجِع بلاطات شفّافة لغير المدعوم).
// Sprint 5b: أُضيف ndre/msavi/evi/moisture (band-math + بلاطات في raster-service).
const GRID_INDEX_MAP: Record<string, GridIndex> = {
  ndvi: 'ndvi',
  ndwi: 'ndwi',
  evi: 'evi',
  ndre: 'ndre',
  msavi: 'msavi',
  moisture: 'moisture',
};

const INDICES = [
  { id:'ndvi',     name:'NDVI',  desc:'الغطاء النباتي', color:'#16a34a', icon:'🌿' },
  { id:'evi',      name:'EVI',   desc:'الغطاء المحسّن', color:'#dc2626', icon:'📊' },
  { id:'msavi',    name:'MSAVI', desc:'تصحيح تربة ذاتي', color:'#ea580c', icon:'🏜' },
  { id:'ndre',     name:'NDRE',  desc:'النيتروجين (red-edge)', color:'#a855f7', icon:'🧪' },
  { id:'moisture', name:'الرطوبة', desc:'محتوى الرطوبة (NDMI)', color:'#0ea5e9', icon:'💦' },
  { id:'savi',     name:'SAVI',  desc:'تصحيح التربة',   color:'#f59e0b', icon:'🏜' },
  { id:'ndwi',     name:'NDWI',  desc:'محتوى المياه',   color:'#3b82f6', icon:'💧' },
  { id:'gndvi',    name:'GNDVI', desc:'NDVI أخضر',      color:'#22c55e', icon:'🌱' },
  { id:'lai',      name:'LAI',   desc:'مساحة الورق',    color:'#8b5cf6', icon:'🍃' },
  { id:'rgb',      name:'صورة حقيقية', desc:'Sentinel-2 RGB', color:'#6b7280', icon:'🛰️' },
];

interface SatField {
  id: string; name: string; area: number; crop: string;
  lat: number | null; lon: number | null; geometry: any;
}

function ndviColor(v: number) {
  if (v > 0.7) return '#16a34a';
  if (v > 0.5) return '#65a30d';
  if (v > 0.3) return '#ca8a04';
  if (v > 0.1) return '#f97316';
  return '#dc2626';
}
function ndviLabel(v: number) {
  if (v > 0.7) return 'ممتاز';
  if (v > 0.5) return 'جيد';
  if (v > 0.3) return 'مقبول';
  return 'منخفض';
}

export default function SatellitePage() {
  const { data: fieldsData, isLoading: fieldsLoading, isError: fieldsError, refetch } = useFields();
  const fields: SatField[] = ((fieldsData as { fields?: any[] } | undefined)?.fields ?? []).map((f) => ({
    id: String(f.field_id ?? f.id),
    name: String(f.name_ar ?? f.name ?? 'حقل'),
    area: Number(f.area_ha ?? f.area ?? 0),
    crop: String(f.crop ?? '—'),
    lat: f.lat ?? f.centroid_lat ?? null,
    lon: f.lon ?? f.centroid_lon ?? null,
    geometry: f.geometry,
  }));

  const [fieldId,     setFieldId]     = useState('');
  const [activeIndex, setActiveIndex] = useState('ndvi');
  const [days,        setDays]        = useState(30);
  const [showLayers,  setShowLayers]  = useState(true);

  // أوّل حقل حقيقيّ يصبح المختار افتراضيّاً عند توفّر القائمة.
  useEffect(() => {
    if (!fieldId && fields.length) setFieldId(fields[0].id);
  }, [fields, fieldId]);

  const field = fields.find((f) => f.id === fieldId) || fields[0];
  const idx   = INDICES.find((i) => i.id === activeIndex) || INDICES[0];
  const gridIndex = GRID_INDEX_MAP[activeIndex] ?? 'ndvi';

  const { data: tsData,  isLoading: tsLoading }  = useVegetationTimeseries(fieldId, days);
  const { data: ndviNow }                        = useCurrentNDVI(fieldId);
  const { mutateAsync: analyze, isPending: analyzing } = useAnalyzeVegetation();

  // شبكة المؤشّر الحقيقيّة — لوسم مصدر البيانات بصدق (حقيقيّة / لا توجد بعد).
  const { data: gridResp } = useIndicatorGrid(fieldId, gridIndex, 'latest');
  const hasGrid = !!gridResp && gridResp.real_data && Array.isArray(gridResp.grid) && gridResp.grid.length > 0;

  // السلسلة الزمنيّة الحقيقيّة من raster-service (متوسّط المؤشّر لكلّ تاريخ COG).
  // صدق: لا COG ⇒ available=false (لا قيم مخترعة) — نُظهر حالة فارغة لا رسماً وهميّاً.
  const { data: rasterTs, isLoading: rasterTsLoading, isError: rasterTsError } =
    useFieldTimeseries(fieldId, gridIndex, '');
  const rasterPoints = rasterTs?.available ? (rasterTs.points ?? []) : [];
  // تواريخ COG الحقيقيّة المتاحة (لاختيار تاريخَي كشف التغيّر).
  const availableDates = useMemo(
    () => rasterPoints.map((p) => p.datetime).filter(Boolean),
    [rasterPoints],
  );

  // كشف التغيّر بين تاريخين (real grids only). الافتراض: الأقدم ↔ الأحدث.
  const [dateA, setDateA] = useState('');
  const [dateB, setDateB] = useState('');
  useEffect(() => {
    if (availableDates.length >= 2) {
      setDateA((prev) => (prev && availableDates.includes(prev) ? prev : availableDates[0]));
      setDateB((prev) =>
        prev && availableDates.includes(prev) ? prev : availableDates[availableDates.length - 1],
      );
    }
  }, [availableDates]);
  const { data: change, isLoading: changeLoading, isError: changeError } =
    useFieldChange(fieldId, gridIndex, dateA, dateB, { enabled: !!dateA && !!dateB && dateA !== dateB });

  const ts: any[] = tsData?.timeseries || (tsData as { data?: any[] } | undefined)?.data || [];
  const currentNdvi = ndviNow?.ndvi?.current ?? ts[ts.length - 1]?.ndvi ?? null;
  // الشريط الزمني يعرض المتوسّطات الحقيقيّة من raster-service عند توفّرها،
  // وإلّا يسقط إلى سلسلة vegetation-service. لا بيانات تركيبيّة.
  // cloud: نسبة الغيوم لكلّ تاريخ (raster فقط) — null في مصدر vegetation البديل.
  const stripPoints = Array.isArray(rasterPoints) && rasterPoints.length
    ? rasterPoints.map((p) => ({ date: p.datetime, value: p.mean, cloud: p.cloudy_pct ?? null }))
    : (Array.isArray(ts) ? ts : []).map((t) => ({ date: t.date, value: t.ndvi ?? 0, cloud: null }));

  // هل يوفّر المصدر نسبة غيوم؟ (raster نعم، vegetation لا) — يضبط إتاحة المُبدِّل.
  const hasCloudData = stripPoints.some((p) => typeof p.cloud === 'number');

  // إخفاء الأيّام الغائمة (نمط FieldView): يُسقط النقاط التي تتجاوز عتبة الغيوم.
  // غير مُفعَّل ما لم يتوفّر cloudy_pct (تعطيل رشيق لمصدر vegetation البديل).
  const [hideCloudy, setHideCloudy] = useState(false);
  const CLOUD_THRESHOLD = 50;
  const visiblePoints = (hideCloudy && hasCloudData)
    ? stripPoints.filter((p) => !(typeof p.cloud === 'number' && p.cloud > CLOUD_THRESHOLD))
    : stripPoints;

  // البلاطات مدفوعة بالبيانات بالكامل (لا تواريخ ثابتة): تنمو مع وصول نقاط جديدة.
  // الشريط قابل للتمرير أفقيّاً، فلا نحدّ العدد بثمانٍ — نعرض كلّ النقاط المرئيّة.
  const thumbs = visiblePoints;

  // قائمة التواريخ المرئيّة مُستقرّة المرجع (مفتاح نصّيّ) — كي لا يُعاد تشغيل
  // التأثير كلّ تصيير (نمط availableDates أعلاه).
  const visibleDates = useMemo(
    () => visiblePoints.map((p) => p.date).filter(Boolean),
    [visiblePoints.map((p) => p.date).join('|')], // eslint-disable-line react-hooks/exhaustive-deps
  );

  // التاريخ المختار يقود طبقة الخريطة (نقر البلاطة). الافتراض: أحدث تاريخ مرئيّ.
  // data-driven: لا قيمة ثابتة — نُعيد المزامنة كلّما تغيّرت النقاط/التصفية.
  const [selectedDate, setSelectedDate] = useState('');
  useEffect(() => {
    if (!visibleDates.length) { setSelectedDate(''); return; }
    setSelectedDate((prev) =>
      prev && visibleDates.includes(prev) ? prev : visibleDates[visibleDates.length - 1],
    );
  }, [visibleDates]);

  // طبقة الخريطة: التاريخ المختار إن وُجِد، وإلّا "latest" (سلوك سابق).
  const mapDate = selectedDate || 'latest';

  // مضلّع الحقل + إطار احتياطيّ للخريطة من هندسة/مركز الحقل الحقيقيّ.
  const fieldPolygon = field ? geomToPolygon(field.geometry) : undefined;
  const fallbackBounds: [number, number, number, number] | undefined =
    field && field.lat != null && field.lon != null
      ? [field.lon - 0.01, field.lat - 0.01, field.lon + 0.01, field.lat + 0.01]
      : undefined;

  return (
    <div className="space-y-4 max-w-7xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">الأقمار الصناعية</h2>
          <p className="text-sm text-slate-400">Sentinel-2 L2A · Copernicus · كل 5 أيام</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 px-2 py-1 rounded-full text-[11px] bg-emerald-950 text-emerald-400 border border-emerald-900">
            <Wifi className="w-3 h-3" /> Copernicus CDSE
          </span>
          <button onClick={() => fieldId && analyze({ fieldId })} disabled={analyzing || !fieldId}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white disabled:opacity-50"
            style={{ background: analyzing ? '#15803d' : '#16a34a' }}>
            {analyzing ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> تحليل...</> : <><RefreshCw className="w-3.5 h-3.5" /> تحليل الآن</>}
          </button>
        </div>
      </div>

      {/* لا حقول حقيقيّة بعد → حالة صادقة بدل خريطة وهميّة */}
      {fieldsLoading ? (
        <LoadingState message="جارٍ تحميل الحقول…" />
      ) : fieldsError ? (
        <ErrorState title="تعذّر تحميل الحقول من الخادم" onRetry={() => refetch()} />
      ) : fields.length === 0 ? (
        <EmptyState
          title="لا توجد حقول بعد"
          hint="أضِف حقلاً من شاشة «إدارة الحقول» (ارسم حدوده على الخريطة) لعرض مؤشّراته الفضائيّة."
        />
      ) : (
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Map */}
        <div className="lg:col-span-3 space-y-3">
          {/* شريط مصدر البيانات: بلاطات حقيقيّة أم لا توجد بعد (صدق المصدر) */}
          <div className="flex items-center gap-2 text-[11px] px-3 py-2 rounded-lg border"
            style={hasGrid
              ? { background:'#13301f', borderColor:'#2d6a3e', color:'#9fe6b4' }
              : { background:'#3a2e14', borderColor:'#7a5a1a', color:'#f0d68a' }}>
            <MapIcon className="w-3.5 h-3.5" />
            {hasGrid
              ? `بلاطات حقيقيّة · Sentinel-2 (Element84)${gridResp?.date ? ` · ${gridResp.date}` : ''}`
              : 'لا توجد بلاطات مؤشّر لهذا الحقل بعد — اضغط «تحليل الآن» أو تحقّق من معالجة الراستر. الخريطة تعرض الأساس والحدود فقط.'}
          </div>

          {/* خريطة Leaflet حقيقيّة ببلاطات المؤشّر مقصوصة فوق الحقل */}
          <FieldIndicatorMap
            key={fieldId}
            fieldId={fieldId}
            index={gridIndex}
            date={mapDate}
            fieldPolygon={fieldPolygon}
            fallbackBounds={fallbackBounds}
            basemap="satellite"
            initialOpacity={0.75}
            height={400}
          />

          {/* Thumbnail strip (سلسلة زمنيّة حقيقيّة من vegetation-service) */}
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <div className="flex items-center gap-2 mb-2">
              <Calendar className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold text-slate-300">الشريط الزمني</span>
              {rasterPoints.length > 0 && (
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900">
                  متوسّطات حقيقيّة · {gridIndex.toUpperCase()}
                </span>
              )}
              {/* إخفاء الأيّام الغائمة (نمط FieldView) — يظهر فقط حين يوفّر المصدر
                  cloudy_pct؛ تعطيل رشيق لمصدر vegetation البديل. */}
              {hasCloudData && (
                <label className="flex items-center gap-1.5 mr-auto cursor-pointer select-none text-[11px] text-slate-300">
                  <input
                    type="checkbox"
                    checked={hideCloudy}
                    onChange={(e)=>setHideCloudy(e.target.checked)}
                    style={{ accentColor:'#16a34a' }}
                  />
                  إخفاء الأيّام الغائمة
                </label>
              )}
              <div className={`flex gap-1 ${hasCloudData ? '' : 'mr-auto'}`}>
                {[14,30,60].map(d=>(
                  <button key={d} onClick={()=>setDays(d)}
                    className="px-2 py-0.5 rounded text-[11px]"
                    style={{ background:days===d?'#16a34a22':'transparent', color:days===d?'#4ade80':'#64748b', border:`1px solid ${days===d?'#16a34a44':'#334155'}` }}>
                    {d}ي
                  </button>
                ))}
              </div>
            </div>
            {(rasterTsLoading || tsLoading) ? (
              <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 text-emerald-500 animate-spin" /></div>
            ) : rasterTsError && !thumbs.length ? (
              <p className="text-amber-400/80 text-xs py-4 w-full text-center">تعذّر جلب السلسلة الزمنيّة للمؤشّر.</p>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1 min-h-[72px]">
                {(Array.isArray(thumbs) ? thumbs : []).map((t,i)=>{
                  const v = t.value||0; const c = ndviColor(v);
                  const selected = !!t.date && t.date === selectedDate;
                  const cloudy = typeof t.cloud === 'number' && t.cloud > CLOUD_THRESHOLD;
                  // نقر البلاطة يختار تاريخها ⇒ يتغيّر mapDate ⇒ طبقة الخريطة تتبدّل
                  // (FieldIndicatorMap يُمرّر date عبر استعلام بلاطات/tilejson).
                  return (
                    <button
                      key={t.date || i}
                      type="button"
                      onClick={()=> t.date && setSelectedDate(t.date)}
                      title={t.date ? (cloudy ? `${t.date} · غائم` : t.date) : ''}
                      className="flex-shrink-0 cursor-pointer text-right rounded-lg p-0.5 transition-all"
                      style={{ width:72,
                        outline: selected ? `2px solid ${c}` : '2px solid transparent',
                        outlineOffset: 1,
                        background: selected ? `${c}1a` : 'transparent' }}
                    >
                      <div className="h-10 rounded-lg mb-1 border relative" style={{
                        borderColor: selected ? c : '#334155',
                        background:`linear-gradient(135deg,${c}44,${c}88,${c}44)`
                      }}>
                        {cloudy && (
                          <span className="absolute top-0.5 left-0.5 text-[10px] leading-none" title="يوم غائم">☁️</span>
                        )}
                      </div>
                      <div className="text-center text-[10px]">
                        <div className="font-bold" style={{color:c}}>{v.toFixed(2)}</div>
                        <div className={selected ? 'text-slate-200' : 'text-slate-500'}>{t.date?.slice(5)||''}</div>
                      </div>
                    </button>
                  );
                })}
                {!thumbs.length && (
                  <p className="text-slate-500 text-xs py-4 w-full text-center">
                    {hideCloudy && hasCloudData
                      ? 'كلّ التواريخ المتاحة غائمة — أوقِف «إخفاء الأيّام الغائمة» لعرضها.'
                      : 'لا توجد متوسّطات مؤشّر بعد — اضغط "تحليل الآن" لمعالجة صور Sentinel-2.'}
                  </p>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Side panel */}
        <div className="space-y-3">
          {/* Field selector (حقول حقيقيّة) */}
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <label className="block text-xs text-slate-400 mb-1">الحقل</label>
            <select value={fieldId} onChange={e=>setFieldId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm"
              style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
              {fields.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <div className="grid grid-cols-2 gap-1.5 mt-2">
              {[
                {l:'NDVI',v:currentNdvi!=null?currentNdvi.toFixed(3):'لا بيانات',c:currentNdvi!=null?ndviColor(currentNdvi):'#94a3b8'},
                {l:'الحالة',v:currentNdvi!=null?ndviLabel(currentNdvi):'بانتظار التحليل',c:currentNdvi!=null?ndviColor(currentNdvi):'#94a3b8'},
                {l:'المساحة',v:field?`${field.area}هـ`:'—',c:'#94a3b8'},
                {l:'المحصول',v:field?field.crop:'—',c:'#94a3b8'},
              ].map((s,i)=>(
                <div key={i} className="rounded-lg px-2 py-1.5 text-center" style={{background:'#0f1117'}}>
                  <div className="text-xs font-bold" style={{color:s.c}}>{s.v}</div>
                  <div className="text-[10px] text-slate-500">{s.l}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Layers */}
          <div className="rounded-xl border overflow-hidden" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <button onClick={()=>setShowLayers(!showLayers)}
              className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-slate-800 transition-colors">
              <div className="flex items-center gap-2">
                <Layers className="w-4 h-4 text-slate-400" />
                <span className="text-sm font-semibold text-slate-200">الطبقات</span>
              </div>
              <span className="text-slate-500 text-xs">{showLayers?'▲':'▼'}</span>
            </button>
            {showLayers && (
              <div className="px-2 pb-3 space-y-1">
                {INDICES.map(ind=>{
                  // فقط المؤشّرات التي لها بلاطات حقيقيّة قابلة للاختيار — تعطيل
                  // الباقي يمنع تضليل المستخدم (خريطة NDVI تحت عنوان EVI مثلاً).
                  const supported = ind.id in GRID_INDEX_MAP;
                  return (
                    <button key={ind.id} disabled={!supported}
                      onClick={()=> supported && setActiveIndex(ind.id)}
                      title={supported ? undefined : 'بلاطات هذا المؤشّر غير متوفّرة بعد'}
                      className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg transition-all text-right disabled:opacity-40 disabled:cursor-not-allowed"
                      style={{ background:activeIndex===ind.id?`${ind.color}22`:'transparent',
                        border:`1px solid ${activeIndex===ind.id?ind.color+'44':'transparent'}` }}>
                      <span>{ind.icon}</span>
                      <div className="flex-1">
                        <div className="text-sm" style={{color:activeIndex===ind.id?ind.color:'#94a3b8'}}>{ind.name}</div>
                        <div className="text-[10px] text-slate-600">{ind.desc}{!supported && ' · بلاطات قريباً'}</div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Legend */}
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <div className="text-[11px] text-slate-400 mb-1.5">مقياس {idx.name}</div>
            <div className="h-3 rounded-full" style={{ background:'linear-gradient(to right,#dc2626,#f97316,#f59e0b,#65a30d,#16a34a)' }} />
            <div className="flex justify-between text-[10px] text-slate-500 mt-1">
              <span>0.2- (تربة)</span><span>0.9+ (صحي)</span>
            </div>
          </div>

          {/* كشف التغيّر بين تاريخين (per-pixel، بيانات COG حقيقيّة فقط) */}
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <div className="flex items-center gap-2 mb-2">
              <GitCompareArrows className="w-4 h-4 text-sky-400" />
              <span className="text-sm font-semibold text-slate-200">كشف التغيّر</span>
              <span className="text-[10px] text-slate-500 mr-auto">{gridIndex.toUpperCase()}</span>
            </div>

            {availableDates.length < 2 ? (
              <p className="text-[11px] text-slate-500 py-2">
                يلزم تاريخان مُعالَجان على الأقلّ لكشف التغيّر. شغّل «تحليل الآن» على تواريخ متعدّدة.
              </p>
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <label className="block">
                    <span className="block text-[10px] text-slate-400 mb-1">من (الأقدم)</span>
                    <select value={dateA} onChange={(e)=>setDateA(e.target.value)}
                      className="w-full px-2 py-1.5 rounded-lg text-[11px]"
                      style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                      {availableDates.map((d)=><option key={d} value={d}>{d}</option>)}
                    </select>
                  </label>
                  <label className="block">
                    <span className="block text-[10px] text-slate-400 mb-1">إلى (الأحدث)</span>
                    <select value={dateB} onChange={(e)=>setDateB(e.target.value)}
                      className="w-full px-2 py-1.5 rounded-lg text-[11px]"
                      style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
                      {availableDates.map((d)=><option key={d} value={d}>{d}</option>)}
                    </select>
                  </label>
                </div>

                {dateA === dateB ? (
                  <p className="text-[11px] text-amber-400/80 py-1">اختر تاريخين مختلفين.</p>
                ) : changeLoading ? (
                  <div className="flex justify-center py-3"><Loader2 className="w-4 h-4 text-sky-400 animate-spin" /></div>
                ) : changeError ? (
                  <p className="text-[11px] text-amber-400/80 py-1">تعذّر حساب التغيّر.</p>
                ) : change && !change.available ? (
                  <p className="text-[11px] text-amber-400/80 py-1">
                    {change.note || 'لا توجد بيانات COG حقيقيّة لأحد التاريخين — لا تغيّر مُفبرَك.'}
                  </p>
                ) : change && change.available ? (
                  <div className="space-y-2">
                    <div className="grid grid-cols-2 gap-2">
                      <div className="rounded-lg px-2 py-1.5 text-center" style={{ background:'#13301f', border:'1px solid #2d6a3e' }}>
                        <div className="text-base font-bold text-emerald-400">{(change.improved_pct ?? 0).toFixed(1)}%</div>
                        <div className="text-[10px] text-emerald-300/70">تحسّن</div>
                      </div>
                      <div className="rounded-lg px-2 py-1.5 text-center" style={{ background:'#3a1414', border:'1px solid #7a2a2a' }}>
                        <div className="text-base font-bold text-red-400">{(change.degraded_pct ?? 0).toFixed(1)}%</div>
                        <div className="text-[10px] text-red-300/70">تدهور</div>
                      </div>
                    </div>
                    <div className="flex justify-between text-[10px] text-slate-500">
                      <span>مستقرّ: {(change.stable_pct ?? 0).toFixed(1)}%</span>
                      <span>Δ متوسّط: {(change.mean_delta ?? 0).toFixed(3)}</span>
                    </div>
                    {change.cloud_warning && (
                      <p className="text-[10px] text-amber-400/80">
                        ⚠️ التغطية {(change.coverage_pct ?? 0).toFixed(0)}% فقط (غيوم/فجوات) — نتيجة جزئيّة.
                      </p>
                    )}
                    {change.interpretation_ar && (
                      <p className="text-[11px] text-slate-300 leading-relaxed border-t border-slate-700 pt-1.5">
                        {change.interpretation_ar}
                      </p>
                    )}
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      </div>
      )}

      {/* Time-series chart */}
      <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
        <div className="flex items-center gap-2 mb-4">
          <Satellite className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">السلسلة الزمنية — {idx.name}</span>
          {rasterPoints.length > 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-900">
              متوسّطات COG حقيقيّة
            </span>
          )}
          <span className="text-[10px] text-slate-500 mr-auto">{stripPoints.length} اكتساب</span>
        </div>
        {(rasterTsLoading || tsLoading) ? (
          <div className="flex justify-center h-24 items-center"><Loader2 className="w-6 h-6 text-emerald-500 animate-spin" /></div>
        ) : stripPoints.length > 0 ? (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={stripPoints}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{fill:'#64748b',fontSize:9}} tickLine={false} interval={Math.max(1,Math.floor(stripPoints.length/6))} />
              <YAxis domain={[0,1]} tick={{fill:'#64748b',fontSize:11}} tickLine={false} width={32} />
              <Tooltip contentStyle={{background:'#0f1117',border:'1px solid #334155',borderRadius:8,fontSize:12}} itemStyle={{color:'#e2e8f0'}} />
              <ReferenceLine y={0.5} stroke="#f59e0b" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="value" stroke={idx.color} strokeWidth={2} dot={{r:3,fill:idx.color}} name={idx.name} />
            </LineChart>
          </ResponsiveContainer>
        ) : rasterTsError ? (
          <div className="text-center py-8 text-amber-400/80 text-sm">تعذّر جلب السلسلة الزمنيّة للمؤشّر.</div>
        ) : (
          <div className="text-center py-8 text-slate-500 text-sm">
            لا توجد متوسّطات مؤشّر بعد — اضغط "تحليل الآن" لبدء تحليل صور Sentinel-2.
          </div>
        )}
      </div>
    </div>
  );
}
