// useEvidenceHistory — هوكات react-query لتاريخ أدلّة الحقل + تحليلات الفجوات (E1).
//
// الأعراف مطابقة لـuseLearningEvidence.ts/useFieldIntelligenceCard.ts: kongApi عبر
// البوّابة (/api/v1/*)، retry:false لحالة صادقة عند الفشل، staleTime متوسّط.
//   • useEvidenceTimeline(fieldId): GET /api/v1/fields/{id}/evidence-graph/timeline
//     (لقطات JSONB الموجزة — أحدث أوّلاً؛ داخليّ للحقل).
//   • useEvidenceGapAnalytics(): GET /api/v1/evidence-graph/analytics
//     (تجميع عبر الحقول من الجداول المُطبَّعة v149؛ آخر لقطة/حقل).

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type { EvidenceGapAnalytics, EvidenceTimeline } from '../lib/evidenceHistory';

export function useEvidenceTimeline(
  fieldId?: string | null,
  enabled = true,
): UseQueryResult<EvidenceTimeline> {
  return useQuery<EvidenceTimeline>({
    queryKey: ['evidence-timeline', fieldId],
    enabled: enabled && !!fieldId,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: () =>
      kongApi
        .get(
          `/api/v1/fields/${encodeURIComponent(fieldId as string)}/evidence-graph/timeline`,
          { params: { limit: 20 } },
        )
        .then((r) => r.data as EvidenceTimeline),
  });
}

export function useEvidenceGapAnalytics(enabled = true): UseQueryResult<EvidenceGapAnalytics> {
  return useQuery<EvidenceGapAnalytics>({
    queryKey: ['evidence-gap-analytics'],
    enabled,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: () =>
      kongApi
        .get('/api/v1/evidence-graph/analytics')
        .then((r) => r.data as EvidenceGapAnalytics),
  });
}
