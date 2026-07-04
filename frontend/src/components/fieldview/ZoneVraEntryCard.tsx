import { MapPin, Grid3x3, FileOutput, ChevronLeft } from 'lucide-react';
import { buildZoneVraReadiness, type ZoneVraReadinessInput, type ZoneVraStep } from '../../lib/fieldZoneVra';
import { T } from '../ds';

const ICONS: Record<ZoneVraStep['key'], typeof MapPin> = {
  field: MapPin,
  zone: Grid3x3,
  action: FileOutput,
};

const TONE: Record<ZoneVraStep['status'], { fg: string; border: string }> = {
  ready: { fg: '#86efac', border: '#14532d' },
  done: { fg: '#93c5fd', border: '#1e3a8a' },
  blocked: { fg: '#94a3b8', border: '#334155' },
};

interface Props extends ZoneVraReadinessInput {
  /** يفتح مصمّم المناطق داخل الخريطة (المسار القائم v60/v62). */
  onOpenZones?: () => void;
}

/** مدخل Field → Zone → Action داخل FieldView (يوجّه إلى محرّكات المناطق/الوصفات القائمة). */
export default function ZoneVraEntryCard(props: Props) {
  const r = buildZoneVraReadiness(props);
  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }}
      data-testid="zone-vra-entry"
      aria-label="مسار المناطق والوصفة"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Grid3x3 className="w-4 h-4 text-emerald-300" aria-hidden="true" /> المناطق والوصفة (Field → Zone → Action)
        </div>
        <button
          type="button"
          onClick={props.onOpenZones}
          disabled={!props.onOpenZones || !r.canBuildZones}
          className="px-2.5 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
          style={{ border: '1px solid #14532d', color: '#86efac', background: 'rgba(15,23,42,.45)' }}
        >
          افتح مصمّم المناطق
        </button>
      </div>

      <div className="flex items-stretch gap-1">
        {r.steps.map((s, i) => {
          const Icon = ICONS[s.key];
          const tone = TONE[s.status];
          return (
            <div key={s.key} className="flex items-center gap-1 flex-1">
              <div className="rounded-xl border p-2 flex-1 min-h-[76px]" style={{ borderColor: tone.border }} data-testid={`zone-vra-step-${s.key}`}>
                <div className="inline-flex items-center gap-1.5 text-xs font-bold mb-1" style={{ color: T.ink }}>
                  <Icon className="w-3.5 h-3.5" style={{ color: tone.fg }} aria-hidden="true" /> {s.label}
                </div>
                <div className="text-[11px] leading-4" style={{ color: T.muted }}>{s.hint}</div>
              </div>
              {i < r.steps.length - 1 && <ChevronLeft className="w-4 h-4 shrink-0" style={{ color: T.faint }} aria-hidden="true" />}
            </div>
          );
        })}
      </div>

      <div className="mt-2 text-[11px]" style={{ color: T.faint }}>{r.summary}</div>
    </section>
  );
}
