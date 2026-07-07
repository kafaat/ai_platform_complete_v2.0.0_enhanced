import { Network, CheckCircle2, HelpCircle } from 'lucide-react';
import { useFieldIntelligenceCard } from '../../hooks/useFieldIntelligenceCard';
import { missingReasonAr } from '../../lib/fieldIntelligenceCard';
import {
  evidenceNodes,
  supportingEvidenceCount,
  type EvidenceGraph,
} from '../../lib/evidenceGraph';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  enabled?: boolean;
}

/** بطاقة رسم الأدلّة (V74-UI): يعرض أدلّة الحقل الحاضرة بمصادرها + فجوات المعرفة
 *  بأسبابها + كم دليل يساند التوصية. يعيد استخدام استعلام بطاقة الذكاء (analyze يرفق
 *  evidence_graph). صدق: الحاضر بمصدره، والناقص بسببه صراحةً. */
export default function EvidenceGraphCard({ fieldId, enabled = true }: Props) {
  const q = useFieldIntelligenceCard(fieldId, enabled);
  if (!enabled || !fieldId) return null;
  const graph: EvidenceGraph | undefined = q.data?.evidence_graph;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: T.card }}
      data-testid="evidence-graph-card"
      aria-label="رسم أدلّة الحقل"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <Network className="w-4 h-4" style={{ color: T.gold }} aria-hidden="true" /> رسم الأدلّة
        </span>
        {graph ? (
          <span className="text-[11px] font-semibold" style={{ color: T.muted }}>
            {graph.summary.evidence_count} دليل · {graph.summary.gap_count} فجوة
          </span>
        ) : null}
      </div>

      {q.isLoading ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          جارٍ بناء رسم الأدلّة…
        </p>
      ) : !graph ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          لا رسم أدلّة متاح لهذا الحقل بعد.
        </p>
      ) : (
        <div className="space-y-2">
          {/* الأدلّة الحاضرة بمصادرها */}
          {evidenceNodes(graph).length ? (
            <div className="flex flex-wrap gap-1">
              {evidenceNodes(graph).map((n) => (
                <span
                  key={n.id}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]"
                  style={{ background: T.card2, color: T.ink }}
                  title={n.source ? `المصدر: ${n.source}` : undefined}
                >
                  <CheckCircle2 className="w-3 h-3" style={{ color: T.green }} aria-hidden="true" />
                  {n.label}
                  {n.source ? <span style={{ color: T.faint }}>· {n.source}</span> : null}
                </span>
              ))}
            </div>
          ) : (
            <p className="text-[12px]" style={{ color: T.faint }}>
              لا أدلّة حاضرة بعد.
            </p>
          )}

          {/* دعم التوصية */}
          {graph.summary.has_recommendation ? (
            <p className="text-[12px]" style={{ color: T.ink }}>
              التوصية مدعومة بـ{supportingEvidenceCount(graph)} دليل.
            </p>
          ) : null}

          {/* فجوات المعرفة بأسبابها (ما لا نعرفه بعد) */}
          {graph.knowledge_gaps.length ? (
            <div className="pt-1">
              <span className="inline-flex items-center gap-1 text-[11px] font-semibold" style={{ color: T.muted }}>
                <HelpCircle className="w-3.5 h-3.5" aria-hidden="true" /> فجوات المعرفة
              </span>
              <div className="flex flex-wrap gap-1 mt-1">
                {graph.knowledge_gaps.map((gp) => (
                  <span
                    key={gp.key}
                    className="px-2 py-0.5 rounded-full text-[10px]"
                    style={{ background: T.card2, color: T.faint }}
                  >
                    {gp.label}: {missingReasonAr(gp.reason)}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      )}
    </section>
  );
}
