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

const STATUS_COLOR: Record<string, string> = {
  excellent: '#16a34a', good: '#65a30d', fair: '#ca8a04',
  poor: '#f97316', critical: '#dc2626',
};

export function KPICard({ kpi }: KPICardProps) {
  const color  = kpi.color || STATUS_COLOR[kpi.status ?? ''] || '#6b7280';
  const td     = kpi.trend_direction;
  const TIcon  = td === 'improving' ? TrendingUp : td === 'declining' ? TrendingDown : Minus;
  const tColor = td === 'improving' ? '#16a34a'  : td === 'declining' ? '#dc2626'    : '#f59e0b';
  const sparkline: number[] = kpi.sparkline || [];

  const val = typeof kpi.value === 'number'
    ? kpi.value.toFixed(kpi.value > 10 ? 1 : kpi.value < 1 ? 3 : 1)
    : kpi.value;

  return (
    <div
      className="rounded-xl p-4 border hover:border-emerald-800 transition-all"
      style={{ background: '#1e293b', borderColor: '#334155' }}
    >
      <div className="flex items-center justify-between mb-3">
        <div
          className="w-9 h-9 rounded-lg flex items-center justify-center"
          style={{ background: `${color}22` }}
        >
          <Activity className="w-4 h-4" style={{ color }} />
        </div>
        <TIcon className="w-4 h-4" style={{ color: tColor }} />
      </div>
      <div className="flex items-baseline gap-1 mb-0.5">
        <span className="text-xl font-bold text-slate-100">{val}</span>
        {kpi.unit && <span className="text-xs text-slate-400">{kpi.unit}</span>}
      </div>
      <p className="text-xs text-slate-400 mb-2">{kpi.name || kpi.name_ar}</p>
      <span
        className="text-[10px] px-1.5 py-0.5 rounded-full"
        style={{ background: `${color}22`, color }}
      >
        {kpi.status_ar || kpi.status}
      </span>
      {sparkline.length > 0 && (
        <div className="h-8 mt-2 -mx-1">
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
