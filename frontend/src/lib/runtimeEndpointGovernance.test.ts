import { describe, expect, it } from 'vitest';
import { evaluateRuntimeEndpointGovernance } from './runtimeEndpointGovernance';

describe('evaluateRuntimeEndpointGovernance', () => {
  it('يرصد إعدادات runtime صحيحة مع api/ws/raster', () => {
    const result = evaluateRuntimeEndpointGovernance({
      apiUrl: 'http://localhost:8000',
      wsUrl: 'ws://localhost:8081/ws',
      rasterUrl: 'http://localhost:8001',
      devProxyTarget: 'http://localhost:8000',
    });
    expect(result.score).toBeGreaterThanOrEqual(80);
    expect(result.portHints.length).toBeGreaterThan(0);
  });

  it('يحذر عندما يكون WebSocket ببروتوكول HTTP', () => {
    const result = evaluateRuntimeEndpointGovernance({ wsUrl: 'http://localhost:8081/ws' });
    expect(result.checks.find((c) => c.id === 'ws')?.severity).toBe('warn');
  });
});
