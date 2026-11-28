import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { useAuthStore } from '../hooks/useAuth';
import { canMutate } from '../lib/permissions';
import { kongApi } from '../services/api';
import { toastStore } from '../services/websocket';
import TasksPage from './TasksPage';

afterEach(() => vi.restoreAllMocks());

function visit(role: string, updateError?: unknown) {
  useAuthStore.setState({ tenantId: 'execution-test', user: { role, email: 'executor@example.test' } });
  const task = { task_id: 'execution-task', field_id: 'field-one', task_type: 'scouting',
    status: 'pending', actual_cost_usd: 18.25 };
  vi.spyOn(kongApi, 'get').mockImplementation(async () => ({ data: { tasks: [{ ...task }] } }));
  const patch = vi.spyOn(kongApi, 'patch').mockImplementation(async (_path, payload) => {
    if (updateError !== undefined) throw updateError;
    Object.assign(task, payload);
    return { data: { ...task } };
  });
  render(<QueryClientProvider client={new QueryClient()}><TasksPage /></QueryClientProvider>);
  return patch;
}

it.each(['owner', 'admin', 'manager', 'worker', 'farmer'])('%s starts and completes tasks under activity:execute', async role => {
  const patch = visit(role);
  await screen.findByText('execution-task');
  const worker = ['worker', 'farmer'].includes(role);
  if (worker) {
    // Executing work must not grant field editing or reveal a cached analytics-only cost.
    expect(canMutate(role, 'field')).toBe(false);
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.queryByText(/18\.25/)).not.toBeInTheDocument();
  } else {
    expect(screen.getByRole('spinbutton')).toBeVisible();
  }
  fireEvent.click(screen.getByRole('button', { name: 'بدء' }));
  await waitFor(() => expect(patch).toHaveBeenNthCalledWith(1, '/api/v1/tasks/execution-task', { status: 'in_progress' }));
  await waitFor(() => expect(screen.queryByRole('button', { name: 'بدء' })).not.toBeInTheDocument());
  fireEvent.click(screen.getByRole('button', { name: 'إنجاز' }));
  await waitFor(() => expect(patch).toHaveBeenCalledTimes(2));
  const [url, body] = patch.mock.calls[1];
  expect(url).toBe('/api/v1/tasks/execution-task');
  expect(body).toMatchObject({ status: 'completed' });
  expect(body).not.toHaveProperty('actual_cost_usd');
  await waitFor(() => expect(screen.queryByRole('button', { name: 'إنجاز' })).not.toBeInTheDocument());
  if (worker) {
    expect(screen.queryByRole('button', { name: 'حفظ تصحيح التكلفة' })).not.toBeInTheDocument();
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.queryByText(/18\.25/)).not.toBeInTheDocument();
  } else {
    expect(screen.getByRole('button', { name: 'حفظ تصحيح التكلفة' })).toBeVisible();
  }
});

it.each(['agronomist', 'expert', 'viewer', 'unknown'])('%s cannot execute task updates without activity:execute', async role => {
  const patch = visit(role);
  await screen.findByText('execution-task');
  expect(screen.queryByRole('button', { name: 'بدء' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'إنجاز' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'حفظ تصحيح التكلفة' })).not.toBeInTheDocument();
  expect(patch).not.toHaveBeenCalled();
});

it.each([
  ['review required', { response: { status: 409, data: { detail: {
    error: 'inspection_review_required', message: 'تتطلب زيارة التفتيش اعتماد نتيجتها قبل الإغلاق',
  } } } }, /اطلب اعتماد النسخة الحالية من المراجع/],
  ['evidence changed', { response: { status: 409, data: { detail: {
    error: 'inspection_evidence_changed', message: 'تغيرت صورة الزيارة بعد الاعتماد. يلزم اعتماد النسخة الجديدة',
  } } } }, /ارفع الأدلة الحالية للمراجعة/],
  ['other conflict', { response: { status: 409, data: { detail: { error: 'illegal_task_transition' } } } }, /تغيّرت حالة المهمة أو سجلها/],
  ['permission denied', { response: { status: 403 } }, /لا تملك صلاحية تحديث هذه المهمة/],
  ['service failure', { response: { status: 503 } }, /مشكلة في الخدمة/],
  ['network failure', new Error('Network Error'), /لم يتأكد حفظ المهمة/],
] as const)('keeps the worker task open and explains %s without claiming completion', async (_label, error, message) => {
  const toast = vi.spyOn(toastStore, 'add');
  const patch = visit('worker', error);
  await screen.findByText('execution-task');
  fireEvent.click(screen.getByRole('button', { name: 'إنجاز' }));
  await waitFor(() => expect(patch).toHaveBeenCalledOnce());
  await waitFor(() => expect(screen.getByRole('button', { name: 'إنجاز' })).toBeEnabled());
  expect(screen.getByRole('button', { name: 'بدء' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'حفظ تصحيح التكلفة' })).not.toBeInTheDocument();
  expect(toast).toHaveBeenCalledWith('error', '⚠️ تعذّر إنجاز المهمة', expect.stringMatching(message));
  expect(toast.mock.calls.some(([type]) => type === 'success')).toBe(false);
});
