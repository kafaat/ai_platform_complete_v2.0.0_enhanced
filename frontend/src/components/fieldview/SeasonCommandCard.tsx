import { CalendarRange, Sprout, ArrowRightCircle } from 'lucide-react';
import { summarizeSeason, type SeasonPhenologyLite } from '../../lib/fieldSeason';
import { T } from '../ds';

interface Props {
  phenology?: SeasonPhenologyLite | null;
  /** اقتراح إجراء الطور الحاليّ (إرشاديّ) من نقطة stage-actions. */
  stageAction?: string | null;
  loading?: boolean;
}

const STATUS_TONE: Record<'past' | 'current' | 'upcoming', string> = {
  past: '#475569',
  current: '#86efac',
  upcoming: '#64748b',
};

/** مركز قيادة الموسم: المرحلة الحاليّة + التقدّم + إجراء الطور المقترَح للحقل النشط. */
export default function SeasonCommandCard({ phenology, stageAction, loading }: Props) {
  const s = summarizeSeason(phenology);
  return (
    <section className="mb-3 rounded-2xl border p-3" style={{ borderColor: T.line, background: 'rgba(2,6,23,.35)' }} data-testid="season-command" aria-label="مركز الموسم">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <CalendarRange className="w-4 h-4 text-emerald-300" aria-hidden="true" /> مركز الموسم
          {s.crop && <span className="text-[11px]" style={{ color: T.faint }}>· {s.crop}</span>}
        </span>
        {s.available && s.daysAfterSowing != null && (
          <span className="text-[11px]" style={{ color: T.muted }}>{s.daysAfterSowing} يوم بعد البذار{s.kc != null ? ` · Kc ${s.kc.toFixed(2)}` : ''}</span>
        )}
      </div>

      {loading ? (
        <div className="text-[11px]" style={{ color: T.faint }}>جارٍ قراءة مراحل الموسم…</div>
      ) : !s.available ? (
        <div className="text-[11px]" style={{ color: T.muted }}>{s.reason ?? 'مراحل الموسم غير متاحة.'}</div>
      ) : (
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2">
            <Sprout className="w-4 h-4 text-emerald-300" aria-hidden="true" />
            <span className="text-sm font-extrabold" style={{ color: T.ink }}>{s.stageName ?? '—'}</span>
            {s.progressPct != null && <span className="text-[11px]" style={{ color: T.faint }}>· تقدّم الموسم {s.progressPct}%</span>}
          </div>

          {s.progressPct != null && (
            <div className="h-1.5 w-full rounded-full overflow-hidden" style={{ background: '#1e293b' }}>
              <div className="h-full rounded-full" style={{ width: `${s.progressPct}%`, background: '#22c55e' }} />
            </div>
          )}

          <div className="flex flex-wrap gap-1">
            {s.stages.map((st, i) => (
              <span key={`${st.name}-${i}`} className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ color: STATUS_TONE[st.status], border: `1px solid ${st.status === 'current' ? '#14532d' : T.line}` }}>
                {st.name}
              </span>
            ))}
          </div>

          {(stageAction || s.nextStageName) && (
            <div className="inline-flex items-center gap-1 text-[11px]" style={{ color: T.muted }}>
              <ArrowRightCircle className="w-3.5 h-3.5 text-emerald-300" aria-hidden="true" />
              {stageAction ? `إجراء الطور: ${stageAction}` : `المرحلة التالية: ${s.nextStageName}`}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
