// ═══════════════════════════════════════════════════════════════
// SAHOOL — Design System · مُغلِّفات الرسوم (Chart Wrappers)
// ───────────────────────────────────────────────────────────────
// مُغلِّفات رقيقة قابلة لإعادة الاستخدام فوق recharts، توحّد ما كانت كلّ صفحة
// تحليل تُكرّره inline: ResponsiveContainer + المحاور + الـTooltip الداكن +
// خطّ الشبكة + الأسطورة (legend) + حالات (تحميل/فراغ/خطأ) عبر StateViews.
//
// الثيم داكن (نفس لوحة شاشات التحليل: #1e293b/#0f1117/#334155 وخطّ عربيّ)،
// لا قيَم سحريّة مبعثرة. RTL: التطبيق dir="rtl" عالميّاً والمحاور تتبع الاتّجاه.
// صدق البيانات: المُغلِّف لا يخترع نقاطاً — يعرض حالة فارغة صريحة عند غياب data
// (مسؤوليّة المستدعي تمرير سلسلة حقيقيّة فقط).
// ═══════════════════════════════════════════════════════════════
import type { ReactNode } from 'react';
import {
  LineChart, Line, BarChart, Bar, AreaChart, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell,
} from 'recharts';
import type { LucideIcon } from 'lucide-react';
import { LoadingState, EmptyState, ErrorState } from '../StateViews';

// ── ثيم الرسوم الداكن الموحّد (مصدر واحد للحقيقة) ───────────────
// مستخرَج من النمط المتكرّر في صفحات التحليل (AnalyticsPage/ReportsPage):
// خلفيّة Tooltip داكنة + حدّ رماديّ + خطّ عربيّ + ألوان محاور باهتة.
export const CHART_THEME = {
  grid:       '#334155',
  axisTick:   '#64748b',
  tooltipBg:  '#0f1117',
  tooltipBorder: '#334155',
  itemColor:  '#e2e8f0',
  legendColor: '#94a3b8',
  accent:     '#16a34a',
} as const;

// نمط Tooltip الداكن الموحّد (يُمرَّر إلى recharts <Tooltip contentStyle>).
export const tooltipContentStyle = {
  background: CHART_THEME.tooltipBg,
  border: `1px solid ${CHART_THEME.tooltipBorder}`,
  borderRadius: 8,
  fontSize: 12,
  // خطّ عربيّ موروث (التطبيق dir="rtl") — لا نفرض عائلة خطّ هنا كي ترث من الجذر.
} as const;

const tooltipItemStyle = { color: CHART_THEME.itemColor } as const;
const legendWrapperStyle = { fontSize: 11, color: CHART_THEME.legendColor } as const;

// مُنسّق Tooltip اختياريّ ([القيمة، الاسم]) — يُمرَّر كما هو إلى recharts.
type TooltipFormatter = (value: number | string, name: string) => [ReactNode, ReactNode];

// ── ChartShell — غلاف بطاقة + عنوان + حالة (تحميل/خطأ/فراغ) ──────
// يلتقط نمط ChartCard+Panel المتكرّر في AnalyticsPage في مكان واحد. عند
// تمرير حالة (isLoading/isError/isEmpty) يعرض StateViews بدل الرسم.
export function ChartShell({
  title, icon: Icon, height = 220, isLoading, isError, isEmpty,
  onRetry, emptyTitle = 'لا توجد بيانات بعد', emptyHint, action, children,
}: {
  title?: string;
  icon?: LucideIcon;
  height?: number;
  isLoading?: boolean;
  isError?: boolean;
  isEmpty?: boolean;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  let body: ReactNode;
  if (isLoading) {
    body = <div style={{ height }}><LoadingState message="جارٍ التحميل…" /></div>;
  } else if (isError) {
    body = <div style={{ height }}><ErrorState onRetry={onRetry} /></div>;
  } else if (isEmpty) {
    body = (
      <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <EmptyState title={emptyTitle} hint={emptyHint} />
      </div>
    );
  } else {
    body = children;
  }

  return (
    <div className="rounded-xl p-4 border" style={{ background: '#1e293b', borderColor: '#334155' }}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-2">
            {Icon && <Icon className="w-4 h-4 text-emerald-400" aria-hidden="true" />}
            {title && <span className="text-sm font-semibold text-slate-200">{title}</span>}
          </div>
          {action}
        </div>
      )}
      {body}
    </div>
  );
}

// شكل سلسلة عامّ (سجلّات مفاتيح/قيَم) — المستدعي يحدّد المفاتيح عبر xKey/dataKey.
type Datum = Record<string, unknown>;

interface BaseChartProps {
  data: Datum[];
  xKey: string;
  height?: number;
  // حالات اختياريّة: حين تُمرَّر تُعرَض عبر ChartShell (StateViews) بدل الرسم.
  title?: string;
  icon?: LucideIcon;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  emptyTitle?: string;
  emptyHint?: string;
  action?: ReactNode;
  showLegend?: boolean;
  tooltipFormatter?: TooltipFormatter;
}

// سلسلة واحدة (خطّ/شريط/مساحة): المفتاح + اللون + الاسم العربيّ (للأسطورة/Tooltip).
export interface Series {
  dataKey: string;
  name?: string;
  color?: string;
}

const commonAxes = (xKey: string, yDomain?: [number | string, number | string]) => ({
  grid: <CartesianGrid strokeDasharray="3 3" stroke={CHART_THEME.grid} />,
  x: (
    <XAxis
      dataKey={xKey}
      tick={{ fill: CHART_THEME.axisTick, fontSize: 10 }}
      tickLine={false}
      interval="preserveStartEnd"
    />
  ),
  y: (
    <YAxis
      domain={yDomain}
      tick={{ fill: CHART_THEME.axisTick, fontSize: 11 }}
      tickLine={false}
      width={36}
      allowDecimals
    />
  ),
});

// ── LineChartCard ── بطاقة رسم خطّيّ (اتّجاه عبر الزمن) ──────────
export function LineChartCard({
  data, xKey, series, height = 220, yDomain,
  title, icon, isLoading, isError, onRetry, emptyTitle, emptyHint, action,
  showLegend = false, tooltipFormatter,
}: BaseChartProps & { series: Series[]; yDomain?: [number | string, number | string] }) {
  const ax = commonAxes(xKey, yDomain);
  return (
    <ChartShell
      title={title} icon={icon} height={height}
      isLoading={isLoading} isError={isError} isEmpty={data.length === 0}
      onRetry={onRetry} emptyTitle={emptyTitle} emptyHint={emptyHint} action={action}
    >
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data}>
          {ax.grid}{ax.x}{ax.y}
          <Tooltip contentStyle={tooltipContentStyle} itemStyle={tooltipItemStyle} formatter={tooltipFormatter} />
          {showLegend && <Legend wrapperStyle={legendWrapperStyle} />}
          {series.map((s) => (
            <Line
              key={s.dataKey}
              type="monotone"
              dataKey={s.dataKey}
              name={s.name ?? s.dataKey}
              stroke={s.color ?? CHART_THEME.accent}
              strokeWidth={2}
              dot={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

// ── BarChartCard ── بطاقة رسم شريطيّ (مقارنة فئات) ──────────────
// barColors اختياريّ: لون لكلّ عمود (Cell) — لتلوين فرديّ (مثلاً شدّة المنطقة).
export function BarChartCard({
  data, xKey, series, height = 200, barSize = 36, yDomain, barColors,
  title, icon, isLoading, isError, onRetry, emptyTitle, emptyHint, action,
  showLegend = false, tooltipFormatter,
}: BaseChartProps & {
  series: Series[];
  barSize?: number;
  yDomain?: [number | string, number | string];
  barColors?: (string | undefined)[];
}) {
  const ax = commonAxes(xKey, yDomain);
  const single = series.length === 1;
  return (
    <ChartShell
      title={title} icon={icon} height={height}
      isLoading={isLoading} isError={isError} isEmpty={data.length === 0}
      onRetry={onRetry} emptyTitle={emptyTitle} emptyHint={emptyHint} action={action}
    >
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} barSize={barSize}>
          {ax.grid}{ax.x}{ax.y}
          <Tooltip
            cursor={{ fill: 'rgba(148,163,184,.08)' }}
            contentStyle={tooltipContentStyle}
            itemStyle={tooltipItemStyle}
            formatter={tooltipFormatter}
          />
          {showLegend && <Legend wrapperStyle={legendWrapperStyle} />}
          {series.map((s) => (
            <Bar
              key={s.dataKey}
              dataKey={s.dataKey}
              name={s.name ?? s.dataKey}
              fill={s.color ?? CHART_THEME.accent}
              radius={[6, 6, 0, 0]}
            >
              {/* تلوين فرديّ للأعمدة (سلسلة واحدة فقط) إن مُرِّر barColors. */}
              {single && barColors &&
                data.map((_, i) => <Cell key={i} fill={barColors[i] ?? s.color ?? CHART_THEME.accent} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}

// ── AreaChartCard ── بطاقة رسم مساحيّ (حجم/تراكم عبر الزمن) ──────
export function AreaChartCard({
  data, xKey, series, height = 220, yDomain,
  title, icon, isLoading, isError, onRetry, emptyTitle, emptyHint, action,
  showLegend = false, tooltipFormatter,
}: BaseChartProps & { series: Series[]; yDomain?: [number | string, number | string] }) {
  const ax = commonAxes(xKey, yDomain);
  return (
    <ChartShell
      title={title} icon={icon} height={height}
      isLoading={isLoading} isError={isError} isEmpty={data.length === 0}
      onRetry={onRetry} emptyTitle={emptyTitle} emptyHint={emptyHint} action={action}
    >
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data}>
          {ax.grid}{ax.x}{ax.y}
          <Tooltip contentStyle={tooltipContentStyle} itemStyle={tooltipItemStyle} formatter={tooltipFormatter} />
          {showLegend && <Legend wrapperStyle={legendWrapperStyle} />}
          {series.map((s) => {
            const color = s.color ?? CHART_THEME.accent;
            return (
              <Area
                key={s.dataKey}
                type="monotone"
                dataKey={s.dataKey}
                name={s.name ?? s.dataKey}
                stroke={color}
                fill={color}
                fillOpacity={0.18}
                strokeWidth={2}
              />
            );
          })}
        </AreaChart>
      </ResponsiveContainer>
    </ChartShell>
  );
}
