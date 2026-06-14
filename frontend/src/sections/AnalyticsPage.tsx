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
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from 'react';
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { TrendingUp, BarChart3, Activity, Droplets, Lightbulb } from 'lucide-react';
import {
  useFields, useFieldTimeseries, useSeasons,
  useIndicatorGrid, useFieldRecommendations,
} from '../hooks/useApi';
import { LoadingState, EmptyState, ErrorState } from '../components/StateViews';

const PRIORITY_STYLE: Record<string, { bg: string; fg: string; label: string }> = {
  high:   { bg: '#3f1d1d', fg: '#f87171', label: 'عالية' },
  medium: { bg: '#3a2f17', fg: '#fbbf24', label: 'متوسّطة' },
  low:    { bg: '#16331e', fg: '#4ade80', label: 'منخفضة' },
};

const CAT_AR: Record<string, string> = {
  irrigation: 'الريّ', fertilizer: 'التسميد', disease: 'الأمراض', yield: 'الإنتاج',
};

function ChartCard({ title, icon: Icon, children }: { title: string; icon: any; children: React.ReactNode }) {
  return (
    <div className="rounded-xl p-4 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
      <div className="flex items-center gap-2 mb-4">
        <Icon className="w-4 h-4 text-emerald-400" />
        <span className="text-sm font-semibold text-slate-200">{title}</span>
      </div>
      {children}
    </div>
  );
}

// حاوية صغيرة: تختار حالة العرض الصادقة (تحميل/خطأ/فراغ) أو ترسم المحتوى.
function Panel({
  isLoading, isError, isEmpty, onRetry, height = 200, emptyHint, children,
}: {
  isLoading: boolean; isError: boolean; isEmpty: boolean;
  onRetry?: () => void; height?: number; emptyHint?: string; children: React.ReactNode;
}) {
  if (isLoading) return <div style={{ height }}><LoadingState message="جارٍ التحميل…" /></div>;
  if (isError)   return <div style={{ height }}><ErrorState onRetry={onRetry} /></div>;
  if (isEmpty)   return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
    <EmptyState title="لا توجد بيانات بعد" hint={emptyHint} />
  </div>;
  return <>{children}</>;
}

export default function AnalyticsPage() {
  const fieldsQ = useFields();
  const fields: any[] = useMemo(() => fieldsQ.data?.fields ?? [], [fieldsQ.data]);

  const [picked, setPicked] = useState<string>('');
  const activeFieldId = picked || (fields[0]?.field_id ?? '');
  const activeFieldName =
    fields.find((f) => f.field_id === activeFieldId)?.field_name ??
    fields.find((f) => f.field_id === activeFieldId)?.name_ar ?? activeFieldId;

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

  if (fieldsQ.isLoading) return <LoadingState message="جارٍ تحميل الحقول…" />;
  if (fieldsQ.isError)   return <ErrorState title="تعذّر تحميل الحقول" onRetry={() => fieldsQ.refetch()} />;
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
          onChange={(e) => setPicked(e.target.value)}
          className="px-3 py-2 rounded-lg text-sm"
          style={{ background: '#1e293b', border: '1px solid #334155', color: '#e2e8f0' }}
        >
          {fields.map((f) => (
            <option key={f.field_id} value={f.field_id}>
              {f.field_name ?? f.name_ar ?? f.field_id}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* الإنتاجيّة المقدَّرة (محاكاة الموسم) */}
        <ChartCard title="الإنتاجيّة المقدَّرة (طن/هـ)" icon={TrendingUp}>
          <Panel
            isLoading={seasQ.isLoading}
            isError={seasQ.isError}
            isEmpty={yieldData.length === 0}
            onRetry={() => seasQ.refetch()}
            emptyHint="شغّل محاكاة الموسم لعرض تقدير الإنتاجيّة."
          >
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={yieldData} barSize={42}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="label" tick={{ fill: '#64748b', fontSize: 10 }} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} width={28} />
                <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} itemStyle={{ color: '#e2e8f0' }} />
                <Bar dataKey="yield" name="طن/هـ" radius={[6, 6, 0, 0]} fill="#16a34a" />
              </BarChart>
            </ResponsiveContainer>
          </Panel>
        </ChartCard>

        {/* اتّجاه NDVI الحقيقيّ */}
        <ChartCard title="اتّجاه NDVI عبر الزمن" icon={Activity}>
          <Panel
            isLoading={tsQ.isLoading}
            isError={tsQ.isError}
            isEmpty={ndviData.length === 0}
            onRetry={() => tsQ.refetch()}
            emptyHint="لا توجد مشاهد Sentinel-2 صافية لهذا الحقل بعد."
          >
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={ndviData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 9 }} tickLine={false} interval="preserveStartEnd" />
                <YAxis domain={[0, 1]} tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} width={32} />
                <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} itemStyle={{ color: '#e2e8f0' }} />
                <Line type="monotone" dataKey="ndvi" stroke="#16a34a" strokeWidth={2} dot={false} name="NDVI" />
              </LineChart>
            </ResponsiveContainer>
          </Panel>
        </ChartCard>

        {/* رطوبة المناطق (NDMI حقيقيّ) */}
        <ChartCard title="رطوبة المناطق (NDMI)" icon={Droplets}>
          <Panel
            isLoading={moistQ.isLoading}
            isError={moistQ.isError}
            isEmpty={moistureData.length === 0}
            onRetry={() => moistQ.refetch()}
            height={180}
            emptyHint="لا تتوفّر شبكة رطوبة حقيقيّة لهذا الحقل بعد."
          >
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={moistureData} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="zone" tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} />
                <YAxis domain={[-1, 1]} tick={{ fill: '#64748b', fontSize: 11 }} tickLine={false} width={32} />
                <Tooltip contentStyle={{ background: '#0f1117', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }} itemStyle={{ color: '#e2e8f0' }} />
                <Bar dataKey="value" name="NDMI" radius={[6, 6, 0, 0]}>
                  {moistureData.map((m, i) => <Cell key={i} fill={m.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Panel>
        </ChartCard>

        {/* رؤى/توصيات حقيقيّة من المحرّك الموحَّد */}
        <ChartCard title="رؤى وتوصيات الحقل" icon={BarChart3}>
          <Panel
            isLoading={recQ.isLoading}
            isError={recQ.isError}
            isEmpty={recs.length === 0}
            onRetry={() => recQ.refetch()}
            height={200}
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
          </Panel>
        </ChartCard>
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
