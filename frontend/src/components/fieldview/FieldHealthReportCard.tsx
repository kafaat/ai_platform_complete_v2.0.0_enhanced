import { Activity, HelpCircle, ArrowRightCircle, FileSearch, Gauge } from 'lucide-react';
import { buildFieldHealthReport } from '../../lib/fieldHealthReport';
import type { FieldViewActionDeckInput } from '../../lib/fieldViewActionDeck';
import type { FieldHealthSeverity } from '../../lib/fieldHealthReport';
import { T } from '../ds';

const TONE: Record<FieldHealthSeverity, { border: string; bg: string; fg: string }> = {
  ok: { border: '#14532d', bg: 'rgba(22,163,74,.10)', fg: '#86efac' },
  info: { border: '#1e3a8a', bg: 'rgba(59,130,246,.10)', fg: '#93c5fd' },
  warn: { border: '#854d0e', bg: 'rgba(245,158,11,.12)', fg: '#fcd34d' },
  critical: { border: '#7f1d1d', bg: 'rgba(239,68,68,.12)', fg: '#fca5a5' },
};

type Props = FieldViewActionDeckInput;

/** تقرير حالة الحقل: يجيب عن الأسئلة الخمسة (حالة/سبب/إجراء/دليل/أثر) للحقل النشط. */
export default function FieldHealthReportCard(props: Props) {
  const report = buildFieldHealthReport(props);
  const tone = TONE[report.state.severity];
  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: tone.border, background: tone.bg }}
      data-testid="field-health-report"
      aria-label="تقرير حالة الحقل"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Activity className="w-4 h-4" style={{ color: tone.fg }} aria-hidden="true" />
          تقرير حالة الحقل
        </div>
        <span className="inline-flex items-center gap-1 text-xs font-bold" style={{ color: tone.fg }}>
          <Gauge className="w-3.5 h-3.5" aria-hidden="true" /> {report.state.label} · ثقة {report.confidence}%
        </span>
      </div>

      <div className="text-xs font-semibold mb-2" style={{ color: T.ink }}>{report.state.headline}</div>

      <div className="grid gap-2 md:grid-cols-2">
        <div className="rounded-xl border p-2 text-[11px] leading-5" style={{ borderColor: T.line, color: T.muted }}>
          <div className="inline-flex items-center gap-1 font-bold mb-1" style={{ color: T.ink }}>
            <HelpCircle className="w-3.5 h-3.5" aria-hidden="true" /> ما السبب؟
          </div>
          <ul className="list-disc pe-4">
            {report.reasons.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>

        <div className="rounded-xl border p-2 text-[11px] leading-5" style={{ borderColor: T.line, color: T.muted }}>
          <div className="inline-flex items-center gap-1 font-bold mb-1" style={{ color: T.ink }}>
            <FileSearch className="w-3.5 h-3.5" aria-hidden="true" /> ما الدليل؟
          </div>
          <ul>
            {report.evidence.slice(0, 4).map((e, i) => (
              <li key={i}><span style={{ color: T.faint }}>{e.label}:</span> {e.value}</li>
            ))}
          </ul>
        </div>
      </div>

      <div className="mt-2 text-[11px] leading-5" style={{ color: T.muted }}>{report.impact}</div>

      {report.nextAction && (
        <div className="mt-2 inline-flex items-center gap-1 text-xs font-semibold" style={{ color: T.ink }}>
          <ArrowRightCircle className="w-3.5 h-3.5" style={{ color: tone.fg }} aria-hidden="true" />
          الإجراء التالي: {report.nextAction.title}
          <span style={{ color: tone.fg }}> — {report.nextAction.cta} (من البطاقات أدناه)</span>
        </div>
      )}
    </section>
  );
}
