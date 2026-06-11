// ═══════════════════════════════════════════════════════════════════
// SAHOOL — HybridIndexPage (لوحة المؤشّرات)
// مصدر البيانات: ربط حيّ بلا تلفيق.
//   • KPIs/التنبيهات/ملخّص الحقول → GET /api/v1/indicators/dashboard (sahool-platform)
//   • جدول المواسم (GDD/LAI/الإنتاجية) → GET /api/v1/fields/{id}/seasons
//     يعرض حقول sim_* المُخزَّنة (تقديرات RUE/FAO-56). موسم بلا محاكاة ⇒ "—" صادق.
//   • لا بيانات WOFOST/Sparklines ثابتة — أُزيلت الزخرفة التجميليّة (audit gap).
// ═══════════════════════════════════════════════════════════════════

import { useState, useMemo } from 'react';
import {
  LayoutDashboard, AlertTriangle, Download,
  RefreshCw, Filter, ChevronDown, FileText, BarChart3,
  Sprout, Timer, Leaf, Droplets, Thermometer,
  FlaskConical, Wind, CheckCircle2, Info, Activity, Zap,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';
import { useDashboardKPIs } from '@/hooks/useIndicators';
import { useSeasons } from '@/hooks/useApi';
import type { SeasonSummary } from '@/services/api';
import { KPICard } from '@/components/KPICard';
import { AlertBanner } from '@/components/AlertBanner';
import { NDVIGauge } from '@/components/NDVIGauge';

// ── Indicator catalog (وصف/أيقونات فقط — للدليل المرجعيّ، لا أرقام مُلفَّقة) ──
const INDICATOR_CATALOG = [
  // نباتية
  { id:'ndvi',  cat:'vegetation', name_ar:'NDVI',   desc_ar:'مؤشر الغطاء النباتي الطبيعي',   unit:'',       icon:Leaf,        color:'#16a34a' },
  { id:'evi',   cat:'vegetation', name_ar:'EVI',    desc_ar:'مؤشر النباتات المحسّن',          unit:'',       icon:Sprout,      color:'#15803d' },
  { id:'gndvi', cat:'vegetation', name_ar:'GNDVI',  desc_ar:'مؤشر الكلوروفيل الأخضر',        unit:'',       icon:Leaf,        color:'#4ade80' },
  { id:'ndre',  cat:'vegetation', name_ar:'NDRE',   desc_ar:'مؤشر الحافة الحمراء',           unit:'',       icon:Activity,    color:'#0891b2' },
  { id:'savi',  cat:'vegetation', name_ar:'SAVI',   desc_ar:'مؤشر النباتات المعدّل',         unit:'',       icon:Sprout,      color:'#65a30d' },
  { id:'lai',   cat:'vegetation', name_ar:'LAI',    desc_ar:'مؤشر مساحة الورقة',             unit:'m²/m²',  icon:Leaf,        color:'#22c55e' },
  { id:'ndwi',  cat:'vegetation', name_ar:'NDWI',   desc_ar:'محتوى المياه في النبات',         unit:'',       icon:Droplets,    color:'#38bdf8' },
  // مائية
  { id:'soil_moisture', cat:'water', name_ar:'رطوبة التربة',  desc_ar:'محتوى الرطوبة في التربة',  unit:'%',     icon:Droplets,    color:'#0ea5e9' },
  { id:'wue',           cat:'water', name_ar:'كفاءة الري',    desc_ar:'كيلوجرام إنتاج/متر مكعب', unit:'kg/m³', icon:Zap,         color:'#38bdf8' },
  { id:'et0',           cat:'water', name_ar:'ET₀',           desc_ar:'البخر-نتح المرجعي',       unit:'mm/d',  icon:Droplets,    color:'#7dd3fc' },
  { id:'water_deficit', cat:'water', name_ar:'عجز المياه',    desc_ar:'الفجوة بين ET0 والأمطار', unit:'mm',    icon:AlertTriangle, color:'#fb923c' },
  // تربة
  { id:'soil_ph', cat:'soil', name_ar:'pH التربة',     desc_ar:'درجة حموضة التربة',      unit:'',      icon:FlaskConical, color:'#92400e' },
  { id:'soil_ec', cat:'soil', name_ar:'EC التربة',     desc_ar:'التوصيل الكهربائي',       unit:'dS/m',  icon:Zap,          color:'#b45309' },
  { id:'nitrogen', cat:'soil', name_ar:'النيتروجين',   desc_ar:'النيتروجين المتاح',       unit:'mg/kg', icon:FlaskConical, color:'#65a30d' },
  // طقس
  { id:'temperature', cat:'weather', name_ar:'الحرارة',  desc_ar:'درجة الحرارة المتوسطة', unit:'°C',   icon:Thermometer,  color:'#f97316' },
  { id:'humidity',    cat:'weather', name_ar:'الرطوبة',  desc_ar:'الرطوبة النسبية',        unit:'%',    icon:Droplets,     color:'#60a5fa' },
  { id:'wind_speed',  cat:'weather', name_ar:'الرياح',   desc_ar:'سرعة الرياح',            unit:'km/h', icon:Wind,         color:'#93c5fd' },
] as const;

const CATEGORIES = [
  { id:'all',         label:'الكل',         color:'#6b7280' },
  { id:'operations',  label:'تشغيليّة 📋',  color:'#0f766e' },
  { id:'vegetation',  label:'نباتية 🌿',    color:'#16a34a' },
  { id:'water',       label:'مائية 💧',     color:'#0ea5e9' },
  { id:'soil',        label:'تربة 🏔',      color:'#92400e' },
  { id:'weather',     label:'طقس 🌤',       color:'#f97316' },
] as const;

const CATALOG_BY_ID = new Map<string, (typeof INDICATOR_CATALOG)[number]>(
  INDICATOR_CATALOG.map(c => [c.id, c]),
);

// sim_* مُخزَّنة كغ/هكتار → طنّ/هكتار للعرض، أو null إن غابت المحاكاة.
const kgHaToTHa = (v: number | null | undefined): number | null =>
  v == null ? null : v / 1000;

function exportToCSV(data: Record<string, unknown>[], filename: string) {
  if (!data.length) return;
  const headers = Object.keys(data[0]).join(',');
  const rows = data.map(row =>
    Object.values(row)
      .map(v => (typeof v === 'string' && v.includes(',') ? `"${v}"` : (v ?? '')))
      .join(',')
  );
  const csv = '﻿' + [headers, ...rows].join('\n'); // BOM for Arabic
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  URL.revokeObjectURL(link.href);
}

// قيمة رقميّة أو "—" صادقة (للحقول التي لم تُشغَّل لها المحاكاة بعد).
function NumOrDash({ value, digits = 1, suffix }: { value: number | null; digits?: number; suffix?: string }) {
  if (value == null) return <span className="text-slate-300">—</span>;
  return <span>{value.toFixed(digits)}{suffix ? <span className="text-xs text-slate-400 mr-1">{suffix}</span> : null}</span>;
}

// ── صفّ موسم حقل واحد (يستدعي useSeasons لذلك الحقل — hook لكلّ صفّ، قانونيّ) ──
// يختار الموسم النشط (أو الأحدث) ويعرض sim_* المُخزَّنة. لا توليد أرقام: غياب
// المحاكاة ⇒ "—".
function WofostFieldRow({ field }: { field: Record<string, unknown> }) {
  const fieldId   = field.field_id as string;
  const fieldName = (field.field_name as string) || fieldId;
  const crop      = (field.crop as string) || '—';
  const { data: seasons, isLoading, isError } = useSeasons(fieldId);

  const season = useMemo<SeasonSummary | undefined>(() => {
    if (!seasons?.length) return undefined;
    return seasons.find(s => s.status === 'active') ?? seasons[0];
  }, [seasons]);

  if (isLoading) {
    return (
      <tr className="border-b border-slate-50">
        <td className="py-2 px-3 font-medium text-slate-800 text-xs">{fieldName}</td>
        <td colSpan={6} className="py-2 px-3 text-xs text-slate-400">
          <RefreshCw className="inline w-3 h-3 animate-spin ml-1" /> جارٍ التحميل…
        </td>
      </tr>
    );
  }

  if (isError || !season) {
    return (
      <tr className="border-b border-slate-50">
        <td className="py-2 px-3 font-medium text-slate-800 text-xs">{fieldName}</td>
        <td className="py-2 px-3 text-slate-600 text-xs">{crop}</td>
        <td colSpan={5} className="py-2 px-3 text-xs text-slate-300">
          {isError ? 'تعذّر جلب المواسم' : 'لا موسم مُسجَّل'}
        </td>
      </tr>
    );
  }

  const seasonCrop = season.crops?.[0] || crop;
  const ranSim = season.sim_ran_at != null;

  return (
    <tr className="border-b border-slate-50 hover:bg-emerald-50/30 transition-colors">
      <td className="py-2 px-3 font-medium text-slate-800 text-xs">{fieldName}</td>
      <td className="py-2 px-3 text-slate-600 text-xs">{seasonCrop}</td>
      <td className="py-2 px-3 text-slate-700 font-mono text-xs">
        <NumOrDash value={season.sim_gdd_total} digits={0} />
      </td>
      <td className="py-2 px-3 text-slate-700 text-xs">
        {/* احتياج الماء التقديريّ (mm) — لا "نسبة اكتمال" مُلفَّقة */}
        <NumOrDash value={season.sim_water_mm} digits={0} suffix="mm" />
      </td>
      <td className="py-2 px-3 text-slate-700 text-xs">
        <NumOrDash value={season.sim_lai_max} digits={1} />
      </td>
      <td className="py-2 px-3">
        {season.sim_yield_kg_ha != null ? (
          <>
            <span className="font-bold text-emerald-700 text-sm">
              {kgHaToTHa(season.sim_yield_kg_ha)!.toFixed(1)}
            </span>
            <span className="text-xs text-slate-400 mr-1">t/ha</span>
          </>
        ) : (
          <span className="text-slate-300">—</span>
        )}
      </td>
      <td className="py-2 px-3">
        <span className={`px-2 py-0.5 text-xs rounded-full ${ranSim ? 'bg-blue-50 text-blue-700' : 'bg-slate-100 text-slate-400'}`}>
          {ranSim ? `محاكاة ${new Date(season.sim_ran_at as string).toLocaleDateString('ar')}` : 'لم تُحاكَ بعد'}
        </span>
      </td>
    </tr>
  );
}

export function HybridIndexPage() {
  const [period, setPeriod]           = useState('30d');
  const [activeCategory, setCategory] = useState<string>('all');
  const [showExportMenu, setExport]   = useState(false);
  const { data, isLoading, error, refetch } = useDashboardKPIs();

  const kpis    = (data?.kpis    || []) as Record<string, unknown>[];
  const alerts  = (data?.alerts  || []) as Record<string, unknown>[];
  const fields  = (data?.fields_summary || []) as Record<string, unknown>[];

  // إثراء KPIs الحيّة بوصف الكتالوج فقط (أيقونة/لون/فئة) — لا قيم/سلاسل مُلفَّقة.
  // فئة الـKPI تُؤخذ من الخادم إن وُجدت، وإلّا من الكتالوج المرجعيّ.
  const enriched = useMemo(() =>
    kpis.map((kpi: Record<string, unknown>) => {
      const meta = CATALOG_BY_ID.get(kpi.id as string);
      return {
        ...kpi,
        category: (kpi.category as string) || meta?.cat || 'operations',
        desc_ar:  (kpi.desc_ar as string)  || meta?.desc_ar || '',
        color:    (kpi.color as string)    || meta?.color || '#16a34a',
      };
    }), [kpis]);

  const filtered = useMemo(() =>
    activeCategory === 'all' ? enriched : enriched.filter((k: Record<string, unknown>) => k.category === activeCategory),
    [enriched, activeCategory]);

  // ملخّص حالة الحقول من ملخّص الخادم: نُصنّف بوجود موسم نشط (has_active_season)
  // بدل NDVI مُلفَّق غير موجود في الحمولة. صادق: "نشط / بلا موسم".
  const summary = useMemo(() => {
    const counts = { active: 0, idle: 0 };
    fields.forEach((f: Record<string, unknown>) => {
      if (f.has_active_season) counts.active++;
      else counts.idle++;
    });
    return counts;
  }, [fields]);

  // Exports — كلّها من بيانات حيّة (لا WOFOST ثابت).
  const doExportKPIs = () => {
    exportToCSV(
      enriched.map((k: Record<string, unknown>) => ({
        المؤشر: (k.name_ar || k.name_en || k.id) as string,
        الفئة: k.category as string,
        القيمة: k.value as number,
        الوحدة: (k.unit || '') as string,
        الحالة: k.status as string,
      })),
      `SAHOOL_KPIs_${new Date().toISOString().slice(0,10)}.csv`
    );
    setExport(false);
  };
  const doExportFields = () => {
    exportToCSV(
      fields.map((f: Record<string, unknown>) => ({
        الحقل: (f.field_name as string) || (f.field_id as string),
        المحصول: (f.crop || '') as string,
        'المساحة (هـ)': (f.area_ha ?? '') as number,
        'موسم نشط': f.has_active_season ? 'نعم' : 'لا',
      })),
      `SAHOOL_Fields_${new Date().toISOString().slice(0,10)}.csv`
    );
    setExport(false);
  };

  if (isLoading) return (
    <div className="flex items-center justify-center py-20" dir="rtl">
      <div className="text-center">
        <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin mx-auto mb-3" />
        <p className="text-sm text-slate-500">جارٍ تحميل لوحة المؤشّرات…</p>
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
            لوحة المؤشّرات
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            عدّادات حيّة من حقولك · المؤشّرات الطيفيّة لكلّ حقل من شاشة الأقمار
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
                  <button onClick={doExportFields} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"><FileText className="w-4 h-4" /> الحقول (CSV)</button>
                  <button onClick={() => { window.print(); setExport(false); }} className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 hover:bg-emerald-50 hover:text-emerald-700"><BarChart3 className="w-4 h-4" /> طباعة التقرير</button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>

      {/* ── Status Summary (من has_active_season الحيّ) ── */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { key:'active', label:'حقول بموسم نشط', Icon:CheckCircle2,  color:'#16a34a', bg:'bg-emerald-50', text:'text-emerald-700' },
          { key:'idle',   label:'حقول بلا موسم',  Icon:Timer,         color:'#64748b', bg:'bg-slate-50',   text:'text-slate-600' },
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
      <AlertBanner alerts={alerts as { id: string; [key: string]: unknown }[]} />

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

      {/* ── KPI Grid (حيّ — بلا sparklines مُلفَّقة) ── */}
      {filtered.length > 0 ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {filtered.map((kpi: Record<string, unknown>, i: number) => (
            <motion.div key={kpi.id as string}
              initial={{ opacity:0, y:20 }} animate={{ opacity:1, y:0 }} transition={{ delay:i*0.04 }}>
              <KPICard kpi={kpi} />
            </motion.div>
          ))}
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 p-8 text-center text-sm text-slate-400">
          لا مؤشّرات لعرضها لهذه الفئة بعد.
        </div>
      )}

      {/* ── NDVI Gauge + Field Status Bar Chart ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 bg-white rounded-xl shadow-sm border border-slate-200 p-5 flex flex-col items-center justify-center">
          {/* لا قيمة NDVI في حمولة اللوحة (تأتي من شاشة الأقمار لكلّ حقل) ⇒ مقياس
              محايد مع وسم صادق بدل قيمة افتراضيّة مُلفَّقة. */}
          <NDVIGauge value={(() => {
            const ndviKpi = kpis.find((k: Record<string,unknown>) => k.id === 'ndvi');
            return ndviKpi ? Number(ndviKpi.value) : 0;
          })()} size={220} />
          <p className="text-[11px] text-slate-400 mt-2 text-center">
            {kpis.some((k) => k.id === 'ndvi')
              ? 'متوسّط NDVI'
              : 'NDVI لكلّ حقل من شاشة الأقمار'}
          </p>
        </div>
        <div className="lg:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-5">
          <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-emerald-600" /> حالة المواسم عبر الحقول
          </h3>
          <ResponsiveContainer width="100%" height={180}>
            <BarChart data={[
              { name:'موسم نشط', count:summary.active, fill:'#16a34a' },
              { name:'بلا موسم', count:summary.idle,   fill:'#94a3b8' },
            ]} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis type="number" allowDecimals={false} tick={{ fontSize:12, fill:'#94a3b8' }} />
              <YAxis dataKey="name" type="category" tick={{ fontSize:13, fill:'#475569' }} width={70} />
              <Tooltip contentStyle={{ direction:'rtl', fontFamily:'Tajawal', borderRadius:8 }} />
              <Bar dataKey="count" radius={[0,8,8,0]}>
                {[summary.active, summary.idle].map((_, idx) => (
                  <Cell key={idx} fill={['#16a34a','#94a3b8'][idx]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Season Simulation Summary (حيّ — sim_* من /simulate) ── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Sprout className="w-4 h-4 text-emerald-600" />
            محاكاة المواسم — تقديرات المحصول (RUE/FAO-56)
          </h3>
          <span className="text-xs text-slate-400 bg-slate-100 px-2 py-1 rounded-full">من /api/v1/seasons/simulate</span>
        </div>
        {fields.length === 0 ? (
          <p className="text-sm text-slate-400 py-6 text-center">لا حقول مُسجَّلة بعد — أضِف حقلاً وموسماً لعرض المحاكاة.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {['الحقل','المحصول','GDD','احتياج الماء','LAI أقصى','الإنتاجية','المصدر'].map(h => (
                    <th key={h} className="text-right py-2 px-3 text-xs font-medium text-slate-500">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {fields.map((f: Record<string, unknown>) => (
                  <WofostFieldRow key={f.field_id as string} field={f} />
                ))}
              </tbody>
            </table>
            <p className="text-[11px] text-slate-400 mt-3">
              القيم تقديرات نموذجيّة (بنطاق وثقة) تظهر بعد تشغيل المحاكاة للموسم؛ "—" تعني عدم تشغيلها بعد.
            </p>
          </div>
        )}
      </div>

      {/* ── Indicator Legend (دليل مرجعيّ — لا أرقام) ── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <h3 className="text-sm font-bold text-slate-800 mb-3 flex items-center gap-2">
          <Info className="w-4 h-4 text-slate-500" /> دليل المؤشرات
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
