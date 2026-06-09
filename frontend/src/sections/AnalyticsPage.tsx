// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — AnalyticsPage
// رسوم بيانية: إنتاجية + NDVI + رطوبة + radar المؤشرات
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  AreaChart, Area, LineChart, Line, BarChart, Bar, RadarChart,
  PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Cell,
} from 'recharts';
import { TrendingUp, BarChart3, Activity, Droplets, Calendar } from 'lucide-react';

const YIELD_DATA = [
  { month:'يناير', predicted:4.2, actual:null },
  { month:'فبراير', predicted:4.8, actual:null },
  { month:'مارس',   predicted:5.5, actual:null },
  { month:'أبريل',  predicted:6.2, actual:5.8  },
  { month:'مايو',   predicted:6.8, actual:6.5  },
  { month:'يونيو',  predicted:7.1, actual:7.0  },
  { month:'يوليو',  predicted:7.3, actual:null },
  { month:'أغسطس',  predicted:7.0, actual:null },
  { month:'سبتمبر', predicted:6.5, actual:null },
  { month:'أكتوبر', predicted:5.8, actual:null },
  { month:'نوفمبر', predicted:4.5, actual:null },
  { month:'ديسمبر', predicted:3.8, actual:null },
];

const MOISTURE_ZONES = [
  { zone:'منطقة 1', moisture:78, color:'#16a34a' },
  { zone:'منطقة 2', moisture:62, color:'#65a30d' },
  { zone:'منطقة 3', moisture:45, color:'#ca8a04' },
  { zone:'منطقة 4', moisture:28, color:'#dc2626' },
  { zone:'منطقة 5', moisture:85, color:'#16a34a' },
];

const NDVI_SERIES = Array.from({length:24},(_,i) => ({
  week:`أسبوع ${i+1}`,
  ndvi:+(0.45+Math.sin(i/5)*0.15+Math.random()*0.05).toFixed(3),
  threshold:0.5,
}));

const RADAR_DATA = [
  { subject:'NDVI', A:72, fullMark:100 },
  { subject:'WUE',  A:68, fullMark:100 },
  { subject:'تربة', A:80, fullMark:100 },
  { subject:'إنتاج',A:65, fullMark:100 },
  { subject:'صحة',  A:75, fullMark:100 },
  { subject:'استدامة',A:70,fullMark:100 },
];

const FIELD_OPTIONS = [
  'حقل وادي سبأ','حقل البيضاء الشمالي','حقل رداع الغربي','حقل ذي السفال',
];

function ChartCard({ title, icon: Icon, children }: any) {
  return (
    <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">{title}</span>
      </div>
      {children}
    </div>
  );
}

export default function AnalyticsPage() {
  const [selectedField, setSelectedField] = useState(FIELD_OPTIONS[0]);
  const [period, setPeriod] = useState('6m');

  return (
    <div className="space-y-5 max-w-7xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">التحليلات المتقدمة</h2>
          <p className="text-sm text-slate-400">رؤى زراعية مبنية على WOFOST + Sentinel-2</p>
        </div>
        <div className="flex gap-2">
          <select value={selectedField} onChange={e => setSelectedField(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm" style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }}>
            {FIELD_OPTIONS.map(f => <option key={f}>{f}</option>)}
          </select>
          <div className="flex rounded-lg overflow-hidden border border-slate-700">
            {['3m','6m','1y'].map(p => (
              <button key={p} onClick={() => setPeriod(p)}
                className="px-3 py-1.5 text-sm transition-colors"
                style={{ background:period===p ? '#1e3a1e' : 'transparent', color:period===p ? '#4ade80' : '#64748b' }}>
                {p}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ChartCard title="توقع الإنتاجية (طن/هـ)" icon={TrendingUp}>
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={YIELD_DATA}>
              <defs>
                <linearGradient id="gPred" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#8b5cf6" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="gAct" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#16a34a" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#16a34a" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="month" tick={{ fill:'#64748b', fontSize:10 }} tickLine={false} />
              <YAxis domain={[3,8]} tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }} itemStyle={{ color:'#e2e8f0' }} />
              <Area type="monotone" dataKey="predicted" stroke="#8b5cf6" strokeWidth={2} fill="url(#gPred)" name="متوقع" />
              <Area type="monotone" dataKey="actual" stroke="#16a34a" strokeWidth={2} fill="url(#gAct)" name="فعلي" />
            </AreaChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="اتجاه NDVI الأسبوعي" icon={Activity}>
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={NDVI_SERIES.slice(0,16)}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="week" tick={{ fill:'#64748b', fontSize:9 }} tickLine={false} interval={3} />
              <YAxis domain={[0.2,0.9]} tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={32} />
              <Tooltip contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }} itemStyle={{ color:'#e2e8f0' }} />
              <Line type="monotone" dataKey="ndvi" stroke="#16a34a" strokeWidth={2} dot={false} name="NDVI" />
              <Line type="monotone" dataKey="threshold" stroke="#dc2626" strokeWidth={1} strokeDasharray="4 2" dot={false} name="الحد الأدنى" />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="توزيع رطوبة التربة بالمناطق" icon={Droplets}>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={MOISTURE_ZONES} barSize={36}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="zone" tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} />
              <YAxis domain={[0,100]} tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={28} unit="%" />
              <Tooltip contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }} itemStyle={{ color:'#e2e8f0' }} />
              <Bar dataKey="moisture" name="الرطوبة %" radius={[6,6,0,0]}>
                {MOISTURE_ZONES.map((m, i) => <Cell key={i} fill={m.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="مؤشر الصحة الزراعية المركّب" icon={BarChart3}>
          <ResponsiveContainer width="100%" height={180}>
            <RadarChart data={RADAR_DATA}>
              <PolarGrid stroke="#334155" />
              <PolarAngleAxis dataKey="subject" tick={{ fill:'#94a3b8', fontSize:11 }} />
              <PolarRadiusAxis domain={[0,100]} tick={{ fill:'#475569', fontSize:9 }} />
              <Radar name={selectedField} dataKey="A" stroke="#16a34a" fill="#16a34a" fillOpacity={0.25} strokeWidth={2} />
            </RadarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* AI Insights */}
      <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
        <div className="flex items-center gap-2 mb-3">
          <span className="text-emerald-400 text-base">🤖</span>
          <span className="text-sm font-semibold text-slate-200">رؤى AI مبنية على WOFOST + Sentinel-2</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { emoji:'🌾', title:'توقع الحصاد', body:'استناداً إلى GDD=960 و NDVI=0.72، يُتوقع حصاد القمح خلال 18-22 يوماً بإنتاجية 2.8 t/ha.' },
            { emoji:'💧', title:'توصية الري', body:'ET0 اليومي 4.2mm والرطوبة 16% — ري 30mm صباح اليوم للحقل الشمالي.' },
            { emoji:'⚠️', title:'تحذير مبكر', body:'حقل عتمة الشرقي: NDVI انخفض 0.08 خلال أسبوعين — فحص فوري للتربة موصى به.' },
          ].map((ins, i) => (
            <div key={i} className="rounded-lg p-3" style={{ background:'#0f1117', border:'1px solid #334155' }}>
              <div className="text-xl mb-1">{ins.emoji}</div>
              <div className="text-sm font-semibold text-slate-100 mb-1">{ins.title}</div>
              <p className="text-xs text-slate-400 leading-relaxed">{ins.body}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
