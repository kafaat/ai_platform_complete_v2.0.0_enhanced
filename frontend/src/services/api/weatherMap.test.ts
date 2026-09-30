// FRONTEND-FETCH-OUTSIDE-API-LAYER-01 — طلباتُ الطقس على الخريطة تمرّ عبر kongApi.
//
// ثلاثةُ ادّعاءاتٍ تُقاس سلوكاً لا نصّاً:
//  ١. الروابطُ تُبنى **بالبايت نفسه** الذي كانت تُبنى به في المكوّنات قبل النقل (بما فيه
//     فواصلُ `hours=0,1,3,…` غيرُ المُرمَّزة) — فالنقلُ لا يُغيّر ما يصل إلى الخادم.
//  ٢. النداءاتُ تذهب إلى kongApi لا إلى `fetch`، فيُرفِق اعتراضُه Bearer و`X-Tenant-ID`.
//  ٣. طلبا الإجراء (POST) يحملان مفتاحَ idempotency المُمرَّر حرفيّاً (F5-08).
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { mockGet, mockPost, requestInterceptors } = vi.hoisted(() => {
  const requestInterceptors: Array<(config: { headers: Record<string, string> }) => unknown> = [];
  return {
    mockGet: vi.fn(),
    mockPost: vi.fn(),
    requestInterceptors,
  };
});

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: mockGet,
      post: mockPost,
      defaults: { baseURL: '' },
      interceptors: {
        request: { use: vi.fn((fn) => requestInterceptors.push(fn)) },
        response: { use: vi.fn() },
      },
    })),
  },
}));

import {
  createWeatherRecommendationFromOperationPlan,
  createWeatherTaskFromOperationPlan,
  getWeatherActionRecommendation,
  getWeatherOperationPlan,
  getWeatherOperationWindow,
  getWeatherProbe,
  getWeatherTileData,
  weatherTileDataUrl,
} from './weatherMap';

beforeEach(() => {
  mockGet.mockReset().mockResolvedValue({ data: { ok: true } });
  mockPost.mockReset().mockResolvedValue({ data: { created: true } });
});

afterEach(() => {
  sessionStorage.clear();
  vi.unstubAllGlobals();
});

describe('weather map API — URLs identical to the pre-move component builders', () => {
  it('probe / window / plan / action-recommendation', async () => {
    await getWeatherProbe(15.123456, 44.987654, '+3h', 'best_match');
    await getWeatherOperationWindow(15.1, 44.2, 'spraying', 'icon');
    await getWeatherOperationPlan(15.1, 44.2, 'icon');
    await getWeatherActionRecommendation(15.1, 44.2, 'fld 1', 'icon');
    expect(mockGet.mock.calls.map((c) => c[0])).toEqual([
      '/api/v1/weather/probe?lat=15.12346&lon=44.98765&time=%2B3h&model=best_match',
      '/api/v1/weather/operation-window?lat=15.10000&lon=44.20000&operation=spraying&hours=0,1,3,6,12,24,48&model=icon',
      '/api/v1/weather/operation-plan?lat=15.10000&lon=44.20000&operations=spraying,irrigation,harvesting,sowing&hours=0,1,3,6,12,24,48&model=icon',
      '/api/v1/weather/action-recommendation?lat=15.10000&lon=44.20000&client_field_ref=fld%201&operations=spraying,irrigation,harvesting,sowing&hours=0,1,3,6,12,24,48&model=icon',
    ]);
  });

  it('tile data: measurement layer vs. agricultural operation layer', async () => {
    const tile = { z: 9, x: 321, y: 210 };
    expect(weatherTileDataUrl(tile, { layer: 'temperature' }, 'now', 'icon')).toBe(
      '/api/v1/weather/tile-data/9/321/210?layer=temperature&time=now&model=icon&interpolation=grid',
    );
    expect(weatherTileDataUrl(tile, { operation: 'spraying' }, 'now', 'icon')).toBe(
      '/api/v1/weather/operation-tile-data/9/321/210?operation=spraying&time=now&model=icon&interpolation=grid',
    );
    await expect(getWeatherTileData(tile, { layer: 'wind' }, 'now', 'icon')).resolves.toEqual({ ok: true });
    expect(mockGet).toHaveBeenCalledWith(
      '/api/v1/weather/tile-data/9/321/210?layer=wind&time=now&model=icon&interpolation=grid',
    );
  });
});

describe('weather map API — goes through kongApi, never raw fetch', () => {
  it('no call reaches the global fetch', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    await getWeatherProbe(1, 2, 'now', 'icon');
    await getWeatherTileData({ z: 1, x: 1, y: 1 }, { layer: 'wind' }, 'now', 'icon');
    await createWeatherTaskFromOperationPlan(
      { field_id: 'f', lat: 1, lon: 2, operation: 'spraying', model: 'icon', dry_run: false },
      'k',
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(mockGet).toHaveBeenCalledTimes(2);
    expect(mockPost).toHaveBeenCalledTimes(1);
  });

  it("kongApi's request interceptor attaches Bearer + tenant (the header the components used to build)", () => {
    const future = Math.floor(Date.now() / 1000) + 3600;
    const payload = btoa(JSON.stringify({ sub: 'u', exp: future })).replace(/=+$/, '');
    const token = `h.${payload}.s`;
    sessionStorage.setItem('sahool_access_token', token);
    sessionStorage.setItem('sahool_tenant_id', 't-1');
    expect(requestInterceptors.length).toBeGreaterThan(0);
    const config = requestInterceptors[0]({ headers: {} }) as { headers: Record<string, string> };
    expect(config.headers.Authorization).toBe(`Bearer ${token}`);
    expect(config.headers['X-Tenant-ID']).toBe('t-1');
  });
});

describe('weather map API — action POSTs carry the caller-derived idempotency key (F5-08)', () => {
  it('task from operation plan', async () => {
    const body = { field_id: 'f1', lat: 15.1, lon: 44.2, operation: 'spraying', model: 'icon', dry_run: false };
    await createWeatherTaskFromOperationPlan(body, 'wx-task:f1:spraying');
    expect(mockPost).toHaveBeenCalledWith('/api/v1/weather/tasks/from-operation-plan', body, {
      headers: { 'Idempotency-Key': 'wx-task:f1:spraying' },
    });
  });

  it('recommendation from operation plan', async () => {
    const body = {
      field_id: 'f1', lat: 15.1, lon: 44.2, operations: 'spraying,irrigation,harvesting,sowing', model: 'icon', dry_run: false,
    };
    await expect(createWeatherRecommendationFromOperationPlan(body, 'wx-rec:f1')).resolves.toEqual({ created: true });
    expect(mockPost).toHaveBeenCalledWith('/api/v1/weather/recommendations/from-operation-plan', body, {
      headers: { 'Idempotency-Key': 'wx-rec:f1' },
    });
  });
});
