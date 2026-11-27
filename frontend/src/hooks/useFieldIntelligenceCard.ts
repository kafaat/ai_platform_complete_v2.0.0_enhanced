// useFieldIntelligenceCard — هوك react-query لبطاقة ذكاء الحقل الموحّدة (V65).
//
// POST /api/v1/field-intelligence/analyze?field_id=… عبر البوّابة (kongApi يحقن JWT).
// analyze حسابٌ قرائيّ للعرض (يُرجِع الحالة + البطاقة)؛ نضعه في queryFn كسابقة
// useDistrictsWeather (POST لحساب قرائيّ). retry:false لحالة صادقة عند الفشل؛
// staleTime متوسّط (البطاقة تُجمَّع من إشارات تتغيّر بطيئاً).

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { useAuthQueryIdentity } from './useAuth';
import { analyzeFieldIntelligence } from '../services/api';
import type { FieldIntelligenceAnalyzeResponse } from '../lib/fieldIntelligenceCard';

export function useFieldIntelligenceCard(
  fieldId?: string | null,
  enabled = true,
): UseQueryResult<FieldIntelligenceAnalyzeResponse> {
  const identity = useAuthQueryIdentity();
  return useQuery<FieldIntelligenceAnalyzeResponse>({
    queryKey: ['field-intelligence-card', ...identity, enabled ? fieldId : null],
    enabled: enabled && !!identity[0] && !!fieldId,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: ({ signal }) => analyzeFieldIntelligence({ field_id: fieldId as string }, signal, {
      failed: 'تعذّر تجميع بطاقة ذكاء الحقل',
      cancelled: 'تم إلغاء تحليل ذكاء الحقل',
      timeout: 'انتهت مهلة متابعة تحليل ذكاء الحقل',
    }),
  });
}
