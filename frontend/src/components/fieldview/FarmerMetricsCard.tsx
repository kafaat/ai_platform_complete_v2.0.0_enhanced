import { Sprout, Droplets, FlaskConical, CloudSun } from 'lucide-react';
import { buildFarmerMetrics, type FarmerMetric, type FarmerMetricKey, type FarmerMetricsInput } from '../../lib/fieldFarmerMetrics';
import { T } from '../ds';

const ICONS: Record<FarmerMetricKey, typeof Sprout> = {
  health: Sprout,
  water: Droplets,
  nutrition: FlaskConical,
  weather: CloudSun,
};

const TONE: Record<FarmerMetric['status'], { border: string; bg: string; fg: string; chip: string }> = {
  good: { border: '#14532d', bg: 'rgba(22,163,74,.10)', fg: '#86efac', chip: 'جيّد' },
  watch: { border: '#854d0e', bg: 'rgba(245,158,11,.12)', fg: '#fcd34d', chip: 'انتباه' },
  risk: { border: '#7f1d1d', bg: 'rgba(239,68,68,.12)', fg: '#fca5a5', chip: 'خطر' },
  unknown: { border: '#334155', bg: 'rgba(51,65,85,.18)', fg: '#94a3b8', chip: 'غير متاح' },
};

/** عرض الفلاح: أربعة مؤشّرات كبيرة سهلة القراءة للحقل النشط. */
export default function FarmerMetricsCard(props: FarmerMetricsInput) {
  const metrics = buildFarmerMetrics(props);
  return (
    <section className="mb-3" aria-label="عرض الفلاح — أربعة مؤشّرات" data-testid="farmer-metrics">
      <div className="grid gap-2 grid-cols-2 xl:grid-cols-4">
        {metrics.map((m) => {
          const Icon = ICONS[m.key];
          const tone = TONE[m.status];
          return (
            <article
              key={m.key}
              className="rounded-2xl border p-3 flex flex-col gap-1 min-h-[104px]"
              style={{ border: `1px solid ${tone.border}`, background: tone.bg }}
              data-testid={`farmer-metric-${m.key}`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="inline-flex items-center gap-1.5 text-xs font-bold" style={{ color: T.ink }}>
                  <Icon className="w-4 h-4" style={{ color: tone.fg }} aria-hidden="true" /> {m.label}
                </span>
                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full" style={{ color: tone.fg, border: `1px solid ${tone.border}` }}>
                  {tone.chip}
                </span>
              </div>
              <div className="text-lg font-extrabold" style={{ color: T.ink }}>{m.value}</div>
              <div className="text-[11px] leading-4 mt-auto" style={{ color: T.muted }}>{m.reason}</div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
