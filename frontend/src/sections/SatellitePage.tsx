// SAHOOL v9 — SatellitePage.tsx (v3)
// ✅ خريطة Leaflet حقيقيّة (FieldIndicatorMap) ببلاطات مؤشّر من raster-service
//    بدل الشبكة المتدرّجة + NDVI الجيبيّ الوهميّ السابق.
// ✅ الحقول من القاعدة (useFields) بدل قائمة مُبرمَجة.
import { useState, useEffect } from 'react';
import { Satellite, Layers, Calendar, RefreshCw, Loader2, Wifi, Map as MapIcon } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import {
  useVegetationTimeseries, useAnalyzeVegetation, useCurrentNDVI,
  useIndicatorGrid, useFields, type GridIndex,
} from '../hooks/useApi';
import FieldIndicatorMap from '../components/FieldIndicatorMap';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

// أيّ مؤشّر من طبقات الواجهة يملك بلاطات/شبكة حقيقيّة في raster-service؟
// غير المدعوم يسقط إلى ndvi (الخدمة تُرجِع بلاطات شفّافة لغير المدعوم).
const GRID_INDEX_MAP: Record<string, GridIndex> = { ndvi: 'ndvi', ndwi: 'ndwi' };

const INDICES = [
  { id:'ndvi',  name:'NDVI',  desc:'الغطاء النباتي', color:'#16a34a', icon:'🌿' },
  { id:'evi',   name:'EVI',   desc:'الغطاء المحسّن', color:'#dc2626', icon:'📊' },
  { id:'savi',  name:'SAVI',  desc:'تصحيح التربة',   color:'#f59e0b', icon:'🏜' },
  { id:'ndwi',  name:'NDWI',  desc:'محتوى المياه',   color:'#3b82f6', icon:'💧' },
  { id:'gndvi', name:'GNDVI', desc:'NDVI أخضر',      color:'#22c55e', icon:'🌱' },
  { id:'lai',   name:'LAI',   desc:'مساحة الورق',    color:'#8b5cf6', icon:'🍃' },
  { id:'rgb',   name:'صورة حقيقية', desc:'Sentinel-2 RGB', color:'#6b7280', icon:'🛰️' },
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

// هندسة الحقل (GeoJSON Polygon، إحداثيّات [lon,lat]) → مضلّع Leaflet [lat,lng].
function geomToPolygon(geometry: any): [number, number][] | undefined {
  const ring = geometry?.coordinates?.[0];
  if (!Array.isArray(ring) || ring.length < 3) return undefined;
  return ring
    .filter((c: any) => Array.isArray(c) && c.length >= 2)
    .map((c: number[]) => [c[1], c[0]] as [number, number]);
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

  const ts: any[] = tsData?.timeseries || (tsData as { data?: any[] } | undefined)?.data || [];
  const currentNdvi = ndviNow?.ndvi?.current ?? ts[ts.length - 1]?.ndvi ?? null;
  const thumbs = ts.filter((_, i) => i % Math.max(1, Math.floor(ts.length / 8)) === 0).slice(0, 8);

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
            date="latest"
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
              <div className="flex gap-1 mr-auto">
                {[14,30,60].map(d=>(
                  <button key={d} onClick={()=>setDays(d)}
                    className="px-2 py-0.5 rounded text-[11px]"
                    style={{ background:days===d?'#16a34a22':'transparent', color:days===d?'#4ade80':'#64748b', border:`1px solid ${days===d?'#16a34a44':'#334155'}` }}>
                    {d}ي
                  </button>
                ))}
              </div>
            </div>
            {tsLoading ? (
              <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 text-emerald-500 animate-spin" /></div>
            ) : (
              <div className="flex gap-2 overflow-x-auto pb-1 min-h-[72px]">
                {thumbs.map((t,i)=>{
                  const v = t.ndvi||0; const c = ndviColor(v);
                  return (
                    <div key={i} className="flex-shrink-0 cursor-default" style={{width:72}}>
                      <div className="h-10 rounded-lg mb-1 border" style={{
                        borderColor:'#334155',
                        background:`linear-gradient(135deg,${c}44,${c}88,${c}44)`
                      }} />
                      <div className="text-center text-[10px]">
                        <div className="font-bold" style={{color:c}}>{v.toFixed(2)}</div>
                        <div className="text-slate-500">{t.date?.slice(5)||''}</div>
                      </div>
                    </div>
                  );
                })}
                {!thumbs.length && <p className="text-slate-500 text-xs py-4 w-full text-center">اضغط "تحليل الآن" لجلب بيانات Sentinel-2</p>}
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
                  const supported = ind.id in GRID_INDEX_MAP;
                  return (
                    <button key={ind.id} onClick={()=>setActiveIndex(ind.id)}
                      className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg transition-all text-right"
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
        </div>
      </div>
      )}

      {/* Time-series chart */}
      <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
        <div className="flex items-center gap-2 mb-4">
          <Satellite className="w-4 h-4 text-emerald-400" />
          <span className="text-sm font-semibold text-slate-200">السلسلة الزمنية — {idx.name}</span>
          <span className="text-[10px] text-slate-500 mr-auto">{ts.length} اكتساب</span>
        </div>
        {tsLoading ? (
          <div className="flex justify-center h-24 items-center"><Loader2 className="w-6 h-6 text-emerald-500 animate-spin" /></div>
        ) : ts.length > 0 ? (
          <ResponsiveContainer width="100%" height={160}>
            <LineChart data={ts}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{fill:'#64748b',fontSize:9}} tickLine={false} interval={Math.floor(ts.length/6)} />
              <YAxis domain={[0,1]} tick={{fill:'#64748b',fontSize:11}} tickLine={false} width={32} />
              <Tooltip contentStyle={{background:'#0f1117',border:'1px solid #334155',borderRadius:8,fontSize:12}} itemStyle={{color:'#e2e8f0'}} />
              <ReferenceLine y={0.5} stroke="#f59e0b" strokeDasharray="4 2" />
              <Line type="monotone" dataKey="ndvi" stroke={idx.color} strokeWidth={2} dot={{r:3,fill:idx.color}} name="NDVI" />
              {ts[0]?.evi !== undefined && (
                <Line type="monotone" dataKey="evi" stroke="#38bdf8" strokeWidth={1.5} dot={false} strokeDasharray="4 2" name="EVI" />
              )}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="text-center py-8 text-slate-500 text-sm">
            اضغط "تحليل الآن" لبدء تحليل صور Sentinel-2
          </div>
        )}
      </div>
    </div>
  );
}
