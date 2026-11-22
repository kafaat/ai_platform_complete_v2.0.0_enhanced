import { apiErrorMessage, asApiError } from '../../services/api';
import { createDrawingFeatureOfflineFirst, isDrawingPendingSync, type PersistedDrawFeature } from '../../components/maphub/drawing/drawingFeatureApi';
import type { DrawFeature } from '../../components/maphub/drawing/drawingTypes';

export type PivotDraftSaveOutcome =
  | { status: 'saved' | 'queued'; draft: DrawFeature; feature: PersistedDrawFeature }
  | { status: 'rejected'; draft: DrawFeature; reason: string };

function rejectionReason(error: unknown): string {
  const detail = asApiError(error).response?.data?.detail;
  const validation = detail && typeof detail === 'object' && 'validation' in detail
    ? detail.validation : undefined;
  const issues = validation && typeof validation === 'object' && 'issues' in validation
    ? validation.issues : undefined;
  const messages = Array.isArray(issues) ? issues.flatMap(issue => {
    if (!issue || typeof issue !== 'object') return [];
    const message = issue.message_ar ?? issue.message ?? issue.msg;
    return typeof message === 'string' && message.trim() ? [message] : [];
  }) : [];
  return messages.length ? messages.join('، ') : apiErrorMessage(error, 'تعذّر حفظ تصميم Pivot في الخادم.');
}

/** Each POST is independent: a permanent rejection must not hide a saved or queued peer. */
export async function savePivotDraftBatch(drafts: readonly DrawFeature[]): Promise<PivotDraftSaveOutcome[]> {
  const results = await Promise.allSettled(drafts.map(draft => createDrawingFeatureOfflineFirst({
    ...draft,
    draft: false,
    properties: { ...draft.properties, localOwnerScope: undefined, workflow: 'design-pivot' },
    updatedAt: new Date().toISOString(),
  })));
  return results.map((result, index) => result.status === 'fulfilled'
    ? { status: isDrawingPendingSync(result.value) ? 'queued' : 'saved', draft: drafts[index], feature: result.value }
    : { status: 'rejected', draft: drafts[index], reason: rejectionReason(result.reason) });
}

function draftKey(draft: DrawFeature): string {
  return JSON.stringify([draft.id, draft.properties.fieldId, draft.properties.localOwnerScope]);
}

/** Keep rejected drafts, drafts added during the requests, and other field/owner scopes. */
export function remainingPivotDrafts(drafts: DrawFeature[], outcomes: PivotDraftSaveOutcome[]): DrawFeature[] {
  const completed = new Set(outcomes.filter(outcome => outcome.status !== 'rejected').map(outcome => draftKey(outcome.draft)));
  return drafts.filter(draft => !completed.has(draftKey(draft)));
}

export function pivotSaveFeedback(outcomes: PivotDraftSaveOutcome[]): {
  type: 'success' | 'warning' | 'error'; title: string; message: string;
} {
  const saved = outcomes.filter(outcome => outcome.status === 'saved');
  const queued = outcomes.filter(outcome => outcome.status === 'queued');
  const rejected = outcomes.filter((outcome): outcome is Extract<PivotDraftSaveOutcome, { status: 'rejected' }> => outcome.status === 'rejected');
  const name = (outcome: PivotDraftSaveOutcome) => outcome.draft.properties.name?.trim() || outcome.draft.id;
  const messages: string[] = [];
  if (saved.length) messages.push(`محفوظة بالخادم (${saved.length}): ${saved.map(name).join('، ')}.`);
  if (queued.length) messages.push(`محلية بانتظار المزامنة (${queued.length}): ${queued.map(name).join('، ')}.`);
  if (rejected.length) messages.push(`بقيت كمسودات (${rejected.length}): ${rejected.map(outcome => `${name(outcome)} — ${outcome.reason}`).join('؛ ')}.`);
  return {
    type: rejected.length === outcomes.length ? 'error' : rejected.length || queued.length ? 'warning' : 'success',
    title: rejected.length
      ? saved.length || queued.length ? 'تعذّر حفظ بعض تصاميم Pivot' : 'تعذّر حفظ تصاميم Pivot'
      : queued.length ? 'تصاميم Pivot بانتظار المزامنة' : 'تم حفظ تصاميم Pivot',
    message: messages.join(' '),
  };
}
