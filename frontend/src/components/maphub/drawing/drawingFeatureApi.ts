import { getAuthScope } from '../../../lib/authStorage';
import { kongApi } from '../../../services/api';
import type { DrawFeature } from './drawingTypes';
import {
  DRAWING_SYNC_AUTH_REQUIRED_EVENT,
  withDrawingOwnerScope,
  classifyDrawingSyncError,
  compactSyncedDrawingQueue,
  enqueueDrawingCreate,
  enqueueDrawingDelete,
  enqueueDrawingUpdate,
  isLikelyOfflineError,
  listQueuedDrawingFeatures,
  nextDrawingSyncDueInMs,
  summarizeDrawingSyncQueue,
  syncDrawingQueue,
  type DrawingOfflineSyncOptions,
  type DrawingOfflineSyncRequestMeta,
  type DrawingSyncQueueSummary,
} from './drawingOfflineSync';

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

function idempotencyConfig(meta?: DrawingOfflineSyncRequestMeta) {
  const ownerScope = meta?.ownerScope ?? getAuthScope();
  if (!ownerScope) throw new Error('يلزم تسجيل الدخول لحفظ الرسم.');
  return { expectedAuthScope: ownerScope, ...(meta?.idempotencyKey ? { headers: { 'Idempotency-Key': meta.idempotencyKey } } : {}) };
}

export function createDrawingFeature(feature: DrawFeature, meta?: DrawingOfflineSyncRequestMeta): Promise<PersistedDrawFeature> {
  return kongApi
    .post<PersistedDrawFeature>('/api/v1/drawing-features', feature, idempotencyConfig(meta))
    .then((r) => r.data);
}

export function updateDrawingFeature(featureId: string, patch: Partial<DrawFeature>, meta?: DrawingOfflineSyncRequestMeta): Promise<PersistedDrawFeature> {
  return kongApi
    .patch<PersistedDrawFeature>(`/api/v1/drawing-features/${featureId}`, patch, idempotencyConfig(meta))
    .then((r) => r.data);
}

export function deleteDrawingFeature(featureId: string, meta?: DrawingOfflineSyncRequestMeta): Promise<{ deleted: true; feature_id: string }> {
  return kongApi
    .delete<{ deleted: true; feature_id: string }>(`/api/v1/drawing-features/${featureId}`, idempotencyConfig(meta))
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


export class DrawingFeatureReadError extends Error {
  constructor(public readonly queuedFeatures: PersistedDrawFeature[], public readonly cause: unknown) {
    super('تعذّر تحميل الرسومات المحفوظة بالخادم');
    this.name = 'DrawingFeatureReadError';
  }
}

export async function listDrawingFeaturesWithOfflineQueue(fieldId: string): Promise<PersistedDrawFeature[]> {
  const queued = listQueuedDrawingFeatures(fieldId) as PersistedDrawFeature[];
  try {
    const remote = await listDrawingFeatures(fieldId);
    const byId = new Map<string, PersistedDrawFeature>();
    for (const feature of remote) byId.set(feature.id, feature);
    for (const feature of queued) byId.set(feature.id, feature);
    return Array.from(byId.values());
  } catch (error) {
    throw new DrawingFeatureReadError(queued, error);
  }
}

// انقطاع أو جلسة منتهية (401/توكن منتهٍ) ⇒ نحفظ في الطابور بدل إسقاط الرسمة؛ 4xx دائم يُرمى.
function shouldQueueOffline(error: unknown): boolean {
  return isLikelyOfflineError(error) || classifyDrawingSyncError(error) === 'auth';
}

export async function createDrawingFeatureOfflineFirst(feature: DrawFeature): Promise<PersistedDrawFeature> {
  const ownerScope = getAuthScope();
  try {
    return await createDrawingFeature(feature);
  } catch (error) {
    if (!ownerScope || (getAuthScope() !== null && getAuthScope() !== ownerScope) || !shouldQueueOffline(error)) throw error;
    const queued = withDrawingOwnerScope(ownerScope, () => enqueueDrawingCreate(feature));
    return {
      ...(queued.feature as DrawFeature),
      draft: true,
      properties: {
        ...(queued.feature?.properties ?? {}),
        offlinePending: true,
        offlineQueueId: queued.id,
        offlineSyncState: classifyDrawingSyncError(error) === 'auth' ? 'auth_required' : 'pending',
      },
      savedBy: null,
      deletedAt: null,
    } as PersistedDrawFeature;
  }
}

export async function updateDrawingFeatureOfflineFirst(featureId: string, patch: Partial<DrawFeature>, fieldId?: string): Promise<PersistedDrawFeature> {
  const ownerScope = getAuthScope();
  try {
    return await updateDrawingFeature(featureId, patch);
  } catch (error) {
    if (!ownerScope || (getAuthScope() !== null && getAuthScope() !== ownerScope) || !shouldQueueOffline(error)) throw error;
    withDrawingOwnerScope(ownerScope, () => enqueueDrawingUpdate(featureId, patch, fieldId));
    return {
      id: featureId,
      kind: patch.kind ?? 'field',
      geometry: patch.geometry ?? { type: 'Polygon', coordinates: [] },
      properties: { ...(patch.properties ?? {}), offlinePending: true, offlineSyncState: 'pending' },
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
  const ownerScope = getAuthScope();
  try {
    return await deleteDrawingFeature(featureId);
  } catch (error) {
    if (!ownerScope || (getAuthScope() !== null && getAuthScope() !== ownerScope) || !shouldQueueOffline(error)) throw error;
    withDrawingOwnerScope(ownerScope, () => enqueueDrawingDelete(featureId, fieldId));
    return { deleted: true, feature_id: featureId, offline: true };
  }
}

export function syncOfflineDrawingFeatures(options: DrawingOfflineSyncOptions = {}) {
  return syncDrawingQueue({
    create: (feature, meta) => createDrawingFeature(feature, meta),
    update: (featureId, patch, meta) => updateDrawingFeature(featureId, patch, meta),
    delete: (featureId, meta) => deleteDrawingFeature(featureId, meta),
  }, options);
}

/** هل الرسمة محفوظة في الخادم فعلاً، أم في الطابور المحليّ بانتظار المزامنة؟ */
export function isDrawingPendingSync(feature: Pick<DrawFeature, 'properties'> | null | undefined): boolean {
  return Boolean(feature?.properties?.offlinePending);
}

export interface OfflineDrawingAutoSyncOptions {
  /** 401 أثناء التفريغ: العناصر باقية؛ الواجهة تطلب إعادة الدخول. */
  onAuthRequired?: (summary: DrawingSyncQueueSummary) => void;
  minDelayMs?: number;
  idleDelayMs?: number;
}

/**
 * R10: مُفرِّغ الطابور — عند البدء (فتح التطبيق/تجدّد الجلسة)، عند حدث `online`، ودوريّاً
 * بـbackoff. يُعيد دالّة إيقاف. Drains on start, on reconnect, and on a backoff timer.
 */
export function startOfflineDrawingAutoSync(options: OfflineDrawingAutoSyncOptions = {}): () => void {
  if (typeof window === 'undefined') return () => {};
  const minDelayMs = options.minDelayMs ?? 1_000;
  const idleDelayMs = options.idleDelayMs ?? 60_000;
  let stopped = false;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const isOffline = () => typeof navigator !== 'undefined' && navigator.onLine === false;

  const schedule = () => {
    if (stopped) return;
    if (timer) clearTimeout(timer);
    // دون اتّصال ننتظر حدث `online` (مع نبضة بطيئة احتياطاً) بدل الدوران كلّ ثانية.
    const due = isOffline() ? null : nextDrawingSyncDueInMs();
    const delay = due === null ? idleDelayMs : Math.max(minDelayMs, due);
    timer = setTimeout(() => void run(false), delay);
  };

  const run = async (force: boolean) => {
    if (stopped) return;
    if (!isOffline()) {
      try {
        const result = await syncOfflineDrawingFeatures({ force });
        if (result.synced > 0) compactSyncedDrawingQueue();
      } catch {
        // التفريغ لا يرمي عادةً؛ أيّ خطأ غير متوقّع لا يوقف المؤقّت.
      }
    }
    schedule();
  };

  const onOnline = () => void run(true);
  const onAuthRequired = () => options.onAuthRequired?.(summarizeDrawingSyncQueue());
  window.addEventListener('online', onOnline);
  window.addEventListener(DRAWING_SYNC_AUTH_REQUIRED_EVENT, onAuthRequired);
  // البدء = فتح التطبيق أو جلسة جديدة/مُجدَّدة ⇒ نُعيد حتى عناصر authRequired.
  void run(true);

  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    window.removeEventListener('online', onOnline);
    window.removeEventListener(DRAWING_SYNC_AUTH_REQUIRED_EVENT, onAuthRequired);
  };
}
