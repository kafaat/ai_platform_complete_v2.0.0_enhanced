import { beforeEach, describe, expect, it, vi } from 'vitest';
import { kongApi } from './api/client';
import { getScoutPhotoGrants, issueScoutPhotoGrant, revokeScoutPhotoGrant } from './scoutPhotoGrants';

vi.mock('./api/client', () => ({ kongApi: { get: vi.fn(), post: vi.fn() } }));
vi.mock('../lib/authStorage', () => ({ getAuthScope: vi.fn(() => 'tenant-a:17') }));

// Owner decision 2026-11-13: the grants belong to scout-ingest; nginx routes
// /api/v1/scouting-media/ to it. No platform /api/v1/admin/... route exists for them.
describe('scout photo grant administration calls scout-ingest', () => {
  beforeEach(() => {
    vi.mocked(kongApi.get).mockReset().mockResolvedValue({ data: { grants: [], events: [] } });
    vi.mocked(kongApi.post).mockReset().mockResolvedValue({ data: { status: 'recorded' } });
  });

  it('lists, issues and revokes under /api/v1/scouting-media/admin with the session scope', async () => {
    await getScoutPhotoGrants('field a/1');
    expect(kongApi.get).toHaveBeenCalledWith(
      '/api/v1/scouting-media/admin/fields/field%20a%2F1/grants',
      { expectedAuthScope: 'tenant-a:17' },
    );
    const issue = {
      event_id: 'e1', user_id: 5, scope: 'photo.read' as const,
      expires_at: '2026-12-01T00:00:00Z', reason: 'field visit this month',
    };
    await issueScoutPhotoGrant('f1', issue);
    expect(kongApi.post).toHaveBeenCalledWith(
      '/api/v1/scouting-media/admin/fields/f1/grants', issue, { expectedAuthScope: 'tenant-a:17' },
    );
    await revokeScoutPhotoGrant('f1', 'g/1', { event_id: 'e2', reason: 'visit finished early' });
    expect(kongApi.post).toHaveBeenLastCalledWith(
      '/api/v1/scouting-media/admin/fields/f1/grants/g%2F1/revoke',
      { event_id: 'e2', reason: 'visit finished early' },
      { expectedAuthScope: 'tenant-a:17' },
    );
  });

  it('refuses to send an admin request without a session identity', async () => {
    const storage = await import('../lib/authStorage');
    vi.mocked(storage.getAuthScope).mockReturnValueOnce(null);
    await expect(getScoutPhotoGrants('f1')).rejects.toThrow(/session identity unavailable/);
    expect(kongApi.get).not.toHaveBeenCalled();
  });
});
