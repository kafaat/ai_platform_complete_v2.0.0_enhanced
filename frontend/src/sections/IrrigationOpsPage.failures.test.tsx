// فشل أمر الصمّام/حذف الجدول: رسالة تسمّي السبب والصمّام، بلا إعادة محاولة تلقائيّة،
// ثمّ تُعاد قراءة القائمة من الخادم (قد يكون الطلب سُجِّل رغم الخطأ) بدل إبقاء حالة مُخمَّنة.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const m = vi.hoisted(() => ({
  setValveState: vi.fn(), listValves: vi.fn(), listSchedules: vi.fn(), deleteSchedule: vi.fn(),
}));
vi.mock('../services/api', async (orig) => ({
  ...(await orig<object>()),
  setValveState: m.setValveState,
  listValves: m.listValves,
  listSchedules: m.listSchedules,
  deleteSchedule: m.deleteSchedule,
}));
vi.mock('../hooks/useAuth', () => {
  const st = { user: { role: 'owner', tenant_id: 't1' }, tenantId: 't1' };
  const useAuthStore = (sel?: (s: unknown) => unknown) => (sel ? sel(st) : st);
  return { useAuthStore, useTenantId: () => 't1' };
});
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({ options: [{ id: 'A', label: 'A' }], isLoading: false, isError: false, fieldId: 'A', setFieldId: vi.fn() }),
}));

import IrrigationOpsPage from './IrrigationOpsPage';

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  m.listValves.mockResolvedValue([{ valve_id: 'v1', name: 'V1', status: 'closed' }]);
  m.listSchedules.mockResolvedValue([{ schedule_id: 's1', name: 'S1', start_time: '06:00', duration_min: 30, enabled: true }]);
});

describe('IrrigationOpsPage write failures', () => {
  it('valve command failure names the valve and cause, does not retry, and reloads valves', async () => {
    m.setValveState.mockRejectedValue(Object.assign(new Error('503'), { response: { status: 503 } }));
    wrap(<IrrigationOpsPage />);
    fireEvent.click(await screen.findByText(/طلب فتح/));
    const alert = await screen.findByText(/تعذّر تسجيل طلب تغيير الصمّام/);
    expect(alert.textContent).toContain('(v1)');
    expect(alert.textContent).toContain('خدمة الريّ غير متاحة حاليّاً');
    await waitFor(() => expect(m.listValves).toHaveBeenCalledTimes(2));
    expect(m.setValveState).toHaveBeenCalledTimes(1);
  });

  it('a write with no server reply says it may have been recorded', async () => {
    m.setValveState.mockRejectedValue(new Error('Network Error'));
    wrap(<IrrigationOpsPage />);
    fireEvent.click(await screen.findByText(/طلب فتح/));
    expect((await screen.findByText(/تعذّر تسجيل طلب تغيير الصمّام/)).textContent).toContain('قد يكون الطلب سُجِّل');
  });

  it('schedule delete failure surfaces the cause and reloads schedules', async () => {
    m.deleteSchedule.mockRejectedValue(Object.assign(new Error('403'), { response: { status: 403 } }));
    wrap(<IrrigationOpsPage />);
    await screen.findByText('S1');
    fireEvent.click(screen.getByTitle('حذف الجدول'));
    const alert = await screen.findByText(/تعذّر حذف الجدول/);
    expect(alert.textContent).toContain('لا تملك صلاحية هذا الإجراء');
    await waitFor(() => expect(m.listSchedules).toHaveBeenCalledTimes(2));
    expect(m.deleteSchedule).toHaveBeenCalledTimes(1);
  });
});
