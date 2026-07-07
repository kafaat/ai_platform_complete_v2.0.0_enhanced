// useFieldIntelligenceCard — هوك react-query لبطاقة ذكاء الحقل الموحّدة (V65).
//
// POST /api/v1/field-intelligence/analyze?field_id=… عبر البوّابة (kongApi يحقن JWT).
// analyze حسابٌ قرائيّ للعرض (يُرجِع الحالة + البطاقة)؛ نضعه في queryFn كسابقة
// useDistrictsWeather (POST لحساب قرائيّ). retry:false لحالة صادقة عند الفشل؛
// staleTime متوسّط (البطاقة تُجمَّع من إشارات تتغيّر بطيئاً).

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type { FieldIntelligenceAnalyzeResponse } from '../lib/fieldIntelligenceCard';

export function useFieldIntelligenceCard(
  fieldId?: string | null,
  enabled = true,
): UseQueryResult<FieldIntelligenceAnalyzeResponse> {
  return useQuery<FieldIntelligenceAnalyzeResponse>({
    queryKey: ['field-intelligence-card', fieldId],
    enabled: enabled && !!fieldId,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: () =>
      kongApi
        .post(`/api/v1/field-intelligence/analyze?field_id=${encodeURIComponent(fieldId as string)}`)
        .then((r) => r.data as FieldIntelligenceAnalyzeResponse),
  });
}
