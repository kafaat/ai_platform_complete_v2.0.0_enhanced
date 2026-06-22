// ═══════════════════════════════════════════════════════════════
// SAHOOL — YieldAnalysisPage (تحليل الغلّة) — نمط FieldView · قراءة فقط
// GET /api/v1/analysis/yield: لكلّ موسم مُقارَنة الزراعة↔الحصاد (محصول/هجين/تاريخ
// بذار/غلّة مستهدفة↔فعليّة)، ومقارنة أداء الهجن (متوسّط الغلّة الفعليّة لكلّ هجين
// عبر الحقول/المواسم). نطاق اختياريّ: حقل + موسم (season_id).
//
// الصدق أوّلاً: كلّ الأرقام من جدول seasons المُخزَّن فقط — لا تلفيق. الغلّة الفعليّة
// قد تكون null (لم تُسجَّل بعد) ⇒ تُعرَض «—» لا 0. حين لا حصاد مُسجَّل تكون قوائم
// الأداء فارغة وتُعرَض ملاحظة provenance.note_ar الصريحة. 503 (DB) / 403 ⇒ حالة خطأ
// صادقة. عرض فقط (يطابق DecisionConfidencePage بصريّاً ولونيّاً). الغلّة بالطنّ/هكتار.
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import { Wheat, MapPin, CalendarRange, Sprout, Trophy, AlertTriangle, Info } from 'lucide-react';
import { useYieldAnalysis } from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { asApiError } from '../services/api';
import type { YieldPlantingHarvestRow, YieldHybridPerformanceRow } from '../services/api';
import { ErrorState, LoadingState, EmptyState } from '../components/StateViews';
import { DataTable, BarChartCard, type Column } from '../components/ds';

// طنّ/هكتار → نصّ (null ⇒ «—»، لا 0 مُختلَق). صدق العرض.
function tText(v: number | null): string {
  return v != null ? v.toFixed(2) : '—';
}

// لون فجوة الغلّة (فعليّ↔مستهدف): موجب أخضر، سالب أحمر، صفر/غياب رماديّ.
function gapHex(gap: number | null): string {
  if (gap == null) return '#9ca3af';
  if (gap > 0) return '#16a34a';
  if (gap < 0) return '#dc2626';
  return '#9ca3af';
}

export default function YieldAnalysisPage() {
  const {
    fieldId, options, isLoading: fieldsLoading, isError: fieldsError, setFieldId,
  } = useSelectedField();

  // الموسم المُختار (season_id) — اختياريّ؛ '' = كلّ مواسم النطاق. مُشتقّ محليّاً.
  const [season, setSeason] = useState('');

  const query = useYieldAnalysis(fieldId || undefined, season || undefined);
  const data = query.data;

  // 403/404 (RBAC أو الميزة) — رسالة ودودة لا حالة خطأ صاخبة.
  const forbidden = query.isError && asApiError(query.error).response?.status === 403;

  // قائمة المواسم لمنتقي الموسم — من الزراعة↔الحصاد (season_id + المحصول للتمييز).
  const seasonOptions = useMemo(() => {
    const rows = data?.planting_vs_harvest ?? [];
    return rows
      .filter((r): r is YieldPlantingHarvestRow & { season_id: string } => !!r.season_id)
      .map((r) => ({
        id: r.season_id,
        label: `${r.crop || 'موسم'}${r.sowing_date ? ` · ${r.sowing_date}` : ''}`,
      }));
  }, [data]);

  // بيانات الرسم الشريطيّ: مقارنة المستهدف↔الفعليّ لكلّ موسم (الفعليّ فقط حين توفّر).
  const chartData = useMemo(() => {
    const rows = data?.planting_vs_harvest ?? [];
    return rows
      .filter((r) => r.actual_yield_t_ha != null || r.target_yield_t_ha != null)
      .map((r) => ({
        name: r.field_name || r.field_id || r.season_id || '—',
        target: r.target_yield_t_ha,
        actual: r.actual_yield_t_ha,
      }));
  }, [data]);

  const phRows: (YieldPlantingHarvestRow & Record<string, unknown>)[] =
    (data?.planting_vs_harvest ?? []) as (YieldPlantingHarvestRow & Record<string, unknown>)[];
  const hybridRows: (YieldHybridPerformanceRow & Record<string, unknown>)[] =
    (data?.hybrid_performance ?? []) as (YieldHybridPerformanceRow & Record<string, unknown>)[];

  // أعمدة جدول الزراعة↔الحصاد.
  const phColumns: Column<YieldPlantingHarvestRow & Record<string, unknown>>[] = [
    { key: 'field_name', label: 'الحقل', render: (r) => r.field_name || r.field_id || '—' },
    { key: 'crop', label: 'المحصول', render: (r) => r.crop || '—' },
    { key: 'hybrid', label: 'الهجين/الصنف', render: (r) => r.hybrid || '—' },
    { key: 'sowing_date', label: 'تاريخ البذار', render: (r) => r.sowing_date || '—' },
    {
      key: 'target_yield_t_ha', label: 'مستهدف (ط/هـ)', align: 'end',
      render: (r) => tText(r.target_yield_t_ha),
    },
    {
      key: 'actual_yield_t_ha', label: 'فعليّ (ط/هـ)', align: 'end',
      render: (r) => (
        <span style={{ fontWeight: 700, color: r.actual_yield_t_ha != null ? '#e2e8f0' : '#64748b' }}>
          {tText(r.actual_yield_t_ha)}
        </span>
      ),
    },
    {
      key: 'yield_gap_t_ha', label: 'الفجوة', align: 'end',
      render: (r) => (
        <span style={{ fontWeight: 700, color: gapHex(r.yield_gap_t_ha) }}>
          {r.yield_gap_t_ha != null ? (r.yield_gap_t_ha > 0 ? '+' : '') + r.yield_gap_t_ha.toFixed(2) : '—'}
        </span>
      ),
    },
  ];

  const hybridColumns: Column<YieldHybridPerformanceRow & Record<string, unknown>>[] = [
    {
      key: 'hybrid', label: 'الهجين/الصنف',
      render: (r, i) => (
        <span className="inline-flex items-center gap-2">
          {i === 0 && <Trophy className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />}
          <span style={{ fontWeight: 700 }}>{r.hybrid}</span>
        </span>
      ),
    },
    { key: 'crops', label: 'المحاصيل', render: (r) => (r.crops.length ? r.crops.join('، ') : '—') },
    { key: 'season_count', label: 'مواسم', align: 'end', render: (r) => String(r.season_count) },
    { key: 'field_count', label: 'حقول', align: 'end', render: (r) => String(r.field_count) },
    {
      key: 'avg_yield_t_ha', label: 'متوسّط (ط/هـ)', align: 'end',
      render: (r) => <span style={{ fontWeight: 800, color: '#16a34a' }}>{r.avg_yield_t_ha.toFixed(2)}</span>,
    },
    {
      key: 'min_yield_t_ha', label: 'المدى (ط/هـ)', align: 'end',
      render: (r) => `${r.min_yield_t_ha.toFixed(2)} – ${r.max_yield_t_ha.toFixed(2)}`,
    },
  ];

  return (
    <div className="space-y-6 max-w-4xl mx-auto" dir="rtl">
      {/* ── الترويسة ── */}
      <div className="flex items-center gap-2">
        <Wheat className="w-5 h-5 text-amber-400" aria-hidden="true" />
        <h2 className="text-xl font-bold text-slate-100">تحليل الغلّة</h2>
        <span
          className="text-[11px] px-2 py-0.5 rounded-full font-semibold"
          style={{ background: '#78350f33', color: '#fbbf24' }}
        >
          تجريبيّ
        </span>
      </div>
      <p className="text-sm text-slate-400">
        على نمط <span className="text-amber-300">FieldView</span>: مقارنة الزراعة↔الحصاد لكلّ موسم
        (محصول/هجين/تاريخ بذار/غلّة مستهدفة↔فعليّة) ومقارنة أداء الهجن. صدق أوّلاً: كلّ الأرقام من
        المواسم المُخزَّنة فقط (الغلّة بالطنّ/هكتار) — الغلّة غير المُسجَّلة تُعرَض «—» لا صفراً، والفجوات
        مُعلَنة صراحةً. عرض فقط.
      </p>

      {/* ── منتقي الحقل + الموسم ── */}
      <div
        className="rounded-xl border p-4 flex flex-wrap gap-4"
        style={{ background: '#1e293b', borderColor: '#334155' }}
      >
        <label className="flex flex-col gap-1 min-w-[12rem]">
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <MapPin className="w-3.5 h-3.5 text-amber-400" /> الحقل (اختياريّ)
          </span>
          {fieldsLoading ? (
            <span className="text-[12px] text-slate-500">جارٍ جلب الحقول…</span>
          ) : fieldsError ? (
            <span className="text-[12px] text-amber-300/80">تعذّر جلب قائمة الحقول.</span>
          ) : (
            <select
              value={fieldId} onChange={(e) => { setFieldId(e.target.value); setSeason(''); }}
              className="px-3 py-2 rounded-lg text-sm"
              style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
            >
              <option value="">— كلّ الحقول —</option>
              {options.map((o) => <option key={o.id} value={o.id}>{o.name || o.id}</option>)}
            </select>
          )}
        </label>

        <label className="flex flex-col gap-1 min-w-[12rem]">
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <CalendarRange className="w-3.5 h-3.5 text-amber-400" /> الموسم (اختياريّ)
          </span>
          <select
            value={season} onChange={(e) => setSeason(e.target.value)}
            disabled={seasonOptions.length === 0}
            className="px-3 py-2 rounded-lg text-sm"
            style={{ background: '#0f1117', border: '1px solid #334155', color: '#e2e8f0' }}
          >
            <option value="">— كلّ المواسم —</option>
            {seasonOptions.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
      </div>

      {/* ── الحالات ── */}
      {query.isLoading && <LoadingState message="جارٍ جلب تحليل الغلّة…" />}

      {forbidden && (
        <EmptyState
          icon={<Wheat className="w-8 h-8" />}
          title="لا صلاحية لعرض تحليل الغلّة"
          hint="هذه الصفحة تتطلّب صلاحية analytics:view. تواصل مع مسؤول المستأجِر."
        />
      )}

      {query.isError && !forbidden && (
        <ErrorState
          title="تعذّر جلب تحليل الغلّة"
          detail="قد تكون قاعدة البيانات غير متاحة (503) أو الحقل ليس لمستأجِرك."
          onRetry={() => query.refetch()}
        />
      )}

      {data && (
        <div className="space-y-6">
          {/* ── الملخّص ── */}
          <section
            className="rounded-xl border p-4 grid grid-cols-3 gap-4"
            style={{ background: '#10151f', borderColor: '#25303f' }}
          >
            <Stat label="مواسم مُسجَّلة" value={data.summary.seasons_total} icon={<Sprout className="w-4 h-4 text-amber-400" />} />
            <Stat label="مواسم بحصاد" value={data.summary.seasons_with_harvest} icon={<Wheat className="w-4 h-4 text-emerald-400" />} />
            <Stat label="هجن مُقارَنة" value={data.summary.hybrids_compared} icon={<Trophy className="w-4 h-4 text-amber-400" />} />
          </section>

          {/* ── ملاحظة الصدق (فجوة بيانات) ── */}
          {data.provenance.note_ar && (
            <div
              className="rounded-xl border p-4 flex items-start gap-3"
              style={{ background: '#1e293b', borderColor: '#334155' }}
              role="status"
            >
              <Info className="w-5 h-5 text-amber-300 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div className="text-[12px] text-slate-300">{data.provenance.note_ar}</div>
            </div>
          )}

          {/* ── الزراعة↔الحصاد: رسم شريطيّ ── */}
          {chartData.length > 0 && (
            <BarChartCard
              title="المستهدف مقابل الفعليّ (طنّ/هكتار)"
              icon={Wheat}
              data={chartData}
              xKey="name"
              series={[
                { dataKey: 'target', name: 'مستهدف', color: '#64748b' },
                { dataKey: 'actual', name: 'فعليّ', color: '#16a34a' },
              ]}
              showLegend
              emptyTitle="لا غلّة لعرضها"
            />
          )}

          {/* ── الزراعة↔الحصاد: جدول ── */}
          <section
            className="rounded-xl border p-4"
            style={{ background: '#10151f', borderColor: '#25303f' }}
          >
            <h3 className="text-sm font-bold text-slate-200 mb-3 flex items-center gap-2">
              <Sprout className="w-4 h-4 text-amber-400" /> الزراعة ↔ الحصاد لكلّ موسم
            </h3>
            <DataTable
              columns={phColumns}
              rows={phRows}
              rowKey={(r, i) => String(r.season_id ?? i)}
              emptyTitle="لا مواسم في هذا النطاق"
              emptyHint="أنشئ موسماً (محصول/هجين/تاريخ بذار) لتظهر مقارنة الزراعة↔الحصاد."
              emptyIcon={<Sprout className="w-8 h-8" />}
            />
          </section>

          {/* ── أداء الهجن ── */}
          <section
            className="rounded-xl border p-4"
            style={{ background: '#10151f', borderColor: '#25303f' }}
          >
            <h3 className="text-sm font-bold text-slate-200 mb-3 flex items-center gap-2">
              <Trophy className="w-4 h-4 text-amber-400" /> أداء الهجن (متوسّط الغلّة الفعليّة)
            </h3>
            <DataTable
              columns={hybridColumns}
              rows={hybridRows}
              rowKey={(r, i) => `${r.hybrid}-${i}`}
              emptyTitle="لا حصاد مُسجَّل لأيّ هجين"
              emptyHint="سجّل الغلّة الفعليّة بعد الحصاد (مع صنف/هجين) لتظهر مقارنة الأداء. لا تلفيق."
              emptyIcon={<AlertTriangle className="w-8 h-8" />}
            />
          </section>
        </div>
      )}
    </div>
  );
}

// خليّة إحصاء صغيرة (تطابق نمط بطاقات الملخّص الداكنة).
function Stat({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs text-slate-400 flex items-center gap-1">{icon}{label}</span>
      <span className="text-2xl font-extrabold text-slate-100">{value}</span>
    </div>
  );
}
