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
  type LucideIcon,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { motion, AnimatePresence } from 'framer-motion';
import { useDashboardKPIs } from '@/hooks/useIndicators';
import { useIndicatorRegistry, type RegistryIndicator } from '@/hooks/useIndicatorRegistry';
import { useSeasons } from '@/hooks/useApi';
import type { SeasonSummary } from '@/services/api';
import { KPICard } from '@/components/KPICard';
import { AlertBanner } from '@/components/AlertBanner';
import { NDVIGauge } from '@/components/NDVIGauge';

// ── خصائص العرض الثابتة (أيقونة/لون/وصف) مفتاحها id — تلميع فقط. ──
// ملاحظة صدق (WS-B.2): هذه *ليست* مصدر الحقيقة لمجموعة المؤشّرات. مجموعة
// المؤشّرات وحالة توفّرها (availability) وتصنيف مصدرها (source_class) وقابليّة
// عرضها (renderable) تأتي حصراً من سجلّ `/api/v1/indicators/registry` الحيّ عبر
// `useIndicatorRegistry`. معرّف لا يعرفه هذا الجدول ⇒ عرض افتراضيّ محايد، لا
// حذف. لا يجوز تقديم هذه القائمة كأنّها السجلّ.
interface Presentation { icon: LucideIcon; color: string; desc_ar: string; cat: string }

const PRESENTATION: Record<string, Presentation> = {
  // نباتية
  ndvi:  { cat:'vegetation', desc_ar:'مؤشر الغطاء النباتي الطبيعي', icon:Leaf,        color:'#16a34a' },
  evi:   { cat:'vegetation', desc_ar:'مؤشر النباتات المحسّن',        icon:Sprout,      color:'#15803d' },
  gndvi: { cat:'vegetation', desc_ar:'مؤشر الكلوروفيل الأخضر',       icon:Leaf,        color:'#4ade80' },
  ndre:  { cat:'vegetation', desc_ar:'مؤشر الحافة الحمراء',          icon:Activity,    color:'#0891b2' },
  savi:  { cat:'vegetation', desc_ar:'مؤشر النباتات المعدّل',        icon:Sprout,      color:'#65a30d' },
  lai:   { cat:'vegetation', desc_ar:'مؤشر مساحة الورقة',            icon:Leaf,        color:'#22c55e' },
  ndwi:  { cat:'vegetation', desc_ar:'محتوى المياه في النبات',        icon:Droplets,    color:'#38bdf8' },
  // مائية
  soil_moisture: { cat:'water', desc_ar:'محتوى الرطوبة في التربة', icon:Droplets,      color:'#0ea5e9' },
  wue:           { cat:'water', desc_ar:'كيلوجرام إنتاج/متر مكعب', icon:Zap,           color:'#38bdf8' },
  et0:           { cat:'water', desc_ar:'البخر-نتح المرجعي',       icon:Droplets,      color:'#7dd3fc' },
  water_deficit: { cat:'water', desc_ar:'الفجوة بين ET0 والأمطار', icon:AlertTriangle, color:'#fb923c' },
  // تربة
  soil_ph:  { cat:'soil', desc_ar:'درجة حموضة التربة', icon:FlaskConical, color:'#92400e' },
  soil_ec:  { cat:'soil', desc_ar:'التوصيل الكهربائي',  icon:Zap,          color:'#b45309' },
  nitrogen: { cat:'soil', desc_ar:'النيتروجين المتاح',  icon:FlaskConical, color:'#65a30d' },
  // طقس
  temperature: { cat:'weather', desc_ar:'درجة الحرارة المتوسطة', icon:Thermometer, color:'#f97316' },
  humidity:    { cat:'weather', desc_ar:'الرطوبة النسبية',        icon:Droplets,    color:'#60a5fa' },
  wind_speed:  { cat:'weather', desc_ar:'سرعة الرياح',            icon:Wind,        color:'#93c5fd' },
};

const DEFAULT_PRESENTATION: Presentation = { icon: Activity, color: '#64748b', desc_ar: '', cat: 'operations' };

// معرّف لا يعرفه جدول العرض ⇒ عرض افتراضيّ محايد بدل الإخفاء.
const presentationFor = (id: string): Presentation => PRESENTATION[id] ?? DEFAULT_PRESENTATION;

const CATEGORIES = [
  { id:'all',         label:'الكل',         color:'#6b7280' },
  { id:'operations',  label:'تشغيليّة 📋',  color:'#0f766e' },
  { id:'vegetation',  label:'نباتية 🌿',    color:'#16a34a' },
  { id:'water',       label:'مائية 💧',     color:'#0ea5e9' },
  { id:'soil',        label:'تربة 🏔',      color:'#92400e' },
  { id:'weather',     label:'طقس 🌤',       color:'#f97316' },
] as const;

// وسم توفّر المؤشّر — عرض صادق لحالة السجلّ: غير متاح بعد لا يُعرض كطبقة عاملة.
function AvailabilityBadge({ indicator }: { indicator: RegistryIndicator }) {
  if (indicator.availability === 'unavailable') {
    return (
      <span className="px-1.5 py-0.5 text-[9px] rounded-full bg-slate-200 text-slate-500 font-medium whitespace-nowrap">
        غير متاح بعد
      </span>
    );
  }
  if (indicator.availability === 'estimated' || indicator.source_class === 'estimated') {
    return (
      <span className="px-1.5 py-0.5 text-[9px] rounded-full bg-amber-100 text-amber-700 font-medium whitespace-nowrap">
        تقديريّ
      </span>
    );
  }
  if (indicator.source_class === 'derived') {
    return (
      <span className="px-1.5 py-0.5 text-[9px] rounded-full bg-sky-100 text-sky-700 font-medium whitespace-nowrap">
        مُشتقّ
      </span>
    );
  }
  return null;
}

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
  // مصدر الحقيقة لمجموعة المؤشّرات + حالتها (WS-B.2) — لا قائمة ثابتة.
  const registry = useIndicatorRegistry();

  const kpis    = (data?.kpis    || []) as Record<string, unknown>[];
  const alerts  = (data?.alerts  || []) as Record<string, unknown>[];
  const fields  = (data?.fields_summary || []) as Record<string, unknown>[];

  // إثراء KPIs الحيّة بوصف الكتالوج فقط (أيقونة/لون/فئة) — لا قيم/سلاسل مُلفَّقة.
  // فئة الـKPI تُؤخذ من الخادم إن وُجدت، وإلّا من الكتالوج المرجعيّ.
  const enriched = useMemo(() =>
    kpis.map((kpi: Record<string, unknown>) => {
      const meta = presentationFor(kpi.id as string);
      return {
        ...kpi,
        category: (kpi.category as string) || meta.cat,
        desc_ar:  (kpi.desc_ar as string)  || meta.desc_ar,
        color:    (kpi.color as string)    || meta.color,
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

      {/* ── Indicator Registry Legend (السجلّ الحيّ WS-B.2 — لا قائمة ثابتة) ── */}
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-5">
        <div className="flex items-center justify-between mb-3 gap-3 flex-wrap">
          <h3 className="text-sm font-bold text-slate-800 flex items-center gap-2">
            <Info className="w-4 h-4 text-slate-500" /> دليل المؤشرات
          </h3>
          {registry.data && (
            <span
              className="text-[10px] text-slate-400 bg-slate-100 px-2 py-1 rounded-full font-mono"
              title="علامة حداثة الـmanifest — بادئة digest بطول 12">
              نسخة السجلّ: {registry.data.registry_version || '—'}
            </span>
          )}
        </div>

        {registry.loading ? (
          // تحميل: مؤشّر صادق، لا نعرض قائمة ثابتة كأنّها السجلّ.
          <div className="py-8 text-center text-sm text-slate-400">
            <RefreshCw className="inline w-4 h-4 animate-spin ml-1" /> جارٍ تحميل سجلّ المؤشّرات…
          </div>
        ) : registry.error || !registry.data ? (
          // تدهور صادق: تعذّر السجلّ ⇒ لا اختلاق قائمة، تحذير واضح فقط.
          <div className="flex items-start gap-2 py-4 px-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-700">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
            <span>
              تعذّر تحميل سجلّ المؤشّرات — القائمة قد تكون غير محدّثة، لذا أُخفيت
              لتفادي عرض بيانات غير موثوقة كأنّها الحقيقة.
            </span>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3 text-sm">
            {registry.data.indicators.map(ind => {
              const p = presentationFor(ind.id);
              const Icon = p.icon;
              const unavailable = ind.availability === 'unavailable';
              return (
                <div
                  key={ind.id}
                  className={`flex items-start gap-2 p-2.5 rounded-lg ${unavailable ? 'bg-slate-100 opacity-60' : 'bg-slate-50'}`}>
                  <Icon className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: p.color }} />
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="font-semibold text-slate-700 text-xs">{ind.name_ar}</span>
                      <AvailabilityBadge indicator={ind} />
                    </div>
                    <p className="text-[11px] text-slate-400 leading-tight">{p.desc_ar || ind.name_en}</p>
                    {ind.unit && <span className="text-[10px] text-slate-300">وحدة: {ind.unit}</span>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
