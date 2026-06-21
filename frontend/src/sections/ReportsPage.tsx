// ═══════════════════════════════════════════════════════════════
// SAHOOL — ReportsPage (تقارير وتحليلات حيّة)
// لوحة المزرعة + ملخّص الحقل من نقاط /api/v1/reports/* (تجميع جداول قائمة،
// مُقيَّد بالدور field:view وبالمستأجِر). ملخّص التكلفة حيّ أيضاً
// (/api/v1/analytics/costs). لا أرقام مُلفَّقة — كلّ بطاقة/مخطّط يعرض حالة
// تحميل/فراغ/خطأ صادقة (StateViews) بدل بيانات وهميّة.
// ═══════════════════════════════════════════════════════════════
import { useState } from 'react';
import {
  Download, BarChart3, DollarSign, ListChecks, Wallet,
  Tractor, Layers, Maximize2, Sprout, BellRing,
} from 'lucide-react';
import {
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';
import { useCostAnalytics, useFields, useFarmSummary, useFieldReport } from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { BarChartCard, ChartShell, tooltipContentStyle, CHART_THEME } from '../components/ds';

// أسماء عربية لمصادر التكلفة القادمة من الخادم (fallback: اسم المصدر كما هو).
const SOURCE_LABELS: Record<string, string> = {
  field_tasks: 'المهام الميدانية',
  maintenance: 'الصيانة',
};

// أسماء عربية لحالات العمليّات (fallback: المفتاح كما هو من الخادم).
const STATUS_LABELS: Record<string, string> = {
  planned:     'مُجدوَلة',
  in_progress: 'قيد التنفيذ',
  done:        'مُنجَزة',
  completed:   'مُكتملة',
  cancelled:   'مُلغاة',
  unknown:     'غير محدّدة',
};

const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  fertilization: 'تسميد',
  irrigation:    'ريّ',
  spraying:      'رشّ',
  pruning:       'تقليم',
  harvest:       'حصاد',
  scouting:      'استكشاف',
  unknown:       'غير محدّد',
};

const CHART_COLORS = ['#16a34a', '#38bdf8', '#f59e0b', '#a855f7', '#ef4444', '#14b8a6', '#eab308'];

const usd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n ?? 0);

const num = (n: number) => (n ?? 0).toLocaleString('en-US');

// هروب CSV قياسيّ (RFC 4180): اقتبس القيمة إن احتوت فاصلة/اقتباس/سطراً جديداً
// وضاعِف الاقتباسات الداخليّة — يمنع تحريف الأعمدة (نصوص عربيّة قد تحوي ",").
function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function exportToCSV(data: Record<string, unknown>[], filename: string) {
  if (!data.length) return;
  const headers = Object.keys(data[0]).map(csvCell).join(',');
  const rows = data.map(r => Object.values(r).map(csvCell).join(','));
  const csv = '﻿' + [headers, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  link.click();
}

const CARD = 'rounded-xl p-4 border';
const CARD_STYLE = { background: '#1e293b', borderColor: '#334155' } as const;
// نمط Tooltip الموحّد من نظام التصميم (ds/charts) — لا تكرار للقيَم.
const TOOLTIP_STYLE = tooltipContentStyle;

function KpiCard({ label, value, icon: Icon, color }: {
  label: string; value: string; icon: typeof Tractor; color: string;
}) {
  return (
    <div className="rounded-xl p-3 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <Icon className="w-4 h-4 mb-1" style={{ color }} />
      <div className="text-lg font-bold" style={{ color }}>{value}</div>
      <div className="text-[10px] text-slate-400">{label}</div>
    </div>
  );
}

// ── لوحة المزرعة: عدّادات + مخطّطان (العمليّات حسب الحالة، المساحة حسب المحصول) ──
function FarmDashboard() {
  const { data, isLoading, isError, error, refetch } = useFarmSummary();

  if (isLoading) return <LoadingState message="جارٍ تحميل ملخّص المزرعة…" />;
  if (isError) {
    const status = (error as { response?: { status?: number } })?.response?.status;
    const detail = status === 503
      ? 'خدمة التقارير غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
      : status === 403
        ? 'لا تملك صلاحية عرض التقارير (field:view).'
        : 'تعذّر الاتصال بخدمة التقارير.';
    return <ErrorState title="تعذّر تحميل ملخّص المزرعة" detail={detail} onRetry={() => refetch()} />;
  }
  if (!data) return <EmptyState title="لا توجد بيانات بعد" />;

  const statusData = Object.entries(data.activities_by_status ?? {}).map(([k, v]) => ({
    status: STATUS_LABELS[k] ?? k,
    count: v,
  }));
  const cropData = (data.area_by_crop ?? []).map(c => ({ crop: c.crop, area_ha: c.area_ha }));
  const hasActivities = statusData.length > 0;
  const hasCrops = cropData.some(c => c.area_ha > 0);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiCard label="المزارع"        value={num(data.farms_count)}             icon={Tractor}    color="#16a34a" />
        <KpiCard label="الحقول"         value={num(data.fields_count)}            icon={Layers}     color="#38bdf8" />
        <KpiCard label="المساحة (هـ)"   value={num(data.total_area_ha)}           icon={Maximize2}  color="#f59e0b" />
        <KpiCard label="مواسم نشطة"     value={num(data.active_seasons_count)}    icon={Sprout}     color="#a855f7" />
        <KpiCard label="العمليّات"      value={num(data.activities_total)}        icon={ListChecks} color="#14b8a6" />
        <KpiCard label="تنبيهات مفتوحة" value={num(data.open_alerts_count)}       icon={BellRing}   color="#ef4444" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* العمليّات حسب الحالة (BarChartCard — حالة الفراغ صادقة) */}
        <BarChartCard
          title="العمليّات حسب الحالة"
          data={hasActivities ? statusData : []}
          xKey="status"
          series={[{ dataKey: 'count', name: 'العدد', color: '#16a34a' }]}
          barSize={28}
          height={180}
          tooltipFormatter={(v) => [num(Number(v)), 'عدد']}
          emptyTitle="لا عمليّات مُسجَّلة بعد"
          emptyHint="سجّل عمليّات للحقول لتظهر هنا."
          action={hasActivities ? (
            <button onClick={() => exportToCSV(statusData, 'SAHOOL_Activities_By_Status.csv')}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300">
              <Download className="w-3 h-3" /> CSV
            </button>
          ) : undefined}
        />

        {/* المساحة حسب المحصول (Pie — يبقى داخل ChartShell بالثيم الموحّد) */}
        <ChartShell
          title="المساحة حسب المحصول (هـ)"
          height={180}
          isEmpty={!hasCrops}
          emptyTitle="لا مساحات مُسجَّلة بعد"
          emptyHint="أضِف حقولاً بمحاصيل ومساحات لتظهر هنا."
          action={hasCrops ? (
            <button onClick={() => exportToCSV(cropData, 'SAHOOL_Area_By_Crop.csv')}
              className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300">
              <Download className="w-3 h-3" /> CSV
            </button>
          ) : undefined}
        >
          <ResponsiveContainer width="100%" height={180}>
            <PieChart>
              <Pie data={cropData} dataKey="area_ha" nameKey="crop" cx="50%" cy="50%"
                outerRadius={70} label={(e: { crop: string }) => e.crop}>
                {cropData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
              </Pie>
              <Tooltip contentStyle={TOOLTIP_STYLE} itemStyle={{ color: CHART_THEME.itemColor }}
                formatter={(v: number) => [`${num(v)} هـ`, 'المساحة']} />
              <Legend wrapperStyle={{ fontSize: 11, color: CHART_THEME.legendColor }} />
            </PieChart>
          </ResponsiveContainer>
        </ChartShell>
      </div>
    </div>
  );
}

// ── ملخّص الحقل: اختيار حقل ثمّ عرض مساحته/محصوله/موسمه/عمليّاته/تنبيهاته ──
function FieldSummaryView() {
  const fieldsQuery = useFields();
  const fields: Array<{ field_id: string; name_ar?: string; name?: string }> =
    fieldsQuery.data?.fields ?? [];
  const [fieldId, setFieldId] = useState('');
  const report = useFieldReport(fieldId || undefined);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-slate-300">اختر حقلاً:</span>
        <select value={fieldId} onChange={e => setFieldId(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}>
          <option value="">— اختر حقلاً —</option>
          {fields.map(f => (
            <option key={f.field_id} value={f.field_id}>{f.name_ar ?? f.name ?? f.field_id}</option>
          ))}
        </select>
      </div>

      {fieldsQuery.isLoading && <LoadingState message="جارٍ تحميل قائمة الحقول…" />}
      {fieldsQuery.isError && (
        <ErrorState title="تعذّر تحميل قائمة الحقول"
          detail="تعذّر الاتصال بخدمة الحقول." onRetry={() => fieldsQuery.refetch()} />
      )}
      {!fieldsQuery.isLoading && !fieldsQuery.isError && fields.length === 0 && (
        <EmptyState title="لا توجد حقول بعد" hint="أنشئ حقلاً أوّلاً لعرض ملخّصه." />
      )}

      {!fieldId ? null : report.isLoading ? (
        <LoadingState message="جارٍ تحميل ملخّص الحقل…" />
      ) : report.isError ? (
        (() => {
          const status = (report.error as { response?: { status?: number } })?.response?.status;
          const detail = status === 404
            ? 'الحقل غير موجود ضمن هذا المستأجِر.'
            : status === 503
              ? 'خدمة التقارير غير متاحة حاليّاً (قاعدة البيانات معطّلة).'
              : status === 403
                ? 'لا تملك صلاحية عرض التقارير (field:view).'
                : 'تعذّر الاتصال بخدمة التقارير.';
          return <ErrorState title="تعذّر تحميل ملخّص الحقل" detail={detail} onRetry={() => report.refetch()} />;
        })()
      ) : report.data ? (
        <div className="space-y-4">
          {/* بطاقات الحقل الأساسيّة */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <KpiCard label="المساحة (هـ)" value={num(report.data.area_ha)}          icon={Maximize2}  color="#f59e0b" />
            <KpiCard label="المحصول"      value={report.data.crop ?? '—'}           icon={Sprout}     color="#16a34a" />
            <KpiCard label="نوع التربة"   value={report.data.soil_type ?? '—'}      icon={Layers}     color="#38bdf8" />
            <KpiCard label="العمليّات"    value={num(report.data.activities_total)} icon={ListChecks} color="#14b8a6" />
          </div>

          {/* الموسم النشط */}
          <div className={CARD} style={CARD_STYLE}>
            <span className="text-sm font-semibold text-slate-200">الموسم النشط</span>
            {report.data.current_season ? (
              <div className="mt-2 text-sm text-slate-300 space-y-1">
                <div>المحاصيل: <span className="text-slate-100">{(report.data.current_season.crops ?? []).join('، ') || '—'}</span></div>
                <div>الصنف: <span className="text-slate-100">{report.data.current_season.cultivar ?? '—'}</span></div>
                <div>تاريخ البذار: <span className="text-slate-100">{report.data.current_season.sowing_date ?? '—'}</span></div>
                <div>نهاية الموسم: <span className="text-slate-100">{report.data.current_season.season_end ?? '—'}</span></div>
              </div>
            ) : (
              <p className="mt-2 text-xs text-slate-400">لا يوجد موسم نشط لهذا الحقل.</p>
            )}
          </div>

          {/* العمليّات حسب النوع */}
          {Object.keys(report.data.activities_by_type ?? {}).length > 0 ? (
            <BarChartCard
              title="العمليّات حسب النوع"
              data={Object.entries(report.data.activities_by_type ?? {}).map(([k, v]) => ({
                type: ACTIVITY_TYPE_LABELS[k] ?? k, count: v,
              }))}
              xKey="type"
              series={[{ dataKey: 'count', name: 'العدد', color: '#a855f7' }]}
              barSize={26}
              height={170}
              tooltipFormatter={(v) => [num(Number(v)), 'عدد']}
            />
          ) : (
            <div className={CARD} style={CARD_STYLE}>
              <span className="text-sm font-semibold text-slate-200">العمليّات حسب النوع</span>
              <p className="mt-2 text-xs text-slate-400">لا عمليّات مُسجَّلة لهذا الحقل.</p>
            </div>
          )}

          {/* أحدث التنبيهات */}
          <div className={CARD} style={CARD_STYLE}>
            <span className="text-sm font-semibold text-slate-200">أحدث التنبيهات</span>
            {(report.data.recent_alerts ?? []).length > 0 ? (
              <ul className="mt-2 space-y-2">
                {(report.data.recent_alerts ?? []).map(a => (
                  <li key={a.alert_id} className="flex items-center justify-between text-sm border-b border-slate-700/50 pb-1">
                    <span className="text-slate-200">{a.title_ar ?? a.alert_type}</span>
                    <span className="text-[11px] text-slate-400">{a.severity} · {a.status}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-slate-400">لا تنبيهات لهذا الحقل.</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CostSummary() {
  const { data, isLoading, isError, error, refetch } = useCostAnalytics();

  if (isLoading) return <LoadingState message="جارٍ تحميل ملخّص التكلفة…" />;
  if (isError) {
    const status = (error as { response?: { status?: number } })?.response?.status;
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
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        {[
          { label: 'إجماليّ التكلفة', val: usd(totalUsd), icon: DollarSign, color: '#f59e0b' },
          { label: 'عدد المهام', val: num(taskCount), icon: ListChecks, color: '#38bdf8' },
          { label: 'مصادر التكلفة', val: num(bySource.length), icon: BarChart3, color: '#a855f7' },
        ].map((k, i) => {
          const Icon = k.icon;
          return (
            <div key={i} className="rounded-xl p-3 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
              <Icon className="w-4 h-4 mb-1" style={{ color: k.color }} />
              <div className="text-lg font-bold" style={{ color: k.color }}>{k.val}</div>
              <div className="text-[10px] text-slate-400">{k.label}</div>
            </div>
          );
        })}
      </div>

      {bySource.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <BarChartCard
            title="التكلفة حسب المصدر (USD)"
            data={chartData}
            xKey="source"
            series={[{ dataKey: 'total_usd', name: 'التكلفة', color: '#f59e0b' }]}
            barSize={28}
            height={160}
            tooltipFormatter={(v) => [usd(Number(v)), 'التكلفة']}
            action={
              <button onClick={() => exportToCSV(chartData, 'SAHOOL_Cost_By_Source.csv')}
                className="flex items-center gap-1 text-xs text-amber-400 hover:text-amber-300">
                <Download className="w-3 h-3" /> CSV
              </button>
            }
          />

          <div className="rounded-xl p-4 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
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

type Tab = 'farm' | 'field';

export function ReportsPage() {
  const [tab, setTab] = useState<Tab>('farm');

  return (
    <div className="space-y-5 max-w-5xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">التقارير والتحليلات</h2>
          <p className="text-sm text-slate-400">ملخّصات حيّة للمزرعة والحقول — مُجمَّعة من بياناتك الفعليّة</p>
        </div>
        <div className="flex gap-2">
          {([['farm', 'لوحة المزرعة'], ['field', 'ملخّص حقل']] as [Tab, string][]).map(([t, label]) => (
            <button key={t} onClick={() => setTab(t)}
              className="px-3 py-2 rounded-lg text-sm font-medium transition-colors"
              style={{
                background: tab === t ? '#16a34a' : '#1e293b',
                border: '1px solid #334155',
                color: tab === t ? '#fff' : '#e2e8f0',
              }}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'farm' ? (
        <>
          <FarmDashboard />
          {/* ملخّص التكلفة — بيانات حيّة من /api/v1/analytics/costs */}
          <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
            <div className="flex items-center gap-2 mb-3">
              <Wallet className="w-4 h-4 text-amber-400" />
              <span className="text-sm font-semibold text-slate-200">ملخّص التكلفة</span>
            </div>
            <CostSummary />
          </div>
        </>
      ) : (
        <FieldSummaryView />
      )}
    </div>
  );
}
export default ReportsPage;
