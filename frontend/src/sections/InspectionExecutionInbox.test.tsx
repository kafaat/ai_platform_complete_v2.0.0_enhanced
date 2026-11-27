import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useAuthStore } from '../hooks/useAuth';
import { STORAGE_KEYS } from '../lib/authStorage';
import type { InspectionExecution, InspectionExecutionInbox as Inbox } from '../services/api/inspectionExecutions';
import InspectionExecutionInbox, { inspectionExecutionKey } from './InspectionExecutionInbox';
import FieldWorkspaceTasksPanel from './FieldWorkspaceTasksPanel';

const api = vi.hoisted(() => ({ list: vi.fn(), receive: vi.fn(), verify: vi.fn(), tasks: vi.fn() }));
vi.mock('../services/api/fieldTasks', () => ({ getFieldTasks: api.tasks }));
vi.mock('../services/api/inspectionExecutions', async importOriginal => ({
  ...await importOriginal<typeof import('../services/api/inspectionExecutions')>(),
  getInspectionExecutions: api.list, receiveInspectionExecution: api.receive, verifyInspectionExecution: api.verify,
}));
const TENANT = 'tenant-a';
const FIELD = 'field-a';
const item: InspectionExecution = {
  execution_request_id: 'exec_1', decision_id: 'decision-a', field_id: FIELD, task_id: null,
  pin_id: 'pin-a', assigned_to: '7', due_at: '2026-11-27T18:00:00Z',
  state: 'queued', can_receive: true, can_verify: false,
};
const inbox = (items: InspectionExecution[] = [{ ...item }], truncated = false): Inbox => ({ field_id: FIELD, items, truncated, limit: 50 });
const clients: QueryClient[] = [];

function login(tenant = TENANT, id = 9, role = 'owner') {
  const user = { id, email: `user-${id}@synthetic.invalid`, role, tenant_id: tenant };
  sessionStorage.setItem(STORAGE_KEYS.tenantId, tenant);
  sessionStorage.setItem(STORAGE_KEYS.accessToken, 'synthetic-unit-token');
  sessionStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
  useAuthStore.setState({ tenantId: tenant, user, token: 'synthetic-unit-token', isAuthenticated: true, isDemoMode: false });
}
function open(ui = <InspectionExecutionInbox fieldId={FIELD} />) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { retry: false } } });
  clients.push(client);
  const view = render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
  return { client, ...view };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}
beforeEach(() => { vi.resetAllMocks(); login(); api.list.mockResolvedValue(inbox()); api.tasks.mockResolvedValue({ tasks: [] }); });
afterEach(() => { cleanup(); clients.splice(0).forEach(client => client.clear()); sessionStorage.clear(); });

it.each(['worker', 'farmer', 'viewer', 'agronomist', 'expert', 'unknown'])('does not expose execution controls or fetch an inbox to %s', role => {
  login(TENANT, 9, role); open();
  expect(screen.queryByRole('region', { name: 'تسليم مهام التفتيش' })).not.toBeInTheDocument();
  expect(api.list).not.toHaveBeenCalled();
});

it.each(['owner', 'admin', 'manager'])('shows operator delivery controls to %s with a scoped request', async role => {
  login(TENANT, 9, role); open();
  await screen.findByRole('button', { name: 'إرسال مهمة التفتيش للمستلم' });
  expect(api.list).toHaveBeenCalledWith(FIELD, expect.objectContaining({ authScope: JSON.stringify([TENANT, '9']), signal: expect.any(AbortSignal) }));
  expect(screen.getByRole('link', { name: 'صفحة المهام الميدانية' })).toHaveAttribute('href', '/ops/tasks');
});

it('hides controls for demo mode or mismatched stored identity', () => {
  useAuthStore.setState({ isDemoMode: true });
  const view = open();
  expect(api.list).not.toHaveBeenCalled();
  act(() => { useAuthStore.setState({ isDemoMode: false }); sessionStorage.removeItem(STORAGE_KEYS.user); });
  view.rerender(<QueryClientProvider client={view.client}><InspectionExecutionInbox fieldId={FIELD} /></QueryClientProvider>);
  expect(api.list).not.toHaveBeenCalled();
});

it.each([
  { response: { status: 401 } }, { response: { status: 403 } },
  { response: { status: 503, data: { detail: { code: 'field_inspection_execution_disabled' } } } },
])('hides the inbox after an unauthorized or disabled response', async error => {
  api.list.mockRejectedValue(error); open();
  await waitFor(() => expect(screen.queryByRole('region', { name: 'تسليم مهام التفتيش' })).not.toBeInTheDocument());
});

it('displays an upstream outage instead of an empty success', async () => {
  api.list.mockRejectedValue({ response: { status: 503 } }); open();
  expect(await screen.findByRole('alert')).toHaveTextContent('تعذّر تحميل');
  expect(screen.queryByText('لا توجد طلبات تفتيش متاحة لهذا الحقل الآن.')).not.toBeInTheDocument();
});

it('states when a bounded list may omit additional requests', async () => {
  api.list.mockResolvedValue(inbox([], true)); open();
  expect(await screen.findByText('القائمة محدودة؛ قد توجد طلبات أخرى غير ظاهرة.')).toBeInTheDocument();
});

it('uses the saved assignee name and keeps technical references in optional trace details', async () => {
  api.list.mockResolvedValue(inbox([{ ...item, assignee_name: 'اسم المستلم المحفوظ' }]));
  open();
  expect(await screen.findByText('اسم المستلم المحفوظ')).toBeVisible();
  const decision = screen.getByText('decision-a');
  expect(decision.closest('details')).not.toHaveAttribute('open');
  expect(decision).not.toBeVisible();
  expect(screen.getByText('7').closest('details')).not.toHaveAttribute('open');
});

it('does not invent a name when the owner has no saved display name', async () => {
  open();
  expect(await screen.findByText('المستلم المحدد في الخطة')).toBeVisible();
  expect(screen.getByText('7')).not.toBeVisible();
});

it.each(['empty', 'unavailable'])('keeps the delivery inbox reachable when the existing task list is %s', async state => {
  if (state === 'unavailable') api.tasks.mockRejectedValue({ response: { status: 503 } });
  open(<FieldWorkspaceTasksPanel fieldId={FIELD} />);
  expect(await screen.findByRole('button', { name: 'إرسال مهمة التفتيش للمستلم' })).toBeInTheDocument();
  expect(await screen.findByText(state === 'empty' ? 'لا توجد مهام محفوظة' : 'مهام الحقل تعمل في وضع متدهور')).toBeInTheDocument();
});

it('waits for the saved receive receipt and prevents duplicate clicks', async () => {
  const saved = deferred<unknown>();
  api.receive.mockReturnValue(saved.promise);
  open();
  const button = await screen.findByRole('button', { name: 'إرسال مهمة التفتيش للمستلم' });
  fireEvent.click(button); fireEvent.click(button);
  await waitFor(() => expect(api.receive).toHaveBeenCalledTimes(1));
  expect(button).toBeDisabled();
  expect(screen.getByText('جاهزة للإرسال إلى المستلم')).toBeInTheDocument();
  expect(screen.queryByText('حُفظت المهمة للمستلم')).not.toBeInTheDocument();
  api.list.mockResolvedValue(inbox([{ ...item, task_id: 'task-a', state: 'accepted', can_receive: false,
    verification_reason: { code: 'inspection_not_completed' } }]));
  await act(async () => saved.resolve({ state: 'accepted', task_id: 'task-a' }));
  expect(await screen.findByText('حُفظت المهمة للمستلم')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'تأكيد نتيجة التفتيش المعتمدة' })).not.toBeInTheDocument();
  expect(api.receive).toHaveBeenCalledWith(FIELD, 'exec_1', expect.objectContaining({ authScope: JSON.stringify([TENANT, '9']) }));
});

it('verifies only a server-eligible task, then refreshes this account and field', async () => {
  api.list.mockResolvedValue(inbox([{ ...item, task_id: 'task-a', state: 'accepted', can_receive: false, can_verify: true }]));
  const { client } = open();
  const own = ['field-workspace', FIELD, 'tasks', TENANT, 'user-9@synthetic.invalid', 'owner'];
  const peerUser = ['field-workspace', FIELD, 'tasks', TENANT, 'user-10@synthetic.invalid', 'owner'];
  const peerTenant = ['field-workspace', FIELD, 'tasks', 'tenant-b', 'user-9@synthetic.invalid', 'owner'];
  [own, peerUser, peerTenant].forEach(key => client.setQueryData(key, { tasks: [] }));
  api.verify.mockResolvedValue({ state: 'verified_success', task_id: 'task-a', outcome_id: 'outcome-a' });
  const button = await screen.findByRole('button', { name: 'تأكيد نتيجة التفتيش المعتمدة' });
  api.list.mockResolvedValue(inbox([{ ...item, task_id: 'task-a', state: 'verified_success',
    can_receive: false, can_verify: false, outcome_id: 'outcome-a' }]));
  fireEvent.click(button);
  expect(await screen.findByText('سُجّل تأكيد النتيجة المعتمدة')).toBeInTheDocument();
  expect(api.verify).toHaveBeenCalledWith(FIELD, 'task-a', 'exec_1', expect.objectContaining({ authScope: JSON.stringify([TENANT, '9']) }));
  expect(client.getQueryState(own)?.isInvalidated).toBe(true);
  expect(client.getQueryState(peerUser)?.isInvalidated).toBe(false);
  expect(client.getQueryState(peerTenant)?.isInvalidated).toBe(false);
});

it('refreshes stale approval after conflict and removes the verify action', async () => {
  api.list.mockResolvedValue(inbox([{ ...item, task_id: 'task-a', state: 'accepted', can_receive: false, can_verify: true }]));
  api.verify.mockRejectedValue({ response: { status: 409 } }); open();
  const button = await screen.findByRole('button', { name: 'تأكيد نتيجة التفتيش المعتمدة' });
  api.list.mockResolvedValue(inbox([{ ...item, task_id: 'task-a', state: 'accepted', can_receive: false,
    verification_reason: { code: 'current_independent_inspection_approval_required' } }]));
  fireEvent.click(button);
  expect(await screen.findByRole('alert')).toHaveTextContent('تغيّرت حالة المهمة أو الدليل');
  await waitFor(() => expect(screen.queryByRole('button', { name: 'تأكيد نتيجة التفتيش المعتمدة' })).not.toBeInTheDocument());
  expect(screen.getByText('يلزم اعتماد النسخة الحالية من مراجع مختلف عن المفتش.')).toBeInTheDocument();
});

it('removes a cached inbox when access is revoked on refetch', async () => {
  open();
  await screen.findByText('decision-a');
  api.list.mockRejectedValue({ response: { status: 403 } });
  fireEvent.click(screen.getByRole('button', { name: 'تحديث مهام التفتيش' }));
  await waitFor(() => expect(screen.queryByText('decision-a')).not.toBeInTheDocument());
  expect(screen.queryByRole('region', { name: 'تسليم مهام التفتيش' })).not.toBeInTheDocument();
});

it('cancels an old account read and never renders its late result in the new account', async () => {
  const old = deferred<Inbox>();
  api.list.mockReturnValueOnce(old.promise);
  const { client } = open();
  await waitFor(() => expect(api.list).toHaveBeenCalledTimes(1));
  const signal = api.list.mock.calls[0][1].signal as AbortSignal;
  api.list.mockResolvedValue(inbox([{ ...item, decision_id: 'decision-peer' }]));
  act(() => login(TENANT, 10));
  await screen.findByText('decision-peer');
  expect(signal.aborted).toBe(true);
  await act(async () => old.resolve(inbox()));
  expect(screen.queryByText('decision-a')).not.toBeInTheDocument();
  expect(client.getQueryData(inspectionExecutionKey(TENANT, '10', 'owner', FIELD))).toEqual(inbox([{ ...item, decision_id: 'decision-peer' }]));
});

it('drops a late mutation notice and invalidation after tenant change', async () => {
  const old = deferred<unknown>();
  api.receive.mockReturnValue(old.promise);
  const { client } = open();
  fireEvent.click(await screen.findByRole('button', { name: 'إرسال مهمة التفتيش للمستلم' }));
  await waitFor(() => expect(api.receive).toHaveBeenCalledTimes(1));
  const signal = api.receive.mock.calls[0][2].signal as AbortSignal;
  api.list.mockResolvedValue(inbox([{ ...item, decision_id: 'decision-tenant-b' }]));
  act(() => login('tenant-b', 12));
  await screen.findByText('decision-tenant-b');
  const invalidation = vi.spyOn(client, 'invalidateQueries');
  await act(async () => old.resolve({ state: 'accepted', task_id: 'task-a' }));
  expect(signal.aborted).toBe(true);
  expect(invalidation).not.toHaveBeenCalled();
  expect(screen.queryByText('حُفظت مهمة التفتيش وأصبح بإمكان المستلم تأكيد استلامها من صفحة المهام.')).not.toBeInTheDocument();
});

it('remounts mutation controls on role and field changes', async () => {
  const { client, rerender } = open();
  await screen.findByText('decision-a');
  act(() => login(TENANT, 9, 'agronomist'));
  expect(screen.queryByText('decision-a')).not.toBeInTheDocument();
  api.list.mockResolvedValue({ field_id: 'field-b', items: [], truncated: false, limit: 50 });
  act(() => login(TENANT, 9));
  rerender(<QueryClientProvider client={client}><InspectionExecutionInbox fieldId="field-b" /></QueryClientProvider>);
  expect(await screen.findByText('لا توجد طلبات تفتيش متاحة لهذا الحقل الآن.')).toBeInTheDocument();
  expect(screen.queryByText('decision-a')).not.toBeInTheDocument();
});
