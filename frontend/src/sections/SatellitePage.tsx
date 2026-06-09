// SAHOOL v8.0 — SatellitePage.tsx (v2)
// ✅ خريطة أولاً + 7 طبقات + قيمة البكسل + شريط زمني
import { useState } from 'react';
import { Satellite, Layers, Calendar, RefreshCw, Loader2, Wifi, Info } from 'lucide-react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useVegetationTimeseries, useAnalyzeVegetation, useCurrentNDVI, useIndicatorGrid, type GridIndex } from '../hooks/useApi';

// أي مؤشر من طبقات الواجهة يملك شبكة per-pixel حقيقيّة في raster-service؟
const GRID_INDEX_MAP: Record<string, GridIndex> = { ndvi: 'ndvi', ndwi: 'ndwi' };

const FIELDS = [
  { id:'field_01', name:'حقل وادي سبأ',        lat:15.05, lon:45.55, area:23.5, crop:'قمح صلب' },
  { id:'field_02', name:'حقل البيضاء الشمالي', lat:15.02, lon:45.58, area:32.0, crop:'شعير' },
  { id:'field_03', name:'حقل البيضاء الجنوبي', lat:14.98, lon:45.52, area:18.7, crop:'ذرة صفراء' },
  { id:'field_04', name:'حقل رداع الغربي',     lat:14.92, lon:45.48, area:41.3, crop:'طماطم' },
  { id:'field_05', name:'حقل ذي السفال',       lat:14.88, lon:45.60, area:28.9, crop:'قمح صلب' },
  { id:'field_06', name:'حقل عتمة الشرقي',    lat:15.10, lon:45.62, area:37.5, crop:'شعير' },
  { id:'field_07', name:'حقل الرياشية',        lat:15.00, lon:45.45, area:22.1, crop:'خضروات' },
  { id:'field_08', name:'حقل ذي ناعم',         lat:14.85, lon:45.65, area:45.0, crop:'بطاطس' },
];

const INDICES = [
  { id:'ndvi',  name:'NDVI',  desc:'الغطاء النباتي', color:'#16a34a', icon:'🌿' },
  { id:'evi',   name:'EVI',   desc:'الغطاء المحسّن', color:'#dc2626', icon:'📊' },
  { id:'savi',  name:'SAVI',  desc:'تصحيح التربة',   color:'#f59e0b', icon:'🏜' },
  { id:'ndwi',  name:'NDWI',  desc:'محتوى المياه',   color:'#3b82f6', icon:'💧' },
  { id:'gndvi', name:'GNDVI', desc:'NDVI أخضر',      color:'#22c55e', icon:'🌱' },
  { id:'lai',   name:'LAI',   desc:'مساحة الورق',    color:'#8b5cf6', icon:'🍃' },
  { id:'rgb',   name:'صورة حقيقية', desc:'Sentinel-2 RGB', color:'#6b7280', icon:'🛰️' },
];

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
  const [fieldId,      setFieldId]      = useState('field_01');
  const [activeIndex,  setActiveIndex]  = useState('ndvi');
  const [opacity,      setOpacity]      = useState(75);
  const [days,         setDays]         = useState(30);
  const [showLayers,   setShowLayers]   = useState(true);
  const [pixelInfo,    setPixelInfo]    = useState<{lat:number;lon:number;ndvi:number;real:boolean}|null>(null);

  const field = FIELDS.find(f => f.id === fieldId) || FIELDS[0];
  const idx   = INDICES.find(i => i.id === activeIndex) || INDICES[0];

  const { data: tsData,  isLoading: tsLoading  } = useVegetationTimeseries(fieldId, days);
  const { data: ndviNow, isLoading: ndviLoading } = useCurrentNDVI(fieldId);
  const { mutateAsync: analyze, isPending: analyzing } = useAnalyzeVegetation();

  // شبكة المؤشر الحقيقيّة لكل بكسل (Sentinel-2 / Element84) — للقراءة عند النقر
  const gridIndex = GRID_INDEX_MAP[activeIndex] ?? 'ndvi';
  const { data: gridResp } = useIndicatorGrid(fieldId, gridIndex, 'latest');
  const hasGrid = !!gridResp && gridResp.real_data && Array.isArray(gridResp.grid) && gridResp.grid.length > 0;

  const ts: any[] = tsData?.timeseries || (tsData as { data?: any[] } | undefined)?.data || [];
  const currentNdvi = ndviNow?.ndvi?.current ?? ts[ts.length-1]?.ndvi ?? null;
  const thumbs = ts.filter((_,i) => i % Math.max(1,Math.floor(ts.length/8)) === 0).slice(0,8);

  const handleMapClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;   // 0=يسار, 1=يمين
    const y = (e.clientY - rect.top)  / rect.height;  // 0=أعلى, 1=أسفل

    // قراءة قيمة البكسل الحقيقيّة من الشبكة: تطبيع موضع النقر داخل bbox → grid[r][c]
    if (hasGrid && gridResp) {
      const [minLon, minLat, maxLon, maxLat] = gridResp.bbox;
      const lon = minLon + x * (maxLon - minLon);
      const lat = maxLat - y * (maxLat - minLat); // الصف 0 = أعلى الحقل (أقصى خط عرض)
      const c = Math.min(gridResp.cols - 1, Math.max(0, Math.floor(x * gridResp.cols)));
      const r = Math.min(gridResp.rows - 1, Math.max(0, Math.floor(y * gridResp.rows)));
      const cell = gridResp.grid[r]?.[c];
      if (cell != null) {
        setPixelInfo({ lat, lon, ndvi: cell, real: true });
        return;
      }
      // خلية خارج الحقل / لا بيانات → أبلغ بصدق بدل تلفيق قيمة
      setPixelInfo({ lat, lon, ndvi: NaN, real: true });
      return;
    }

    // سقوط آمن: تقدير توضيحي عند غياب الشبكة الحقيقيّة (موسوم بوضوح في الواجهة)
    const mockNdvi = 0.35 + Math.sin(x*5+y*3)*0.25 + Math.cos(x*3+y*5)*0.15;
    setPixelInfo({
      lat: field.lat + (0.5-y)*0.1,
      lon: field.lon + (x-0.5)*0.1,
      ndvi: Math.max(-1, Math.min(1, mockNdvi)),
      real: false,
    });
  };

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
          <button onClick={() => analyze({ fieldId })} disabled={analyzing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-white"
            style={{ background: analyzing ? '#15803d' : '#16a34a' }}>
            {analyzing ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> تحليل...</> : <><RefreshCw className="w-3.5 h-3.5" /> تحليل الآن</>}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4">
        {/* Map */}
        <div className="lg:col-span-3 space-y-3">
          <div style={{ height:400, position:'relative', borderRadius:12, overflow:'hidden', border:'1px solid #334155', cursor:'crosshair' }}
            onClick={handleMapClick}>
            {/* Background */}
            <div className="absolute inset-0" style={{ background:'linear-gradient(135deg,#1a2a1a,#0a1a0a,#1a1a2a)' }} />
            {/* Grid */}
            <div className="absolute inset-0 opacity-10" style={{
              backgroundImage:'repeating-linear-gradient(0deg,transparent,transparent 39px,#16a34a22 40px),repeating-linear-gradient(90deg,transparent,transparent 39px,#16a34a22 40px)'
            }} />
            {/* NDVI overlay */}
            {idx.id !== 'rgb' && (
              <div className="absolute inset-0" style={{ opacity: opacity/100,
                background:`linear-gradient(45deg, ${idx.color}55 0%, ${idx.color}22 50%, ${idx.color}44 100%)` }} />
            )}
            {/* Pivot circles — قيم العرض التوضيحي؛ القيمة الحقيقية من زر "تحليل الآن" */}
            {[{x:'35%',y:'40%',r:90,v:currentNdvi},{x:'65%',y:'60%',r:70,v:null}].map((p,i)=>(
              <div key={i} className="absolute rounded-full border-2 flex items-center justify-center"
                style={{ left:p.x, top:p.y, width:p.r*2, height:p.r*2, transform:'translate(-50%,-50%)',
                  borderColor: p.v!=null?ndviColor(p.v):'#475569', background:`radial-gradient(circle,${p.v!=null?ndviColor(p.v):'#475569'}22,transparent)` }}>
                <div className="text-center">
                  <div className="text-sm font-bold" style={{ color:p.v!=null?ndviColor(p.v):'#94a3b8' }}>{p.v!=null?p.v.toFixed(2):'—'}</div>
                  <div className="text-[9px] text-slate-300">{p.v!=null?ndviLabel(p.v):'لا بيانات'}</div>
                </div>
              </div>
            ))}
            {/* Layer badge */}
            <div className="absolute top-3 right-3 z-10 px-2.5 py-1.5 rounded-xl text-sm font-bold"
              style={{ background:'#0f1117dd', color:idx.color, border:`1px solid ${idx.color}44` }}>
              {idx.icon} {idx.name}
            </div>
            {/* Pixel info */}
            {pixelInfo && (() => {
              const noData = Number.isNaN(pixelInfo.ndvi);
              const valLabel = pixelInfo.real
                ? `${gridIndex.toUpperCase()} (حقيقي)`
                : 'NDVI (تقديري)';
              const valColor = noData ? '#94a3b8' : ndviColor(pixelInfo.ndvi);
              return (
                <div className="absolute top-3 left-3 z-10 rounded-xl p-3 text-xs"
                  style={{ background:'#0f1117dd', border:'1px solid #334155', backdropFilter:'blur(8px)' }}>
                  <div className="mb-1 flex items-center gap-1"
                    style={{ color: pixelInfo.real ? '#4ade80' : '#94a3b8' }}>
                    <Info className="w-3 h-3" /> {pixelInfo.real ? 'قيمة حقيقية · Sentinel-2 (Element84)' : 'قيمة تقديرية للعرض'}
                  </div>
                  {[[valLabel, noData ? 'لا بيانات' : pixelInfo.ndvi.toFixed(2), valColor],
                    ['الحالة', noData ? 'خارج الحقل' : ndviLabel(pixelInfo.ndvi), valColor],
                    ['lat', pixelInfo.lat.toFixed(5), '#94a3b8'],
                    ['lon', pixelInfo.lon.toFixed(5), '#94a3b8']].map(([k,v,c],i)=>(
                    <div key={i} className="flex justify-between gap-6">
                      <span className="text-slate-500">{k}</span>
                      <span className="font-bold" style={{ color:c as string }}>{v}</span>
                    </div>
                  ))}
                </div>
              );
            })()}
            {!pixelInfo && (
              <div className="absolute bottom-3 left-3 z-10 px-2 py-1 rounded text-[10px] text-slate-400"
                style={{ background:'#0f1117cc' }}>
                {hasGrid ? 'انقر لقراءة قيمة البكسل الحقيقيّة' : 'انقر لعرض قيمة تقديرية (للعرض فقط)'}
              </div>
            )}
            {/* Attribution */}
            <div className="absolute bottom-2 right-2 text-[10px] text-slate-600">Sentinel-2 © Copernicus</div>
          </div>

          {/* Thumbnail strip */}
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
                    <div key={i} className="flex-shrink-0 w-18 cursor-pointer" style={{width:72}}
                      onClick={()=>setPixelInfo({lat:field.lat,lon:field.lon,ndvi:v,real:false})}>
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
          {/* Field selector */}
          <div className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <label className="block text-xs text-slate-400 mb-1">الحقل</label>
            <select value={fieldId} onChange={e=>setFieldId(e.target.value)}
              className="w-full px-3 py-2 rounded-lg text-sm"
              style={{ background:'#0f1117', border:'1px solid #334155', color:'#e2e8f0' }}>
              {FIELDS.map(f=><option key={f.id} value={f.id}>{f.name}</option>)}
            </select>
            <div className="grid grid-cols-2 gap-1.5 mt-2">
              {[
                {l:'NDVI',v:currentNdvi!=null?currentNdvi.toFixed(3):'لا بيانات',c:currentNdvi!=null?ndviColor(currentNdvi):'#94a3b8'},
                {l:'الحالة',v:currentNdvi!=null?ndviLabel(currentNdvi):'بانتظار التحليل',c:currentNdvi!=null?ndviColor(currentNdvi):'#94a3b8'},
                {l:'المساحة',v:`${field.area}هـ`,c:'#94a3b8'},
                {l:'المحصول',v:field.crop,c:'#94a3b8'},
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
                {INDICES.map(ind=>(
                  <button key={ind.id} onClick={()=>setActiveIndex(ind.id)}
                    className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg transition-all text-right"
                    style={{ background:activeIndex===ind.id?`${ind.color}22`:'transparent',
                      border:`1px solid ${activeIndex===ind.id?ind.color+'44':'transparent'}` }}>
                    <span>{ind.icon}</span>
                    <div className="flex-1">
                      <div className="text-sm" style={{color:activeIndex===ind.id?ind.color:'#94a3b8'}}>{ind.name}</div>
                      <div className="text-[10px] text-slate-600">{ind.desc}</div>
                    </div>
                  </button>
                ))}
                <div className="pt-1 px-1">
                  <div className="flex justify-between text-[11px] mb-1 text-slate-400">
                    <span>شفافية</span><span>{opacity}%</span>
                  </div>
                  <input type="range" min="0" max="100" value={opacity}
                    onChange={e=>setOpacity(+e.target.value)} className="w-full accent-emerald-500" />
                </div>
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
