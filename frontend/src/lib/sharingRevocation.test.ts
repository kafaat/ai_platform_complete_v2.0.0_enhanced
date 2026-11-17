import { describe, expect, it, vi } from 'vitest';
import {
  revokeAndReconcileSharingKey,
  SHARING_REVOKE_REFRESH_FAILED_AR,
  SHARING_REVOKE_UNKNOWN_AR,
} from './sharingRevocation';

describe('sharing-key revocation result truth', () => {
  it('does not claim unchanged when the server commits but the response is lost', async () => {
    let serverRevoked = false;
    let observedRevoked = false;
    const request = vi.fn(async (url: string) => {
      expect(url).toBe('/api/v1/sharing/keys/key%207/revoke');
      serverRevoked = true;
      throw new Error('response lost after commit');
    });
    const refetch = vi.fn(async () => {
      observedRevoked = serverRevoked;
    });
    const outcome = await revokeAndReconcileSharingKey('key 7', request, refetch);
    expect(outcome).toBe('unknown');
    expect(request).toHaveBeenCalledTimes(1);
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(observedRevoked).toBe(true);
    expect(SHARING_REVOKE_UNKNOWN_AR).not.toContain('لم تتغير حالته');
  });

  it('keeps a rejected request and failed refresh uncertain', async () => {
    const refetch = vi.fn(async () => { throw new Error('offline'); });
    const outcome = await revokeAndReconcileSharingKey(
      'id',
      async () => { throw new Error('network'); },
      refetch,
    );
    expect(outcome).toBe('unknown');
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('preserves a confirmed server revocation when refreshing the list fails', async () => {
    const result = await revokeAndReconcileSharingKey(
      'id',
      async () => ({}),
      async () => { throw new Error('refresh failure'); },
    );
    expect(result).toBe('confirmed_refresh_unavailable');
    expect(SHARING_REVOKE_REFRESH_FAILED_AR).toContain('أكّد الخادم الإلغاء');
  });

  it('confirms a normal revocation and refreshes exactly once', async () => {
    const refetch = vi.fn(async () => {});
    expect(await revokeAndReconcileSharingKey('id', async () => ({}), refetch))
      .toBe('confirmed');
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
