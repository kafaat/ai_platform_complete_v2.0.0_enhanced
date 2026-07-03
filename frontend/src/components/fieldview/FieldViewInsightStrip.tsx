import { Sparkles, Satellite, ClipboardCheck, MapPinned, AlertTriangle, FileText, ShieldCheck, Network } from 'lucide-react';
import { buildFieldViewActionDeck, type FieldViewActionCard, type FieldViewActionDeckInput } from '../../lib/fieldViewActionDeck';
import { evaluateFieldViewGovernance } from '../../lib/fieldViewGovernance';
import { T } from '../ds';

const ICONS: Record<FieldViewActionCard['kind'], typeof Satellite> = {
  imagery: Satellite,
  scouting: MapPinned,
  weather: Sparkles,
  operations: ClipboardCheck,
  records: FileText,
  context: AlertTriangle,
  governance: ShieldCheck,
};

const TONE_STYLE: Record<FieldViewActionCard['tone'], { border: string; bg: string; fg: string }> = {
  ok: { border: '#14532d', bg: 'rgba(22, 163, 74, 0.10)', fg: '#86efac' },
  info: { border: '#1e3a8a', bg: 'rgba(59, 130, 246, 0.10)', fg: '#93c5fd' },
  warn: { border: '#854d0e', bg: 'rgba(245, 158, 11, 0.12)', fg: '#fcd34d' },
  critical: { border: '#7f1d1d', bg: 'rgba(239, 68, 68, 0.12)', fg: '#fca5a5' },
};

interface Props extends FieldViewActionDeckInput {
  onBackfill?: () => void;
  onShowAlerts?: () => void;
  onShowTasks?: () => void;
  onOpenTimeline?: () => void;
}

function actionHandler(card: FieldViewActionCard, props: Props) {
  if (card.id.includes('backfill') || card.id.includes('stale')) return props.onBackfill;
  if (card.id.includes('imagery-ready')) return props.onOpenTimeline;
  if (card.id.includes('alerts')) return props.onShowAlerts;
  if (card.id.includes('tasks') || card.id.includes('next-job')) return props.onShowTasks;
  return undefined;
}

export default function FieldViewInsightStrip(props: Props) {
  const cards = buildFieldViewActionDeck(props);
  const governance = evaluateFieldViewGovernance(props);
  if (!cards.length) return null;
  return (
    <section className="mb-3" aria-label="FieldView smart action deck" data-testid="fieldview-insight-strip">
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="inline-flex items-center gap-2 text-xs font-bold" style={{ color: T.ink }}>
          <Sparkles className="w-4 h-4 text-emerald-300" aria-hidden="true" />
          FieldView Smart Deck
        </div>
        <div className="inline-flex items-center gap-2 text-[11px]" style={{ color: T.faint }}>
          <Network className="w-3.5 h-3.5" aria-hidden="true" />
          <span>ثقة المصادر {governance.score}% · {governance.sources.filter((s) => s.status === 'ready').length}/{governance.sources.length} جاهزة</span>
        </div>
      </div>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-5">
        {cards.map((card) => {
          const Icon = ICONS[card.kind];
          const tone = TONE_STYLE[card.tone];
          const onClick = actionHandler(card, props);
          return (
            <article
              key={card.id}
              className="rounded-xl p-3 min-h-[128px] flex flex-col gap-2"
              style={{ border: `1px solid ${tone.border}`, background: tone.bg }}
              data-testid={`fieldview-action-${card.id}`}
            >
              <div className="flex items-start gap-2">
                <Icon className="w-4 h-4 mt-0.5" style={{ color: tone.fg }} aria-hidden="true" />
                <div className="min-w-0">
                  <h3 className="text-sm font-bold leading-5" style={{ color: T.ink }}>{card.title}</h3>
                  <p className="text-xs leading-5 mt-1" style={{ color: T.muted }}>{card.summary}</p>
                </div>
              </div>
              <div className="mt-auto flex items-center justify-between gap-2">
                <span className="text-[10px] truncate" title={card.evidence} style={{ color: T.faint }}>{card.evidence}</span>
                <button
                  type="button"
                  onClick={onClick}
                  disabled={!onClick}
                  className="px-2 py-1 rounded-lg text-[11px] font-semibold disabled:opacity-50"
                  style={{ border: `1px solid ${tone.border}`, color: tone.fg, background: 'rgba(15, 23, 42, 0.45)' }}
                >
                  {card.cta}
                </button>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
