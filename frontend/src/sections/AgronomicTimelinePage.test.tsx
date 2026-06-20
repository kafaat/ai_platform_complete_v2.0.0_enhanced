// اختبارات الخطّ الزمنيّ الأغرونوميّ — عقد الـfetcher (المسار + المعاملات + التطبيع
// الدفاعيّ) + سلوك المكوّن (loading/empty/error + فلترة الفئات + note_ar صادق).
// المحاكاة في الاختبار فقط (لا mock في كود الإنتاج).
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
      interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
    },
  };
});
vi.mock('axios', () => ({ default: { create: vi.fn(() => mockClient) } }));

// نُثبّت «الحقل النشط» المشترك — لكلّ اختبار نضبط fieldId صراحةً.
const selectedField = {
  options: [{ id: 'f-1', name: 'حقل القمح' }],
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
  fieldId: 'f-1',
  field: { id: 'f-1', name: 'حقل القمح' },
  setFieldId: vi.fn(),
};
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => selectedField,
}));

// يُستورَد بعد التهيئة كي يلتقط makeClient العميل الوهميّ.
import { fetchUnifiedTimeline, type UnifiedTimeline } from '../services/api';
import * as useApiModule from '../hooks/useApi';
import AgronomicTimelinePage from './AgronomicTimelinePage';

const TL: UnifiedTimeline = {
  field_id: 'f-1',
  total_events: 2,
  earliest_at: '2026-05-01T08:00:00',
  latest_at: '2026-06-01T08:00:00',
  category_counts: { operation: 1, weather: 1 },
  events: [
    {
      timestamp: '2026-06-01T08:00:00',
      event_type: 'operation.irrigation.completed',
      category: 'operation',
      summary_ar: 'اكتمل الريّ',
      actor_id: 'u1',
      payload: {},
    },
    {
      timestamp: '2026-05-01T08:00:00',
      event_type: 'weather.rainfall',
      category: 'weather',
      summary_ar: 'هطول مطر',
      actor_id: null,
      payload: {},
    },
  ],
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('عقد fetchUnifiedTimeline', () => {
  it('يطلب المسار الصحيح + المعاملات ويُعيد البيانات مُطبَّعة', async () => {
    mockGet.mockResolvedValueOnce({ data: TL });
    const out = await fetchUnifiedTimeline('f-1', { category: 'operation' });
    expect(mockGet).toHaveBeenCalledWith('/api/v1/fields/f-1/unified-timeline', {
      params: { limit: 200, newest_first: true, category: 'operation' },
    });
    expect(out.total_events).toBe(2);
    expect(out.events[0].category).toBe('operation');
  });

  it('تطبيع دفاعيّ: ردّ تعطّل القاعدة (note_ar، بلا events) ⇒ خطّ فارغ صادق', async () => {
    mockGet.mockResolvedValueOnce({
      data: { field_id: 'f-1', events: [], total_events: 0, note_ar: 'القاعدة غير مفعّلة' },
    });
    const out = await fetchUnifiedTimeline('f-1');
    expect(out.events).toEqual([]);
    expect(out.total_events).toBe(0);
    expect(out.note_ar).toBe('القاعدة غير مفعّلة');
    expect(out.category_counts).toEqual({});
  });

  it('يرمي عند 503 (لا fallback وهميّ)', async () => {
    mockGet.mockRejectedValueOnce(new Error('503'));
    await expect(fetchUnifiedTimeline('f-1')).rejects.toThrow('503');
  });
});

describe('سلوك AgronomicTimelinePage', () => {
  const base = { isLoading: false, isError: false, refetch: vi.fn(), error: null, isSuccess: true };
  function stub(over: Record<string, unknown>) {
    vi.spyOn(useApiModule, 'useUnifiedTimeline').mockReturnValue({
      ...base, data: undefined, ...over,
    } as unknown as ReturnType<typeof useApiModule.useUnifiedTimeline>);
  }

  it('loading: يعرض حالة التحميل', () => {
    stub({ isLoading: true, isSuccess: false });
    render(<AgronomicTimelinePage />, { wrapper });
    expect(screen.getByText(/جارٍ جلب الخطّ الزمنيّ/)).toBeInTheDocument();
  });

  it('error: يعرض حالة خطأ صادقة', () => {
    stub({ isError: true, isSuccess: false, error: new Error('503') });
    render(<AgronomicTimelinePage />, { wrapper });
    expect(screen.getByText(/تعذّر جلب الخطّ الزمنيّ/)).toBeInTheDocument();
  });

  it('بيانات: يعرض الأحداث + أزرار الفلترة بالفئة (من إحصاءات الخادم)', () => {
    stub({ data: TL });
    render(<AgronomicTimelinePage />, { wrapper });
    expect(screen.getByText('اكتمل الريّ')).toBeInTheDocument();
    expect(screen.getByText('هطول مطر')).toBeInTheDocument();
    expect(screen.getByText(/الكلّ \(2\)/)).toBeInTheDocument();
    expect(screen.getByText(/عمليّات \(1\)/)).toBeInTheDocument();
  });

  it('empty: لا أحداث ⇒ EmptyState صادق (لا تاريخ مخترَع)', () => {
    stub({ data: { ...TL, total_events: 0, events: [], category_counts: {} } });
    render(<AgronomicTimelinePage />, { wrapper });
    expect(screen.getByText(/لا أحداث في الخطّ الزمنيّ/)).toBeInTheDocument();
  });

  it('تعطّل القاعدة: note_ar معروض كحالة فارغة صادقة', () => {
    stub({ data: { ...TL, total_events: 0, events: [], category_counts: {}, note_ar: 'القاعدة غير مفعّلة (DATABASE_URL) — لا تاريخ حيّ' } });
    render(<AgronomicTimelinePage />, { wrapper });
    expect(screen.getByText(/القاعدة غير مفعّلة/)).toBeInTheDocument();
  });
});
