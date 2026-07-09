// UI-30 — Field Workspace availability contract.
// يحدد سبب تعطيل التبويبات من السياق، ولا يحاول ملء season_id أو field_id افتراضياً.

import { FIELD_WORKSPACE_TABS, type FieldWorkspaceTab } from './fieldWorkspaceContract';

export interface WorkspaceAvailabilityContext {
  fieldId?: string | null;
  seasonId?: string | null;
}

export interface WorkspaceTabAvailability {
  tab: FieldWorkspaceTab;
  available: boolean;
  reason_ar?: string;
}

export function getWorkspaceTabAvailability(
  tabId: FieldWorkspaceTab,
  context: WorkspaceAvailabilityContext,
): WorkspaceTabAvailability {
  const tab = FIELD_WORKSPACE_TABS.find((x) => x.id === tabId);
  if (!tab) return { tab: tabId, available: false, reason_ar: 'تبويب غير معروف.' };
  if (tab.requires_field && !context.fieldId) {
    return { tab: tabId, available: false, reason_ar: 'يتطلب field_id حقيقياً.' };
  }
  if (tab.requires_season && !context.seasonId) {
    return { tab: tabId, available: false, reason_ar: 'يتطلب موسماً نشطاً season_id.' };
  }
  return { tab: tabId, available: true };
}

export function listUnavailableWorkspaceTabs(context: WorkspaceAvailabilityContext): WorkspaceTabAvailability[] {
  return FIELD_WORKSPACE_TABS
    .map((tab) => getWorkspaceTabAvailability(tab.id, context))
    .filter((state) => !state.available);
}
