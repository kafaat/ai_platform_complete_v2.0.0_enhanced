import { useSyncExternalStore } from 'react';
import { wsService } from '../services/websocket';

// One observable source for all badges. This describes the authenticated
// notification channel, not Internet connectivity or the health of NATS.
const subscribe = (notify: () => void) => wsService.subscribeConnection(notify);
const snapshot = () => wsService.isAuthenticatedConnection();
export function useConnectionStatus() {
  return useSyncExternalStore(subscribe, snapshot, () => false);
}
