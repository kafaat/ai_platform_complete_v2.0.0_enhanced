import { TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react';
import { LineChart, Line, ResponsiveContainer } from 'recharts';

interface KPIData {
  id?: string;
  name?: string;
  name_ar?: string;
  value?: number | string;
  unit?: string;
  status?: string;
  status_ar?: string;
  color?: string;
  trend_direction?: 'improving' | 'declining' | 'stable';
  sparkline?: number[];
  [key: string]: unknown;
}

interface KPICardProps {
  kpi: KPIData;
}

// مصدر وحيد لألوان الحالة (نفس قيم status-* في index.css). يُصدَّر ليستورده
// Dashboard وغيره بدل إعادة تعريفه (كان مكرّراً ⇒ ازدواج صيانة).
export const STATUS_COLOR: Record<string, string> = {
  excellent: '#16a34a', good: '#65a30d', fair: '#ca8a04',
  poor: '#f97316', critical: '#dc2626',
};

// الاتّجاه نصّيّاً (a11y): يُعلَن للقارئ الشاشي بدل الاعتماد على اللون فقط.
const TREND_AR: Record<string, string> = {
  improving: 'تحسّن', declining: 'تراجع', stable: 'مستقر',
};

export function KPICard({ kpi }: KPICardProps) {
  const color  = kpi.color || STATUS_COLOR[kpi.status ?? ''] || '#6b7280';
  const td     = kpi.trend_direction;
  const TIcon  = td === 'improving' ? TrendingUp : td === 'declining' ? TrendingDown : Minus;
  const tColor = td === 'improving' ? '#16a34a'  : td === 'declining' ? '#dc2626'    : '#f59e0b';
  const trendAr = td ? TREND_AR[td] : '';
  const sparkline: number[] = kpi.sparkline || [];

  const val = typeof kpi.value === 'number'
    ? kpi.value.toFixed(kpi.value > 10 ? 1 : kpi.value < 1 ? 3 : 1)
    : kpi.value;

  const label = kpi.name || kpi.name_ar || '';
  const statusAr = kpi.status_ar || kpi.status || '';
  // وصف موحّد للبطاقة (قيمة + وحدة + حالة + اتّجاه) — يقرؤه القارئ الشاشي كاملاً.
  const ariaLabel = [
    label,
    `${val}${kpi.unit ? ' ' + kpi.unit : ''}`,
    statusAr && `الحالة ${statusAr}`,
    trendAr && `الاتّجاه ${trendAr}`,
  ].filter(Boolean).join('، ');

  return (
    <div
      role="group"
      aria-label={ariaLabel}
      className="rounded-xl p-4 border border-sahool-border bg-sahool-surface hover:border-sahool-green transition-all"
    >
      <div className="flex items-center justify-between mb-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: `${color}22` }}
        >
          <Activity className="w-4 h-4" style={{ color }} aria-hidden="true" />
        </div>
        <span className="inline-flex items-center">
          <TIcon className="w-4 h-4" style={{ color: tColor }} aria-hidden="true" />
          {trendAr && <span className="sr-only">{trendAr}</span>}
        </span>
      </div>
      <div className="flex items-baseline gap-1 mb-0.5">
        <span className="text-xl font-bold text-sahool-text">{val}</span>
        {kpi.unit && <span className="text-xs text-sahool-muted">{kpi.unit}</span>}
      </div>
      <p className="text-xs text-sahool-muted mb-2">{label}</p>
      <span
        className="text-[10px] px-1.5 py-0.5 rounded-full"
        style={{ background: `${color}22`, color }}
      >
        {statusAr}
      </span>
      {sparkline.length > 0 && (
        <div className="h-8 mt-2 -mx-1" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={sparkline.map((v, i) => ({ i, v }))}>
              <Line
                dataKey="v"
                stroke={color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
