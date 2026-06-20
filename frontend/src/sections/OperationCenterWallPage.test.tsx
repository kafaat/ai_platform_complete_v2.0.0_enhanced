// اختبارات جدار مركز العمليّات — عقد الـfetchers (fetchOperationsSummary مع الارتداد
// 404 ⇒ null، fetchFleetHealth مع التطبيع الدفاعيّ) + سلوك المكوّن: كلّ بلاطة لها
// حالة loading/empty/error مستقلّة (فشل بلاطة لا يكسر الجدار). المحاكاة في الاختبار
// فقط — لا mock في كود الإنتاج (الصدق: كلّ بلاطة حالتها الصادقة).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// ── عميل axios وهميّ (يُلتقط داخل makeClient عبر axios.create) ──
const { mockGet, mockClient } = vi.hoisted(() => {
  const get = vi.fn();
  return {
    mockGet: get,
    mockClient: {
      get,
      post: vi.fn(),
      put: vi.fn(),
      patch: vi.fn(),
      delete: vi.fn(),
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    },
  };
});
vi.mock('axios', () => ({ default: { create: vi.fn(() => mockClient) } }));

// react-leaflet يُمثَّل بظِلّ خفيف: jsdom لا يصيّر خرائط فعليّة، ونريد اختبار حالات
// البلاطة لا الخريطة. (المكوّنات تصبح عناصر فارغة — لا تكسر الشجرة.)
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => <div data-testid="map">{children}</div>,
  TileLayer: () => null,
  Polygon: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  CircleMarker: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Tooltip: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
}));
// تفادي side-effect تحميل Leaflet CSS/الأيقونات في jsdom.
vi.mock('../lib/leafletSetup', () => ({}));

// يُستورَد بعد التهيئة كي يلتقط makeClient العميل الوهميّ.
import {
  fetchOperationsSummary,
  fetchFleetHealth,
} from '../services/api';
import * as useApiModule from '../hooks/useApi';
import * as useFieldOptionsModule from '../hooks/useFieldOptions';
import OperationCenterWallPage from './OperationCenterWallPage';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

// ════════════════════ عقد الـfetchers ════════════════════
describe('عقد fetchOperationsSummary', () => {
  it('يطلب المسار الصحيح ويُرجِع الكائن حين تكون الاستجابة كائناً', async () => {
    const summary = { fields_total: 5, alerts: { critical: 1 }, generated_at: '2026-06-20' };
    mockGet.mockResolvedValueOnce({ data: summary });
    const out = await fetchOperationsSummary();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/operations/summary');
    expect(out).toEqual(summary);
  });

  it('ارتداد 404 (العلم مُطفأ/النقطة غير منشورة) ⇒ null (لا تلفيق)', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 404 } });
    expect(await fetchOperationsSummary()).toBeNull();
  });

  it('أيّ خطأ (503 DB) ⇒ null فترتدّ الصفحة لكلّ بلاطة لنقطتها', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 503 } });
    expect(await fetchOperationsSummary()).toBeNull();
  });

  it('استجابة غير كائن (مصفوفة/نصّ) ⇒ null', async () => {
    mockGet.mockResolvedValueOnce({ data: [1, 2, 3] });
    expect(await fetchOperationsSummary()).toBeNull();
    mockGet.mockResolvedValueOnce({ data: '<html/>' });
    expect(await fetchOperationsSummary()).toBeNull();
  });
});

describe('عقد fetchFleetHealth', () => {
  it('يطلب المسار الصحيح ويُمرّر الملخّص + الأجهزة الصامتة', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        total_devices: 3, online: 2, silent: 1, critical_silent: 0,
        fleet_status_ar: '🟡 جهاز صامت',
        silent_devices: [{ device_id: 'd1', name: 'حسّاس', type: 'soil_moisture', field_id: 'f1', silent: true, criticality: 'important', detail_ar: 'صامت', criticality_note_ar: '', threshold_minutes: 60 }],
      },
    });
    const out = await fetchFleetHealth();
    expect(mockGet).toHaveBeenCalledWith('/api/v1/devices/fleet-health');
    expect(out.total_devices).toBe(3);
    expect(out.silent_devices[0].name).toBe('حسّاس');
  });

  it('تطبيع دفاعيّ: حقول ناقصة/شكل غير متوقّع ⇒ أصفار + مصفوفة فارغة (لا انهيار)', async () => {
    mockGet.mockResolvedValueOnce({ data: { fleet_status_ar: 'x', silent_devices: 'oops' } });
    const out = await fetchFleetHealth();
    expect(out.total_devices).toBe(0);
    expect(out.online).toBe(0);
    expect(Array.isArray(out.silent_devices)).toBe(true);
    expect(out.silent_devices).toHaveLength(0);
  });

  it('الخطأ (503/403) يُرفع — حالة صادقة لبلاطة المعدّات (لا fallback وهميّ)', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 503 } });
    await expect(fetchFleetHealth()).rejects.toMatchObject({ response: { status: 503 } });
  });
});

// ════════════════════ سلوك المكوّن: حالات البلاطات المستقلّة ════════════════════
// نُمسرِح الـhooks مباشرةً كي نتحكّم في حالة كلّ بلاطة على حدة (عزل تامّ).
type Q = Record<string, unknown>;
const qLoading: Q = { isLoading: true, isError: false, data: undefined, refetch: vi.fn() };
const qError:   Q = { isLoading: false, isError: true, data: undefined, refetch: vi.fn(), error: new Error('503') };
function qData(data: unknown): Q { return { isLoading: false, isError: false, data, refetch: vi.fn() }; }

function stubAll(over: Partial<Record<
  'summary' | 'fields' | 'alerts' | 'fleet' | 'weather' | 'valves' | 'schedules' | 'decisions', Q
>> = {}) {
  vi.spyOn(useApiModule, 'useOperationsSummary').mockReturnValue(
    (over.summary ?? qData(null)) as never);
  vi.spyOn(useFieldOptionsModule, 'useFieldOptions').mockReturnValue(
    { ...(over.fields ?? qData(undefined)), options: (over.fields?.data as unknown[]) ?? [] } as never);
  vi.spyOn(useApiModule, 'useAlerts').mockReturnValue((over.alerts ?? qData([])) as never);
  vi.spyOn(useApiModule, 'useFleetHealth').mockReturnValue((over.fleet ?? qData(undefined)) as never);
  vi.spyOn(useApiModule, 'useWeatherForecast').mockReturnValue((over.weather ?? qData(undefined)) as never);
  vi.spyOn(useApiModule, 'useValves').mockReturnValue((over.valves ?? qData([])) as never);
  vi.spyOn(useApiModule, 'useSchedules').mockReturnValue((over.schedules ?? qData([])) as never);
  vi.spyOn(useApiModule, 'useDecisionRecords').mockReturnValue(
    (over.decisions ?? qData({ decisions: [], count: 0 })) as never);
}

describe('سلوك OperationCenterWallPage', () => {
  it('التلخيص الموحّد متاح ⇒ ترويسة «تلخيص موحّد»؛ null ⇒ «مصادر منفصلة»', () => {
    stubAll({ summary: qData({ fields_total: 1 }) });
    const { unmount } = render(<OperationCenterWallPage />, { wrapper });
    expect(screen.getByText(/تلخيص موحّد متاح/)).toBeInTheDocument();
    unmount();

    stubAll({ summary: qData(null) });
    render(<OperationCenterWallPage />, { wrapper });
    expect(screen.getByText(/مصادر منفصلة/)).toBeInTheDocument();
  });

  it('عزل البلاطات: فشل بلاطة واحدة (المعدّات) لا يكسر الجدار — البقيّة تعرض حالاتها', () => {
    stubAll({
      fleet: qError,                                  // بلاطة المعدّات: خطأ
      alerts: qLoading,                               // بلاطة التنبيهات: تحميل
      decisions: qData({ decisions: [], count: 0 }),  // بلاطة القرارات: فارغة
    });
    render(<OperationCenterWallPage />, { wrapper });
    // الجدار يُعرَض كاملاً (كلّ العناوين موجودة) رغم فشل بلاطة واحدة.
    expect(screen.getByText('خريطة الحقول')).toBeInTheDocument();
    expect(screen.getByText('المعدّات والأجهزة')).toBeInTheDocument();
    expect(screen.getByText('آخر القرارات')).toBeInTheDocument();
    // بلاطة المعدّات الفاشلة تعرض خطأها المستقلّ.
    expect(screen.getByText('تعذّر جلب صحّة الأسطول')).toBeInTheDocument();
    // وبلاطة القرارات الفارغة تعرض «لا تتوفّر» بصدق (لا أرقام مُختلَقة).
    expect(screen.getByText(/لا قرارات مُدامة بعد/)).toBeInTheDocument();
  });

  it('بلاطة التنبيهات تُجمّع بالخطورة (critical/warning/info) من بيانات حيّة', () => {
    stubAll({
      alerts: qData([
        { alert_id: 'a1', severity: 'critical', title_ar: 'إجهاد', field_id: null, alert_type: 'heat_stress', message_ar: null, status: 'active', created_at: null },
        { alert_id: 'a2', severity: 'warning', title_ar: 'رطوبة', field_id: null, alert_type: 'low_moisture', message_ar: null, status: 'active', created_at: null },
        { alert_id: 'a3', severity: 'info', title_ar: 'ملاحظة', field_id: null, alert_type: 'other', message_ar: null, status: 'active', created_at: null },
      ]),
    });
    render(<OperationCenterWallPage />, { wrapper });
    expect(screen.getByText('حرِجة')).toBeInTheDocument();
    expect(screen.getByText('تحذير')).toBeInTheDocument();
    expect(screen.getByText('معلومة')).toBeInTheDocument();
  });

  it('بلاطة الطقس بلا لقطة ⇒ «لا تتوفّر» (لا تلفيق قيمة)', () => {
    stubAll({ weather: qData({ current: null }) });
    render(<OperationCenterWallPage />, { wrapper });
    expect(screen.getByText(/لا تتوفّر لقطة طقس/)).toBeInTheDocument();
  });
});
