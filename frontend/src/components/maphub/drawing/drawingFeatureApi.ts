import { kongApi } from '../../../services/api';
import type { DrawFeature } from './drawingTypes';
import { enqueueDrawingCreate, enqueueDrawingDelete, enqueueDrawingUpdate, isLikelyOfflineError, listQueuedDrawingFeatures, syncDrawingQueue } from './drawingOfflineSync';

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


export async function listDrawingFeaturesWithOfflineQueue(fieldId: string): Promise<PersistedDrawFeature[]> {
  const queued = listQueuedDrawingFeatures(fieldId) as PersistedDrawFeature[];
  try {
    const remote = await listDrawingFeatures(fieldId);
    const byId = new Map<string, PersistedDrawFeature>();
    for (const feature of remote) byId.set(feature.id, feature);
    for (const feature of queued) byId.set(feature.id, feature);
    return Array.from(byId.values());
  } catch {
    return queued;
  }
}

export async function createDrawingFeatureOfflineFirst(feature: DrawFeature): Promise<PersistedDrawFeature> {
  try {
    return await createDrawingFeature(feature);
  } catch (error) {
    if (!isLikelyOfflineError(error)) throw error;
    const queued = enqueueDrawingCreate(feature);
    return {
      ...(queued.feature as DrawFeature),
      draft: true,
      properties: {
        ...(queued.feature?.properties ?? {}),
        offlinePending: true,
        offlineQueueId: queued.id,
      },
      savedBy: null,
      deletedAt: null,
    } as PersistedDrawFeature;
  }
}

export async function updateDrawingFeatureOfflineFirst(featureId: string, patch: Partial<DrawFeature>, fieldId?: string): Promise<PersistedDrawFeature> {
  try {
    return await updateDrawingFeature(featureId, patch);
  } catch (error) {
    if (!isLikelyOfflineError(error)) throw error;
    enqueueDrawingUpdate(featureId, patch, fieldId);
    return {
      id: featureId,
      kind: patch.kind ?? 'field',
      geometry: patch.geometry ?? { type: 'Polygon', coordinates: [] },
      properties: { ...(patch.properties ?? {}), offlinePending: true },
      measurements: patch.measurements,
      validation: patch.validation,
      version: patch.version ?? 1,
      draft: true,
      updatedAt: new Date().toISOString(),
      savedBy: null,
      deletedAt: null,
    } as PersistedDrawFeature;
  }
}

export async function deleteDrawingFeatureOfflineFirst(featureId: string, fieldId?: string): Promise<{ deleted: true; feature_id: string; offline?: true }> {
  try {
    return await deleteDrawingFeature(featureId);
  } catch (error) {
    if (!isLikelyOfflineError(error)) throw error;
    enqueueDrawingDelete(featureId, fieldId);
    return { deleted: true, feature_id: featureId, offline: true };
  }
}

export function syncOfflineDrawingFeatures() {
  return syncDrawingQueue({
    create: (feature) => createDrawingFeature(feature),
    update: (featureId, patch) => updateDrawingFeature(featureId, patch),
    delete: (featureId) => deleteDrawingFeature(featureId),
  });
}
