import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { analyzeFieldIntelligence, kongApi } from './api';

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });

const field = { field_id: 'example' };
const queued = { data: { status: 'queued', job_id: 'job/a' } };

it('polls five times at one second and then at three seconds, using the submitted job id', async () => {
  vi.spyOn(kongApi, 'post').mockResolvedValue(queued);
  const status = vi.spyOn(kongApi, 'get').mockResolvedValue({ data: { status: 'running' } });
  const result = analyzeFieldIntelligence(field);
  await vi.advanceTimersByTimeAsync(7999);
  expect(status).toHaveBeenCalledTimes(5);
  status.mockResolvedValue({ data: { status: 'completed', result: field } });
  await vi.advanceTimersByTimeAsync(1);
  await expect(result).resolves.toEqual(field);
  expect(status).toHaveBeenLastCalledWith('/api/v1/field-intelligence/analyze/jobs/job%2Fa', { signal: expect.any(AbortSignal) });
  expect(vi.getTimerCount()).toBe(0);
});

it('aborts an outstanding wait immediately and releases its timers', async () => {
  vi.spyOn(kongApi, 'post').mockResolvedValue(queued);
  const status = vi.spyOn(kongApi, 'get');
  const controller = new AbortController();
  const result = expect(analyzeFieldIntelligence(field, controller.signal)).rejects.toThrow('field changed');
  await vi.advanceTimersByTimeAsync(10);
  controller.abort(new Error('field changed'));
  await result;
  expect(vi.getTimerCount()).toBe(0);
  expect(status).not.toHaveBeenCalled();
});

it('skips job submission when already aborted', async () => {
  const controller = new AbortController();
  controller.abort();
  const submit = vi.spyOn(kongApi, 'post');
  await expect(analyzeFieldIntelligence(field, controller.signal)).rejects.toThrow();
  expect(submit).not.toHaveBeenCalled();
});

it('cancels a pending HTTP read at the polling deadline', async () => {
  vi.spyOn(kongApi, 'post').mockResolvedValue(queued);
  const status = vi.spyOn(kongApi, 'get').mockImplementation((_path, options) => new Promise((_resolve, reject) => {
    (options?.signal as AbortSignal).addEventListener('abort', () => reject(new Error('HTTP cancelled')), { once: true });
  }));
  const result = expect(analyzeFieldIntelligence(field)).rejects.toThrow('timed out while polling');
  await vi.advanceTimersByTimeAsync(120_000);
  await result;
  expect(status).toHaveBeenCalledTimes(1);
  expect(vi.getTimerCount()).toBe(0);
});

it('sends no status request at or after the deadline when jobs remain queued', async () => {
  vi.spyOn(kongApi, 'post').mockResolvedValue(queued);
  const status = vi.spyOn(kongApi, 'get').mockResolvedValue(queued);
  const result = expect(analyzeFieldIntelligence(field)).rejects.toThrow('timed out while polling');
  await vi.advanceTimersByTimeAsync(120_000);
  await result;
  // Five checks through 5 s, then thirty-eight through 119 s.
  expect(status).toHaveBeenCalledTimes(43);
  expect(vi.getTimerCount()).toBe(0);
});

it.each([
  [{ status: 'failed', error: { message: 'service failed' } }, 'service failed'],
  [{ status: 'failed', error: 'server message' }, 'server message'],
  [{ status: 'failed' }, 'تعذّر التحليل'],
  [{ status: 'cancelled' }, 'أُلغي التحليل'],
] as const)('preserves terminal errors without sending another request', async (job, expected) => {
  vi.spyOn(kongApi, 'post').mockResolvedValue({ data: job });
  const status = vi.spyOn(kongApi, 'get');
  await expect(analyzeFieldIntelligence(field, undefined, {
    failed: 'تعذّر التحليل', cancelled: 'أُلغي التحليل', timeout: 'انتهت المهلة',
  })).rejects.toThrow(expected);
  expect(status).not.toHaveBeenCalled();
  expect(vi.getTimerCount()).toBe(0);
});
