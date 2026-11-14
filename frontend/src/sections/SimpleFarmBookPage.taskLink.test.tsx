import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import SimpleFarmBookPage from './SimpleFarmBookPage';

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('../services/api/client', () => ({ kongApi: api }));
const task = '123e4567-e89b-12d3-a456-426614174000';
const invoice = { entry_id: 'invoice-1', occurred_on: '2026-11-12', entry_type: 'expense',
  payment_method: 'credit', field_id: 'wheat', category: 'maintenance', party_id: 'vendor',
  amount: 12000, currency: 'YER', task_id: task };
const field = () => screen.getByPlaceholderText('الحقل (اختياري)');
const save = () => screen.getByRole('button', { name: 'حفظ الحركة' });
const change = (element: Element, value: string) => fireEvent.change(element, { target: { value } });
const select = (option: string, value: string) =>
  change(screen.getByRole('option', { name: option }).closest('select')!, value);
async function open() {
  render(<SimpleFarmBookPage />);
  change(screen.getByPlaceholderText('معرّف المزرعة'), 'farm');
  fireEvent.click(screen.getByRole('button', { name: 'تحميل' }));
  const row = (await screen.findByText('invoice-1')).closest('tr')!;
  expect(within(row).getByText(task)).toBeVisible();
  change(screen.getByPlaceholderText('المبلغ'), '5000');
}
beforeEach(() => {
  api.get.mockReset().mockImplementation(async (path: string) => ({ data: {
    items: path.endsWith('/entries') ? [invoice] : path.endsWith('/parties')
      ? [{ party_id: 'vendor', name: 'المورد', party_type: 'supplier' }] : [],
  } }));
  api.post.mockReset().mockResolvedValue({ data: {} });
});

it('requires a field and submits the task and invoice reference with the cash expense', async () => {
  await open();
  change(screen.getByLabelText('معرّف المهمة المرتبطة بالقيد'), task);
  expect(save()).toBeDisabled();
  change(field(), 'wheat');
  change(screen.getByPlaceholderText('معرّف صورة الفاتورة'), 'receipt-1');
  fireEvent.click(save());
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/farm-book/entries',
    expect.objectContaining({ task_id: task, field_id: 'wheat', amount: 5000, receipt_document_id: 'receipt-1' })));
  await waitFor(() => expect(screen.getByLabelText('معرّف المهمة المرتبطة بالقيد')).toHaveValue(''));
});

it('lets a payment inherit its invoice task and field without carrying a prior draft reference', async () => {
  await open();
  change(field(), 'other-field');
  change(screen.getByLabelText('معرّف المهمة المرتبطة بالقيد'), 'other-task');
  select('سداد دين', 'payment');
  expect(screen.queryByLabelText('معرّف المهمة المرتبطة بالقيد')).toBeNull();
  select('اختر القيد الآجل المراد سداده', 'invoice-1');
  fireEvent.click(save());
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/farm-book/entries',
    expect.objectContaining({ entry_type: 'payment', amount: 5000, settles_entry_id: 'invoice-1',
      party_id: 'vendor', field_id: null, task_id: null })));
  await waitFor(() => expect(screen.getByPlaceholderText('المبلغ')).toHaveValue(null));
});

it('drops the settlement reference when the user switches back to an expense', async () => {
  await open();
  select('سداد دين', 'payment');
  select('اختر القيد الآجل المراد سداده', 'invoice-1');
  select('مصروف', 'expense');
  fireEvent.click(save());
  await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/farm-book/entries',
    expect.objectContaining({ entry_type: 'expense', settles_entry_id: null })));
  await waitFor(() => expect(screen.getByPlaceholderText('المبلغ')).toHaveValue(null));
});

it('keeps the draft visible when FastAPI rejects a task identifier with validation details', async () => {
  await open();
  change(field(), 'wheat');
  change(screen.getByLabelText('معرّف المهمة المرتبطة بالقيد'), 'invalid');
  api.post.mockRejectedValue({ response: { data: { detail: [{ loc: ['body', 'task_id'], msg: 'Input should be a valid UUID' }] } } });
  fireEvent.click(save());
  expect(await screen.findByText(/معرّف المهمة غير صالح/)).toBeVisible();
  expect(screen.getByLabelText('معرّف المهمة المرتبطة بالقيد')).toHaveValue('invalid');
});

it('prefills the originating task and links an old expense while read-only totals are restricted', async () => {
  window.history.replaceState({}, '', `/ops/farm-book?farm_id=farm&field_id=wheat&task_id=${task}&cost_usd=31.25`);
  try {
    api.get.mockImplementation(async (path: string) => {
      if (path.endsWith('/monthly') || path.endsWith('/balances')) throw { response: { status: 403 } };
      return { data: { items: path.endsWith('/entries') ? [{ ...invoice, task_id: null }] : [] } };
    });
    render(<SimpleFarmBookPage />);
    expect(screen.getByLabelText('معرّف المهمة المرتبطة بالقيد')).toHaveValue(task);
    expect(field()).toHaveValue('wheat');
    expect(screen.getByLabelText('العملة')).toHaveValue('USD');
    expect(screen.getByPlaceholderText('المبلغ')).toHaveValue(31.25);
    fireEvent.click(await screen.findByRole('button', { name: 'ربط بالمهمة' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/api/v1/field-tasks/farm-book/entries/invoice-1/task', { task_id: task }));
    change(screen.getByLabelText('العملة'), 'yer');
    expect(screen.getByLabelText('العملة')).toHaveValue('YER');
    expect(screen.getByPlaceholderText('المبلغ')).toHaveValue(null);
  } finally {
    window.history.replaceState({}, '', '/');
  }
});
