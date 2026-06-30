import type { DrawFeature } from './drawingTypes';

export type DrawingOfflineOperationType = 'create' | 'update' | 'delete';
export type DrawingOfflineOperationStatus = 'pending' | 'syncing' | 'failed' | 'synced';

export const DRAWING_DRAFTS_STORAGE_KEY = 'sahool.drawing.offline.drafts.v1';
export const DRAWING_SYNC_QUEUE_STORAGE_KEY = 'sahool.drawing.offline.syncQueue.v1';

export interface DrawingOfflineQueueItem {
  id: string;
  operationId: string;
  type: DrawingOfflineOperationType;
  featureId: string;
  fieldId?: string;
  feature?: DrawFeature;
  patch?: Partial<DrawFeature>;
  status: DrawingOfflineOperationStatus;
  attemptCount: number;
  lastError?: string;
  createdAt: string;
  updatedAt: string;
  syncedAt?: string;
}

export interface DrawingOfflineSyncClient {
  create(feature: DrawFeature): Promise<DrawFeature>;
  update(featureId: string, patch: Partial<DrawFeature>): Promise<DrawFeature>;
  delete(featureId: string): Promise<unknown>;
}

export interface DrawingOfflineSyncResult {
  attempted: number;
  synced: number;
  failed: number;
  remaining: number;
}

function nowIso(): string {
  return new Date().toISOString();
}

function randomId(prefix: string): string {
  const cryptoObj = typeof globalThis !== 'undefined' ? globalThis.crypto : undefined;
  if (cryptoObj && 'randomUUID' in cryptoObj) {
    return `${prefix}_${cryptoObj.randomUUID()}`;
  }
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function getStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage ?? null;
  } catch {
    return null;
  }
}

function readJsonArray<T>(key: string): T[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const raw = storage.getItem(key);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeJsonArray<T>(key: string, value: T[]): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.setItem(key, JSON.stringify(value));
  } catch {
    // لا نكسر الرسم إذا كان localStorage ممتلئاً أو محجوباً.
  }
}

export function isLikelyOfflineError(error: unknown): boolean {
  const maybe = error as { code?: string; message?: string; response?: unknown } | undefined;
  if (!maybe) return true;
  if (!maybe.response) return true;
  const text = `${maybe.code ?? ''} ${maybe.message ?? ''}`.toLowerCase();
  return text.includes('network') || text.includes('timeout') || text.includes('offline') || text.includes('failed to fetch');
}

export function listOfflineDrawingDrafts(fieldId?: string): DrawFeature[] {
  const drafts = readJsonArray<DrawFeature>(DRAWING_DRAFTS_STORAGE_KEY);
  return fieldId ? drafts.filter((f) => f.properties?.fieldId === fieldId) : drafts;
}

export function saveOfflineDrawingDraft(feature: DrawFeature): DrawFeature {
  const draft: DrawFeature = {
    ...feature,
    id: feature.id || randomId('draw_draft'),
    draft: true,
    properties: {
      ...feature.properties,
      offlineDraft: true,
      operationId: feature.properties?.operationId ?? randomId('draw_op'),
    },
    updatedAt: nowIso(),
  };
  const drafts = listOfflineDrawingDrafts().filter((f) => f.id !== draft.id);
  writeJsonArray(DRAWING_DRAFTS_STORAGE_KEY, [draft, ...drafts]);
  return draft;
}

export function removeOfflineDrawingDraft(featureId: string): void {
  writeJsonArray(
    DRAWING_DRAFTS_STORAGE_KEY,
    listOfflineDrawingDrafts().filter((f) => f.id !== featureId),
  );
}

export function clearOfflineDrawingDrafts(fieldId?: string): void {
  if (!fieldId) {
    writeJsonArray(DRAWING_DRAFTS_STORAGE_KEY, []);
    return;
  }
  writeJsonArray(
    DRAWING_DRAFTS_STORAGE_KEY,
    listOfflineDrawingDrafts().filter((f) => f.properties?.fieldId !== fieldId),
  );
}

export function listDrawingSyncQueue(status?: DrawingOfflineOperationStatus): DrawingOfflineQueueItem[] {
  const queue = readJsonArray<DrawingOfflineQueueItem>(DRAWING_SYNC_QUEUE_STORAGE_KEY);
  return status ? queue.filter((item) => item.status === status) : queue;
}

export function listQueuedDrawingFeatures(fieldId?: string): DrawFeature[] {
  return listDrawingSyncQueue()
    .filter((item) => item.type === 'create' && item.feature && item.status !== 'synced')
    .map((item) => item.feature as DrawFeature)
    .filter((feature) => !fieldId || feature.properties?.fieldId === fieldId);
}

function writeDrawingSyncQueue(queue: DrawingOfflineQueueItem[]): void {
  writeJsonArray(DRAWING_SYNC_QUEUE_STORAGE_KEY, queue);
}

export function enqueueDrawingOperation(item: Omit<DrawingOfflineQueueItem, 'id' | 'operationId' | 'status' | 'attemptCount' | 'createdAt' | 'updatedAt'> & {
  operationId?: string;
  status?: DrawingOfflineOperationStatus;
}): DrawingOfflineQueueItem {
  const timestamp = nowIso();
  const featureId = item.featureId || item.feature?.id || randomId('draw_feature');
  const operationId = item.operationId || item.feature?.properties?.operationId?.toString() || randomId('draw_op');
  const queueItem: DrawingOfflineQueueItem = {
    ...item,
    id: randomId('draw_queue'),
    operationId,
    featureId,
    status: item.status ?? 'pending',
    attemptCount: 0,
    createdAt: timestamp,
    updatedAt: timestamp,
  };
  writeDrawingSyncQueue([...listDrawingSyncQueue(), queueItem]);
  if (item.feature && item.type === 'create') saveOfflineDrawingDraft(item.feature);
  return queueItem;
}

export function enqueueDrawingCreate(feature: DrawFeature): DrawingOfflineQueueItem {
  const offlineFeature = saveOfflineDrawingDraft({
    ...feature,
    draft: true,
    properties: { ...feature.properties, offlinePending: true },
  });
  return enqueueDrawingOperation({
    type: 'create',
    featureId: offlineFeature.id,
    fieldId: offlineFeature.properties.fieldId?.toString(),
    feature: offlineFeature,
  });
}

export function enqueueDrawingUpdate(featureId: string, patch: Partial<DrawFeature>, fieldId?: string): DrawingOfflineQueueItem {
  return enqueueDrawingOperation({ type: 'update', featureId, fieldId, patch });
}

export function enqueueDrawingDelete(featureId: string, fieldId?: string): DrawingOfflineQueueItem {
  return enqueueDrawingOperation({ type: 'delete', featureId, fieldId });
}

function updateQueueItem(id: string, patch: Partial<DrawingOfflineQueueItem>): void {
  writeDrawingSyncQueue(
    listDrawingSyncQueue().map((item) => (item.id === id ? { ...item, ...patch, updatedAt: nowIso() } : item)),
  );
}

export async function syncDrawingQueue(client: DrawingOfflineSyncClient): Promise<DrawingOfflineSyncResult> {
  const pending = listDrawingSyncQueue().filter((item) => item.status === 'pending' || item.status === 'failed');
  let synced = 0;
  let failed = 0;

  for (const item of pending) {
    updateQueueItem(item.id, { status: 'syncing', attemptCount: item.attemptCount + 1, lastError: undefined });
    try {
      if (item.type === 'create' && item.feature) {
        const saved = await client.create({
          ...item.feature,
          draft: false,
          properties: { ...item.feature.properties, offlinePending: false, offlineDraft: false },
        });
        removeOfflineDrawingDraft(item.feature.id);
        if (saved.id && saved.id !== item.feature.id) removeOfflineDrawingDraft(saved.id);
      } else if (item.type === 'update') {
        await client.update(item.featureId, item.patch ?? {});
      } else if (item.type === 'delete') {
        await client.delete(item.featureId);
        removeOfflineDrawingDraft(item.featureId);
      }
      updateQueueItem(item.id, { status: 'synced', syncedAt: nowIso() });
      synced += 1;
    } catch (error) {
      const message = error instanceof Error ? error.message : 'sync failed';
      updateQueueItem(item.id, { status: 'failed', lastError: message });
      failed += 1;
    }
  }

  const remaining = listDrawingSyncQueue().filter((item) => item.status !== 'synced').length;
  return { attempted: pending.length, synced, failed, remaining };
}

export function compactSyncedDrawingQueue(): void {
  writeDrawingSyncQueue(listDrawingSyncQueue().filter((item) => item.status !== 'synced'));
}
