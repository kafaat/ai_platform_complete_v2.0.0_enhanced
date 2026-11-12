// حالات بيانات لوحة المزرعة: فشلٌ بلا بيانات يستبدل الصفحة؛ فشل تحديثٍ خلفيّ مع بيانات سابقة
// يُبقي آخر ملخّص ناجح ويُعلن ذلك؛ وقراءة NDVI الغائبة تُوصَف بحسب حالة استعلامها (لا «غير مقيس»
// أثناء التحميل)؛ وفشل التنبيهات لا يُصفّر عدّادها.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

type Q = Record<string, unknown>;
const st = vi.hoisted(() => ({ dash: {} as Record<string, unknown>, allNdvi: {} as Record<string, unknown>, alerts: {} as Record<string, unknown>, fields: [] as unknown[] }));
vi.mock('../hooks/useApi', () => ({
  useDashboardData: () => ({
    data: { kpis: [], fields_summary: st.fields, alerts: [], total_fields: st.fields.length, active_alerts: 0 },
    dash: st.dash, allNdvi: st.allNdvi, refetch: vi.fn(),
  }),
  useAlerts: () => st.alerts,
}));
vi.mock('../hooks/useSelectedField', () => ({ useSelectedField: () => ({ setFieldId: vi.fn() }) }));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'owner' } }) }));
vi.mock('../hooks/useFeatureRegistry', () => ({ useFeatureRegistry: () => null, isRuntimePageEnabled: () => true }));
vi.mock('../components/ConnectionStatus', () => ({ default: () => null }));

import DashboardPage from './DashboardPage';

const ok = (data?: unknown): Q => ({ isSuccess: true, isError: false, isLoading: false, isFetching: false, data, refetch: vi.fn() });
const err = (data?: unknown): Q => ({ isSuccess: false, isError: true, isLoading: false, isFetching: false, data, error: { response: { status: 503 } }, refetch: vi.fn() });
const loading = (): Q => ({ isSuccess: false, isError: false, isLoading: true, isFetching: true, data: undefined, refetch: vi.fn() });
const renderPage = () => render(<DashboardPage setPage={() => {}} />);

afterEach(cleanup);

describe('DashboardPage data states', () => {
  it('first load failure replaces the summary with an error state', () => {
    st.dash = err(); st.allNdvi = ok(); st.alerts = ok([]); st.fields = [];
    const { container } = renderPage();
    expect(screen.getByText('تعذّر تحميل ملخص المزرعة')).toBeInTheDocument();
    expect(container.querySelectorAll('.ops-metric')).toHaveLength(0);
  });

  it('first load in progress shows loading, not zeros', () => {
    st.dash = loading(); st.allNdvi = loading(); st.alerts = loading(); st.fields = [];
    const { container } = renderPage();
    expect(screen.getByText('جارٍ تحميل ملخص المزرعة…')).toBeInTheDocument();
    expect(container.querySelectorAll('.ops-metric')).toHaveLength(0);
  });

  it('background refetch failure keeps the last good summary and says so', () => {
    st.fields = [{ field_id: '1', field_name: 'a', ndvi: 0.6 }];
    st.dash = err({ kpis: [], fields_summary: st.fields }); st.allNdvi = ok(); st.alerts = ok([]);
    const { container } = renderPage();
    expect(container.querySelectorAll('.ops-metric')).toHaveLength(3);
    expect(screen.getByText(/المعروض آخر ملخص ناجح/)).toBeInTheDocument();
    expect(screen.queryByText('تعذّر تحميل ملخص المزرعة')).not.toBeInTheDocument();
  });

  it('a field without NDVI reads by query state: loading / unknown / not measured', () => {
    st.dash = ok({}); st.alerts = ok([]); st.fields = [{ field_id: '1', field_name: 'a' }];
    st.allNdvi = loading();
    const a = renderPage();
    expect(a.container.querySelector('.ops-reading-note')?.textContent).toBe('جارٍ التحميل…');
    cleanup();
    st.allNdvi = err();
    const b = renderPage();
    expect(b.container.querySelector('.ops-reading-note')?.textContent).toBe('غير معروف');
    cleanup();
    st.allNdvi = ok();
    const c = renderPage();
    expect(c.container.querySelector('.ops-reading-note')?.textContent).toBe('غير مقيس');
  });

  it('alerts failure shows a dash in the counter, not zero', () => {
    st.dash = ok({}); st.allNdvi = ok(); st.alerts = err(); st.fields = [];
    const { container } = renderPage();
    expect(screen.getByText('تعذّر تحميل التنبيهات')).toBeInTheDocument();
    expect(container.querySelectorAll('.ops-metric')[2].textContent).toContain('—');
  });
});
