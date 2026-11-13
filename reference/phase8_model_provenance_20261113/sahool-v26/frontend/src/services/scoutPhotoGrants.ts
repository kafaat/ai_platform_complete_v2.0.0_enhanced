/** Field-scoped media-grant management; platform is the sole authority.
 * Never use MOCK_MODE or persist grant state in localStorage. JWT remains in
 * the existing kongApi auth interceptor, not in component state or URLs.
 */
import { kongApi } from './api/client';
import { getAuthScope } from '../lib/authStorage';

export type ScoutPhotoScope = 'photo.read' | 'photo.upload' | 'photo.context' | 'photo.season_link' | 'photo.detection_link';
export interface ScoutPhotoGrant {
  grant_id: string;
  user_id: number;
  scope: ScoutPhotoScope;
  granted_by: number;
  granted_at: string;
  expires_at: string | null;
  revoked_at: string | null;
  revoked_by: number | null;
}
export interface ScoutPhotoGrantEvent {
  event_id: string;
  grant_id: string;
  actor_user_id: number;
  target_user_id: number;
  scope: ScoutPhotoScope;
  action: 'issue' | 'revoke';
  recorded_at: string;
  reason: string;
}
export interface ScoutPhotoGrantListing {
  field_id: string;
  grants: ScoutPhotoGrant[];
  events: ScoutPhotoGrantEvent[];
  limit: number;
}
export interface ScoutPhotoGrantReceipt {
  event_id: string;
  grant_id: string;
  status: 'recorded' | 'revoked';
  idempotent: boolean;
  scope?: ScoutPhotoScope;
}

const fieldRoot = (fieldId: string) => `/api/v1/admin/fields/${encodeURIComponent(fieldId)}/scouting-media-grants`;
// This is the same session guard used by other platform mutations. The server
// derives the tenant + actor from the signed bearer token, never client fields.
const authenticated = () => {
  const scope = getAuthScope();
  if (!scope) throw new Error('session identity unavailable; refusing grant administration');
  return { expectedAuthScope: scope };
};

export async function getScoutPhotoGrants(fieldId: string): Promise<ScoutPhotoGrantListing> {
  const { data } = await kongApi.get<ScoutPhotoGrantListing>(fieldRoot(fieldId), authenticated());
  return data;
}
export async function issueScoutPhotoGrant(fieldId: string, request: {
  event_id: string;
  user_id: number;
  scope: ScoutPhotoScope;
  expires_at: string;
  reason: string;
}): Promise<ScoutPhotoGrantReceipt> {
  const { data } = await kongApi.post<ScoutPhotoGrantReceipt>(fieldRoot(fieldId), request, authenticated());
  return data;
}
export async function revokeScoutPhotoGrant(fieldId: string, grantId: string, request: {
  event_id: string;
  reason: string;
}): Promise<ScoutPhotoGrantReceipt> {
  const { data } = await kongApi.post<ScoutPhotoGrantReceipt>(
    `${fieldRoot(fieldId)}/${encodeURIComponent(grantId)}/revoke`, request, authenticated(),
  );
  return data;
}
