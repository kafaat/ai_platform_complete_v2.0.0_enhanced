export type OperationalOverlayId = 'weather' | 'alerts' | 'devices' | 'equipment' | 'tasks';

export const MAPHUB_OPERATIONAL_OVERLAY_LIMIT = 3;

export type OperationalOverlayState = Record<OperationalOverlayId, boolean>;

export function countActiveOperationalOverlays(state: OperationalOverlayState): number {
  return Object.values(state).filter(Boolean).length;
}

export function isOperationalOverlayBlocked(
  id: OperationalOverlayId,
  state: OperationalOverlayState,
  limit = MAPHUB_OPERATIONAL_OVERLAY_LIMIT,
): boolean {
  return !state[id] && countActiveOperationalOverlays(state) >= limit;
}

export function mapClutterBlockedTitle(blocked: boolean): string | undefined {
  return blocked
    ? `لا يمكن تفعيل أكثر من ${MAPHUB_OPERATIONAL_OVERLAY_LIMIT} طبقات تشغيلية في وقت واحد. أوقف طبقة أخرى أولاً.`
    : undefined;
}
