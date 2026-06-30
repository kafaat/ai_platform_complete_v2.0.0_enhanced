import { kongApi } from '../../../services/api';
import type { DrawFeature } from './drawingTypes';

export interface PersistedDrawFeature extends DrawFeature {
  tenantId?: string;
  savedBy?: string | number | null;
  deletedAt?: string | null;
}

export interface DrawingFeatureListResponse {
  features: PersistedDrawFeature[];
}

export function listDrawingFeatures(fieldId: string): Promise<PersistedDrawFeature[]> {
  return kongApi
    .get<DrawingFeatureListResponse>(`/api/v1/fields/${fieldId}/drawing-features`)
    .then((r) => r.data.features ?? []);
}

export function createDrawingFeature(feature: DrawFeature): Promise<PersistedDrawFeature> {
  return kongApi
    .post<PersistedDrawFeature>('/api/v1/drawing-features', feature)
    .then((r) => r.data);
}

export function updateDrawingFeature(featureId: string, patch: Partial<DrawFeature>): Promise<PersistedDrawFeature> {
  return kongApi
    .patch<PersistedDrawFeature>(`/api/v1/drawing-features/${featureId}`, patch)
    .then((r) => r.data);
}

export function deleteDrawingFeature(featureId: string): Promise<{ deleted: true; feature_id: string }> {
  return kongApi
    .delete<{ deleted: true; feature_id: string }>(`/api/v1/drawing-features/${featureId}`)
    .then((r) => r.data);
}


export interface DrawingTopologyValidationResponse {
  valid: boolean;
  postgis: boolean;
  geometryType?: string | null;
  validReason?: string | null;
  areaHa?: number | null;
  withinField?: boolean | null;
  overlapCount: number;
  overlapAreaHa: number;
  issues: Array<Record<string, unknown>>;
}

export function validateDrawingFeatureTopology(feature: DrawFeature, excludeFeatureId?: string): Promise<DrawingTopologyValidationResponse> {
  return kongApi
    .post<DrawingTopologyValidationResponse>('/api/v1/drawing-features/validate', { feature, excludeFeatureId })
    .then((r) => r.data);
}
