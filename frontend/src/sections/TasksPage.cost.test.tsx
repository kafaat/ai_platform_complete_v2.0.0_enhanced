import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { useAuthStore } from '../hooks/useAuth';
import { kongApi } from '../services/api';
import TasksPage from './TasksPage';

afterEach(() => vi.restoreAllMocks());

function visit(role = 'manager') {
  useAuthStore.setState({ tenantId: 'test', user: { role, email: 'field@example.test' } });
  const task = { task_id: 't1', field_id: 'wheat', task_type: 'scouting',
    status: 'in_progress', estimated_cost_usd: 30, actual_cost_usd: 18.25 };
  vi.spyOn(kongApi, 'get').mockImplementation(async () => ({ data: { tasks: [{ ...task }] } }));
  const patch = vi.spyOn(kongApi, 'patch').mockImplementation(async (_path, payload) => {
    Object.assign(task, payload);
    return { data: { ...task } };
  });
  render(<QueryClientProvider client={new QueryClient()}><TasksPage /></QueryClientProvider>);
  return patch;
}

it.each([
  ['0', 0],
  ['22.50', 22.5],
  ['', undefined],
])('completes and reads the server cost for input %s', async (input, amount) => {
  const patch = visit();
  const cost = await screen.findByRole('spinbutton');
  expect(screen.getByText('t1')).toBeVisible();
  expect(screen.getByText('التقدير: $30')).toBeVisible();
  expect(screen.getByText('التكلفة الفعلية: $18.25')).toBeVisible();
  fireEvent.change(cost, { target: { value: input } });
  fireEvent.click(screen.getByRole('button', { name: 'إنجاز' }));
  await waitFor(() => expect(patch).toHaveBeenCalledOnce());
  const [url, body] = patch.mock.calls[0];
  expect(url).toBe('/api/v1/tasks/t1');
  expect(body).toMatchObject({ status: 'completed' });
  if (amount === undefined) expect(body).not.toHaveProperty('actual_cost_usd');
  else expect(body).toHaveProperty('actual_cost_usd', amount);
  await screen.findByRole('button', { name: 'حفظ تصحيح التكلفة' });
  expect(screen.getByText(`التكلفة الفعلية: $${amount ?? 18.25}`)).toBeVisible();
});

it('rejects negative and fractional-cent costs before sending', async () => {
  const patch = visit();
  const cost = await screen.findByRole('spinbutton');
  for (const value of ['-1', '0.001', '100000000']) {
    fireEvent.change(cost, { target: { value } });
    fireEvent.click(screen.getByRole('button', { name: 'إنجاز' }));
    expect(cost).toBeInvalid();
    expect(patch).not.toHaveBeenCalled();
  }
});

it('hides cached actual costs and trace from workers who cannot view analytics', async () => {
  visit('worker');
  expect(await screen.findByText('t1')).toBeVisible();
  expect(screen.queryByText('التكلفة الفعلية: $18.25')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'تتبع التكلفة والقيود' })).not.toBeInTheDocument();
  expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
});

it('lets a worker with expense-write record the task receipt without seeing cost totals', async () => {
  visit('worker');
  expect(await screen.findByText('t1')).toBeVisible();
  const link = screen.getByRole('link', { name: 'تسجيل مصروف أو ربط قيد سابق' });
  expect(link).toHaveAttribute('href', '/ops/farm-book?task_id=t1&field_id=wheat');
  expect(screen.queryByText(/18\.25/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'تتبع التكلفة والقيود' })).not.toBeInTheDocument();
});

it.each(['viewer', 'agronomist'])('offers no expense entry to a %s, who lacks activity:execute', async role => {
  visit(role);
  expect(await screen.findByText('t1')).toBeVisible();
  expect(screen.queryByRole('link', { name: 'تسجيل مصروف أو ربط قيد سابق' })).not.toBeInTheDocument();
});

it('keeps the suggested amount on the manager link beside the cost trace', async () => {
  visit('manager');
  const link = await screen.findByRole('link', { name: 'تسجيل مصروف أو ربط قيد سابق' });
  expect(link).toHaveAttribute('href', '/ops/farm-book?task_id=t1&field_id=wheat&cost_usd=18.25');
  expect(screen.getByRole('button', { name: 'تتبع التكلفة والقيود' })).toBeVisible();
});
