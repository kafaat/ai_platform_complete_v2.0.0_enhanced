// ═══════════════════════════════════════════════════════════════
// SAHOOL v8.0 — ReportsPage
// ملخّص التكلفة الآن حيّ (useCostAnalytics → /api/v1/analytics/costs):
// إجماليّ التكلفة + التوزيع حسب المصدر + عدد المهام، مُقيَّد بالدور والمستأجِر.
// لا أرقام مُلفَّقة — عند الخطأ/الفراغ تُعرض حالة صادقة (StateViews).
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import { Download, BarChart3, DollarSign, ListChecks, Wallet } from 'lucide-react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, BarChart, Bar } from 'recharts';
import { useCostAnalytics } from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

const FIELDS = ['جميع الحقول','حقل وادي سبأ','حقل البيضاء الشمالي','حقل رداع الغربي'];

const MONTHLY_DATA = [
  { month:'يناير',  ndvi:0.52, yield:2.1, rain:12 },
  { month:'فبراير', ndvi:0.55, yield:2.4, rain:18 },
  { month:'مارس',   ndvi:0.61, yield:2.8, rain:32 },
  { month:'أبريل',  ndvi:0.68, yield:3.2, rain:42 },
  { month:'مايو',   ndvi:0.72, yield:3.5, rain:28 },
  { month:'يونيو',  ndvi:0.70, yield:3.3, rain:8  },
];

// أسماء عربية لمصادر التكلفة القادمة من الخادم (fallback: اسم المصدر كما هو).
const SOURCE_LABELS: Record<string, string> = {
  field_tasks: 'المهام الميدانية',
  maintenance: 'الصيانة',
};

const usd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n ?? 0);

function exportToCSV(data: any[], filename: string) {
  const headers = Object.keys(data[0]).join(',');
  const rows = data.map(r => Object.values(r).join(','));
  const csv = '﻿' + [headers, ...rows].join('\n');
  const blob = new Blob([csv], { type:'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
}

function CostSummary() {
  const { data, isLoading, isError, error, refetch } = useCostAnalytics();

  if (isLoading) return <LoadingState message="جارٍ تحميل ملخّص التكلفة…" />;
  if (isError) {
    const status = (error as any)?.response?.status;
    const detail = status === 503
      ? 'خدمة التحليلات غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
      : status === 403
        ? 'لا تملك صلاحية عرض التحليلات (analytics:view).'
        : 'تعذّر الاتصال بخدمة التحليلات.';
    return <ErrorState title="تعذّر تحميل ملخّص التكلفة" detail={detail} onRetry={() => refetch()} />;
  }

  const bySource = data?.by_source ?? [];
  const totalUsd = data?.total_usd ?? 0;
  const taskCount = data?.task_count ?? 0;

  if (bySource.length === 0 && totalUsd === 0 && taskCount === 0) {
    return (
      <EmptyState
        icon={<Wallet className="w-8 h-8" />}
        title="لا توجد بيانات تكلفة بعد"
        hint="لم تُسجَّل أي تكاليف للمهام حتى الآن."
      />
    );
  }

  const chartData = bySource.map(s => ({
    source: SOURCE_LABELS[s.source] ?? s.source,
    total_usd: s.total_usd,
  }));

  return (
    <div className="space-y-3">
      {/* إجماليّات حيّة */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {[
          { label:'إجماليّ التكلفة', val:usd(totalUsd),                  icon:DollarSign, color:'#f59e0b' },
          { label:'عدد المهام',      val:taskCount.toLocaleString('en-US'), icon:ListChecks, color:'#38bdf8' },
          { label:'مصادر التكلفة',   val:bySource.length.toLocaleString('en-US'), icon:BarChart3, color:'#a855f7' },
        ].map((k, i) => {
          const Icon = k.icon;
          return (
            <div key={i} className="rounded-xl p-3 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
              <Icon className="w-4 h-4 mb-1" style={{ color:k.color }} />
              <div className="text-lg font-bold" style={{ color:k.color }}>{k.val}</div>
              <div className="text-[10px] text-slate-400">{k.label}</div>
            </div>
          );
        })}
      </div>

      {/* التوزيع حسب المصدر */}
      {bySource.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <div className="flex items-center justify-between mb-3">
              <span className="text-sm font-semibold text-slate-200">التكلفة حسب المصدر (USD)</span>
              <button onClick={() => exportToCSV(chartData, 'SAHOOL_Cost_By_Source.csv')}
                className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300">
                <Download className="w-3 h-3" /> CSV
              </button>
            </div>
            <ResponsiveContainer width="100%" height={160}>
              <BarChart data={chartData} barSize={28}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="source" tick={{ fill:'#64748b', fontSize:10 }} tickLine={false} />
                <YAxis tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={44} />
                <Tooltip
                  contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }}
                  itemStyle={{ color:'#e2e8f0' }}
                  formatter={(v: any) => [usd(Number(v)), 'التكلفة']}
                />
                <Bar dataKey="total_usd" fill="#f59e0b" radius={[4,4,0,0]} name="التكلفة" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
            <span className="text-sm font-semibold text-slate-200">تفصيل المصادر</span>
            <ul className="mt-3 space-y-2">
              {bySource.map((s, i) => {
                const pct = totalUsd > 0 ? (s.total_usd / totalUsd) * 100 : 0;
                return (
                  <li key={i} className="flex items-center justify-between text-sm">
                    <span className="text-slate-300">{SOURCE_LABELS[s.source] ?? s.source}</span>
                    <span className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-500">{pct.toFixed(0)}%</span>
                      <span className="font-semibold text-amber-400">{usd(s.total_usd)}</span>
                    </span>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

export function ReportsPage() {
  const [field, setField] = useState(FIELDS[0]);
  const [period, setPeriod] = useState('30d');

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">التقارير</h2>
          <p className="text-sm text-slate-400">تقارير دورية شاملة للمزرعة</p>
        </div>
        <div className="flex gap-2">
          <select value={field} onChange={e => setField(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm" style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }}>
            {FIELDS.map(f => <option key={f}>{f}</option>)}
          </select>
          <select value={period} onChange={e => setPeriod(e.target.value)}
            className="px-3 py-2 rounded-lg text-sm" style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0' }}>
            {['7d','30d','90d','1y'].map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      {/* ملخّص التكلفة — بيانات حيّة من /api/v1/analytics/costs */}
      <div className="rounded-xl p-4 border" style={{ background:'#0f1117', borderColor:'#334155' }}>
        <div className="flex items-center gap-2 mb-3">
          <Wallet className="w-4 h-4 text-amber-400" />
          <span className="text-sm font-semibold text-slate-200">ملخّص التكلفة</span>
        </div>
        <CostSummary />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-200">اتجاه NDVI الشهري</span>
            <button onClick={() => exportToCSV(MONTHLY_DATA, 'SAHOOL_NDVI_Report.csv')}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300">
              <Download className="w-3 h-3" /> CSV
            </button>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <AreaChart data={MONTHLY_DATA}>
              <defs>
                <linearGradient id="gNdvi" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#16a34a" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="#16a34a" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="month" tick={{ fill:'#64748b', fontSize:10 }} tickLine={false} />
              <YAxis domain={[0.3,0.9]} tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={32} />
              <Tooltip contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }} itemStyle={{ color:'#e2e8f0' }} />
              <Area type="monotone" dataKey="ndvi" stroke="#16a34a" strokeWidth={2} fill="url(#gNdvi)" name="NDVI" />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="rounded-xl p-4 border" style={{ background:'#1e293b', borderColor:'#334155' }}>
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-semibold text-slate-200">الإنتاجية الشهرية (t/ha)</span>
            <button onClick={() => exportToCSV(MONTHLY_DATA, 'SAHOOL_Yield_Report.csv')}
              className="flex items-center gap-1 text-xs text-purple-400 hover:text-purple-300">
              <Download className="w-3 h-3" /> CSV
            </button>
          </div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={MONTHLY_DATA} barSize={28}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="month" tick={{ fill:'#64748b', fontSize:10 }} tickLine={false} />
              <YAxis domain={[0,5]} tick={{ fill:'#64748b', fontSize:11 }} tickLine={false} width={28} />
              <Tooltip contentStyle={{ background:'#0f1117', border:'1px solid #334155', borderRadius:8, fontSize:12 }} itemStyle={{ color:'#e2e8f0' }} />
              <Bar dataKey="yield" fill="#8b5cf6" radius={[4,4,0,0]} name="الإنتاجية" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Report buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {[
          { label:'تقرير أسبوعي',  icon:'📅', desc:'ملخص آخر 7 أيام', color:'#16a34a' },
          { label:'تقرير شهري',    icon:'📊', desc:'تقرير مفصل شامل', color:'#8b5cf6' },
          { label:'تقرير WOFOST',  icon:'🌾', desc:'محاكاة موسم كامل', color:'#f59e0b' },
        ].map((r, i) => (
          <button key={i}
            onClick={() => exportToCSV(MONTHLY_DATA, `SAHOOL_${r.label}.csv`)}
            className="flex items-center gap-3 p-4 rounded-xl border transition-all hover:scale-[1.02] text-right"
            style={{ background:'#1e293b', borderColor:`${r.color}33` }}>
            <span className="text-2xl">{r.icon}</span>
            <div>
              <div className="font-semibold text-slate-100 text-sm">{r.label}</div>
              <div className="text-xs text-slate-400">{r.desc}</div>
            </div>
            <Download className="w-4 h-4 mr-auto" style={{ color:r.color }} />
          </button>
        ))}
      </div>
    </div>
  );
}
export default ReportsPage;
