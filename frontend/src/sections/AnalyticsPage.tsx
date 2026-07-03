// ═══════════════════════════════════════════════════════════════
// SAHOOL — AnalyticsPage (بيانات حقيقيّة، لا تلفيق)
// كانت هذه الشاشة تعرض أرقاماً ثابتة/عشوائيّة (Math.random) لا علاقة لها
// بالمستأجِر. أُعيد ربطها بالكامل بمصادر حيّة:
//   • قائمة الحقول        ← useFields           (/api/v1/fields)
//   • اتّجاه NDVI         ← useFieldTimeseries  (raster-service، COG حقيقيّ)
//   • الإنتاجيّة المقدَّرة ← useSeasons (sim_*)  (محاكاة الموسم المخزَّنة)
//   • رطوبة المناطق       ← useIndicatorGrid ndmi (شبكة بكسليّة حقيقيّة)
//   • رؤى/توصيات          ← useFieldRecommendations (المحرّك الموحَّد)
// كلّ بطاقة تعرض حالة صادقة (تحميل/فراغ/خطأ) عند غياب البيانات — لا قيم مخترعة.
//
// عرضيّاً: مُوحَّدة على نظام التصميم — البطاقات/الرسوم عبر مُغلِّفات ds/charts
// (LineChartCard/BarChartCard/ChartShell) بثيم Tooltip داكن موحّد بدل تكرار
// ResponsiveContainer + المحاور inline. البيانات والسلوك دون تغيير.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import { TrendingUp, Activity, Droplets, BarChart3, Lightbulb } from 'lucide-react';
import {
  useFieldTimeseries, useSeasons,
  useIndicatorGrid, useFieldRecommendations,
} from '../hooks/useApi';
import { useSelectedField } from '../hooks/useSelectedField';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';
import { LineChartCard, BarChartCard, ChartShell } from '../components/ds';

const PRIORITY_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  high:   { bg: '#3f1d1d', fg: '#f87171', label: 'عالية' },
  medium: { bg: '#3a2f17', fg: '#fbbf24', label: 'متوسّطة' },
  low:    { bg: '#16331e', fg: '#4ade80', label: 'منخفضة' },
};

const CAT_AR: Record<string, string> = {
  irrigation: 'الريّ', fertilizer: 'التسميد', disease: 'الأمراض', yield: 'الإنتاج',
};

export default function AnalyticsPage() {
  const { options: fields, isLoading: fieldsLoading, isError: fieldsError, refetch: refetchFields, fieldId: activeFieldId, setFieldId } = useSelectedField();
  const activeFieldName = fields.find((f) => f.id === activeFieldId)?.name ?? activeFieldId;

  // مصادر حيّة لكلّ بطاقة (مُفعَّلة فقط عند وجود حقل مختار)
  const tsQ   = useFieldTimeseries(activeFieldId, 'ndvi', '', { enabled: !!activeFieldId });
  const seasQ = useSeasons(activeFieldId || undefined);
  const moistQ = useIndicatorGrid(activeFieldId, 'ndmi', 'latest');
  const recQ  = useFieldRecommendations(activeFieldId || undefined);

  // ── NDVI: نقاط زمنيّة حقيقيّة (datetime/mean) ──
  const ndviData = useMemo(() =>
    (tsQ.data?.points ?? []).map((p) => ({
      date: (p.datetime || '').slice(0, 10),
      ndvi: typeof p.mean === 'number' ? +p.mean.toFixed(3) : null,
    })).filter((d) => d.ndvi != null),
  [tsQ.data]);

  // ── الإنتاجيّة: نتائج محاكاة الموسم المخزَّنة (kg/ha → t/ha) ──
  const yieldData = useMemo(() =>
    (seasQ.data ?? [])
      .filter((s) => typeof s.sim_yield_kg_ha === 'number')
      .map((s) => ({
        label: (s.crops?.[0] ?? 'موسم') + (s.sowing_date ? ` ${s.sowing_date.slice(0, 4)}` : ''),
        yield: +((s.sim_yield_kg_ha as number) / 1000).toFixed(2),
      })),
  [seasQ.data]);

  // ── الرطوبة: متوسّط NDMI لكلّ منطقة شدّة من الشبكة البكسليّة الحقيقيّة ──
  const moistureData = useMemo(() => {
    const zones = moistQ.data?.zones ?? [];
    const sevColor: Record<string, string> = { low: '#dc2626', medium: '#ca8a04', high: '#16a34a' };
    return zones.map((z, i) => ({
      zone: `منطقة ${i + 1}`,
      value: +(z.mean ?? 0).toFixed(3),
      color: sevColor[z.severity] ?? '#65a30d',
    }));
  }, [moistQ.data]);

  const recs = recQ.data?.recommendations ?? [];

  if (fieldsLoading) return <LoadingState message="جارٍ تحميل الحقول…" />;
  if (fieldsError)   return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => refetchFields()} />;
  if (fields.length === 0)
    return <EmptyState title="لا توجد حقول بعد" hint="أضِف حقلاً أوّلاً لعرض التحليلات الحيّة." />;

  return (
    <div className="space-y-5 max-w-7xl mx-auto" dir="rtl">
      <div className="flex flex-wrap items-center gap-3 justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100">التحليلات المتقدّمة</h2>
          <p className="text-sm text-slate-400">مؤشّرات حيّة من Sentinel-2 ومحاكاة المحصول — لكلّ حقل</p>
        </div>
        <select
          value={activeFieldId}
          onChange={(e) => setFieldId(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
        >
          {fields.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}{f.crop && f.crop !== '—' ? ` — ${f.crop}` : ''}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* الإنتاجيّة المقدَّرة (محاكاة الموسم) */}
        <BarChartCard
          title="الإنتاجيّة المقدَّرة (طن/هـ)"
          icon={TrendingUp}
          data={yieldData}
          xKey="label"
          series={[{ dataKey: 'yield', name: 'طن/هـ', color: '#16a34a' }]}
          barSize={42}
          height={200}
          isLoading={seasQ.isLoading}
          isError={seasQ.isError}
          onRetry={() => seasQ.refetch()}
          emptyHint="شغّل محاكاة الموسم لعرض تقدير الإنتاجيّة."
        />

        {/* اتّجاه NDVI الحقيقيّ */}
        <LineChartCard
          title="اتّجاه NDVI عبر الزمن"
          icon={Activity}
          data={ndviData}
          xKey="date"
          series={[{ dataKey: 'ndvi', name: 'NDVI', color: '#16a34a' }]}
          yDomain={[0, 1]}
          height={200}
          isLoading={tsQ.isLoading}
          isError={tsQ.isError}
          onRetry={() => tsQ.refetch()}
          emptyHint="لا توجد مشاهد Sentinel-2 صافية لهذا الحقل بعد."
        />

        {/* رطوبة المناطق (NDMI حقيقيّ) — تلوين فرديّ لكلّ منطقة حسب شدّتها */}
        <BarChartCard
          title="رطوبة المناطق (NDMI)"
          icon={Droplets}
          data={moistureData}
          xKey="zone"
          series={[{ dataKey: 'value', name: 'NDMI' }]}
          barColors={moistureData.map((m) => m.color)}
          barSize={36}
          yDomain={[-1, 1]}
          height={180}
          isLoading={moistQ.isLoading}
          isError={moistQ.isError}
          onRetry={() => moistQ.refetch()}
          emptyHint="لا تتوفّر شبكة رطوبة حقيقيّة لهذا الحقل بعد."
        />

        {/* رؤى/توصيات حقيقيّة من المحرّك الموحَّد */}
        <ChartShell
          title="رؤى وتوصيات الحقل"
          icon={BarChart3}
          height={200}
          isLoading={recQ.isLoading}
          isError={recQ.isError}
          isEmpty={recs.length === 0}
          onRetry={() => recQ.refetch()}
          emptyTitle="لا توجد بيانات بعد"
          emptyHint="لا توجد توصيات حاليّة لهذا الحقل."
        >
          <div className="space-y-2" style={{ maxHeight: 220, overflowY: 'auto' }}>
            {recs.map((r, i) => {
              const ps = PRIORITY_STYLE[r.priority] ?? PRIORITY_STYLE.low;
              return (
                <div key={i} className="rounded-lg p-3" style={{ background: '#0f1117', border: '1px solid #334155' }}>
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-sm font-semibold text-slate-100">{r.title_ar}</span>
                    <span className="text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap"
                      style={{ background: ps.bg, color: ps.fg }}>
                      {CAT_AR[r.category] ?? r.category} · {ps.label}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed">{r.detail_ar}</p>
                </div>
              );
            })}
          </div>
        </ChartShell>
      </div>

      {!recQ.data?.weather_available && recs.length > 0 && (
        <div className="rounded-lg p-3 flex items-center gap-2 text-xs" style={{ background: '#1e293b', border: '1px solid #334155', color: '#94a3b8' }}>
          <Lightbulb className="w-4 h-4 text-amber-400" />
          بعض توصيات الطقس غير متاحة حاليّاً (خدمة الطقس متعذّرة) — التوصيات المعروضة مبنيّة على المتاح.
        </div>
      )}

      <p className="text-[11px] text-slate-500 text-center">
        كلّ الأرقام أعلاه حيّة لحقل: <span className="text-slate-300">{activeFieldName}</span>. عند غياب مصدر، تُعرض حالة صادقة بدل قيمة مخترعة.
      </p>
    </div>
  );
}
