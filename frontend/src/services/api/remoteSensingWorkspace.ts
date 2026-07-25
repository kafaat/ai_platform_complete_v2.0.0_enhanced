import { kongApi } from './client';

export interface RemoteSensingWorkspaceOverview {
  latest_observation_refs: Record<string, unknown>;
  observation_count: number;
  open_anomaly_count: number;
  decision_count: number;
  verified_outcome_count: number;
}

export interface RemoteSensingWorkspaceResponse {
  field_id: string;
  season_id: string;
  sections: {
    overview?: RemoteSensingWorkspaceOverview;
  };
  partial: boolean;
  errors?: Record<string, string>;
}

/**
 * RS-9 canonical workspace consumer.
 *
 * The browser calls the same-origin gateway only. nginx verifies the JWT,
 * derives the tenant from auth, and forwards the request to the aggregation
 * BFF; React never calls its indicators/vegetation/decision upstreams.
 */
export async function getRemoteSensingWorkspaceOverview(
  fieldId: string,
  seasonId: string,
): Promise<RemoteSensingWorkspaceResponse> {
  const { data } = await kongApi.get<RemoteSensingWorkspaceResponse>(
    `/api/remote-sensing-workspace/v1/fields/${encodeURIComponent(fieldId)}/remote-sensing-workspace`,
    { params: { season_id: seasonId, include: 'overview' } },
  );
  return data;
}
