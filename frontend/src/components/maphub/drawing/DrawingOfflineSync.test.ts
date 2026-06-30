import { beforeEach, describe, expect, it } from 'vitest';
import {
  DRAWING_DRAFTS_STORAGE_KEY,
  DRAWING_SYNC_QUEUE_STORAGE_KEY,
  clearOfflineDrawingDrafts,
  enqueueDrawingCreate,
  listDrawingSyncQueue,
  listOfflineDrawingDrafts,
  listQueuedDrawingFeatures,
  saveOfflineDrawingDraft,
  syncDrawingQueue,
  type DrawFeature,
} from './index';

const feature: DrawFeature = {
  id: 'offline-pivot-1',
  kind: 'pivot',
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [44.0, 15.0],
      [44.01, 15.0],
      [44.01, 15.01],
      [44.0, 15.01],
      [44.0, 15.0],
    ]],
  },
  properties: {
    fieldId: 'field-1',
    seasonId: 'season-1',
    workflow: 'design-pivot',
  },
  measurements: { areaHa: 1.2, radiusM: 120 },
  version: 1,
  draft: true,
};

describe('v41 offline drawing drafts and sync queue', () => {
  beforeEach(() => {
    window.localStorage.removeItem(DRAWING_DRAFTS_STORAGE_KEY);
    window.localStorage.removeItem(DRAWING_SYNC_QUEUE_STORAGE_KEY);
  });

  it('stores drawing drafts by field without throwing when users work offline', () => {
    const saved = saveOfflineDrawingDraft(feature);
    expect(saved.draft).toBe(true);
    expect(saved.properties.offlineDraft).toBe(true);
    expect(listOfflineDrawingDrafts('field-1')).toHaveLength(1);
    expect(listOfflineDrawingDrafts('other-field')).toHaveLength(0);

    clearOfflineDrawingDrafts('field-1');
    expect(listOfflineDrawingDrafts('field-1')).toHaveLength(0);
  });

  it('queues create operations and exposes queued features for offline-aware map loading', () => {
    const queued = enqueueDrawingCreate(feature);
    expect(queued.type).toBe('create');
    expect(queued.status).toBe('pending');
    expect(listDrawingSyncQueue('pending')).toHaveLength(1);
    expect(listQueuedDrawingFeatures('field-1')[0].id).toBe('offline-pivot-1');
  });

  it('syncs queued drawing operations through an injected API client', async () => {
    enqueueDrawingCreate(feature);
    const result = await syncDrawingQueue({
      create: async (draft) => ({ ...draft, id: 'server-pivot-1', draft: false }),
      update: async (_id, patch) => ({ ...feature, ...patch, draft: false }),
      delete: async () => ({ deleted: true }),
    });

    expect(result.attempted).toBe(1);
    expect(result.synced).toBe(1);
    expect(result.failed).toBe(0);
    expect(listDrawingSyncQueue('synced')).toHaveLength(1);
    expect(listOfflineDrawingDrafts('field-1')).toHaveLength(0);
  });
});
