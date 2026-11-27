import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { kongApi } from '../services/api';
import { useAuthStore } from '../hooks/useAuth';
import FieldIntelligencePage from './FieldIntelligencePage';

const selection = vi.hoisted(() => ({ fieldId: 'first' }));
vi.mock('../hooks/useSelectedField', () => ({ useSelectedField: () => selection }));
vi.mock('../components/FieldSelector', () => ({ default: () => null }));
const session = useAuthStore.getState();

afterEach(() => {
  vi.restoreAllMocks();
  useAuthStore.setState(session);
  selection.fieldId = 'first';
});

it('discards late submission and job progress from the previous field or tenant', async () => {
  useAuthStore.setState({ tenantId: 'T1', user: { id: 1, role: 'farmer', email: 'test@example.org' } });
  let finishFirst!: (value: { data: { job_id: string; status: string } }) => void;
  const post = vi.spyOn(kongApi, 'post').mockImplementationOnce(() => new Promise(resolve => { finishFirst = resolve; }))
    .mockResolvedValue({ data: { job_id: 'second-job', status: 'queued' } });
  let polling: AbortSignal | undefined;
  const get = vi.spyOn(kongApi, 'get').mockImplementation((_url, options) => {
    const signal = options?.signal as AbortSignal;
    polling = signal;
    return new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(signal.reason), { once: true }));
  });
  const client = new QueryClient();
  const page = () => <QueryClientProvider client={client}><FieldIntelligencePage /></QueryClientProvider>;
  const view = render(page());

  fireEvent.click(screen.getByRole('button', { name: 'تحليل الحقل' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  selection.fieldId = 'second';
  view.rerender(page());
  await act(async () => { finishFirst({ data: { job_id: 'old-job', status: 'queued' } }); });
  expect(get).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'تحليل الحقل' }));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
  expect(get.mock.calls[0][0]).toContain('second-job');
  act(() => { useAuthStore.setState({ tenantId: 'T2' }); });
  expect(polling?.aborted).toBe(true);
  expect(screen.queryByRole('button', { name: 'إلغاء التحليل' })).toBeNull();
  expect(screen.getByRole('button', { name: 'تحليل الحقل' })).toBeEnabled();
  view.unmount();
  client.clear();
});
