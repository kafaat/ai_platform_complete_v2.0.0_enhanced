// ═══════════════════════════════════════════════════════════════
// SAHOOL — ReportsPage (تقارير وتحليلات حيّة + ملخّصات طراز FieldView)
// لوحة المزرعة + ملخّص الحقل من نقاط /api/v1/reports/* (تجميع جداول قائمة،
// مُقيَّد بالدور field:view وبالمستأجِر). ملخّص التكلفة حيّ (/api/v1/analytics/costs).
//
// تقارير الملخّص (طراز FieldView): زراعة / حصاد / تطبيق — مُجمَّعة على العميل من
// بياناتك الفعليّة فقط: المواسم (/api/v1/fields/{id}/seasons) + العمليّات
// (/api/v1/fields/{id}/activities) عبر كلّ الحقول. صدق أوّلاً — لا أرقام مُلفَّقة:
//   • الغلّة غير المُسجَّلة (actual_yield_kg_ha = null) تُعرَض «—» لا 0.
//   • المساحة لكلّ موسم من خيار الحقل؛ إن لم تتوفّر مساحة حقيقيّة ⇒ «—».
//   • التصدير: CSV (موجود) + طباعة/PDF عبر window.print() بنطاق طباعة مخصّص.
// كلّ بطاقة/مخطّط يعرض حالة تحميل/فراغ/خطأ صادقة (StateViews) بدل بيانات وهميّة.
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import { useQueries } from '@tanstack/react-query';
import { csvRow } from '../lib/csv';
import {
  Download, BarChart3, DollarSign, ListChecks, Wallet, Printer,
  Tractor, Layers, Maximize2, Sprout, BellRing, Wheat, ClipboardList,
} from 'lucide-react';
import {
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  useCostAnalytics, useFields, useFarmSummary, useFieldReport,
} from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { useAuthStore } from '../hooks/useAuth';
import { fetchSeasons, fetchActivities } from '../services/api';
import type { SeasonSummary, Activity } from '../services/api';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { BarChartCard, ChartShell, DataTable, tooltipContentStyle, CHART_THEME } from '../components/ds';
import type { Column } from '../components/ds';
import {
  buildPlantingRows, buildHarvestRows, summarizeActivities, harvestedCount, tHa,
  type PlantingRow, type HarvestRow,
} from '../lib/reports';

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
  skipped:     'مُتجاوَزة',
  closed:      'مُغلَق',
  active:      'نشط',
  unknown:     'غير محدّدة',
};

const ACTIVITY_TYPE_LABELS: Record<string, string> = {
  planting:      'بذر/زراعة',
  fertilization: 'تسميد',
  irrigation:    'ريّ',
  spraying:      'رشّ',
  pruning:       'تقليم',
  harvest:       'حصاد',
  scouting:      'كشف/مسح',
  unknown:       'غير محدّد',
};

const CHART_COLORS = ['#16a34a', '#38bdf8', '#f59e0b', '#a855f7', '#ef4444', '#14b8a6', '#eab308'];

const usd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n ?? 0);

const num = (n: number) => (n ?? 0).toLocaleString('en-US');

// هروب CSV قياسيّ (RFC 4180): اقتبس القيمة إن احتوت فاصلة/اقتباس/سطراً جديداً
// وضاعِف الاقتباسات الداخليّة — يمنع تحريف الأعمدة (نصوص عربيّة قد تحوي ",").
function exportToCSV(data: Record<string, unknown>[], filename: string) {
  if (!data.length) return;
  // ترميز آمن مُشترَك: تهريب RFC-4180 + تحييد حقن الصيغ (F-UI-38).
  const headers = csvRow(Object.keys(data[0]));
  const rows = data.map(r => csvRow(Object.values(r)));
  const csv = '﻿' + [headers, ...rows].join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  // إبطال object URL بعد التنزيل — كان يُترَك دون إبطال فيتسرّب (continuation-3 P1).
  URL.revokeObjectURL(url);
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
  const { options: fields, isLoading: fieldsLoading, isError: fieldsError, refetch: refetchFields, fieldId, setFieldId } = useSelectedField();
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
            <option key={f.id} value={f.id}>{f.name}{f.crop && f.crop !== '—' ? ` — ${f.crop}` : ''}</option>
          ))}
        </select>
      </div>

      {fieldsLoading && <LoadingState message="جارٍ تحميل قائمة الحقول…" />}
      {fieldsError && (
        <ErrorState title="تعذّر تحميل قائمة الحقول"
          detail="تعذّر الاتصال بخدمة الحقول." onRetry={() => refetchFields()} />
      )}
      {!fieldsLoading && !fieldsError && fields.length === 0 && (
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

// ════════════════════════════════════════════════════════════════
// ملخّصات طراز FieldView — مُجمَّعة على العميل من المواسم/العمليّات الفعليّة.
// نجلب لكلّ حقل مواسمه وعمليّاته عبر useQueries (مُفعَّل لكلّ حقل)، ثمّ نُجمِّع
// منطقاً نقيّاً (lib/reports). صدق: لا تلفيق — null ⇒ «—».
// ════════════════════════════════════════════════════════════════

// عنوان قسم موحّد للملخّصات (RTL) — أيقونة + عنوان + إجراء (تصدير).
function SummaryHeader({ icon: Icon, title, color, action }: {
  icon: typeof Wheat; title: string; color: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2 mb-3">
      <div className="flex items-center gap-2">
        <Icon className="w-4 h-4" style={{ color }} />
        <span className="text-sm font-semibold text-slate-200">{title}</span>
      </div>
      {action}
    </div>
  );
}

// hook التجميع: يجلب مواسم/عمليّات كلّ الحقول. يبقى ضمن ReportsPage (لا hook عامّ
// جديد) — يستعمل دوال الجلب المُصدَّرة من api.ts عبر useQueries.
function useAllFieldsReportData() {
  const tid = useAuthStore((s) => s.tenantId) ?? 'default';
  const fieldsQuery = useSelectedField();
  const fieldIds = useMemo(
    () => fieldsQuery.options.map((f) => f.id),
    [fieldsQuery.options],
  );

  const seasonQueries = useQueries({
    queries: fieldIds.map((id) => ({
      queryKey: ['seasons', tid, id] as const,
      queryFn: () => fetchSeasons(id),
      staleTime: 5 * 60_000,
      retry: false,
    })),
  });

  const activityQueries = useQueries({
    queries: fieldIds.map((id) => ({
      queryKey: ['activities', tid, id] as const,
      queryFn: () => fetchActivities(id),
      staleTime: 2 * 60_000,
      retry: false,
    })),
  });

  const seasons: SeasonSummary[] = useMemo(
    () => seasonQueries.flatMap((q) => (Array.isArray(q.data) ? q.data : [])),
    [seasonQueries],
  );
  const activities: Activity[] = useMemo(
    () => activityQueries.flatMap((q) => (Array.isArray(q.data) ? q.data : [])),
    [activityQueries],
  );

  const isLoading =
    fieldsQuery.isLoading ||
    seasonQueries.some((q) => q.isLoading) ||
    activityQueries.some((q) => q.isLoading);
  // خطأ الحقول وحده يُعتبر فشلاً صريحاً للقسم؛ فشل جلب حقل مفرد لا يُسقِط الكلّ
  // (نعرض ما نجح بصدق). يُعلَن وجود فشل جزئيّ ليُذكَر بنزاهة في الواجهة.
  const fieldsError = fieldsQuery.isError;
  const partialError =
    seasonQueries.some((q) => q.isError) || activityQueries.some((q) => q.isError);

  return {
    fields: fieldsQuery.options,
    seasons,
    activities,
    isLoading,
    fieldsError,
    partialError,
    refetch: () => fieldsQuery.refetch(),
    fieldsErrorObj: fieldsQuery.error,
  };
}

// رسالة خطأ صادقة من رمز الحالة (مشترَكة بين أقسام الملخّص).
function honestDetail(err: unknown): string {
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 503) return 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
  if (status === 403) return 'لا تملك صلاحية عرض هذه البيانات (field:view).';
  return 'تعذّر الاتصال بالخدمة.';
}

// ملاحظة نزاهة عند فشل جلب بعض الحقول (لا نُخفي نقصاً).
function PartialNote() {
  return (
    <p className="text-[11px] text-amber-400/90 mt-2" dir="rtl">
      تنبيه نزاهة: تعذّر جلب بيانات بعض الحقول — الملخّص أدناه مبنيّ على ما تَوفّر فقط.
    </p>
  );
}

// ── ملخّص الزراعة ────────────────────────────────────────────────
function PlantingSummary() {
  const { fields, seasons, isLoading, fieldsError, partialError, refetch, fieldsErrorObj } =
    useAllFieldsReportData();

  if (isLoading) return <LoadingState message="جارٍ تجميع ملخّص الزراعة…" />;
  if (fieldsError)
    return <ErrorState title="تعذّر تحميل ملخّص الزراعة" detail={honestDetail(fieldsErrorObj)} onRetry={refetch} />;

  const rows = buildPlantingRows(seasons, fields);

  if (rows.length === 0) {
    return (
      <>
        {partialError && <PartialNote />}
        <EmptyState
          icon={<Sprout className="w-8 h-8" />}
          title="لا مواسم مُسجَّلة بعد"
          hint="أنشئ موسماً لحقل (محصول/صنف/تاريخ بذار) ليظهر في ملخّص الزراعة."
        />
      </>
    );
  }

  const columns: Column<PlantingRow & Record<string, unknown>>[] = [
    { key: 'field_name', label: 'الحقل', sortable: true },
    { key: 'crop', label: 'المحصول', sortable: true,
      render: (r) => ACTIVITY_TYPE_LABELS[r.crop] ?? r.crop },
    { key: 'cultivar', label: 'الصنف/الهجين',
      render: (r) => r.cultivar ?? '—' },
    { key: 'sowing_date', label: 'تاريخ البذار', sortable: true,
      render: (r) => r.sowing_date ?? '—' },
    { key: 'area_ha', label: 'المساحة (هـ)', align: 'end', sortable: true,
      render: (r) => (r.area_ha != null ? r.area_ha.toLocaleString('en-US') : '—') },
    { key: 'status', label: 'الحالة', align: 'center',
      render: (r) => STATUS_LABELS[r.status] ?? r.status },
  ];

  const csv = rows.map((r) => ({
    field: r.field_name, crop: r.crop, cultivar: r.cultivar ?? '',
    sowing_date: r.sowing_date ?? '', area_ha: r.area_ha ?? '', status: r.status,
  }));

  return (
    <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
      <SummaryHeader
        icon={Sprout} title="ملخّص الزراعة (لكلّ موسم/حقل)" color="#16a34a"
        action={
          <button onClick={() => exportToCSV(csv, 'SAHOOL_Planting_Summary.csv')}
            className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 print:hidden">
            <Download className="w-3 h-3" /> CSV
          </button>
        }
      />
      {partialError && <PartialNote />}
      <div className="mt-2">
        <DataTable
          rows={rows as (PlantingRow & Record<string, unknown>)[]}
          columns={columns}
          rowKey={(r) => r.season_id}
          emptyTitle="لا مواسم مُسجَّلة بعد"
        />
      </div>
    </div>
  );
}

// ── ملخّص الحصاد ─────────────────────────────────────────────────
function HarvestSummary() {
  const { fields, seasons, isLoading, fieldsError, partialError, refetch, fieldsErrorObj } =
    useAllFieldsReportData();

  if (isLoading) return <LoadingState message="جارٍ تجميع ملخّص الحصاد…" />;
  if (fieldsError)
    return <ErrorState title="تعذّر تحميل ملخّص الحصاد" detail={honestDetail(fieldsErrorObj)} onRetry={refetch} />;

  const rows = buildHarvestRows(seasons, fields);

  if (rows.length === 0) {
    return (
      <>
        {partialError && <PartialNote />}
        <EmptyState
          icon={<Wheat className="w-8 h-8" />}
          title="لا مواسم مُسجَّلة بعد"
          hint="بعد الحصاد، سجّل الغلّة الفعليّة للموسم لتظهر هنا مقابل الغلّة المستهدفة."
        />
      </>
    );
  }

  const harvested = harvestedCount(rows);

  const columns: Column<HarvestRow & Record<string, unknown>>[] = [
    { key: 'field_name', label: 'الحقل', sortable: true },
    { key: 'crop', label: 'المحصول', sortable: true,
      render: (r) => ACTIVITY_TYPE_LABELS[r.crop] ?? r.crop },
    { key: 'actual_t_ha', label: 'الغلّة الفعليّة (ط/هـ)', align: 'end', sortable: true,
      render: (r) => tHa(r.actual_t_ha) },
    { key: 'target_t_ha', label: 'المستهدفة (ط/هـ)', align: 'end', sortable: true,
      render: (r) => tHa(r.target_t_ha) },
    { key: 'gap_t_ha', label: 'الفجوة (ط/هـ)', align: 'end', sortable: true,
      render: (r) => {
        if (r.gap_t_ha == null) return '—';
        const c = r.gap_t_ha > 0 ? '#16a34a' : r.gap_t_ha < 0 ? '#dc2626' : '#9ca3af';
        const sign = r.gap_t_ha > 0 ? '+' : '';
        return <span style={{ color: c, fontWeight: 600 }}>{sign}{r.gap_t_ha.toFixed(2)}</span>;
      } },
    { key: 'status', label: 'الحالة', align: 'center',
      render: (r) => STATUS_LABELS[r.status] ?? r.status },
  ];

  const csv = rows.map((r) => ({
    field: r.field_name, crop: r.crop,
    actual_t_ha: r.actual_t_ha ?? '', target_t_ha: r.target_t_ha ?? '',
    gap_t_ha: r.gap_t_ha ?? '', status: r.status,
  }));

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <KpiCard label="مواسم"               value={num(rows.length)} icon={Sprout}     color="#a855f7" />
        <KpiCard label="مواسم بغلّة مُسجَّلة" value={num(harvested)}   icon={Wheat}      color="#16a34a" />
        <KpiCard label="بانتظار الحصاد"       value={num(rows.length - harvested)} icon={ListChecks} color="#f59e0b" />
      </div>

      <div className="rounded-xl p-4 border" style={{ background: '#0f1117', borderColor: '#334155' }}>
        <SummaryHeader
          icon={Wheat} title="ملخّص الحصاد (الفعليّ مقابل المستهدف)" color="#16a34a"
          action={
            <button onClick={() => exportToCSV(csv, 'SAHOOL_Harvest_Summary.csv')}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 print:hidden">
              <Download className="w-3 h-3" /> CSV
            </button>
          }
        />
        {partialError && <PartialNote />}
        <div className="mt-2">
          <DataTable
            rows={rows as (HarvestRow & Record<string, unknown>)[]}
            columns={columns}
            rowKey={(r) => r.season_id}
            emptyTitle="لا مواسم مُسجَّلة بعد"
          />
        </div>
        <p className="text-[11px] text-slate-500 mt-2">«—» تعني أنّ الغلّة لم تُسجَّل بعد — لا أرقام مُلفَّقة.</p>
      </div>
    </div>
  );
}

// ── ملخّص التطبيق/العمليّات ───────────────────────────────────────
function ApplicationSummary() {
  const { activities, isLoading, fieldsError, partialError, refetch, fieldsErrorObj } =
    useAllFieldsReportData();

  if (isLoading) return <LoadingState message="جارٍ تجميع ملخّص العمليّات…" />;
  if (fieldsError)
    return <ErrorState title="تعذّر تحميل ملخّص العمليّات" detail={honestDetail(fieldsErrorObj)} onRetry={refetch} />;

  const summary = summarizeActivities(activities);

  if (summary.total === 0) {
    return (
      <>
        {partialError && <PartialNote />}
        <EmptyState
          icon={<ClipboardList className="w-8 h-8" />}
          title="لا عمليّات مُسجَّلة بعد"
          hint="سجّل عمليّات ميدانيّة (رشّ/تسميد/ريّ/حصاد…) لتظهر هنا حسب النوع والحالة."
        />
      </>
    );
  }

  const byType = Object.entries(summary.by_type).map(([k, v]) => ({
    type: ACTIVITY_TYPE_LABELS[k] ?? k, count: v,
  }));
  const byStatus = Object.entries(summary.by_status).map(([k, v]) => ({
    status: STATUS_LABELS[k] ?? k, count: v,
  }));

  const csv = Object.entries(summary.by_type).map(([k, v]) => ({
    activity_type: ACTIVITY_TYPE_LABELS[k] ?? k, count: v,
  }));

  return (
    <div className="space-y-4">
      {partialError && <PartialNote />}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <KpiCard label="إجماليّ العمليّات" value={num(summary.total)}                       icon={ClipboardList} color="#14b8a6" />
        <KpiCard label="أنواع العمليّات"   value={num(Object.keys(summary.by_type).length)}  icon={Layers}        color="#38bdf8" />
        <KpiCard label="حالات"             value={num(Object.keys(summary.by_status).length)} icon={ListChecks}    color="#f59e0b" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <BarChartCard
          title="العمليّات حسب النوع"
          data={byType}
          xKey="type"
          series={[{ dataKey: 'count', name: 'العدد', color: '#14b8a6' }]}
          barSize={26}
          height={200}
          tooltipFormatter={(v) => [num(Number(v)), 'عدد']}
          action={
            <button onClick={() => exportToCSV(csv, 'SAHOOL_Application_Summary.csv')}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 print:hidden">
              <Download className="w-3 h-3" /> CSV
            </button>
          }
        />
        <BarChartCard
          title="العمليّات حسب الحالة"
          data={byStatus}
          xKey="status"
          series={[{ dataKey: 'count', name: 'العدد', color: '#a855f7' }]}
          barSize={26}
          height={200}
          tooltipFormatter={(v) => [num(Number(v)), 'عدد']}
        />
      </div>
      <p className="text-[11px] text-slate-500" dir="rtl">
        ملاحظة نزاهة: لا تُسجَّل تكلفة لكلّ عمليّة في مصدر البيانات الحاليّ، لذا يقتصر الملخّص على
        العدد حسب النوع/الحالة. تكاليف المهام متاحة في تبويب «لوحة المزرعة» (ملخّص التكلفة).
      </p>
    </div>
  );
}

// CSS نطاق الطباعة: عند الطباعة (print) نُخفي عناصر التحكّم (التبويبات/الأزرار)
// ونضبط الخلفيّة بيضاء لمخرج PDF نظيف عبر window.print() — لا تبعيّة PDF ثقيلة.
const PRINT_CSS = `
@media print {
  body { background: #ffffff !important; }
  .reports-no-print { display: none !important; }
  .reports-print-area { color: #111 !important; }
  .reports-print-area .rounded-xl { box-shadow: none !important; }
}
`;

type Tab = 'planting' | 'harvest' | 'application' | 'farm' | 'field';

const TABS: [Tab, string][] = [
  ['planting',    'ملخّص الزراعة'],
  ['harvest',     'ملخّص الحصاد'],
  ['application', 'ملخّص العمليّات'],
  ['farm',        'لوحة المزرعة'],
  ['field',       'ملخّص حقل'],
];

export function ReportsPage() {
  const [tab, setTab] = useState<Tab>('planting');

  return (
    <div className="space-y-5 max-w-5xl mx-auto reports-print-area" dir="rtl">
      <style>{PRINT_CSS}</style>
      <div className="flex flex-wrap items-center gap-3 justify-between reports-no-print">
        <div>
          <h2 className="text-xl font-bold text-slate-100">التقارير والتحليلات</h2>
          <p className="text-sm text-slate-400">ملخّصات طراز FieldView — مُجمَّعة من بياناتك الفعليّة (زراعة/حصاد/عمليّات)</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex flex-wrap gap-2">
            {TABS.map(([t, label]) => (
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
          <button onClick={() => window.print()}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium"
            style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
            title="طباعة التقرير الحاليّ كـPDF (طباعة المتصفّح)">
            <Printer className="w-4 h-4" /> طباعة / PDF
          </button>
        </div>
      </div>

      {tab === 'planting' ? (
        <PlantingSummary />
      ) : tab === 'harvest' ? (
        <HarvestSummary />
      ) : tab === 'application' ? (
        <ApplicationSummary />
      ) : tab === 'farm' ? (
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
