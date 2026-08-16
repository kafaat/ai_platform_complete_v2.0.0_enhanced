// ═══════════════════════════════════════════════════════════════
// SAHOOL — لوحة الاقتصاد والعائد (Economics / ROI Dashboard)
// ───────────────────────────────────────────────────────────────
// نظرة اقتصاديّة للقراءة فقط: إجماليّ تكلفة المهام (USD) + عدد المهام +
// توزيع التكلفة حسب المصدر (نسبة من الإجماليّ) مع سياق المزرعة (مزارع/حقول/
// مساحة) من ملخّص المزرعة. تُبنى على القشرة الموحّدة (FieldCabin) ونظام
// التصميم (Card/StatGrid/Row/Badge/Pill/SectionLabel/ProgressBar).
//
// صدق البيانات: أرقام مالية حيّة من useCostAnalytics فقط — لا fallback وهميّ.
// حالات صريحة: تحميل/خطأ (مع تمييز 503 DB و403 RBAC)/فراغ («لا بيانات تكلفة»).
// القيم الغائبة تُعرَض «—» لا صفراً مُلفَّقاً. سياق المزرعة اختياريّ: إن تعذّر
// لا يُكسَر شيء (يُعرَض «—»). شاشة قراءة فقط.
// ═══════════════════════════════════════════════════════════════
import { useMemo } from 'react';
import {
  Wallet, ListChecks, Layers, DollarSign, Building2, Map as MapIcon,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts';
import { useCostAnalytics, useFarmSummary } from '../hooks/useApi';
import {
  T, T_DARK, Card, Pill, Badge, SectionLabel, Row, StatGrid, ProgressBar, FieldCabin,
} from '../components/ds';

// الصفحة داكنة (نغمة ds الداكنة): أسطح/نصوص من T_DARK؛ ألوان التمييز من T.
const t = T_DARK;

// تسميات عربيّة لمصادر التكلفة (fallback: المفتاح كما هو من الخادم).
const SOURCE_LABELS: Record<string, string> = {
  field_tasks: 'المهام الميدانيّة',
  maintenance: 'الصيانة',
};
const sourceAr = (s: string) => SOURCE_LABELS[s] ?? s;

// تنسيق مبلغ بالدولار (أرقام لاتينيّة موحّدة للماليّات).
const usd = (n: number) =>
  new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(n ?? 0);

// عدد صحيح مُنسَّق أو «—» إن غاب (لا تلفيق صفر).
const fmtCount = (n?: number | null) =>
  typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('en-US') : '—';

// مساحة بالهكتار (منزلة واحدة) أو «—» إن غابت.
const fmtArea = (n?: number | null) =>
  typeof n === 'number' && Number.isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: 1 }) : '—';

// لون ثابت دوّار لشرائح المصادر (تمييز بصريّ بلا دلالة حالة).
const SOURCE_COLORS = [T.gold, T.info, T.green, T.greenDark, T.ndvi3];
const colorFor = (i: number) => SOURCE_COLORS[i % SOURCE_COLORS.length];

export default function EconomicsDashboard() {
  const costQ = useCostAnalytics();
  const farmQ = useFarmSummary();

  const cost = costQ.data;
  const bySource = useMemo(() => (Array.isArray(cost?.by_source) ? cost!.by_source : []), [cost]);
  const totalUsd = typeof cost?.total_usd === 'number' && Number.isFinite(cost.total_usd) ? cost.total_usd : 0;
  const taskCount = typeof cost?.task_count === 'number' && Number.isFinite(cost.task_count) ? cost.task_count : 0;

  // بيانات الرسم البيانيّ — تسمية عربيّة + قيمة المصدر.
  const chartData = useMemo(
    () => bySource.map((s) => ({ source: sourceAr(s.source), total_usd: s.total_usd })),
    [bySource],
  );

  // أعلى مصدر تكلفة (للوسم العلويّ) — يُعلِم القارئ أين يذهب أكبر إنفاق.
  const topSource = useMemo(() => {
    if (bySource.length === 0) return null;
    return bySource.reduce((a, b) => (b.total_usd > a.total_usd ? b : a));
  }, [bySource]);

  const farm = farmQ.data;

  // رسالة خطأ صادقة تميّز سبب الفشل (DB مُعطَّلة / صلاحية / اتصال).
  const errDetail = (err: unknown): string => {
    const status = (err as { response?: { status?: number } })?.response?.status;
    if (status === 503) return 'خدمة التحليلات غير متاحة حاليّاً (قاعدة البيانات معطّلة).';
    if (status === 403) return 'لا تملك صلاحية عرض التحليلات (analytics:view).';
    return 'تعذّر الاتصال بخدمة التحليلات.';
  };

  const isEmpty =
    !costQ.isLoading && !costQ.isError &&
    bySource.length === 0 && totalUsd === 0 && taskCount === 0;

  return (
    <FieldCabin
      tone="dark"
      eyebrow="الاقتصاد"
      title="الاقتصاد والعائد"
      subtitle="تكلفة المهام (USD) + توزيعها حسب المصدر + سياق المزرعة"
      headerRight={
        <Pill tone="info" icon={<Wallet style={{ width: 12, height: 12 }} />}>
          {costQ.isLoading ? 'تحميل…' : usd(totalUsd)}
        </Pill>
      }
      note={
        <>
          نظرة اقتصاديّة حيّة — تكلفة من <code>/analytics/costs</code> وسياق من
          <code>/reports/farm-summary</code>. أرقام مالية حقيقيّة فقط؛ لا بيانات
          متاحة ⇒ «لا بيانات تكلفة» صراحةً لا قيم مُختلَقة. شاشة قراءة فقط.
        </>
      }
    >
      {/* ── ملخّص التكلفة (StatGrid) ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            <Badge tone={costQ.isLoading ? 'neutral' : costQ.isError ? 'danger' : 'ok'}>
              {costQ.isLoading ? 'تحميل…' : costQ.isError ? 'خطأ' : isEmpty ? 'لا بيانات' : 'حيّ'}
            </Badge>
          }
        >
          ملخّص التكلفة
        </SectionLabel>

        {costQ.isLoading ? (
          <div style={{ color: t.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل ملخّص التكلفة…</div>
        ) : costQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>{errDetail(costQ.error)}</div>
        ) : isEmpty ? (
          <div style={{ color: t.muted, fontSize: 13, padding: '8px 0' }}>لا بيانات تكلفة</div>
        ) : (
          <StatGrid
            cols={3}
            items={[
              {
                label: 'إجماليّ التكلفة',
                value: usd(totalUsd),
                color: T.gold,
                icon: <DollarSign style={{ width: 16, height: 16, color: T.gold }} />,
              },
              {
                label: 'عدد المهام',
                value: fmtCount(taskCount),
                color: T.info,
                icon: <ListChecks style={{ width: 16, height: 16, color: T.info }} />,
              },
              {
                label: 'مصادر التكلفة',
                value: fmtCount(bySource.length),
                color: T.green,
                icon: <Layers style={{ width: 16, height: 16, color: T.green }} />,
              },
            ]}
          />
        )}
      </Card>

      {/* ── التوزيع حسب المصدر (Rows + ProgressBar) ── */}
      <Card pad={14} style={{ marginBottom: 10 }}>
        <SectionLabel
          action={
            topSource ? (
              <Pill tone="warn">الأعلى: {sourceAr(topSource.source)}</Pill>
            ) : undefined
          }
        >
          التكلفة حسب المصدر
        </SectionLabel>

        {costQ.isLoading ? (
          <div style={{ color: t.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل التوزيع…</div>
        ) : costQ.isError ? (
          <div style={{ color: T.danger, fontSize: 12, padding: '8px 0' }}>{errDetail(costQ.error)}</div>
        ) : bySource.length === 0 ? (
          <div style={{ color: t.muted, fontSize: 13, padding: '8px 0' }}>لا بيانات تكلفة</div>
        ) : (
          <div>
            {bySource.map((s, i) => {
              const share = totalUsd > 0 ? s.total_usd / totalUsd : 0;
              const c = colorFor(i);
              return (
                <div key={s.source ?? i} style={{ marginBottom: 10 }}>
                  <Row
                    icon={<span style={{
                      width: 10, height: 10, borderRadius: 999, background: c,
                      display: 'inline-block', flexShrink: 0,
                    }} />}
                    label={sourceAr(s.source)}
                    value={
                      <span className="inline-flex items-center gap-2">
                        <span style={{ color: t.muted, fontSize: 11, fontWeight: 600 }}>
                          {Math.round(share * 100)}%
                        </span>
                        <span style={{ color: t.ink, fontWeight: 700 }}>{usd(s.total_usd)}</span>
                      </span>
                    }
                  />
                  <div style={{ marginTop: 6 }}>
                    <ProgressBar value={share} color={c} />
                  </div>
                </div>
              );
            })}

            {/* رسم بيانيّ شريطيّ مكمّل (Recharts) — قراءة بصريّة للمقارنة. */}
            <div style={{ marginTop: 6 }}>
              <ResponsiveContainer width="100%" height={150}>
                <BarChart data={chartData} barSize={26} margin={{ top: 6, right: 8, bottom: 0, left: -14 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={t.line} />
                  <XAxis dataKey="source" tick={{ fill: t.faint, fontSize: 10 }} tickLine={false} />
                  <YAxis tick={{ fill: t.faint, fontSize: 10 }} tickLine={false} width={44} />
                  <Tooltip
                    cursor={{ fill: t.card2 }}
                    contentStyle={{ background: t.card, border: `1px solid ${t.line}`, borderRadius: 8, fontSize: 12 }}
                    labelStyle={{ color: t.ink }}
                    formatter={(v: number | string) => [usd(Number(v)), 'التكلفة']}
                  />
                  <Bar dataKey="total_usd" fill={T.gold} radius={[4, 4, 0, 0]} name="التكلفة" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </Card>

      {/* ── سياق المزرعة (اختياريّ — لا يُكسِر إن غاب) ── */}
      <Card pad={14}>
        <SectionLabel
          action={
            <Badge tone={farmQ.isLoading ? 'neutral' : farmQ.isError ? 'danger' : 'ok'}>
              {farmQ.isLoading ? 'تحميل…' : farmQ.isError ? 'غير متاح' : 'سياق'}
            </Badge>
          }
        >
          سياق المزرعة
        </SectionLabel>

        {farmQ.isLoading ? (
          <div style={{ color: t.muted, fontSize: 12, padding: '8px 0' }}>جارٍ تحميل ملخّص المزرعة…</div>
        ) : farmQ.isError ? (
          <div style={{ color: t.muted, fontSize: 12, padding: '8px 0' }}>تعذّر تحميل سياق المزرعة — يُعرَض «—».</div>
        ) : (
          <>
            <StatGrid
              cols={3}
              items={[
                {
                  label: 'المزارع',
                  value: fmtCount(farm?.farms_count),
                  color: t.ink,
                  icon: <Building2 style={{ width: 16, height: 16, color: t.brownSoft }} />,
                },
                {
                  label: 'الحقول',
                  value: fmtCount(farm?.fields_count),
                  color: t.ink,
                  icon: <MapIcon style={{ width: 16, height: 16, color: t.brownSoft }} />,
                },
                {
                  label: 'المساحة',
                  value: fmtArea(farm?.total_area_ha),
                  unit: 'هكتار',
                  color: T.green,
                },
              ]}
            />
            {/* تكلفة لكلّ هكتار (مشتقّة) — مؤشّر عائد بسيط حين تتوفّر المساحة. */}
            {!costQ.isError && !isEmpty &&
              typeof farm?.total_area_ha === 'number' && farm.total_area_ha > 0 && (
                <div style={{ marginTop: 10 }}>
                  <Row
                    icon={<DollarSign style={{ width: 14, height: 14, color: T.gold }} />}
                    label="التكلفة لكلّ هكتار"
                    value={usd(totalUsd / farm.total_area_ha)}
                  />
                </div>
              )}
          </>
        )}
      </Card>
    </FieldCabin>
  );
}
