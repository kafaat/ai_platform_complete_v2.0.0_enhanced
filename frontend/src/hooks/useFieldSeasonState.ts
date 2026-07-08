// useFieldSeasonState — هوك react-query للحقيقة التشغيليّة الموحّدة للحقل-الموسم.
// نمط مطابق لـuseEvidenceHistory: kongApi عبر البوّابة، retry:false (حالة صادقة عند الفشل)،
// staleTime متوسّط، ولا يعمل إلّا بوجود field+season.
//   • GET /api/v1/fields/{field_id}/seasons/{season_id}/state

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type { FieldSeasonState } from '../lib/fieldSeasonState';

export function useFieldSeasonState(
  fieldId?: string | null,
  seasonId?: string | null,
  enabled = true,
): UseQueryResult<FieldSeasonState> {
  return useQuery<FieldSeasonState>({
    queryKey: ['field-season-state', fieldId, seasonId],
    enabled: enabled && !!fieldId && !!seasonId,
    retry: false,
    staleTime: 5 * 60_000,
    queryFn: () =>
      kongApi
        .get(
          `/api/v1/fields/${encodeURIComponent(fieldId as string)}` +
            `/seasons/${encodeURIComponent(seasonId as string)}/state`,
        )
        .then((r) => r.data as FieldSeasonState),
  });
}
