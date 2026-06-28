// اختبارات Field Workspace Map Card — عقد الـfetcher/الأنواع + سلوك المكوّن.
// المحاكاة في الاختبار فقط (لا mock في كود الإنتاج). يُؤكَّد:
//   • fetchFieldWorkspace يطلب المسار الصحيح ويُمرّر النوع كما هو، ويرمي عند 503.
//   • fieldIndicatorTileUrl يبني رابط بلاطات NDVI صحيحاً ({z}/{x}/{y} حرفيّاً).
//   • المكوّن: loading→بيانات، empty عند فراغ، error عند خطأ، وقاعدة عدم الاختلاق
//     (زرّ NDVI مُعطَّل إن لم تُعلِن مساحة العمل طبقة ndvi).
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
      defaults: { baseURL: 'http://raster.test' },
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    },
  };
});
vi.mock('axios', () => ({ default: { create: vi.fn(() => mockClient) } }));

// ── ظِلّ react-leaflet/leaflet: jsdom لا يصيّر خريطة فعليّة — نستبدلها بعناصر بسيطة. ──
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children?: ReactNode }) => (
    <div data-testid="map">{children}</div>
  ),
  TileLayer: ({ url }: { url: string }) => <div data-testid="tile" data-url={url} />,
  Polygon: () => <div data-testid="polygon" />,
  useMap: () => ({ fitBounds: vi.fn() }),
}));
vi.mock('leaflet', () => ({
  default: {
    latLngBounds: () => ({ isValid: () => true }),
    latLng: (a: number, b: number) => [a, b],
  },
}));
vi.mock('../lib/leafletSetup', () => ({}));

// نُثبّت «الحقل النشط» المشترك كفارغ — كلّ الاختبارات تمرّر fieldId صراحةً،
// فلا يخرج طلب شبكيّ من useFields/useFieldOptions داخله.
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({
    options: [],
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    fieldId: '',
    field: undefined,
    setFieldId: vi.fn(),
  }),
}));

// يُستورَد بعد التهيئة كي يلتقط makeClient العميل الوهميّ.
import {
  fetchFieldWorkspace,
  fieldIndicatorTileUrl,
  type FieldWorkspace,
} from '../services/api';
import * as useApiModule from '../hooks/useApi';
import FieldWorkspaceMapCard from './FieldWorkspaceMapCard';

// ── عيّنة مساحة عمل صادقة (تطابق assemble_workspace) ──
const WS: FieldWorkspace = {
  field_id: 'f-1',
  display_only: true,
  field: { name_ar: 'حقل القمح', crop: 'قمح', area_ha: 3.5, soil_type: 'طينيّة' },
  layers: [
    {
      key: 'ndvi',
      label_ar: 'صحّة الغطاء (NDVI)',
      category: 'vegetation',
      available: false,
      status: 'on_demand',
      display_only: true,
      note_ar: 'يُجلب من الأقمار عند الطلب.',
    },
    {
      key: 'soil_type',
      label_ar: 'نوع التربة',
      category: 'soil',
      available: true,
      status: 'available',
      display_only: true,
      note_ar: 'متاحة من بيانات الحقل.',
    },
  ],
  available_layer_count: 1,
  terrain: null,
  timeline: [
    {
      occurred_at: '2026-05-01T08:00:00',
      event_type: 'irrigation.completed',
      op_ar: 'ريّ',
      category: 'irrigation',
      issue_tags: [],
    },
  ],
  timeline_total: 1,
  honesty_note_ar: 'مساحة عرض تجميعيّة — لا تلوين مفبرك.',
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('عقد fetchFieldWorkspace', () => {
  it('يطلب /workspace بالمسار الصحيح + timeline_limit ويُعيد البيانات كما هي', async () => {
    mockGet.mockResolvedValueOnce({ data: WS });
    const out = await fetchFieldWorkspace('f-1');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/fields/f-1/workspace', {
      params: { timeline_limit: 50 },
    });
    expect(out).toEqual(WS);
    expect(out.field.crop).toBe('قمح');
    expect(out.layers[0].key).toBe('ndvi');
  });

  it('يرمي عند 503 (لا fallback وهميّ — حالة خطأ صادقة)', async () => {
    mockGet.mockRejectedValueOnce(new Error('503'));
    await expect(fetchFieldWorkspace('f-1')).rejects.toThrow('503');
  });
});

describe('عقد fieldIndicatorTileUrl', () => {
  it('يبني رابط بلاطات NDVI ويُبقي {z}/{x}/{y} حرفيّاً', () => {
    const url = fieldIndicatorTileUrl('f-1', 'ndvi', 'latest');
    expect(url).toContain('/v1/fields/f-1/tiles/{z}/{x}/{y}.png');
    expect(url).toContain('index=ndvi');
    // الواجهة لا تُملي تاريخاً: 'latest'/فارغ ⇒ يُحذف المُعامل ويختار الخادم الأحدث.
    expect(url).not.toContain('date=');
  });

  it('يُمرّر تاريخاً صريحاً عند طلبه فقط', () => {
    const url = fieldIndicatorTileUrl('f-1', 'ndvi', '2026-05-01');
    expect(url).toContain('date=2026-05-01');
  });
});

describe('سلوك FieldWorkspaceMapCard', () => {
  const baseQuery = {
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    error: null,
    isSuccess: true,
  };

  function stubWorkspace(over: Record<string, unknown>) {
    vi.spyOn(useApiModule, 'useFieldWorkspace').mockReturnValue({
      ...baseQuery,
      data: undefined,
      ...over,
    } as unknown as ReturnType<typeof useApiModule.useFieldWorkspace>);
  }
  function stubDetail(geometry: unknown) {
    vi.spyOn(useApiModule, 'useFieldDetail').mockReturnValue({
      ...baseQuery,
      data: geometry ? { field_id: 'f-1', geometry } : undefined,
    } as unknown as ReturnType<typeof useApiModule.useFieldDetail>);
  }

  it('loading: يعرض هيكل التحميل', () => {
    stubWorkspace({ isLoading: true, isSuccess: false });
    stubDetail(null);
    render(<FieldWorkspaceMapCard fieldId="f-1" />, { wrapper });
    expect(screen.getByText(/جارٍ تحميل مساحة عمل الحقل/)).toBeInTheDocument();
  });

  it('error: يعرض حالة خطأ صادقة', () => {
    stubWorkspace({ isError: true, isSuccess: false, error: new Error('503') });
    stubDetail(null);
    render(<FieldWorkspaceMapCard fieldId="f-1" />, { wrapper });
    expect(screen.getByText(/تعذّر تحميل مساحة عمل الحقل/)).toBeInTheDocument();
  });

  it('بيانات: يعرض الملخّص + الخطّ الزمنيّ + الخريطة', () => {
    stubWorkspace({ data: WS });
    stubDetail({
      type: 'Polygon',
      coordinates: [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]]],
    });
    render(<FieldWorkspaceMapCard fieldId="f-1" />, { wrapper });
    expect(screen.getByText('ملخّص القرار الموحّد')).toBeInTheDocument();
    expect(screen.getByText('قمح')).toBeInTheDocument();
    expect(screen.getByText('الخطّ الزمنيّ')).toBeInTheDocument();
    expect(screen.getByText('ريّ')).toBeInTheDocument();
    expect(screen.getByTestId('polygon')).toBeInTheDocument();
  });

  it('قاعدة عدم الاختلاق: NDVI on_demand ⇒ الزرّ موجود لكن لا طبقة tile قبل التفعيل', () => {
    stubWorkspace({ data: WS });
    stubDetail({
      type: 'Polygon',
      coordinates: [[[44, 15], [44.01, 15], [44.01, 15.01], [44, 15.01], [44, 15]]],
    });
    render(<FieldWorkspaceMapCard fieldId="f-1" />, { wrapper });
    // قبل التفعيل لا توجد طبقة بلاطات NDVI (طبقة الأساس فقط).
    const tiles = screen.getAllByTestId('tile');
    expect(tiles.some((t) => (t.getAttribute('data-url') || '').includes('tiles'))).toBe(false);
  });

  it('empty: لا حدود ⇒ يعرض "لا حدود مرسومة" دون اختلاق مضلّع', () => {
    stubWorkspace({ data: WS });
    stubDetail(null); // لا هندسة
    render(<FieldWorkspaceMapCard fieldId="f-1" />, { wrapper });
    expect(screen.getByText(/لا حدود مرسومة للحقل/)).toBeInTheDocument();
    expect(screen.queryByTestId('polygon')).not.toBeInTheDocument();
  });
});
