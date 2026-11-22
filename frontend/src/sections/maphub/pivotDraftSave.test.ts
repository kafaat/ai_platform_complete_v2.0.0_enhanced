import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kongApi } from '../../services/api';
import { getAuthScope } from '../../lib/authStorage';
import { listQueuedDrawingFeatures } from '../../components/maphub/drawing/drawingOfflineSync';
import type { DrawFeature } from '../../components/maphub/drawing/drawingTypes';
import { pivotSaveFeedback, remainingPivotDrafts, savePivotDraftBatch } from './pivotDraftSave';

function draft(id: string, name: string): DrawFeature {
  return {
    id, kind: 'pivot', version: 1, draft: true,
    geometry: { type: 'Polygon', coordinates: [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15]]] },
    properties: { name, fieldId: 'field-1', seasonId: 'season-1', localOwnerScope: getAuthScope() },
  };
}

const outsideField = 'التصميم يمتد خارج حدود الحقل المرتبط.';
function topologyError() {
  return Object.assign(new Error('Request failed with status code 422'), {
    response: { status: 422, data: { detail: {
      code: 'drawing_topology_invalid', message_ar: 'فشل تحقق PostGIS للهندسة.',
      validation: { valid: false, issues: [{ code: 'postgis-outside-parent-field', severity: 'error', message_ar: outsideField }] },
    } } },
  });
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  sessionStorage.setItem('sahool_access_token', 'test-token');
  sessionStorage.setItem('sahool_tenant_id', 'test-tenant');
  sessionStorage.setItem('sahool_user', JSON.stringify({ id: 'test-user' }));
});
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe('Pivot batch save through the existing offline-first API', () => {
  it('waits for a delayed success after a topology rejection and retries only the rejected draft', async () => {
    const accepted = draft('accepted', 'المحوري الشمالي');
    const rejected = draft('rejected', 'المحوري الجنوبي');
    let finishAccepted!: () => void;
    const post = vi.spyOn(kongApi, 'post').mockImplementation((_url, body) => {
      const feature = body as DrawFeature;
      if (feature.id === rejected.id) return Promise.reject(topologyError());
      return new Promise(resolve => { finishAccepted = () => resolve({ data: { ...feature, savedBy: 'test-user' } }); });
    });
    let settled = false;
    const pending = savePivotDraftBatch([accepted, rejected]).finally(() => { settled = true; });
    await new Promise(resolve => setTimeout(resolve, 0));
    expect(post).toHaveBeenCalledTimes(2);
    expect(settled).toBe(false);
    finishAccepted();
    const outcomes = await pending;
    expect(outcomes.map(outcome => outcome.status)).toEqual(['saved', 'rejected']);
    const remaining = remainingPivotDrafts([accepted, rejected], outcomes);
    expect(remaining).toEqual([rejected]);
    expect(listQueuedDrawingFeatures('field-1')).toHaveLength(0);

    // A newly drawn shape or another field/owner's matching id is not part of this save.
    const addedDuringSave = draft('new', 'مسودة جديدة');
    const otherField = { ...accepted, properties: { ...accepted.properties, fieldId: 'field-2' } };
    const otherOwner = { ...accepted, properties: { ...accepted.properties, localOwnerScope: 'other-owner' } };
    expect(remainingPivotDrafts([accepted, rejected, addedDuringSave, otherField, otherOwner], outcomes))
      .toEqual([rejected, addedDuringSave, otherField, otherOwner]);

    const feedback = pivotSaveFeedback(outcomes);
    expect(feedback.type).toBe('warning');
    expect(feedback.message).toContain('محفوظة بالخادم (1): المحوري الشمالي');
    expect(feedback.message).toContain(`بقيت كمسودات (1): المحوري الجنوبي — ${outsideField}`);
    expect(feedback.message).not.toContain('بانتظار المزامنة');

    post.mockImplementation(async (_url, body) => ({ data: { ...(body as DrawFeature), savedBy: 'test-user' } }));
    const retried = await savePivotDraftBatch(remaining);
    expect(remainingPivotDrafts(remaining, retried)).toEqual([]);
    expect(pivotSaveFeedback(retried).type).toBe('success');
    expect(post.mock.calls.map(([, body]) => (body as DrawFeature).id)).toEqual(['accepted', 'rejected', 'rejected']);
    for (const [url, rawBody, config] of post.mock.calls) {
      const body = rawBody as DrawFeature;
      expect(url).toBe('/api/v1/drawing-features');
      expect(body.draft).toBe(false);
      expect(body.properties).toMatchObject({ fieldId: 'field-1', seasonId: 'season-1', workflow: 'design-pivot' });
      expect(body.properties.localOwnerScope).toBeUndefined();
      expect(config?.expectedAuthScope).toBe(getAuthScope());
    }
  });

  it('keeps saved, durable queued and rejected outcomes distinct without resubmitting queued drafts', async () => {
    const accepted = draft('accepted', 'محفوظ');
    const queued = draft('queued', 'محلي');
    const rejected = draft('rejected', 'مرفوض');
    vi.spyOn(kongApi, 'post').mockImplementation(async (_url, body) => {
      const feature = body as DrawFeature;
      if (feature.id === queued.id) throw Object.assign(new Error('Network Error'), { code: 'ERR_NETWORK' });
      if (feature.id === rejected.id) throw topologyError();
      return { data: feature };
    });
    const outcomes = await savePivotDraftBatch([accepted, queued, rejected]);
    expect(outcomes.map(outcome => outcome.status)).toEqual(['saved', 'queued', 'rejected']);
    expect(remainingPivotDrafts([accepted, queued, rejected], outcomes)).toEqual([rejected]);
    const queuedFeatures = listQueuedDrawingFeatures('field-1');
    expect(queuedFeatures).toHaveLength(1);
    expect(queuedFeatures[0]).toMatchObject({ id: 'queued', properties: { offlinePending: true, offlineSyncState: 'pending' } });
    const feedback = pivotSaveFeedback(outcomes);
    expect(feedback.type).toBe('warning');
    expect(feedback.message).toContain('محفوظة بالخادم (1): محفوظ');
    expect(feedback.message).toContain('محلية بانتظار المزامنة (1): محلي');
    expect(feedback.message).toContain(`بقيت كمسودات (1): مرفوض — ${outsideField}`);
  });

  it('retains every permanently rejected draft and reports an error with its API reason', async () => {
    const rejected = draft('forbidden', 'تصميم غير مسموح');
    vi.spyOn(kongApi, 'post').mockRejectedValue({ response: { status: 403, data: { detail: 'لا تملك صلاحية تعديل الحقل.' } } });
    const outcomes = await savePivotDraftBatch([rejected]);
    expect(remainingPivotDrafts([rejected], outcomes)).toEqual([rejected]);
    expect(listQueuedDrawingFeatures('field-1')).toHaveLength(0);
    const feedback = pivotSaveFeedback(outcomes);
    expect(feedback.type).toBe('error');
    expect(feedback.message).toContain('تصميم غير مسموح — لا تملك صلاحية تعديل الحقل.');
    expect(feedback.message).not.toContain('محفوظة بالخادم');
  });
});
