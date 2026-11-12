// طابور الرسم دون اتّصال مقيَّد بالجلسة (المستأجِر + المستخدم): لا يُفرَّغ طابور مستخدمٍ تحت
// جلسة غيره، والطابور القديم غير المقيَّد لا يُعاد بثّه بل يُعَدّ ويُعرَض على المستخدم ليقرّر،
// والتفريغ الخامل (لا شيء حاول الإرسال) لا يبثّ حدث تغيير يُعيد تحميل القائمة.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { DrawFeature } from './drawingTypes';

const kong = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), patch: vi.fn(), delete: vi.fn() }));
vi.mock('../../../services/api', () => ({ kongApi: kong }));

import {
  DRAWING_DRAFTS_STORAGE_KEY,
  DRAWING_SYNC_CHANGED_EVENT,
  DRAWING_SYNC_QUEUE_STORAGE_KEY,
  countLegacyUnscopedDrawingOperations,
  discardLegacyUnscopedDrawingData,
  listDrawingSyncQueue,
  summarizeDrawingSyncQueue,
} from './drawingOfflineSync';
import {
  createDrawingFeatureOfflineFirst,
  isDrawingPendingSync,
  syncOfflineDrawingFeatures,
} from './drawingFeatureApi';

function login(tenant: string, id: string) {
  sessionStorage.setItem('sahool_access_token', `tok-${id}`);
  sessionStorage.setItem('sahool_tenant_id', tenant);
  sessionStorage.setItem('sahool_user', JSON.stringify({ id, email: `${id}@example.test` }));
}
const feat = (id: string): DrawFeature => ({
  id, kind: 'management-zone', geometry: { type: 'Point', coordinates: [44, 15] }, properties: { fieldId: 'f1' }, version: 1,
} as unknown as DrawFeature);
const offlineErr = () => Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK', isAxiosError: true });
const legacyItem = (featureId: string) => ({
  id: `q-${featureId}`, operationId: `o-${featureId}`, type: 'create', featureId, feature: feat(featureId),
  status: 'pending', attemptCount: 0, createdAt: '', updatedAt: '',
});

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  Object.values(kong).forEach((m) => m.mockReset());
});

describe('drawing offline queue is scoped to the session', () => {
  it('does not replay tenant A / user A operations under user B', async () => {
    login('tA', 'uA');
    kong.post.mockRejectedValueOnce(offlineErr());
    expect(isDrawingPendingSync(await createDrawingFeatureOfflineFirst(feat('z1')))).toBe(true);
    expect(listDrawingSyncQueue()).toHaveLength(1);

    login('tB', 'uB');
    expect(listDrawingSyncQueue()).toHaveLength(0);
    kong.post.mockReset();
    kong.post.mockResolvedValue({ data: feat('z1') });
    const underB = await syncOfflineDrawingFeatures({ force: true });
    expect(underB.attempted).toBe(0);
    expect(kong.post).not.toHaveBeenCalled();

    login('tA', 'uA');
    const underA = await syncOfflineDrawingFeatures({ force: true });
    expect(underA.synced).toBe(1);
    expect(kong.post.mock.calls[0][2].expectedAuthScope).toBe(JSON.stringify(['tA', 'uA']));
  });

  it('isolates the same user id across tenants', async () => {
    login('tA', 'u1');
    kong.post.mockRejectedValueOnce(offlineErr());
    await createDrawingFeatureOfflineFirst(feat('z2'));
    login('tB', 'u1');
    expect(listDrawingSyncQueue()).toHaveLength(0);
  });

  it('keeps A item when the session switches mid-request and writes nothing into B', async () => {
    login('tA', 'uA');
    kong.post.mockRejectedValueOnce(offlineErr());
    await createDrawingFeatureOfflineFirst(feat('z5'));
    kong.post.mockImplementationOnce(async () => { login('tB', 'uB'); return { data: feat('z5') }; });
    const res = await syncOfflineDrawingFeatures({ force: true });
    expect(res.authRequired).toBe(true);
    expect(listDrawingSyncQueue()).toHaveLength(0);
    login('tA', 'uA');
    expect(listDrawingSyncQueue()).toHaveLength(1);
  });
});

describe('legacy unscoped queue', () => {
  it('is neither replayed nor summarized, but is counted for the user', async () => {
    localStorage.setItem(DRAWING_SYNC_QUEUE_STORAGE_KEY, JSON.stringify([legacyItem('z9'), legacyItem('z10')]));
    login('tA', 'uA');
    expect(listDrawingSyncQueue()).toHaveLength(0);
    expect(summarizeDrawingSyncQueue()).toEqual({ pending: 0, authRequired: 0, failed: 0 });
    expect(countLegacyUnscopedDrawingOperations()).toBe(2);
    await syncOfflineDrawingFeatures({ force: true });
    expect(kong.post).not.toHaveBeenCalled();
  });

  it('discard removes the old keys and announces the change', () => {
    localStorage.setItem(DRAWING_SYNC_QUEUE_STORAGE_KEY, JSON.stringify([legacyItem('z9')]));
    localStorage.setItem(DRAWING_DRAFTS_STORAGE_KEY, JSON.stringify([feat('z9')]));
    const onChange = vi.fn();
    window.addEventListener(DRAWING_SYNC_CHANGED_EVENT, onChange);
    try {
      discardLegacyUnscopedDrawingData();
    } finally {
      window.removeEventListener(DRAWING_SYNC_CHANGED_EVENT, onChange);
    }
    expect(localStorage.getItem(DRAWING_SYNC_QUEUE_STORAGE_KEY)).toBeNull();
    expect(localStorage.getItem(DRAWING_DRAFTS_STORAGE_KEY)).toBeNull();
    expect(countLegacyUnscopedDrawingOperations()).toBe(0);
    expect(onChange).toHaveBeenCalledTimes(1);
  });

  it('a malformed legacy value counts as zero', () => {
    localStorage.setItem(DRAWING_SYNC_QUEUE_STORAGE_KEY, '{not json');
    expect(countLegacyUnscopedDrawingOperations()).toBe(0);
  });
});

describe('idle drain', () => {
  it('emits no change event when nothing was attempted', async () => {
    login('tA', 'uA');
    const onChange = vi.fn();
    window.addEventListener(DRAWING_SYNC_CHANGED_EVENT, onChange);
    try {
      const res = await syncOfflineDrawingFeatures({ force: true });
      expect(res.attempted).toBe(0);
    } finally {
      window.removeEventListener(DRAWING_SYNC_CHANGED_EVENT, onChange);
    }
    expect(onChange).not.toHaveBeenCalled();
  });
});
