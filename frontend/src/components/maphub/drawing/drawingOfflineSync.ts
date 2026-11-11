import { getAuthScope } from '../../../lib/authStorage';
import type { DrawFeature } from './drawingTypes';

export type DrawingOfflineOperationType = 'create' | 'update' | 'delete';
export type DrawingOfflineOperationStatus = 'pending' | 'syncing' | 'failed' | 'synced';
// الحالة الظاهرة للمستخدم (R10): «محفوظ محلياً بانتظار المزامنة» ≠ «محفوظ في الخادم».
// UI-facing state: a queued drawing is never presented as server-saved.
export type DrawingOfflineSyncState = 'pending' | 'auth_required' | 'failed';
export type DrawingSyncErrorClass = 'transient' | 'auth' | 'permanent';

export const DRAWING_DRAFTS_STORAGE_KEY = 'sahool.drawing.offline.drafts.v1';
export const DRAWING_SYNC_QUEUE_STORAGE_KEY = 'sahool.drawing.offline.syncQueue.v1';
/** يُطلَق عند 401 أثناء التفريغ: العناصر تبقى في الطابور والمستخدم يُطالَب بإعادة الدخول. */
export const DRAWING_SYNC_AUTH_REQUIRED_EVENT = 'sahool:drawing-sync:auth-required';
/** يُطلَق بعد كلّ تغيّر في حالة الطابور كي تُحدِّث الواجهة شاراتها. */
export const DRAWING_SYNC_CHANGED_EVENT = 'sahool:drawing-sync:changed';
// عنصر «syncing» أقدم من هذا يُعدّ يتيماً (أُغلقت الصفحة أثناء الرفع) فيُعاد — آمن لأنّ
// الرفع idempotent (معرّف العميل + Idempotency-Key). A crashed upload is retried safely.
export const DRAWING_SYNC_LEASE_MS = 2 * 60 * 1000;
const BACKOFF_BASE_MS = 5_000;
const BACKOFF_MAX_MS = 5 * 60 * 1000;

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
  /** لا يُعاد قبل هذا الوقت (backoff أُسّيّ بعد فشل عابر). */
  nextAttemptAt?: string;
  /** 401/توكن منتهٍ: يبقى معلّقاً حتى تتجدّد الجلسة. */
  authRequired?: boolean;
  createdAt: string;
  updatedAt: string;
  syncedAt?: string;
}

export interface DrawingOfflineSyncRequestMeta {
  /** ثابت عبر كلّ المحاولات لنفس العملية ⇒ إعادة المحاولة لا تُكرِّر. */
  idempotencyKey: string;
  ownerScope?: string;
}

export interface DrawingOfflineSyncClient {
  create(feature: DrawFeature, meta?: DrawingOfflineSyncRequestMeta): Promise<DrawFeature>;
  update(featureId: string, patch: Partial<DrawFeature>, meta?: DrawingOfflineSyncRequestMeta): Promise<DrawFeature>;
  delete(featureId: string, meta?: DrawingOfflineSyncRequestMeta): Promise<unknown>;
}

export interface DrawingOfflineSyncOptions {
  /** تجاهل نافذة الـbackoff وأعِد عناصر authRequired (عودة الاتّصال/تجدّد الجلسة). */
  force?: boolean;
  now?: number;
}

export interface DrawingOfflineSyncResult {
  attempted: number;
  synced: number;
  failed: number;
  remaining: number;
  /** فشل عابر أُجِّل بـbackoff (يبقى pending). */
  deferred?: number;
  /** 401: توقّف التفريغ والعناصر باقية بانتظار إعادة الدخول. */
  authRequired?: boolean;
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

let capturedStorageOwner: string | null = null;
/** Synchronous preservation after a request clears an expired session. Never used for replay. */
export function withDrawingOwnerScope<T>(owner: string, operation: () => T): T {
  const previous = capturedStorageOwner;
  capturedStorageOwner = owner;
  try { return operation(); } finally { capturedStorageOwner = previous; }
}

function readJsonArray<T>(key: string): T[] {
  const storage = getStorage();
  if (!storage) return [];
  try {
    const owner = capturedStorageOwner ?? getAuthScope();
    if (!owner) return [];
    const raw = storage.getItem(`${key}:owner:${encodeURIComponent(owner)}`);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function writeJsonArray<T>(key: string, value: T[]): void {
  const storage = getStorage();
  const owner = capturedStorageOwner ?? getAuthScope();
  if (!storage || !owner) throw new Error('تعذّر حفظ الرسم محليًا: لا توجد جلسة معرّفة أو مساحة تخزين متاحة.');
  // Legacy unscoped data is deliberately not migrated to a possibly different owner.
  storage.setItem(`${key}:owner:${encodeURIComponent(owner)}`, JSON.stringify(value));
}

/**
 * Drawings queued by a build that stored them under one shared key (no tenant/user scope).
 * They are never replayed: the owner is unknown, and sending them under whoever is signed in now
 * is exactly the cross-account replay the scoped storage prevents. They are counted so the map
 * can tell the user they exist instead of letting them vanish silently.
 */
export function countLegacyUnscopedDrawingOperations(): number {
  const storage = getStorage();
  if (!storage) return 0;
  try {
    const parsed = JSON.parse(storage.getItem(DRAWING_SYNC_QUEUE_STORAGE_KEY) || '[]');
    return Array.isArray(parsed)
      ? parsed.filter((item: { status?: string }) => item?.status !== 'synced').length
      : 0;
  } catch { return 0; }
}

/** Explicit user action: drop the legacy unscoped drafts and queue (never sent anywhere). */
export function discardLegacyUnscopedDrawingData(): void {
  const storage = getStorage();
  if (!storage) return;
  try {
    storage.removeItem(DRAWING_SYNC_QUEUE_STORAGE_KEY);
    storage.removeItem(DRAWING_DRAFTS_STORAGE_KEY);
  } catch { /* storage blocked: nothing to discard */ }
  emitDrawingSyncEvent(DRAWING_SYNC_CHANGED_EVENT);
}

export function isLikelyOfflineError(error: unknown): boolean {
  const maybe = error as { code?: string; message?: string; response?: unknown } | undefined;
  if (!maybe) return true;
  if (!maybe.response) return true;
  const text = `${maybe.code ?? ''} ${maybe.message ?? ''}`.toLowerCase();
  return text.includes('network') || text.includes('timeout') || text.includes('offline') || text.includes('failed to fetch');
}

/**
 * تصنيف خطأ الرفع: 401 (أو توكن منتهٍ يرفضه interceptor قبل الإرسال) ⇒ auth يُبقي
 * العنصر في الطابور؛ 408/425/429/5xx/انقطاع ⇒ عابر يُعاد بـbackoff؛ باقي 4xx ⇒ دائم.
 */
export function classifyDrawingSyncError(error: unknown): DrawingSyncErrorClass {
  const maybe = error as { message?: string; response?: { status?: number } } | undefined;
  const status = maybe?.response?.status;
  if (status === 401) return 'auth';
  if (typeof status === 'number') {
    if (status === 408 || status === 425 || status === 429 || status >= 500) return 'transient';
    if (status >= 400) return 'permanent';
  }
  if (!status && /access token expired/i.test(maybe?.message ?? '')) return 'auth';
  return 'transient';
}

export function drawingSyncBackoffMs(attemptCount: number): number {
  const exp = Math.max(0, attemptCount - 1);
  return Math.min(BACKOFF_MAX_MS, BACKOFF_BASE_MS * 2 ** exp);
}

function emitDrawingSyncEvent(name: string, detail?: Record<string, unknown>): void {
  if (typeof window === 'undefined' || typeof window.dispatchEvent !== 'function') return;
  try {
    window.dispatchEvent(new CustomEvent(name, { detail }));
  } catch {
    // لا نكسر المزامنة إن لم يتوفّر CustomEvent.
  }
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

export function drawingSyncStateOf(item: DrawingOfflineQueueItem): DrawingOfflineSyncState | null {
  if (item.status === 'synced') return null;
  if (item.status === 'failed') return 'failed';
  return item.authRequired ? 'auth_required' : 'pending';
}

export function listQueuedDrawingFeatures(fieldId?: string): DrawFeature[] {
  // الحالة الحقيقيّة تُحمَل على النموذج (offlineSyncState) فلا تُعرَض الرسمة «محفوظة».
  return listDrawingSyncQueue()
    .filter((item) => item.type === 'create' && item.feature && item.status !== 'synced')
    .map((item) => {
      const feature = item.feature as DrawFeature;
      return {
        ...feature,
        draft: true,
        properties: {
          ...feature.properties,
          offlinePending: true,
          offlineQueueId: item.id,
          offlineSyncState: drawingSyncStateOf(item),
          ...(item.status === 'failed' && item.lastError ? { offlineSyncError: item.lastError } : {}),
        },
      } as DrawFeature;
    })
    .filter((feature) => !fieldId || feature.properties?.fieldId === fieldId);
}

export interface DrawingSyncQueueSummary {
  pending: number;
  authRequired: number;
  failed: number;
}

export function summarizeDrawingSyncQueue(): DrawingSyncQueueSummary {
  const summary: DrawingSyncQueueSummary = { pending: 0, authRequired: 0, failed: 0 };
  for (const item of listDrawingSyncQueue()) {
    const state = drawingSyncStateOf(item);
    if (state === 'pending') summary.pending += 1;
    else if (state === 'auth_required') summary.authRequired += 1;
    else if (state === 'failed') summary.failed += 1;
  }
  return summary;
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
  emitDrawingSyncEvent(DRAWING_SYNC_CHANGED_EVENT);
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

function stripOfflineProps(feature: DrawFeature): DrawFeature {
  const { offlinePending: _p, offlineDraft: _d, offlineQueueId: _q, offlineSyncState: _s, offlineSyncError: _e, ...properties } =
    feature.properties ?? {};
  return { ...feature, draft: false, properties };
}

function isDueForSync(item: DrawingOfflineQueueItem, now: number, force: boolean): boolean {
  if (item.status === 'syncing') return now - Date.parse(item.updatedAt) >= DRAWING_SYNC_LEASE_MS;
  if (item.status !== 'pending') return false; // failed دائم: يُعرَض ولا يُعاد تلقائياً.
  if (force) return true;
  if (item.authRequired) return false;
  return !item.nextAttemptAt || Date.parse(item.nextAttemptAt) <= now;
}

let inFlightDrain: Promise<DrawingOfflineSyncResult> | null = null;

/**
 * تفريغ الطابور. single-flight: استدعاء متزامن يعيد نفس الوعد فلا يُرسَل عنصر مرّتين.
 * Single-flight drain — concurrent callers share one run, so no item is double-posted.
 */
export function syncDrawingQueue(client: DrawingOfflineSyncClient, options: DrawingOfflineSyncOptions = {}): Promise<DrawingOfflineSyncResult> {
  if (inFlightDrain) return inFlightDrain;
  inFlightDrain = drainDrawingQueue(client, options).finally(() => {
    inFlightDrain = null;
  });
  return inFlightDrain;
}

async function drainDrawingQueue(client: DrawingOfflineSyncClient, options: DrawingOfflineSyncOptions): Promise<DrawingOfflineSyncResult> {
  const ownerScope = getAuthScope();
  const now = options.now ?? Date.now();
  const due = listDrawingSyncQueue().filter((item) => isDueForSync(item, now, Boolean(options.force)));
  let attempted = 0;
  let synced = 0;
  let failed = 0;
  let deferred = 0;
  let authRequired = false;

  for (const item of due) {
    if (!ownerScope || getAuthScope() !== ownerScope) { authRequired = true; break; }
    attempted += 1;
    const attemptCount = item.attemptCount + 1;
    const meta: DrawingOfflineSyncRequestMeta = { idempotencyKey: item.operationId, ownerScope };
    updateQueueItem(item.id, { status: 'syncing', attemptCount, lastError: undefined });
    try {
      if (item.type === 'create' && item.feature) {
        // معرّف الرسمة يولّده العميل والخادم يعمل upsert عليه ⇒ الإعادة لا تُنشئ نسخة ثانية.
        const saved = await client.create(stripOfflineProps(item.feature), meta);
        if (getAuthScope() !== ownerScope) { authRequired = true; break; }
        removeOfflineDrawingDraft(item.feature.id);
        if (saved?.id && saved.id !== item.feature.id) removeOfflineDrawingDraft(saved.id);
      } else if (item.type === 'update') {
        await client.update(item.featureId, item.patch ?? {}, meta);
      } else if (item.type === 'delete') {
        try {
          await client.delete(item.featureId, meta);
        } catch (error) {
          // 404 على حذف = محذوفة أصلاً (إعادة بعد نجاح لم يُسجَّل) ⇒ نجاح.
          if ((error as { response?: { status?: number } })?.response?.status !== 404) throw error;
        }
        if (getAuthScope() !== ownerScope) { authRequired = true; break; }
        removeOfflineDrawingDraft(item.featureId);
      }
      if (getAuthScope() !== ownerScope) { authRequired = true; break; }
      updateQueueItem(item.id, { status: 'synced', syncedAt: nowIso(), authRequired: false, nextAttemptAt: undefined });
      synced += 1;
    } catch (error) {
      if (getAuthScope() !== ownerScope) { authRequired = true; break; }
      const message = error instanceof Error ? error.message : 'sync failed';
      const kind = classifyDrawingSyncError(error);
      if (kind === 'permanent') {
        updateQueueItem(item.id, { status: 'failed', lastError: message, nextAttemptAt: undefined });
        failed += 1;
        continue;
      }
      if (kind === 'auth') {
        // 401 لا يستهلك محاولة ولا يُسقط العنصر: يبقى pending حتى تتجدّد الجلسة.
        updateQueueItem(item.id, { status: 'pending', attemptCount: item.attemptCount, authRequired: true, lastError: message });
        authRequired = true;
      } else {
        updateQueueItem(item.id, {
          status: 'pending',
          lastError: message,
          nextAttemptAt: new Date(now + drawingSyncBackoffMs(attemptCount)).toISOString(),
        });
        deferred += 1;
      }
      // عابر/مصادقة: نتوقّف كي لا نُرسل عمليات لاحقة لنفس الرسمة قبل سابقتها.
      break;
    }
  }

  const remaining = listDrawingSyncQueue().filter((item) => item.status !== 'synced').length;
  // Only a drain that touched the queue changes what the map shows; an idle periodic run must
  // not make every listener refetch (MapHub reloads its saved drawings on this event).
  if (attempted > 0) emitDrawingSyncEvent(DRAWING_SYNC_CHANGED_EVENT, { synced, failed, remaining });
  if (authRequired) {
    emitDrawingSyncEvent(DRAWING_SYNC_AUTH_REQUIRED_EVENT, { pending: remaining });
  }
  return { attempted, synced, failed, remaining, deferred, authRequired };
}

/** إعادة عنصر فشل دائماً إلى الطابور بطلب صريح من المستخدم (بعد تصحيح السبب). */
export function retryFailedDrawingOperation(queueId: string): void {
  updateQueueItem(queueId, { status: 'pending', nextAttemptAt: undefined, authRequired: false });
  emitDrawingSyncEvent(DRAWING_SYNC_CHANGED_EVENT);
}

/** نافذة المحاولة التالية لأقرب عنصر مؤجَّل (لجدولة المؤقّت الدوريّ). */
export function nextDrawingSyncDueInMs(now: number = Date.now()): number | null {
  let next: number | null = null;
  for (const item of listDrawingSyncQueue()) {
    if (item.status !== 'pending' || item.authRequired) continue;
    const due = item.nextAttemptAt ? Date.parse(item.nextAttemptAt) - now : 0;
    next = next === null ? due : Math.min(next, due);
  }
  return next === null ? null : Math.max(0, next);
}

export function compactSyncedDrawingQueue(): void {
  writeDrawingSyncQueue(listDrawingSyncQueue().filter((item) => item.status !== 'synced'));
}
