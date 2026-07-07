import { History, TrendingUp, TrendingDown, Minus, HelpCircle, Layers } from 'lucide-react';
import { useEvidenceTimeline, useEvidenceGapAnalytics } from '../../hooks/useEvidenceHistory';
import {
  gapTrend,
  evidenceTrend,
  hasHistory,
  type Trend,
} from '../../lib/evidenceHistory';
import { T } from '../ds';

interface Props {
  fieldId?: string | null;
  enabled?: boolean;
}

const TREND_LABEL: Record<Trend, string> = {
  improving: 'تحسّن',
  worsening: 'تراجع',
  stable: 'ثابت',
  unknown: '—',
};

function TrendBadge({ label, trend }: { label: string; trend: Trend }) {
  const color =
    trend === 'improving' ? T.green : trend === 'worsening' ? T.danger : T.muted;
  const Icon =
    trend === 'improving' ? TrendingUp : trend === 'worsening' ? TrendingDown : Minus;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]"
      style={{ background: T.card2, color }}
      title={`${label}: ${TREND_LABEL[trend]}`}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      {label} · {TREND_LABEL[trend]}
    </span>
  );
}

/** بطاقة تاريخ الأدلّة (E1-UI): كيف تطوّرت أدلّة/فجوات/ثقة الحقل عبر اللقطات المحفوظة
 *  + أكثر الفجوات تكراراً عبر حقولك (من الجداول المُطبَّعة v149). صدق: الاتّجاه من
 *  لقطتَين فعليّتَين فقط؛ لا لقطات ⇒ يُعلَن؛ لا تحليلات ⇒ يُعلَن (لا اختلاق). */
export default function EvidenceHistoryCard({ fieldId, enabled = true }: Props) {
  const timelineQ = useEvidenceTimeline(fieldId, enabled);
  const analyticsQ = useEvidenceGapAnalytics(enabled);
  if (!enabled || !fieldId) return null;

  const timeline = timelineQ.data;
  const snapshots = timeline?.snapshots ?? [];
  const analytics = analyticsQ.data;

  return (
    <section
      className="mb-3 rounded-2xl border p-3"
      style={{ borderColor: T.line, background: T.card }}
      data-testid="evidence-history-card"
      aria-label="تاريخ أدلّة الحقل"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="inline-flex items-center gap-2 text-sm font-bold" style={{ color: T.ink }}>
          <History className="w-4 h-4" style={{ color: T.gold }} aria-hidden="true" /> تاريخ الأدلّة
        </span>
        {hasHistory(timeline) ? (
          <div className="flex flex-wrap gap-1 justify-end">
            <TrendBadge label="الأدلّة" trend={evidenceTrend(snapshots)} />
            <TrendBadge label="الفجوات" trend={gapTrend(snapshots)} />
          </div>
        ) : null}
      </div>

      {timelineQ.isLoading ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          جارٍ جلب تاريخ الأدلّة…
        </p>
      ) : !hasHistory(timeline) ? (
        <p className="text-[12px]" style={{ color: T.muted }}>
          لا لقطات أدلّة محفوظة لهذا الحقل بعد (تُحفَظ عند كلّ تحليل).
        </p>
      ) : (
        <div className="space-y-1">
          {snapshots.slice(0, 8).map((s, i) => (
            <div
              key={`${s.generated_at}-${i}`}
              className="flex items-center justify-between gap-2 text-[11px] px-2 py-1 rounded-lg"
              style={{ background: T.card2, color: T.ink }}
            >
              <span style={{ color: T.muted }}>
                {new Date(s.generated_at).toLocaleDateString('ar', {
                  year: 'numeric',
                  month: 'short',
                  day: 'numeric',
                })}
              </span>
              <span className="inline-flex items-center gap-2">
                <span title="أدلّة حاضرة">🟢 {s.evidence_count ?? '—'}</span>
                <span title="فجوات معرفة">🟡 {s.gap_count ?? '—'}</span>
                {typeof s.confidence_score === 'number' ? (
                  <span style={{ color: T.faint }} title="الثقة">
                    ثقة {Math.round(s.confidence_score * 100)}%
                  </span>
                ) : null}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* أكثر الفجوات تكراراً عبر حقول المستأجِر (تحليلات v149) — يوجّه أولويّة جمع البيانات. */}
      <div className="pt-2 mt-2 border-t" style={{ borderColor: T.line }}>
        <span
          className="inline-flex items-center gap-1 text-[11px] font-semibold mb-1"
          style={{ color: T.muted }}
        >
          <Layers className="w-3.5 h-3.5" aria-hidden="true" /> فجوات متكرّرة عبر حقولك
        </span>
        {analyticsQ.isLoading ? (
          <p className="text-[12px]" style={{ color: T.muted }}>
            جارٍ حساب التحليلات…
          </p>
        ) : !analytics?.available || !analytics.top_gaps.length ? (
          <p className="inline-flex items-center gap-1 text-[12px]" style={{ color: T.faint }}>
            <HelpCircle className="w-3.5 h-3.5" aria-hidden="true" />
            لا تحليلات فجوات متاحة بعد ({analytics?.fields_analyzed ?? 0} حقل مُحلَّل).
          </p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {analytics.top_gaps.slice(0, 8).map((g) => (
              <span
                key={g.node_type}
                className="px-2 py-0.5 rounded-full text-[10px]"
                style={{ background: T.card2, color: T.faint }}
                title={`ناقص في ${g.field_count} حقل`}
              >
                {g.node_type}: {g.field_count} حقل
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
