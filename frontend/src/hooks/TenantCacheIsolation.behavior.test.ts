// @vitest-environment jsdom
/**
 * Behavioural tenant isolation contract: exercises the real main.tsx subscriber,
 * not text-presence assertions. A disabled queryClient.clear() must fail this suite.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  authState: { tenantId: 'tenant-A' as string | null },
  subscriber: null as null | ((state: { tenantId: string | null }) => void),
  clearQuery: vi.fn(),
  clearField: vi.fn(),
  resetDuckDB: vi.fn(async () => undefined),
  disconnectSocket: vi.fn(),
  render: vi.fn(),
}));

// main.tsx imports and mounts the app. The render tree is irrelevant to this contract.
vi.mock('react-dom/client', () => ({
  default: { createRoot: () => ({ render: mocks.render }) },
}));
vi.mock('react-router', () => ({ BrowserRouter: () => null }));
vi.mock('@tanstack/react-query', () => ({
  QueryClient: class {
    constructor(_options: unknown) {}
    clear() { mocks.clearQuery(); }
  },
  QueryClientProvider: () => null,
}));
vi.mock('../App', () => ({ default: () => null }));
vi.mock('../hooks/useAuth', () => ({
  useAuthStore: {
    getState: () => mocks.authState,
    subscribe: (callback: (state: { tenantId: string | null }) => void) => {
      mocks.subscriber = callback;
      return () => { mocks.subscriber = null; };
    },
  },
}));
vi.mock('../hooks/useFieldContext', () => ({
  useFieldContextStore: { getState: () => ({ clearSelectedField: mocks.clearField }) },
}));
vi.mock('../services/duckdb', () => ({ resetDuckDB: mocks.resetDuckDB }));
vi.mock('../services/websocket', () => ({ wsService: { disconnect: mocks.disconnectSocket } }));

function setTenant(next: string | null): void {
  const onChange = mocks.subscriber;
  if (!onChange) throw new Error('main.tsx did not register the tenant listener');
  mocks.authState.tenantId = next;
  onChange({ tenantId: next });
}

describe('real main.tsx tenant-change cleanup', () => {
  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();
    mocks.authState.tenantId = 'tenant-A';
    mocks.subscriber = null;
    document.body.innerHTML = '<div id="root"></div>';
    localStorage.clear();
    await import('../main');
    expect(mocks.subscriber).not.toBeNull();
  });

  it('clears private QueryClient data, field context and DuckDB on tenant A → B', () => {
    setTenant('tenant-B');
    expect(mocks.clearQuery).toHaveBeenCalledTimes(1);
    expect(mocks.clearField).toHaveBeenCalledTimes(1);
    expect(mocks.resetDuckDB).toHaveBeenCalledTimes(1);
  });

  it('does not clear caches when the tenant identity is unchanged', () => {
    setTenant('tenant-A');
    expect(mocks.clearQuery).not.toHaveBeenCalled();
    expect(mocks.clearField).not.toHaveBeenCalled();
    expect(mocks.resetDuckDB).not.toHaveBeenCalled();
  });

  it('logout also drops WebSocket and persisted settings', () => {
    localStorage.setItem('sahool_settings', 'old-settings');
    setTenant(null);
    expect(mocks.clearQuery).toHaveBeenCalledTimes(1);
    expect(mocks.clearField).toHaveBeenCalledTimes(1);
    expect(mocks.resetDuckDB).toHaveBeenCalledTimes(1);
    expect(mocks.disconnectSocket).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem('sahool_settings')).toBeNull();
  });

  it('two consecutive tenant changes clear state each time, not just on first login', () => {
    setTenant('tenant-B');
    setTenant('tenant-C');
    expect(mocks.clearQuery).toHaveBeenCalledTimes(2);
    expect(mocks.clearField).toHaveBeenCalledTimes(2);
    expect(mocks.resetDuckDB).toHaveBeenCalledTimes(2);
  });
});
