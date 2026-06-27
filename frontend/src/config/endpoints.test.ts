import { afterEach, describe, expect, it, vi } from 'vitest';

describe('endpoint policy', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('uses gateway-relative defaults outside dev mode', async () => {
    vi.stubEnv('VITE_API_MODE', 'gateway');
    const { ENDPOINTS } = await import('./endpoints');
    expect(ENDPOINTS.kong).toBe('');
    expect(ENDPOINTS.auth).toBe('');
    expect(ENDPOINTS.raster).toBe('/api/raster');
    expect(ENDPOINTS.ws.endsWith('/ws')).toBe(true);
  });

  it('allows direct local ports only in explicit dev mode', async () => {
    vi.stubEnv('VITE_API_MODE', 'dev');
    const { ENDPOINTS } = await import('./endpoints');
    expect(ENDPOINTS.kong).toBe('http://localhost:8000');
    expect(ENDPOINTS.weather).toBe('http://localhost:8092');
  });

  it('rejects local endpoints in gateway/production mode', async () => {
    vi.stubEnv('VITE_API_MODE', 'gateway');
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000');
    await expect(import('./endpoints')).rejects.toThrow(/local endpoint/);
  });
});
