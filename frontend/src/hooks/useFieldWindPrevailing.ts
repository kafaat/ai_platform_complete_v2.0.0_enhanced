// useFieldWindPrevailing — هوك react-query للرياح السائدة + توصية المصدّ (V73-UI).
//
// GET /api/v1/fields/{id}/wind/prevailing عبر البوّابة (kongApi يحقن JWT). حساب
// قرائيّ من تاريخ NASA POWER (وردة رياح ⇒ سائد ⇒ مصدّ). retry:false لحالة صادقة عند
// الفشل؛ staleTime طويل (الرياح السائدة تتغيّر ببطء موسميّ). tree_height_m اختياريّ.

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type { WindPrevailingResponse } from '../lib/windbreak';

export function useFieldWindPrevailing(
  fieldId?: string | null,
  opts: { enabled?: boolean; treeHeightM?: number } = {},
): UseQueryResult<WindPrevailingResponse> {
  const { enabled = true, treeHeightM } = opts;
  return useQuery<WindPrevailingResponse>({
    queryKey: ['field-wind-prevailing', fieldId, treeHeightM ?? null],
    enabled: enabled && !!fieldId,
    retry: false,
    staleTime: 30 * 60_000,
    queryFn: () => {
      const q = treeHeightM ? `?tree_height_m=${encodeURIComponent(treeHeightM)}` : '';
      return kongApi
        .get(`/api/v1/fields/${encodeURIComponent(fieldId as string)}/wind/prevailing${q}`)
        .then((r) => r.data as WindPrevailingResponse);
    },
  });
}
