// useFieldDriftRisk — هوك react-query لخطر انجراف الرشّ نحو مناطق حسّاسة (V79-UI).
//
// POST /api/v1/fields/{id}/wind/drift-risk بمناطق حسّاسة (الحقول المجاورة) عبر البوّابة.
// حساب قرائيّ من الريح السائدة (NASA POWER) + هندسة الانجراف. لا مناطق ⇒ لا استعلام.

import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { kongApi } from '../services/api';
import type { DriftRiskResponse, SensitiveZoneInput } from '../lib/driftZones';

export function useFieldDriftRisk(
  fieldId: string | null | undefined,
  zones: SensitiveZoneInput[],
  enabled = true,
): UseQueryResult<DriftRiskResponse> {
  const key = zones
    .map((z) => z.id)
    .sort()
    .join(',');
  return useQuery<DriftRiskResponse>({
    queryKey: ['field-drift-risk', fieldId, key],
    enabled: enabled && !!fieldId && zones.length > 0,
    retry: false,
    staleTime: 15 * 60_000,
    queryFn: () =>
      kongApi
        .post(`/api/v1/fields/${encodeURIComponent(fieldId as string)}/wind/drift-risk`, {
          sensitive_zones: zones,
        })
        .then((r) => r.data as DriftRiskResponse),
  });
}
