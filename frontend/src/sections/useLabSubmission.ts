import { useRef, useState } from 'react';
import { asApiError } from '../services/api';

function commandId(): string {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  return [hex.slice(0, 8), hex.slice(8, 12), hex.slice(12, 16), hex.slice(16, 20), hex.slice(20)].join('-');
}

// The parent keys this component by tenant, actor, field and collection point.
export function useLabSubmission<P extends { idempotency_key?: string }, R>(
  kind: 'sample' | 'result', scope: string, send: (body: P) => Promise<R>,
) {
  const key = 'sahool.lab.pending.' + kind + '.' + scope;
  const [restored] = useState(() => {
    try {
      const raw = sessionStorage.getItem(key);
      const pending: P | null = raw ? JSON.parse(raw) : null;
      if (raw && !pending?.idempotency_key) throw new Error('invalid local submission');
      return {pending, blocked: false};
    } catch {
      return {pending: null, blocked: true};
    }
  });
  const [pending, setPending] = useState(restored.pending);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  // A synchronous guard, not state: two clicks in one tick must not both send.
  const release = () => { inFlight.current = false; };

  async function submit(build: () => P | undefined) {
    if (inFlight.current || restored.blocked) return;
    const body = pending ?? build();
    if (!body) return;
    inFlight.current = true;
    setBusy(true);
    try {
      if (!pending) {
        body.idempotency_key = commandId();
        sessionStorage.setItem(key, JSON.stringify(body));
        setPending(body);
      }
      function clearOriginal() {
        // A late response from another mount must not clear a newer command.
        const current = sessionStorage.getItem(key);
        if (current && JSON.parse(current).idempotency_key === body?.idempotency_key) {
          sessionStorage.removeItem(key);
        }
        setPending(null);
      }
      let result: R;
      try {
        result = await send(body);
      } catch (error) {
        const status = asApiError(error).response?.status;
        if (!pending && [400, 401, 403, 404, 422].includes(status ?? 0)) {
          clearOriginal();
        }
        throw error;
      }
      clearOriginal();
      return result;
    } finally {
      release();
      setBusy(false);
    }
  }
  return {submit, pending, busy, blocked: restored.blocked};
}
