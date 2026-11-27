import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, expect, it, vi } from 'vitest';
import { kongApi } from '../services/api';
import { useAuthStore } from './useAuth';
import { useFieldIntelligenceJob } from './useApi';
import { useFieldIntelligenceCard } from './useFieldIntelligenceCard';

const session = useAuthStore.getState();

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  useAuthStore.setState(session);
});

it('replaces outstanding work when a field, account, or tenant changes; shares work until the last subscriber leaves', async () => {
  useAuthStore.setState({ tenantId: 'T1', user: { id: 1, email: 'test@example.org', role: 'farmer' } });
  const requests: AbortSignal[] = [];
  const post = vi.spyOn(kongApi, 'post').mockImplementation((_path, _data, options) => {
    const signal = options?.signal as AbortSignal;
    requests.push(signal);
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
  });
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const useCard = ([field, enabled]: [string, boolean]) => useFieldIntelligenceCard(field, enabled);
  const a = renderHook(useCard, { wrapper, initialProps: ['A', true] as [string, boolean] });
  const b = renderHook(useCard, { wrapper, initialProps: ['A', true] as [string, boolean] });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  a.unmount();
  expect(requests[0].aborted).toBe(false);
  b.rerender(['B', true]);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(requests[0].aborted).toBe(true);
  expect(post.mock.calls[1][2]).toMatchObject({ params: { field_id: 'B' } });

  act(() => { useAuthStore.setState({ user: { id: 2, email: 'second@example.org', role: 'farmer' } }); });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(requests[1].aborted).toBe(true);
  act(() => { useAuthStore.setState({ tenantId: 'T2' }); });
  await waitFor(() => expect(post).toHaveBeenCalledTimes(4));
  expect(requests[2].aborted).toBe(true);
  b.rerender(['B', false]);
  expect(requests[3].aborted).toBe(true);
  expect(post).toHaveBeenCalledTimes(4);
  b.unmount();
  client.clear();
});


it('slows the progress observer after its fifth status read and stops on completion', async () => {
  vi.useFakeTimers();
  useAuthStore.setState({ tenantId: 'T1', user: { id: 1, email: 'test@example.org', role: 'farmer' } });
  const status = vi.spyOn(kongApi, 'get').mockResolvedValue({ data: { status: 'running' } });
  const client = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  const observer = renderHook(() => useFieldIntelligenceJob('job'), { wrapper });
  await act(async () => { await vi.advanceTimersByTimeAsync(6999); });
  // This observer fetches once immediately and four further times through 4 s.
  expect(status).toHaveBeenCalledTimes(5);
  status.mockResolvedValue({ data: { status: 'completed' } });
  await act(async () => { await vi.advanceTimersByTimeAsync(10_001); });
  expect(status).toHaveBeenCalledTimes(6);
  expect(observer.result.current.data?.status).toBe('completed');
  observer.unmount();
  client.clear();
});
