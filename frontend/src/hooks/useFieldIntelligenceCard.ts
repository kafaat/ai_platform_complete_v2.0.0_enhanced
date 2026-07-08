// useFieldIntelligenceCard — هوك react-query لبطاقة ذكاء الحقل الموحّدة (V65).
//
// POST /api/v1/field-intelligence/analyze?field_id=… عبر البوّابة (kongApi يحقن JWT).
// analyze حسابٌ قرائيّ للعرض (يُرجِع الحالة + البطاقة)؛ نضعه في queryFn كسابقة
// useDistrictsWeather (POST لحساب قرائيّ). retry:false لحالة صادقة عند الفشل؛
// staleTime متوسّط (البطاقة تُجمَّع من إشارات تتغيّر بطيئاً).

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { getFieldIntelligenceJob, startAnalyzeFieldIntelligence } from '../services/api';
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
    queryFn: async () => {
      const started = await startAnalyzeFieldIntelligence({ field_id: fieldId as string });
      let job = started;
      for (let i = 0; i < 120; i += 1) {
        if (job.status === 'completed' && job.result) return job.result as FieldIntelligenceAnalyzeResponse;
        if (job.status === 'failed') throw new Error(typeof job.error === 'string' ? job.error : job.error?.message || 'تعذّر تجميع بطاقة ذكاء الحقل');
        if (job.status === 'cancelled') throw new Error('تم إلغاء تحليل ذكاء الحقل');
        await new Promise(resolve => setTimeout(resolve, 1000));
        job = await getFieldIntelligenceJob(started.job_id);
      }
      throw new Error('انتهت مهلة متابعة تحليل ذكاء الحقل');
    },
  });
}
