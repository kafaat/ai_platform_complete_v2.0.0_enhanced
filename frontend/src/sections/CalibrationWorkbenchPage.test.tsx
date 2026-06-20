// اختبارات منضدة المعايرة — عقد الـfetchers (مسارات/أفعال + رمي POST/DELETE عند
// الخطأ + ارتداد /audit ⇒ null) وسلوك المكوّن (مقارنة/اقتراح/حارس الموافقة/empty/error).
// المحاكاة في الاختبار فقط (لا mock في كود الإنتاج).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// ── عميل axios وهميّ (يُلتقط داخل makeClient عبر axios.create) ──
const { mockGet, mockPost, mockDelete, mockClient } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  const del = vi.fn();
  return {
    mockGet: get,
    mockPost: post,
    mockDelete: del,
    mockClient: {
      get,
      post,
      delete: del,
      put: vi.fn(),
      patch: vi.fn(),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    },
  };
});
vi.mock('axios', () => ({ default: { create: vi.fn(() => mockClient) } }));

// يُستورَد بعد التهيئة كي يلتقط makeClient العميل الوهميّ.
import {
  fetchRegionCalibration, fetchResolvedCalibration,
  proposeCalibrationValues, setRegionOverride, deleteRegionOverride,
  applyAdaptFromEvidence, fetchCalibrationOverrides, fetchCalibrationAudit,
} from '../services/api';

beforeEach(() => {
  vi.clearAllMocks();
});

// ───────────────────────────── عقد الـfetchers ─────────────────────────────
describe('عقد fetchers المعايرة', () => {
  it('fetchRegionCalibration: يطلب /{region} (القاعدة) ويُرجِع البيانات', async () => {
    mockGet.mockResolvedValueOnce({ data: { region: 'jawf', kc_dyn_min: 0.3 } });
    const out = await fetchRegionCalibration('jawf');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/calibration/jawf');
    expect(out.region).toBe('jawf');
  });

  it('fetchResolvedCalibration: يطلب /{region}/resolved (المُحلّ)', async () => {
    mockGet.mockResolvedValueOnce({ data: { region: 'ibb', override_source: 'db_override', override_applied: ['kc_dyn_min'] } });
    const out = await fetchResolvedCalibration('ibb');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/calibration/ibb/resolved');
    expect(out.override_source).toBe('db_override');
  });

  it('proposeCalibrationValues: POST /{region}/propose-values بالحمولة (يقترح لا يكتب)', async () => {
    const v = { region: 'jawf', accepted: { kc_dyn_min: 0.3 }, rejected: [], override_block: {}, validated: false, source_ar: null, ready_to_persist: false, calibrated: false, warnings_ar: [] };
    mockPost.mockResolvedValueOnce({ data: v });
    const out = await proposeCalibrationValues('jawf', { kc_dyn_min: 0.3 });
    expect(mockPost).toHaveBeenCalledWith('/api/v1/calibration/jawf/propose-values', { kc_dyn_min: 0.3 });
    expect(out.accepted.kc_dyn_min).toBe(0.3);
  });

  it('setRegionOverride: POST /{region}/override — يرمي عند 422 (رفض/نقص مصدر)', async () => {
    mockPost.mockResolvedValueOnce({ data: { region: 'jawf', persisted: true, accepted: {}, source_ar: 'مصدر', resolved: {} } });
    await setRegionOverride('jawf', { kc_dyn_min: 0.3, source_ar: 'مصدر' });
    expect(mockPost).toHaveBeenCalledWith('/api/v1/calibration/jawf/override', { kc_dyn_min: 0.3, source_ar: 'مصدر' });

    mockPost.mockRejectedValueOnce({ response: { status: 422, data: { detail: { warnings_ar: ['مرفوض'] } } } });
    await expect(setRegionOverride('jawf', { kc_dyn_min: 9 })).rejects.toMatchObject({ response: { status: 422 } });
  });

  it('deleteRegionOverride: DELETE /{region}/override — يرمي عند الخطأ', async () => {
    mockDelete.mockResolvedValueOnce({ data: { region: 'jawf', reverted: true } });
    const out = await deleteRegionOverride('jawf');
    expect(mockDelete).toHaveBeenCalledWith('/api/v1/calibration/jawf/override');
    expect(out.reverted).toBe(true);

    mockDelete.mockRejectedValueOnce({ response: { status: 503 } });
    await expect(deleteRegionOverride('jawf')).rejects.toMatchObject({ response: { status: 503 } });
  });

  it('applyAdaptFromEvidence: POST /{region}/adapt-from-evidence/apply مع confirm=true', async () => {
    mockPost.mockResolvedValueOnce({ data: { status: 'gated', applied: false, proposals: [] } });
    const out = await applyAdaptFromEvidence('marib', { confirm: true });
    expect(mockPost).toHaveBeenCalledWith('/api/v1/calibration/marib/adapt-from-evidence/apply', { confirm: true });
    expect(out.applied).toBe(false);

    mockPost.mockRejectedValueOnce({ response: { status: 422 } }); // بلا تأكيد ⇒ يرمي
    await expect(applyAdaptFromEvidence('marib', { confirm: false })).rejects.toMatchObject({ response: { status: 422 } });
  });

  it('fetchCalibrationOverrides: GET /overrides/all مع تطبيع دفاعيّ', async () => {
    mockGet.mockResolvedValueOnce({ data: { overrides: [{ region: 'jawf', override_values: {}, source_ar: 'م', validated: true, updated_at: '2026-06-01' }], count: 1 } });
    const out = await fetchCalibrationOverrides();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/calibration/overrides/all');
    expect(out.count).toBe(1);
    // شكل غير متوقّع ⇒ مصفوفة فارغة + 0 (لا كسر)
    mockGet.mockResolvedValueOnce({ data: {} });
    const empty = await fetchCalibrationOverrides();
    expect(empty.overrides).toEqual([]);
    expect(empty.count).toBe(0);
  });

  it('fetchCalibrationAudit: 404/خطأ ⇒ null (أفضل-جهد، لا تلفيق)', async () => {
    mockGet.mockResolvedValueOnce({ data: { entries: [{ action: 'override', field: 'kc_dyn_min' }] } });
    const ok = await fetchCalibrationAudit('jawf');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/calibration/jawf/audit');
    expect(ok?.entries).toHaveLength(1);

    mockGet.mockRejectedValueOnce({ response: { status: 404 } });
    expect(await fetchCalibrationAudit('jawf')).toBeNull();
  });
});

// ───────────────────────────── سلوك المكوّن ─────────────────────────────
// نتحكّم بالدور عبر useAuthStore الوهميّ، وبالـhooks عبر تجسّس useApi.
let mockRole = 'owner';
vi.mock('../hooks/useAuth', () => ({
  useAuthStore: (sel: (s: { user: { role: string } }) => unknown) => sel({ user: { role: mockRole } }),
}));

import * as useApiModule from '../hooks/useApi';
import CalibrationWorkbenchPage from './CalibrationWorkbenchPage';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const qBase = { isLoading: false, isError: false, isFetching: false, isSuccess: true, refetch: vi.fn(), error: null };
const mBase = { isPending: false, isError: false, error: null, mutate: vi.fn(), reset: vi.fn() };

function stubHooks(over: {
  base?: Record<string, unknown>; resolved?: Record<string, unknown>;
  audit?: Record<string, unknown>; overrides?: Record<string, unknown>;
  propose?: Record<string, unknown>; setOverride?: Record<string, unknown>;
} = {}) {
  vi.spyOn(useApiModule, 'useRegionCalibration').mockReturnValue({ ...qBase, data: { region: 'jawf', kc_dyn_min: 0.3, kc_dyn_max: 1.0, raw_fraction: 0.5, root_depth_m: 1.0, forecast_infiltration: 0.5, yield_uncertainty: 0.2, price_uncertainty: 0.2 }, ...over.base } as unknown as ReturnType<typeof useApiModule.useRegionCalibration>);
  vi.spyOn(useApiModule, 'useResolvedCalibration').mockReturnValue({ ...qBase, data: { region: 'jawf', kc_dyn_min: 0.35, kc_dyn_max: 1.0, raw_fraction: 0.5, root_depth_m: 1.0, forecast_infiltration: 0.5, yield_uncertainty: 0.2, price_uncertainty: 0.2, source_ar: 'قيم مُدامة', override_applied: ['kc_dyn_min'], override_source: 'db_override' }, ...over.resolved } as unknown as ReturnType<typeof useApiModule.useResolvedCalibration>);
  vi.spyOn(useApiModule, 'useCalibrationAudit').mockReturnValue({ ...qBase, data: null, ...over.audit } as unknown as ReturnType<typeof useApiModule.useCalibrationAudit>);
  vi.spyOn(useApiModule, 'useCalibrationOverrides').mockReturnValue({ ...qBase, data: { overrides: [], count: 0 }, ...over.overrides } as unknown as ReturnType<typeof useApiModule.useCalibrationOverrides>);
  vi.spyOn(useApiModule, 'useProposeCalibrationValues').mockReturnValue({ ...mBase, ...over.propose } as unknown as ReturnType<typeof useApiModule.useProposeCalibrationValues>);
  vi.spyOn(useApiModule, 'useSetRegionOverride').mockReturnValue({ ...mBase, ...over.setOverride } as unknown as ReturnType<typeof useApiModule.useSetRegionOverride>);
  vi.spyOn(useApiModule, 'useDeleteRegionOverride').mockReturnValue({ ...mBase } as unknown as ReturnType<typeof useApiModule.useDeleteRegionOverride>);
  vi.spyOn(useApiModule, 'useApplyAdaptFromEvidence').mockReturnValue({ ...mBase } as unknown as ReturnType<typeof useApiModule.useApplyAdaptFromEvidence>);
}

describe('سلوك CalibrationWorkbenchPage', () => {
  beforeEach(() => { mockRole = 'owner'; });

  it('مقارنة: يعرض القاعدة مقابل المُدام مع إبراز المعايرة المُدامة', () => {
    stubHooks();
    render(<CalibrationWorkbenchPage />, { wrapper });
    expect(screen.getByText('القاعدة مقابل المُدام')).toBeInTheDocument();
    expect(screen.getByText(/مُعايَر مُدام/)).toBeInTheDocument();
  });

  it('اقتراح: إدخال قيمة + زرّ التحقّق يستدعي mutate (يقترح لا يكتب)', () => {
    const mutate = vi.fn();
    stubHooks({ propose: { mutate } });
    render(<CalibrationWorkbenchPage />, { wrapper });
    const kcMin = screen.getAllByPlaceholderText('—')[0];
    fireEvent.change(kcMin, { target: { value: '0.32' } });
    fireEvent.click(screen.getByText('تحقّق (اقتراح)'));
    expect(mutate).toHaveBeenCalledTimes(1);
    expect(mutate.mock.calls[0][0]).toMatchObject({ region: 'jawf', values: { kc_dyn_min: 0.32 } });
  });

  it('حارس الموافقة: زرّ «وافِق وأَدِم» معطَّل بلا مصدر، ولا يُدِيم حتى يُملأ المصدر', () => {
    const mutate = vi.fn();
    stubHooks({ setOverride: { mutate } });
    render(<CalibrationWorkbenchPage />, { wrapper });
    const kcMin = screen.getAllByPlaceholderText('—')[0];
    fireEvent.change(kcMin, { target: { value: '0.32' } });
    const approve = screen.getByText('وافِق وأَدِم').closest('button')!;
    expect(approve).toBeDisabled(); // بلا source_ar
    expect(mutate).not.toHaveBeenCalled();
  });

  it('صلاحيّة: المُشاهِد (viewer) لا يرى قسم الاقتراح/الموافقة (قراءة فقط)', () => {
    mockRole = 'viewer';
    stubHooks();
    render(<CalibrationWorkbenchPage />, { wrapper });
    expect(screen.queryByText('اقتراح وتحقّق')).not.toBeInTheDocument();
    expect(screen.getByText(/دورك للعرض فقط/)).toBeInTheDocument();
    // لكنّه يرى المقارنة
    expect(screen.getByText('القاعدة مقابل المُدام')).toBeInTheDocument();
  });

  it('empty: لا تجاوز ولا /audit ⇒ حالة تدقيق فارغة صادقة', () => {
    stubHooks();
    render(<CalibrationWorkbenchPage />, { wrapper });
    expect(screen.getByText(/لا سجلّ تدقيق لهذه المنطقة بعد/)).toBeInTheDocument();
  });

  it('error: فشل جلب المقارنة ⇒ حالة خطأ صادقة', () => {
    stubHooks({ base: { isError: true, isLoading: false, data: undefined } });
    render(<CalibrationWorkbenchPage />, { wrapper });
    expect(screen.getByText(/تعذّر جلب ملفّ المعايرة/)).toBeInTheDocument();
  });
});
