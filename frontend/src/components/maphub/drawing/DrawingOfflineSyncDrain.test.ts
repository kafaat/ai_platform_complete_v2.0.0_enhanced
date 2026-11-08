// R10 (audit 2026-11-01): الرسوم المحفوظة دون اتّصال كانت تُعرَض «محفوظة» ولا يُفرَّغ طابورها أبداً
// (syncOfflineDrawingFeatures بلا أيّ مُستدعٍ). هذه الاختبارات تُثبت: الحالة الحقيقيّة (pending)،
// التفريغ عند عودة الاتّصال مرّة واحدة، بقاء العنصر عند 401، وعدم الإرسال المزدوج.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const kong = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}));
vi.mock('../../../services/api', () => ({ kongApi: kong }));

import {
  DRAWING_DRAFTS_STORAGE_KEY,
  DRAWING_SYNC_AUTH_REQUIRED_EVENT,
  DRAWING_SYNC_QUEUE_STORAGE_KEY,
  listDrawingSyncQueue,
  listQueuedDrawingFeatures,
} from './drawingOfflineSync';
import {
  createDrawingFeatureOfflineFirst,
  isDrawingPendingSync,
  startOfflineDrawingAutoSync,
  syncOfflineDrawingFeatures,
} from './drawingFeatureApi';
import type { DrawFeature } from './drawingTypes';

const feature: DrawFeature = {
  id: 'zone-offline-1',
  kind: 'management-zone',
  geometry: {
    type: 'Polygon',
    coordinates: [[[44.0, 15.0], [44.01, 15.0], [44.01, 15.01], [44.0, 15.0]]],
  },
  properties: { fieldId: 'field-1', name: 'Zone A' },
  version: 1,
  draft: false,
};

const networkError = () => Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' });
const httpError = (status: number) =>
  Object.assign(new Error(`Request failed with status code ${status}`), { response: { status } });
const ok = (data: unknown) => Promise.resolve({ data });

let online = true;

async function saveWhileOffline() {
  kong.post.mockRejectedValueOnce(networkError());
  return createDrawingFeatureOfflineFirst(feature);
}

describe('R10 offline drawing queue is drained, idempotent and honest about its state', () => {
  beforeEach(() => {
    window.localStorage.removeItem(DRAWING_DRAFTS_STORAGE_KEY);
    window.localStorage.removeItem(DRAWING_SYNC_QUEUE_STORAGE_KEY);
    kong.post.mockReset();
    kong.patch.mockReset();
    kong.delete.mockReset();
    online = true;
    vi.spyOn(window.navigator, 'onLine', 'get').mockImplementation(() => online);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('offline save is reported as pending sync, not as saved', async () => {
    const saved = await saveWhileOffline();

    expect(isDrawingPendingSync(saved)).toBe(true);
    expect(saved.properties.offlineSyncState).toBe('pending');
    const [queued] = listQueuedDrawingFeatures('field-1');
    expect(queued.id).toBe('zone-offline-1');
    expect(queued.properties.offlineSyncState).toBe('pending');
    expect(isDrawingPendingSync(queued)).toBe(true);
  });

  it('reconnect (online event) uploads the queued drawing exactly once with a stable Idempotency-Key', async () => {
    vi.useFakeTimers();
    await saveWhileOffline();
    const [item] = listDrawingSyncQueue();

    online = false;
    const stop = startOfflineDrawingAutoSync();
    await vi.advanceTimersByTimeAsync(0);
    expect(kong.post).toHaveBeenCalledTimes(1); // فقط محاولة الحفظ الأصليّة

    kong.post.mockImplementation((_url: string, body: DrawFeature) => ok({ ...body }));
    online = true;
    window.dispatchEvent(new Event('online'));
    await vi.advanceTimersByTimeAsync(0);
    // دورة المؤقّت الدوريّ اللاحقة لا تُعيد إرسال ما رُفع.
    await vi.advanceTimersByTimeAsync(120_000);
    stop();

    expect(kong.post).toHaveBeenCalledTimes(2);
    const [url, body, config] = kong.post.mock.calls[1];
    expect(url).toBe('/api/v1/drawing-features');
    expect(body.id).toBe('zone-offline-1'); // معرّف العميل ⇒ upsert في الخادم
    expect(body.draft).toBe(false);
    expect(body.properties.offlinePending).toBeUndefined();
    expect(config).toEqual({ headers: { 'Idempotency-Key': item.operationId } });
    expect(listQueuedDrawingFeatures('field-1')).toHaveLength(0);
  });

  it('401 keeps the item queued as auth_required and asks for re-login', async () => {
    await saveWhileOffline();
    const onAuth = vi.fn();
    window.addEventListener(DRAWING_SYNC_AUTH_REQUIRED_EVENT, onAuth);

    kong.post.mockRejectedValueOnce(httpError(401));
    const result = await syncOfflineDrawingFeatures();
    window.removeEventListener(DRAWING_SYNC_AUTH_REQUIRED_EVENT, onAuth);

    expect(result.authRequired).toBe(true);
    expect(result.synced).toBe(0);
    expect(result.remaining).toBe(1);
    expect(onAuth).toHaveBeenCalledTimes(1);
    const [item] = listDrawingSyncQueue();
    expect(item.status).toBe('pending');
    expect(item.authRequired).toBe(true);
    expect(listQueuedDrawingFeatures('field-1')[0].properties.offlineSyncState).toBe('auth_required');

    // لا إعادة إرسال دوريّة بلا جلسة جديدة؛ بعد تجدّد الجلسة (force) يُرفع.
    await syncOfflineDrawingFeatures();
    expect(kong.post).toHaveBeenCalledTimes(2);
    kong.post.mockImplementation((_url: string, body: DrawFeature) => ok(body));
    const after = await syncOfflineDrawingFeatures({ force: true });
    expect(after.synced).toBe(1);
    expect(kong.post).toHaveBeenCalledTimes(3);
  });

  it('a save rejected for an expired session is queued instead of lost', async () => {
    kong.post.mockRejectedValueOnce(httpError(401));
    const saved = await createDrawingFeatureOfflineFirst(feature);
    expect(isDrawingPendingSync(saved)).toBe(true);
    expect(saved.properties.offlineSyncState).toBe('auth_required');
    expect(listDrawingSyncQueue()).toHaveLength(1);
  });

  it('concurrent and repeated drains do not double-post', async () => {
    await saveWhileOffline();
    let release!: (v: { data: DrawFeature }) => void;
    kong.post.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));

    const first = syncOfflineDrawingFeatures();
    const second = syncOfflineDrawingFeatures();
    release({ data: feature });
    const [a, b] = await Promise.all([first, second]);
    await syncOfflineDrawingFeatures();

    expect(kong.post).toHaveBeenCalledTimes(2); // الحفظ الأصليّ + رفع واحد
    expect(a).toBe(b);
    expect(a.synced).toBe(1);
  });

  it('permanent 4xx moves the item to a visible failed state and stops retrying it', async () => {
    await saveWhileOffline();
    kong.post.mockRejectedValueOnce(httpError(422));
    const result = await syncOfflineDrawingFeatures();

    expect(result.failed).toBe(1);
    const [queued] = listQueuedDrawingFeatures('field-1');
    expect(queued.properties.offlineSyncState).toBe('failed');
    expect(queued.properties.offlineSyncError).toContain('422');
    await syncOfflineDrawingFeatures({ force: true });
    expect(kong.post).toHaveBeenCalledTimes(2);
  });

  it('transient failures back off instead of hammering the server', async () => {
    await saveWhileOffline();
    const now = Date.parse('2026-11-02T00:00:00Z');
    kong.post.mockRejectedValueOnce(httpError(503));
    const first = await syncOfflineDrawingFeatures({ now });
    expect(first.deferred).toBe(1);
    expect(listDrawingSyncQueue()[0].status).toBe('pending');

    await syncOfflineDrawingFeatures({ now: now + 1_000 });
    expect(kong.post).toHaveBeenCalledTimes(2);

    kong.post.mockImplementation((_url: string, body: DrawFeature) => ok(body));
    const later = await syncOfflineDrawingFeatures({ now: now + 10_000 });
    expect(later.synced).toBe(1);
  });
});
