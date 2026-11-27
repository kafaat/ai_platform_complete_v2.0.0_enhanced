import { beforeEach, expect, it, vi } from 'vitest';
import {
  getInspectionExecutions, inspectionInboxHidden, receiveInspectionExecution, verifyInspectionExecution,
} from './inspectionExecutions';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), scope: vi.fn() }));
vi.mock('./client', () => ({ kongApi: { get: api.get, post: api.post } }));
vi.mock('../../lib/authStorage', () => ({ getAuthScope: api.scope }));
const scope = { authScope: '["tenant-a","9"]', signal: new AbortController().signal };
const row = {
  execution_request_id: 'exec_1', decision_id: 'decision_1', field_id: 'field-a', task_id: null,
  pin_id: 'pin-a', assigned_to: '7', due_at: '2026-11-27T18:00:00Z',
  state: 'queued', can_receive: true, can_verify: false,
};
const inbox = () => ({ field_id: 'field-a', items: [{ ...row }], truncated: false, limit: 50 });
const received = () => ({
  state: 'accepted', persisted: true, replayed: false, execution_request_id: 'exec_1',
  task_id: 'task_1', field_id: 'field-a', receipt_id: 'receipt_1', physical_execution_verified: false,
});
const verified = () => ({
  state: 'verified_success', persisted: true, replayed: false, execution_request_id: 'exec_1',
  task_id: 'task_1', outcome_id: 'outcome_1', evidence_snapshot_id: 'inspection_1', verified_at: '2026-11-27T18:00:00Z',
});
beforeEach(() => { vi.resetAllMocks(); api.scope.mockReturnValue(scope.authScope); });

it('reads a bounded inbox only through the gateway with the captured session and cancellation', async () => {
  api.get.mockResolvedValue({ data: inbox() });
  expect((await getInspectionExecutions('field-a', scope)).items[0].execution_request_id).toBe('exec_1');
  expect(api.get).toHaveBeenCalledWith('/api/v1/inspection-executions/fields/field-a', {
    expectedAuthScope: scope.authScope, signal: scope.signal, params: { limit: 50 },
  });
});

it.each([
  { field_id: 'peer-field', items: [], truncated: false, limit: 50 },
  { field_id: 'field-a', items: null, truncated: false, limit: 50 },
  { field_id: 'field-a', items: [], truncated: 'false', limit: 50 },
  { field_id: 'field-a', items: [], truncated: false },
  { field_id: 'field-a', items: [{ ...row, field_id: 'peer-field' }], truncated: false, limit: 50 },
  { field_id: 'field-a', items: [{ ...row, can_verify: true }], truncated: false, limit: 50 },
  { field_id: 'field-a', items: [{ ...row, state: 'accepted', can_receive: false }], truncated: false, limit: 50 },
  { field_id: 'field-a', items: [{ ...row, state: 'verified_success' }], truncated: false, limit: 50 },
  { field_id: 'field-a', items: [row, row], truncated: false, limit: 50 },
])('rejects incomplete, misbound or contradictory inbox data instead of inventing an empty list', async data => {
  api.get.mockResolvedValue({ data });
  await expect(getInspectionExecutions('field-a', scope)).rejects.toThrow('استجابة');
});

it('propagates upstream failure without a successful fallback', async () => {
  const error = { response: { status: 503 } };
  api.get.mockRejectedValue(error);
  await expect(getInspectionExecutions('field-a', scope)).rejects.toBe(error);
});

it('posts an empty receive command and validates the committed owner receipt', async () => {
  api.post.mockResolvedValue({ data: received() });
  expect((await receiveInspectionExecution('field-a', 'exec_1', scope)).state).toBe('accepted');
  expect(api.post).toHaveBeenCalledWith('/api/v1/inspection-executions/fields/field-a/requests/exec_1/receive', {}, {
    expectedAuthScope: scope.authScope, signal: scope.signal,
  });
});

it.each([
  { state: 'delivering' }, { persisted: false }, { execution_request_id: 'peer-request' },
  { field_id: 'peer-field' }, { task_id: null }, { receipt_id: null }, { physical_execution_verified: true },
])('does not treat a claim or a mismatched receive response as accepted delivery', async change => {
  api.post.mockResolvedValue({ data: { ...received(), ...change } });
  await expect(receiveInspectionExecution('field-a', 'exec_1', scope)).rejects.toThrow('استجابة');
});

it('posts verification without client-supplied actuals, proof or tenant identity', async () => {
  api.post.mockResolvedValue({ data: verified() });
  expect((await verifyInspectionExecution('field-a', 'task_1', 'exec_1', scope)).outcome_id).toBe('outcome_1');
  expect(api.post).toHaveBeenCalledWith('/api/v1/inspection-executions/fields/field-a/tasks/task_1/verify', {}, {
    expectedAuthScope: scope.authScope, signal: scope.signal,
  });
});

it.each([{ persisted: false }, { task_id: 'peer-task' }, { execution_request_id: 'peer-request' }, { outcome_id: '' }, { evidence_snapshot_id: '' }])(
  'rejects a mismatched or incomplete outcome receipt', async change => {
    api.post.mockResolvedValue({ data: { ...verified(), ...change } });
    await expect(verifyInspectionExecution('field-a', 'task_1', 'exec_1', scope)).rejects.toThrow('استجابة');
  },
);

it('prevents sending under a different session', async () => {
  api.scope.mockReturnValue('["tenant-b","12"]');
  await expect(receiveInspectionExecution('field-a', 'exec_1', scope)).rejects.toThrow('الجلسة');
  expect(api.post).not.toHaveBeenCalled();
});

it('rejects an old response after the session changes', async () => {
  api.get.mockImplementation(async () => {
    api.scope.mockReturnValue('["tenant-b","12"]');
    return { data: inbox() };
  });
  await expect(getInspectionExecutions('field-a', scope)).rejects.toThrow('الجلسة');
});

it('rejects an aborted mutation even if a transport returns a saved response', async () => {
  const controller = new AbortController();
  api.post.mockImplementation(async () => { controller.abort(); return { data: received() }; });
  await expect(receiveInspectionExecution('field-a', 'exec_1', { ...scope, signal: controller.signal })).rejects.toThrow('الجلسة');
});

it('hides disabled/unauthorized features but keeps an upstream outage visible', () => {
  expect(inspectionInboxHidden({ response: { status: 401 } })).toBe(true);
  expect(inspectionInboxHidden({ response: { status: 403 } })).toBe(true);
  expect(inspectionInboxHidden({ response: { status: 503, data: { detail: { code: 'field_inspection_execution_disabled' } } } })).toBe(true);
  expect(inspectionInboxHidden({ response: { status: 503, data: { detail: { code: 'decision_service_unavailable' } } } })).toBe(false);
});
