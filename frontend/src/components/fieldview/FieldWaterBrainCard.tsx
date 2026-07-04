import { Droplet, Gauge } from 'lucide-react';
import { evaluateWaterBrain, type WaterBrainInput, type WaterDecision } from '../../lib/fieldWaterBrain';
import { T } from '../ds';

const TONE: Record<WaterDecision, { border: string; bg: string; fg: string }> = {
  irrigate_now: { border: '#7f1d1d', bg: 'rgba(239,68,68,.12)', fg: '#fca5a5' },
  soon: { border: '#854d0e', bg: 'rgba(245,158,11,.12)', fg: '#fcd34d' },
  watch: { border: '#854d0e', bg: 'rgba(245,158,11,.10)', fg: '#fcd34d' },
  defer: { border: '#14532d', bg: 'rgba(22,163,74,.10)', fg: '#86efac' },
  unknown: { border: '#334155', bg: 'rgba(51,65,85,.18)', fg: '#94a3b8' },
};

/** دماغ ماء الحقل: قرار ريّ واحد واضح من الرطوبة + المطر + الحرارة. */
export default function FieldWaterBrainCard(props: WaterBrainInput) {
  const r = evaluateWaterBrain(props);
  const tone = TONE[r.decision];
  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: tone.border, background: tone.bg }}
      data-testid="water-brain"
      aria-label="دماغ ماء الحقل"
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Droplet className="w-4 h-4" style={{ color: tone.fg }} aria-hidden="true" /> قرار ريّ الحقل
        </span>
        <span className="inline-flex items-center gap-1 text-xs font-bold" style={{ color: tone.fg }}>
          <Gauge className="w-3.5 h-3.5" aria-hidden="true" /> ثقة {r.confidence}%
        </span>
      </div>

      <div className="text-lg font-extrabold mb-1" style={{ color: tone.fg }}>{r.label}</div>
      <div className="text-[11px] leading-4 mb-2" style={{ color: T.muted }}>{r.reason}</div>

      <div className="flex flex-wrap gap-1.5">
        {r.evidence.map((e) => (
          <span key={e.label} className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ color: T.faint, border: `1px solid ${T.line}` }}>
            {e.label}: {e.value}
          </span>
        ))}
      </div>

      <div className="mt-2 text-[10px]" style={{ color: T.faint }}>
        للتخطيط التفصيليّ (FAO-56 · ETc · عمق الريّ): افتح التوأم المائيّ للحقل.
      </div>
    </section>
  );
}
