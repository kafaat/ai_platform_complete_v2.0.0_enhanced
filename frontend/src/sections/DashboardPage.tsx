// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — DashboardPage (ربط حقيقي مع APIs)
// ═══════════════════════════════════════════════════════════════
import {
  Leaf, BarChart3, Map, RefreshCw, Zap, ChevronLeft, Wifi, WifiOff, AlertTriangle,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { useDashboardData, useWeatherForecast, useAlerts, useAllServicesHealth } from '../hooks/useApi';
import { KPICard, STATUS_COLOR } from '../components/KPICard';
import { LoadingState, SkeletonGrid, EmptyState } from '../components/StateViews';
import type { PageId } from '../App';

function ndviStatus(v: number) {
  return v>=0.70 ? 'excellent' : v>=0.50 ? 'good' : v>=0.30 ? 'fair' : 'poor';
}

export default function DashboardPage({ setPage }: { setPage: (p: PageId) => void }) {
  const { data: dashboard, isLoading: loadDash, refetch } = useDashboardData();
  const { data: weatherData } = useWeatherForecast();
  const { data: alertsData } = useAlerts();
  const { data: natsData } = useAllServicesHealth();

  const kpis   = dashboard?.kpis           || [];
  const fields  = Array.isArray(dashboard?.fields_summary) ? dashboard.fields_summary : [];
  // alertsData هو AlertRecord[] من sahool-platform (v36). حارس Array.isArray يمنع انهيار
  // alerts.slice(...).map لو رجعت الاستجابة بصيغة غير متوقّعة (كائن/نصّ بدل مصفوفة).
  const alerts  = Array.isArray(alertsData)
    ? alertsData
    : Array.isArray(dashboard?.alerts) ? dashboard.alerts : [];
  const weather = weatherData?.current;
  // natsData is a ServiceHealth[]; these aggregate fields are read defensively
  // (undefined at runtime) — typed via a narrow optional shape to match usage.
  const natsInfo = natsData as unknown as { nats_connected?: boolean; events_processed?: number } | undefined;
  const natsOk  = natsInfo?.nats_connected ?? false;

  // Inject live temperature
  const enrichedKpis = kpis.map((k: any) =>
    k.id === 'temperature' && weather ? { ...k, value: weather.tmean } : k
  );

  const barData = fields.map((f: any) => ({
    name: (f.field_name||'').replace('حقل ','').substring(0,7),
    ndvi: +(f.ndvi||0),
  }));

  if (loadDash && kpis.length === 0)
    return <LoadingState message="جارٍ تحميل البيانات من indicators-service…" />;

  return (
    <div className="space-y-6 max-w-7xl mx-auto" dir="rtl">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">لوحة المعلومات</h2>
          <p className="text-sm text-slate-400">
            {dashboard?.total_fields||8} حقل · {dashboard?.total_indicators||33} مؤشر · {dashboard?.active_alerts||0} تنبيه
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-[11px] border ${natsOk ? 'bg-emerald-950 text-emerald-400 border-emerald-900' : 'bg-slate-800 text-slate-500 border-slate-700'}`}>
            {natsOk ? <Wifi className="w-3 h-3"/> : <WifiOff className="w-3 h-3"/>}
            NATS {natsOk ? `✓ (${natsInfo?.events_processed||0})` : 'offline'}
          </span>
          <button onClick={() => refetch()} className="p-2 rounded-lg hover:bg-slate-800 text-slate-400">
            <RefreshCw className={`w-4 h-4 ${loadDash ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Live weather */}
      {weather && (
        <div className="grid grid-cols-5 gap-2 rounded-xl p-3 border" style={{ background:'#172032', borderColor:'#1e3a4a' }}>
          {[
            { label:'الحرارة', val:`${weather.tmean}°C`, color:'#f97316' },
            { label:'الرطوبة', val:`${weather.humidity_pct}%`, color:'#38bdf8' },
            { label:'الرياح', val:`${weather.wind_speed_kmh}كم/س`, color:'#94a3b8' },
            { label:'ET0', val:`${weather.et0_mm}mm`, color:'#0ea5e9' },
            { label:'GDD', val:`${weather.gdd}`, color:'#16a34a' },
          ].map((w,i) => (
            <div key={i} className="text-center">
              <div className="font-bold text-sm" style={{ color:w.color }}>{w.val}</div>
              <div className="text-[10px] text-slate-500">{w.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* KPIs */}
      {enrichedKpis.length > 0 ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {enrichedKpis.map((k: any) => <KPICard key={k.id} kpi={k} />)}
        </div>
      ) : (
        <SkeletonGrid count={6} />
      )}

      {/* NDVI Chart + Alerts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-semibold text-slate-200">NDVI — الحقول الثمانية</span>
            <span className="text-[10px] text-slate-500 mr-auto">
              {dashboard?.data_freshness?.source || 'sentinel2+wofost+iot'}
            </span>
          </div>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={barData.length > 0 ? barData : Array(8).fill({name:'—',ndvi:0.5})} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" tick={{ fill:'#64748b', fontSize:10 }} tickLine={false} />
              <YAxis domain={[0,1]} tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }} itemStyle={{ color:'#e2e8f0' }} />
              <Bar dataKey="ndvi" name="NDVI" radius={[4,4,0,0]}>
                {barData.map((_: any, i: number) => (
                  <Cell key={i} fill={STATUS_COLOR[ndviStatus(barData[i]?.ndvi||0)]||'#6b7280'} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Alerts panel */}
        <div className="rounded-xl p-4 border flex flex-col gap-3" style={{ background:'#1e293b', borderColor:'#334155' }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-semibold text-slate-200">التنبيهات</span>
            </div>
            <button onClick={() => setPage('alerts')} className="text-xs text-emerald-400">الكل</button>
          </div>
          {alerts.slice(0,3).map((a: any) => {
            const color = a.severity === 'critical' ? '#dc2626' : a.severity === 'warning' ? '#f59e0b' : a.color || '#38bdf8';
            return (
              <div key={a.alert_id || a.id} className="rounded-lg p-3 cursor-pointer" style={{ background:`${color}11`, border:`1px solid ${color}33` }}
                onClick={() => setPage('alerts')}>
                <div className="flex justify-between mb-1">
                  <span className="text-xs font-semibold" style={{ color }}>{a.title_ar || a.field_id || a.field_name || a.field || 'تنبيه'}</span>
                  <span className="text-[10px] text-slate-500">{(a.created_at || a.timestamp) ? new Date(a.created_at || a.timestamp).toLocaleTimeString('ar-SA',{hour:'2-digit',minute:'2-digit'}) : ''}</span>
                </div>
                <p className="text-xs text-slate-300">{a.message_ar || a.message}</p>
              </div>
            );
          })}
          {alerts.length === 0 && (
            <EmptyState icon={<span className="text-2xl">✅</span>} title="لا توجد تنبيهات" />
          )}
        </div>
      </div>

      {/* Fields mini-grid */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Map className="w-4 h-4 text-emerald-400" />
            <span className="text-sm font-semibold text-slate-200">ملخص الحقول</span>
          </div>
          <button onClick={() => setPage('fields')} className="text-xs text-emerald-400 flex items-center gap-1">
            إدارة <ChevronLeft className="w-3 h-3" />
          </button>
        </div>
        {fields.length === 0 ? (
          // لا حقول حقيقيّة ⇒ حالة فارغة صادقة بدل ٨ بطاقات وهميّة (NDVI=0.5 مُلفَّق).
          <div className="text-center py-6 text-slate-400 text-sm">
            لا توجد حقول مُسجّلة بعد.
            <button onClick={() => setPage('fields')} className="text-emerald-400 mr-1 underline">أضِف حقلاً</button>
            لعرض ملخّص المؤشّرات.
          </div>
        ) : (
          <div className="grid grid-cols-4 sm:grid-cols-8 gap-2">
            {fields.map((f: any) => {
              const ndvi = f.ndvi || 0;
              const c = STATUS_COLOR[ndviStatus(ndvi)];
              return (
                <button key={f.field_id} onClick={() => setPage('satellite')}
                  className="rounded-xl p-2 border hover:border-emerald-800 transition-all text-center"
                  style={{ background:'#1e293b', borderColor:'#334155' }}>
                  <div className="text-sm font-bold" style={{ color:c }}>{ndvi.toFixed(2)}</div>
                  <div className="h-1 rounded-full my-1.5" style={{ background:'#334155' }}>
                    <div className="h-full rounded-full" style={{ width:`${ndvi*100}%`, background:c }} />
                  </div>
                  <div className="text-[9px] text-slate-400 truncate">{(f.field_name||'').replace('حقل ','').substring(0,6)}</div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {([
          { label:'تحليل NDVI',    icon:Leaf,         page:'satellite'    , color:'#16a34a' },
          { label:'المؤشرات 17',  icon:BarChart3,     page:'hybrid-index' , color:'#8b5cf6' },
          { label:'التنبيهات',     icon:AlertTriangle, page:'alerts'       , color:'#f59e0b' },
          { label:'المستشار الذكي',icon:Zap,           page:'chatbot'      , color:'#38bdf8' },
        ] as const).map(a => {
          const Icon = a.icon;
          return (
            <button key={a.label} onClick={() => setPage(a.page as PageId)}
              className="flex items-center gap-3 p-3 rounded-xl border transition-all hover:scale-[1.02]"
              style={{ background:`${a.color}11`, borderColor:`${a.color}33`, color:a.color }}>
              <Icon className="w-5 h-5" />
              <span className="text-sm font-medium">{a.label}</span>
            </button>
          );
        })}
      </div>

      {dashboard?.generated_at && (
        <p className="text-center text-[10px] text-slate-600">
          آخر تحديث: {new Date(dashboard.generated_at).toLocaleString('ar-SA')} ·
          مصدر البيانات: {dashboard.data_freshness?.source || 'indicators-service'}
        </p>
      )}
    </div>
  );
}
