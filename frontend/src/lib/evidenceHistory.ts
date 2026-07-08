// evidenceHistory.ts — عقد «تاريخ أدلّة الحقل» + تحليلات الفجوات (E1) + مساعِدات نقيّة.
//
// يطابق مخرجات backend:
//   • GET /api/v1/fields/{id}/evidence-graph/timeline  ⇒ لقطات تنازليّة (أحدث أوّلاً).
//   • GET /api/v1/evidence-graph/analytics             ⇒ فجوات عبر الحقول (من v149).
// صدق: الاتّجاه يُحسَب من لقطتَين فعليّتَين فقط؛ بلقطة واحدة/صفر ⇒ 'unknown' (لا اختلاق
// اتّجاه). مساعِدات نقيّة (بلا React) لتُختبَر منفصلةً.

export interface EvidenceTimelineSnapshot {
  generated_at: string;
  recommendation_hash: string | null;
  confidence_score: number | null;
  evidence_count: number | null;
  gap_count: number | null;
}

export interface EvidenceTimeline {
  field_id: string;
  snapshots: EvidenceTimelineSnapshot[];
  reason?: string;
}

export interface GapAnalyticsEntry {
  node_type: string;
  field_count: number;
  occurrence_count: number;
}

export interface EvidenceGapAnalytics {
  available: boolean;
  derived?: string;
  fields_analyzed: number;
  top_gaps: GapAnalyticsEntry[];
  status_distribution: { status: string; count: number }[];
  reason?: string;
}

export type Trend = 'improving' | 'worsening' | 'stable' | 'unknown';

/** اتّجاه عدد الفجوات عبر الزمن (اللقطات أحدث-أوّلاً): نقص الفجوات = تحسّن. */
export function gapTrend(snapshots?: EvidenceTimelineSnapshot[] | null): Trend {
  return _trend(snapshots, 'gap_count', /* lessIsBetter */ true);
}

/** اتّجاه عدد الأدلّة الحاضرة عبر الزمن: زيادة الأدلّة = تحسّن. */
export function evidenceTrend(snapshots?: EvidenceTimelineSnapshot[] | null): Trend {
  return _trend(snapshots, 'evidence_count', /* lessIsBetter */ false);
}

function _trend(
  snapshots: EvidenceTimelineSnapshot[] | null | undefined,
  key: 'gap_count' | 'evidence_count',
  lessIsBetter: boolean,
): Trend {
  if (!Array.isArray(snapshots) || snapshots.length < 2) return 'unknown';
  const latest = snapshots[0]?.[key];
  const prev = snapshots[1]?.[key];
  if (typeof latest !== 'number' || typeof prev !== 'number') return 'unknown';
  if (latest === prev) return 'stable';
  const decreased = latest < prev;
  const better = lessIsBetter ? decreased : !decreased;
  return better ? 'improving' : 'worsening';
}

/** هل يوجد تاريخ لقطات فعليّ؟ (صدق: لا يعرض «تاريخ» بلا لقطات). */
export function hasHistory(timeline?: EvidenceTimeline | null): boolean {
  return !!timeline && Array.isArray(timeline.snapshots) && timeline.snapshots.length > 0;
}
