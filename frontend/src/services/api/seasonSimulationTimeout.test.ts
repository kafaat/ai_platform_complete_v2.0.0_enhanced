// Devin review on #1582: the season simulation run awaits the NDVI series (raster, 20 s), the
// weather archive (20 s), ET0 (20 s), GDD (20 s) and the decision mirror (3 s) one after another,
// and the shared client gives up after 15 s, so the dialog reported failure for runs the server
// saved.
import { describe, expect, it, vi } from 'vitest';

const { mockPost } = vi.hoisted(() => ({ mockPost: vi.fn() }));

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: vi.fn(),
      post: mockPost,
      defaults: { baseURL: '' },
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    })),
  },
}));

import { SEASON_SIMULATION_TIMEOUT_MS, simulateSeason } from './reports';

describe('season simulation request', () => {
  it('waits longer than the two upstream reads it depends on', async () => {
    mockPost.mockResolvedValue({ data: { season_id: 's-1' } });
    await simulateSeason('s-1');
    expect(mockPost).toHaveBeenCalledWith('/api/v1/seasons/s-1/simulate', undefined, {
      timeout: SEASON_SIMULATION_TIMEOUT_MS,
    });
    // raster 20 + weather archive 20 + ET0 20 + GDD 20 + decision mirror 3, before database reads
    expect(SEASON_SIMULATION_TIMEOUT_MS).toBeGreaterThan(83_000);
    expect(SEASON_SIMULATION_TIMEOUT_MS).toBe(110_000);
  });
});
