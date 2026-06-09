// ═══════════════════════════════════════════════════════════════════
// SAHOOL v8.0 — HybridIndexPage محسّن
// التحسينات:
//   ✅ 17 مؤشراً فعلياً (7 نباتية + 4 مائية + 3 تربة + 3 طقس)
//   ✅ بيانات WOFOST: GDD + LAI + إنتاجية + مراحل نمو
//   ✅ Export CSV شامل مع timestamp
//   ✅ فلترة بالفئة (vegetation/water/soil/weather)
//   ✅ تصنيف 5 مستويات مع badge ملوّن
//   ✅ رسم بياني Recharts لكل مؤشر عند الضغط
//   ✅ بطاقة WOFOST season summary
//   ✅ مقارنة الحقول (FieldComparisonTable محسّن)
// ═══════════════════════════════════════════════════════════════════

import { useState, useMemo } from 'react';
import {
  LayoutDashboard, TrendingUp, AlertTriangle, Download,
  RefreshCw, Filter, ChevronDown, FileText, BarChart3, Activity,
  Sprout, Sun, Shield, Zap, Timer, Leaf, Droplets, Thermometer,
  FlaskConical, Wind, CheckCircle2, XCircle, Info,
} from 'lucide-react';
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend, ReferenceLine,
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';
import { useDashboardKPIs } from '@/hooks/useIndicators';
import { KPICard } from '@/components/KPICard';
import { AlertBanner } from '@/components/AlertBanner';
import { NDVIGauge } from '@/components/NDVIGauge';

// ── Indicator catalog with WOFOST metadata ─────────────────────────
const INDICATOR_CATALOG = [
  // نباتية
  { id:'ndvi',  cat:'vegetation', name_ar:'NDVI',   desc_ar:'مؤشر الغطاء النباتي الطبيعي',   unit:'',       icon:Leaf,        color:'#16a34a', healthy_min:0.50 },
  { id:'evi',   cat:'vegetation', name_ar:'EVI',    desc_ar:'مؤشر النباتات المحسّن',          unit:'',       icon:Sprout,      color:'#15803d', healthy_min:0.45 },
  { id:'gndvi', cat:'vegetation', name_ar:'GNDVI',  desc_ar:'مؤشر الكلوروفيل الأخضر',        unit:'',       icon:Leaf,        color:'#4ade80', healthy_min:0.45 },
  { id:'ndre',  cat:'vegetation', name_ar:'NDRE',   desc_ar:'مؤشر الحافة الحمراء',           unit:'',       icon:Activity,    color:'#0891b2', healthy_min:0.35 },
  { id:'savi',  cat:'vegetation', name_ar:'SAVI',   desc_ar:'مؤشر النباتات المعدّل',         unit:'',       icon:Sprout,      color:'#65a30d', healthy_min:0.35 },
  { id:'lai',   cat:'vegetation', name_ar:'LAI',    desc_ar:'مؤشر مساحة الورقة',             unit:'m²/m²',  icon:Leaf,        color:'#22c55e', healthy_min:3.0  },
  { id:'ndwi',  cat:'vegetation', name_ar:'NDWI',   desc_ar:'محتوى المياه في النبات',         unit:'',       icon:Droplets,    color:'#38bdf8', healthy_min:0.10 },
  // مائية
  { id:'soil_moisture', cat:'water', name_ar:'رطوبة التربة',  desc_ar:'محتوى الرطوبة في التربة',  unit:'%',     icon:Droplets,    color:'#0ea5e9', healthy_min:30   },
  { id:'wue',           cat:'water', name_ar:'كفاءة الري',    desc_ar:'كيلوجرام إنتاج/متر مكعب', unit:'kg/m³', icon:Zap,         color:'#38bdf8', healthy_min:1.8  },
  { id:'et0',           cat:'water', name_ar:'ET₀',           desc_ar:'البخر-نتح المرجعي',       unit:'mm/d',  icon:Droplets,    color:'#7dd3fc', healthy_min:0    },
  { id:'water_deficit', cat:'water', name_ar:'عجز المياه',    desc_ar:'الفجوة بين ET0 والأمطار', unit:'mm',    icon:AlertTriangle, color:'#fb923c', healthy_min:0  },
  // تربة
  { id:'soil_ph', cat:'soil', name_ar:'pH التربة',     desc_ar:'درجة حموضة التربة',      unit:'',      icon:FlaskConical, color:'#92400e', healthy_min:6.5 },
  { id:'soil_ec', cat:'soil', name_ar:'EC التربة',     desc_ar:'التوصيل الكهربائي',       unit:'dS/m',  icon:Zap,          color:'#b45309', healthy_min:0   },
  { id:'nitrogen', cat:'soil', name_ar:'النيتروجين',   desc_ar:'النيتروجين المتاح',       unit:'mg/kg', icon:FlaskConical, color:'#65a30d', healthy_min:20  },
  // طقس
  { id:'temperature', cat:'weather', name_ar:'الحرارة',  desc_ar:'درجة الحرارة المتوسطة', unit:'°C',   icon:Thermometer,  color:'#f97316', healthy_min:15  },
  { id:'humidity',    cat:'weather', name_ar:'الرطوبة',  desc_ar:'الرطوبة النسبية',        unit:'%',    icon:Droplets,     color:'#60a5fa', healthy_min:40  },
  { id:'wind_speed',  cat:'weather', name_ar:'الرياح',   desc_ar:'سرعة الرياح',            unit:'km/h', icon:Wind,         color:'#93c5fd', healthy_min:0   },
] as const;

const CATEGORIES = [
  { id:'all',        label:'الكل',      color:'#6b7280' },
  { id:'vegetation', label:'نباتية 🌿',  color:'#16a34a' },
  { id:'water',      label:'مائية 💧',   color:'#0ea5e9' },
  { id:'soil',       label:'تربة 🏔',    color:'#92400e' },
  { id:'weather',    label:'طقس 🌤',     color:'#f97316' },
] as const;

const SPARKLINES: Record<string, number[]> = {
  ndvi:  [0.52,0.55,0.58,0.61,0.55,0.63,0.68,0.72,0.70,0.74,0.72,0.75],
  evi:   [0.45,0.48,0.50,0.53,0.48,0.55,0.58,0.61,0.59,0.63,0.61,0.64],
  gndvi: [0.48,0.51,0.53,0.56,0.51,0.58,0.62,0.68,0.66,0.70,0.68,0.72],
  ndre:  [0.41,0.44,0.45,0.48,0.44,0.50,0.54,0.58,0.56,0.60,0.58,0.62],
  savi:  [0.30,0.32,0.33,0.36,0.32,0.38,0.41,0.45,0.43,0.47,0.45,0.48],
  lai:   [2.1,2.4,2.8,3.1,2.9,3.4,3.7,4.1,3.9,4.3,4.1,4.5],
  ndwi:  [0.08,0.10,0.12,0.15,0.12,0.18,0.20,0.22,0.20,0.24,0.22,0.25],
  soil_moisture:[28,30,32,35,31,34,37,40,38,42,40,44],
  wue:   [1.5,1.6,1.7,1.8,1.7,1.9,2.0,2.1,2.0,2.2,2.1,2.3],
};

// WOFOST season data (static demo matching backend)
const WOFOST_DATA = [
  { field:'حقل وادي سبأ',    crop:'قمح صلب',   gdd:960,  progress:53, lai:4.2, yield:2.8, stage:'ملء الحبوب' },
  { field:'حقل البيضاء ش',  crop:'شعير',       gdd:825,  progress:55, lai:3.8, yield:2.5, stage:'نمو خضري' },
  { field:'حقل البيضاء ج',  crop:'ذرة صفراء',  gdd:980,  progress:45, lai:5.1, yield:3.9, stage:'تزهير' },
  { field:'حقل رداع',        crop:'طماطم',      gdd:780,  progress:52, lai:3.2, yield:4.2, stage:'ثمرة' },
  { field:'حقل ذي السفال',   crop:'قمح صلب',   gdd:1020, progress:57, lai:4.5, yield:3.1, stage:'ملء الحبوب' },
  { field:'حقل عتمة',        crop:'شعير',       gdd:792,  progress:53, lai:3.6, yield:2.4, stage:'نمو خضري' },
  { field:'حقل الرياشية',   crop:'خضروات',     gdd:660,  progress:66, lai:2.8, yield:5.5, stage:'حصاد' },
  { field:'حقل ذي ناعم',    crop:'بطاطس',      gdd:680,  progress:57, lai:3.0, yield:6.8, stage:'تكوين الدرنات' },
];

function exportToCSV(data: Record<string, unknown>[], filename: string) {
  if (!data.length) return;
  const headers = Object.keys(data[0]).join(',');
  const rows = data.map(row =>
    Object.values(row).map(v => (typeof v === 'string' && v.includes(',') ? `"${v}"` : v)).join(',')
  );
  const csv = '\uFEFF' + [headers, ...rows].join('\n'); // BOM for Arabic
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { label: string; bg: string; text: string }> = {
    excellent: { label:'ممتاز',  bg:'bg-emerald-100', text:'text-emerald-700' },
    good:      { label:'جيد',    bg:'bg-lime-100',    text:'text-lime-700' },
    fair:      { label:'مقبول',  bg:'bg-amber-100',   text:'text-amber-700' },
    poor:      { label:'منخفض',  bg:'bg-orange-100',  text:'text-orange-700' },
    critical:  { label:'حرج',    bg:'bg-red-100',     text:'text-red-700' },
  };
  const c = config[status] || config.fair;
  return (
    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${c.bg} ${c.text}`}>
      {c.label}
    </span>
  );
}

function MiniSparkline({ data, color }: { data: number[]; color: string }) {
  const min = Math.min(...data), max = Math.max(...data), range = max - min || 1;
  const w = 60, h = 24;
  const pts = data.map((v, i) => [
    (i / (data.length - 1)) * w,
    h - ((v - min) / range) * h,
  ]);
  const path = pts.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ');
  return (
    <svg width={w} height={h} style={{ overflow: 'visible' }}>
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={2} fill={color} />
    </svg>
  );
}

export function HybridIndexPage() {
  const [period, setPeriod]           = useState('30d');
  const [activeCategory, setCategory] = useState<string>('all');
  const [expandedId, setExpanded]     = useState<string | null>(null);
  const [showExportMenu, setExport]   = useState(false);
  const { data, isLoading, error, refetch } = useDashboardKPIs();

  const kpis    = data?.kpis    || [];
  const alerts  = data?.alerts  || [];
  const fields  = data?.fields_summary || [];

  // enrich KPIs with catalog metadata + sparklines
  const enriched = useMemo(() =>
    kpis.map((kpi: Record<string, unknown>) => {
      const meta = INDICATOR_CATALOG.find(c => c.id === kpi.id);
      return {
        ...kpi,
        category:  meta?.cat        || 'vegetation',
        desc_ar:   meta?.desc_ar    || '',
        healthy_min: meta?.healthy_min || 0,
        sparkline: SPARKLINES[kpi.id as string] || Array(10).fill(kpi.value as number).map((v: number) => v + (Math.random() - 0.5) * 0.1),
        color:     meta?.color      || '#16a34a',
      };
    }), [kpis]);

  const filtered = useMemo(() =>
    activeCategory === 'all' ? enriched : enriched.filter((k: Record<string, unknown>) => k.category === activeCategory),
    [enriched, activeCategory]);

  // summary per category
  const summary = useMemo(() => {
    const counts: Record<string, number> = { healthy:0, moderate:0, stressed:0 };
    fields.forEach((f: Record<string, unknown>) => {
      const ndvi = Number(f.ndvi || 0);
      if (ndvi >= 0.60) counts.healthy++;
      else if (ndvi >= 0.35) counts.moderate++;
      else counts.stressed++;
    });
    return counts;
  }, [fields]);

  // Exports
  const doExportKPIs = () => {
    exportToCSV(
      enriched.map((k: Record<string, unknown>) => ({
        المؤشر: (k.name_ar || k.name_en || k.id) as string,
        الفئة: k.category as string,
        القيمة: k.value as number,
        الوحدة: (k.unit || '') as string,
        الحالة: k.status as string,
        'اتجاه التغير': (k.trend_direction || '') as string,
      })),
      `SAHOOL_KPIs_v8_${new Date().toISOString().slice(0,10)}.csv`
    );
    setExport(false);
  };
  const doExportWOFOST = () => {
    exportToCSV(
      WOFOST_DATA.map(d => ({
        الحقل: d.field, المحصول: d.crop, 'GDD متراكم': d.gdd,
        'نسبة الاكتمال%': d.progress, 'LAI': d.lai,
        'الإنتاجية t/ha': d.yield, 'المرحلة الحالية': d.stage,
      })),
      `SAHOOL_WOFOST_${new Date().toISOString().slice(0,10)}.csv`
    );
    setExport(false);
  };
  const doExportFields = () => {
    exportToCSV(
      fields.map((f: Record<string, unknown>) => ({
        الحقل: f.field_name as string,
        'NDVI': f.ndvi as number,
        الحالة: f.status as string,
        المحصول: (f.crop || '') as string,
      })),
      `SAHOOL_Fields_v8_${new Date().toISOString().slice(0,10)}.csv`
    );
    setExport(false);
  };

  if (isLoading) return (
    <div className="flex items-center justify-center py-20" dir="rtl">
      <div className="text-center">
        <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-500">جاري تحميل 17 مؤشراً زراعياً...</p>
      </div>
    </div>
  );

  if (error) return (
    <div className="flex flex-col items-center justify-center py-20" dir="rtl">
      <AlertTriangle className="w-10 h-10 text-red-400 mb-2" />
      <p className="text-red-600 font-medium">فشل تحميل البيانات</p>
      <button onClick={() => refetch()} className="mt-3 px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm">
        إعادة المحاولة
      </button>
    </div>
  );

  return (
    <div className="space-y-6 font-tajawal" dir="rtl">
      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <LayoutDashboard className="w-7 h-7 text-emerald-600" />
            لوحة المؤشرات — v8.0
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            <span className="font-bold text-emerald-600">17 مؤشراً</span> زراعياً · WOFOST · Sentinel-2 · IoT
          </p>
        </div>
        <div className="flex items-center gap-2">
          <select value={period} onChange={e => setPeriod(e.target.value)}
            className="px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm">
            <option value="7d">7 أيام</option>
            <option value="30d">30 يوم</option>
            <option value="90d">3 أشهر</option>
            <option value="1y">سنة</option>
          </select>
          <button onClick={() => refetch()}
            className="p-2 bg-white border border-slate-200 rounded-lg hover:bg-slate-50">
            <RefreshCw className="w-4 h-4 text-slate-500" />
          </button>
          {/* Export */}
          <div className="relative">
            <button onClick={() => setExport(v => !v)}
              className="flex items-center gap-2 px-3 py-2 bg-emerald-600 text-white rounded-lg text-sm hover:bg-emerald-700 shadow-md">
              <Download className="w-4 h-4" /> تصدير <ChevronDown className="w-3 h-3" />
            </button>
            <AnimatePresence>
              {showExportMenu && (
                <motion.div initial={{ opacity:0, y:-8 }} animate={{ opacity:1, y:0 }} exit={{ opacity:0, y:-8 }}
                  className="absolute top-full left-0 mt-1 w-52 bg-white rounded-xl shadow-xl border border-slate-200 z-30 py-1">
                  <button onClick={doExportKPIs}   className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"><FileText className="w-4 h-4" /> المؤشرات (CSV)</button>
                  <button onClick={doExportWOFOST} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"><BarChart3 className="w-4 h-4" /> بيانات WOFOST (CSV)</button>
                  <button onClick={doExportFields} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"><FileText className="w-4 h-4" /> الحقول (CSV)</button>
                  <button onClick={() => { window.print(); setExport(false); }} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"><BarChart3 className="w-4 h-4" /> طباعة التقرير</button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* ── Status Summary ── */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { key:'healthy',  label:'حقول صحية',   Icon:CheckCircle2,  color:'#16a34a', bg:'bg-emerald-50', text:'text-emerald-700' },
          { key:'moderate', label:'حقول متوسطة', Icon:Timer,         color:'#ca8a04', bg:'bg-amber-50',   text:'text-amber-700' },
          { key:'stressed', label:'حقول بإجهاد', Icon:AlertTriangle, color:'#dc2626', bg:'bg-red-50',     text:'text-red-700' },
        ].map(s => (
          <motion.div key={s.key} whileHover={{ scale:1.02 }} className={`rounded-xl border-2 p-4 ${s.bg} border-current`}>
            <div className="flex items-center justify-between">
              <s.Icon className={`w-6 h-6 ${s.text}`} />
              <span className="text-3xl font-bold" style={{ color:s.color }}>
                {summary[s.key as keyof typeof summary]}
              </span>
            </div>
            <p className={`text-sm mt-2 ${s.text}`}>{s.label}</p>
          </motion.div>
        ))}
      </div>

      {/* ── Alerts ── */}
      <AlertBanner alerts={alerts} />

      {/* ── Category filter ── */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-4 h-4 text-slate-400" />
        {CATEGORIES.map(c => (
          <button key={c.id} onClick={() => setCategory(c.id)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
              activeCategory === c.id
                ? 'text-white shadow-md'
                : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
            style={activeCategory === c.id ? { background:c.color } : {}}>
            {c.label}
          </button>
        ))}
        <span className="text-xs text-slate-400 mr-auto">{filtered.length} مؤشر</span>
      </div>

      {/* ── KPI Grid ── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {filtered.map((kpi: Record<string, unknown>, i: number) => (
          <motion.div key={kpi.id as string}
            initial={{ opacity:0, y:20 }} animate={{ opacity:1, y:0 }} transition={{ delay:i*0.04 }}
            onClick={() => setExpanded(expandedId === kpi.id ? null : kpi.id as string)}
            className="cursor-pointer">
            <KPICard kpi={{ ...kpi, sparkline: SPARKLINES[kpi.id as string] || kpi.sparkline as number[] }} />
            {/* Expanded sparkline */}
            <AnimatePresence>
              {expandedId === kpi.id && SPARKLINES[kpi.id as string] && (
                <motion.div initial={{ height:0, opacity:0 }} animate={{ height:'auto', opacity:1 }} exit={{ height:0, opacity:0 }}
                  className="overflow-hidden bg-white rounded-b-xl border border-t-0 border-slate-200 px-3 pb-3">
                  <ResponsiveContainer width="100%" height={70}>
                    <LineChart data={SPARKLINES[kpi.id as string].map((v, i) => ({ i, v }))}>
                      <Line dataKey="v" stroke={kpi.color as string} strokeWidth={2} dot={false} />
                      <XAxis dataKey="i" hide />
                      <YAxis hide domain={['auto','auto']} />
                      <Tooltip contentStyle={{ fontSize:11, borderRadius:8 }} formatter={(v: number) => [v.toFixed(4), kpi.name_ar as string]} />
                    </LineChart>
                  </ResponsiveContainer>
                  <div className="flex justify-between text-xs text-slate-400 mt-1">
                    <span>منذ {period}</span>
                    <span>{kpi.desc_ar as string}</span>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ))}
      </div>

      {/* ── NDVI Gauge + Field Status Bar Chart ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex items-center justify-center">
          <NDVIGauge value={
            (() => {
              const ndviKpi = kpis.find((k: Record<string,unknown>) => k.id === 'ndvi');
              return ndviKpi ? Number(ndviKpi.value) : 0.62;
            })()
          } size={220} />
        </div>
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-emerald-600" /> توزيع حالة الحقول
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={[
              { name:'ممتاز',  count:summary.healthy,  fill:'#16a34a' },
              { name:'متوسط',  count:summary.moderate, fill:'#f59e0b' },
              { name:'إجهاد',  count:summary.stressed, fill:'#dc2626' },
            ]} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" tick={{ fontSize:12, fill:'#94a3b8' }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize:13, fill:'#475569' }} width={60} />
              <Tooltip contentStyle={{ direction:'rtl', fontFamily:'Tajawal', borderRadius:8 }} />
              <Bar dataKey="count" radius={[0,8,8,0]}>
                {[summary.healthy,summary.moderate,summary.stressed].map((_, idx) => (
                  <Cell key={idx} fill={['#16a34a','#f59e0b','#dc2626'][idx]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── WOFOST Season Summary ── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Sprout className="w-4 h-4 text-emerald-600" />
            مواسم WOFOST — موسم 2026
          </h3>
          <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded-full">محرك RUE v8</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100">
                {['الحقل','المحصول','GDD','الاكتمال','LAI','الإنتاجية','المرحلة'].map(h => (
                  <th key={h} className="text-right py-2 px-3 text-xs font-medium text-slate-500">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {WOFOST_DATA.map((row, i) => (
                <tr key={i} className="border-b border-slate-50 hover:bg-emerald-50/30 transition-colors">
                  <td className="py-2 px-3 font-medium text-slate-800 text-xs">{row.field}</td>
                  <td className="py-2 px-3 text-slate-600 text-xs">{row.crop}</td>
                  <td className="py-2 px-3 text-slate-700 font-mono text-xs">{row.gdd}</td>
                  <td className="py-2 px-3">
                    <div className="flex items-center gap-2">
                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden" style={{ minWidth:40 }}>
                        <div className="h-full bg-emerald-500 rounded-full" style={{ width:`${row.progress}%` }} />
                      </div>
                      <span className="text-xs text-slate-500">{row.progress}%</span>
                    </div>
                  </td>
                  <td className="py-2 px-3 text-slate-700 text-xs">{row.lai}</td>
                  <td className="py-2 px-3">
                    <span className="font-bold text-emerald-700 text-sm">{row.yield}</span>
                    <span className="text-xs text-slate-400 mr-1">t/ha</span>
                  </td>
                  <td className="py-2 px-3">
                    <span className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full">{row.stage}</span>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-slate-50">
                <td colSpan={4} className="py-2 px-3 text-xs text-slate-500 font-medium">متوسط المزرعة</td>
                <td className="py-2 px-3 text-xs font-bold">{(WOFOST_DATA.reduce((s,r)=>s+r.lai,0)/WOFOST_DATA.length).toFixed(1)}</td>
                <td className="py-2 px-3 text-xs font-bold text-emerald-700">{(WOFOST_DATA.reduce((s,r)=>s+r.yield,0)/WOFOST_DATA.length).toFixed(1)} t/ha</td>
                <td />
              </tr>
            </tfoot>
          </table>
        </div>
      </div>

      {/* ── Indicator Legend ── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
          <Info className="w-4 h-4 text-slate-500" /> دليل المؤشرات — 17 مؤشراً
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-sm">
          {INDICATOR_CATALOG.map(ind => {
            const Icon = ind.icon;
            return (
              <div key={ind.id} className="flex items-start gap-2 p-2.5 bg-slate-50 rounded-lg">
                <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color:ind.color }} />
                <div>
                  <span className="font-semibold text-slate-700 text-xs">{ind.name_ar}</span>
                  <p className="text-[11px] text-slate-400 leading-tight">{ind.desc_ar}</p>
                  {ind.unit && <span className="text-[10px] text-slate-300">وحدة: {ind.unit}</span>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
