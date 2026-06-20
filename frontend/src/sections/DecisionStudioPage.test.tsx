// اختبارات استوديو القرار — عقد الـfetcher (incl. الارتداد 404 ⇒ lineage) +
// سلوك المكوّن (loading/empty/error + القرار غير المُدام ⇒ «غير متاح»).
// المحاكاة في الاختبار فقط (لا mock في كود الإنتاج).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

// يُستورَد بعد التهيئة كي يلتقط makeClient العميل الوهميّ.
import {
  fetchDecisionExplain,
  type DecisionExplainResult,
  type DecisionLineage,
} from '../services/api';
import * as useApiModule from '../hooks/useApi';
import DecisionStudioPage from './DecisionStudioPage';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('عقد fetchDecisionExplain', () => {
  it('يطلب /explain أوّلاً ويُطبّع الردّ كما هو (المصدر explain)', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        decision_id: 'dec_1',
        decision_type: 'crop_decision',
        found: true,
        explanation: {
          confidence: 0.8,
          calibrated: false,
          signals: [{ key: 'ndvi', label_ar: 'الغطاء', value: 0.6, status: 'ok' }],
          policy: { resolved_policy: undefined, applied: 'balanced', auto: true, reasons_ar: ['سبب'] },
          constraints: [{ key: 'cap', label_ar: 'سقف', value: 5 }],
          final: { الريّ: 'ابدأ' },
          warnings_ar: ['تحذير'],
        },
        outcomes: [],
        evidence: null,
      },
    });
    const out: DecisionExplainResult = await fetchDecisionExplain('dec_1');
    expect(mockGet).toHaveBeenCalledWith('/api/v1/decision/dec_1/explain');
    expect(out.source).toBe('explain');
    expect(out.found).toBe(true);
    expect(out.explanation?.calibrated).toBe(false);
    expect(out.explanation?.signals[0].label_ar).toBe('الغطاء');
  });

  it('يرتدّ عند 404 إلى /lineage ويشتقّ شرحاً صادقاً من decision_value', async () => {
    // أوّل نداء (/explain) ⇒ 404؛ ثانٍ (/lineage) ⇒ نَسَب مُدام.
    mockGet.mockRejectedValueOnce({ response: { status: 404 } });
    const lineage: DecisionLineage = {
      decision_id: 'dec_2',
      decision: {
        decision_id: 'dec_2',
        field_id: 'f1',
        decision_type: 'profit_aware',
        region: 'jawf',
        stage: 'decision',
        confidence: 0.7,
        created_by: 'u1',
        created_at: '2026-06-01',
        decision_value: {
          calibrated: false,
          policy_decision: { resolved_policy: 'deficit', applied_policy: 'deficit', auto: true, reasons_ar: ['ماء محدود'] },
          water_state: { needs_irrigation: true },
          irrigation: { policy: 'deficit', total_mm: 12, stress_days: 2, action_ar: 'اروِ غداً' },
          risks: [{ key: 'heat', label_ar: 'إجهاد حراريّ', level_ar: 'مرتفع' }],
          warnings_ar: ['تقديريّ غير مُعايَر'],
        },
      },
      outcomes: [],
      outcome_count: 0,
      stages_present: ['decision'],
    };
    mockGet.mockResolvedValueOnce({ data: lineage });

    const out = await fetchDecisionExplain('dec_2');
    expect(mockGet).toHaveBeenNthCalledWith(1, '/api/v1/decision/dec_2/explain');
    expect(mockGet).toHaveBeenNthCalledWith(2, '/api/v1/decision/dec_2/lineage');
    expect(out.source).toBe('lineage_derived');
    expect(out.found).toBe(true);
    expect(out.explanation?.policy?.applied).toBe('deficit');
    expect(out.explanation?.policy?.reasons_ar).toContain('ماء محدود');
    // الإشارات مُشتقّة من حقائق مُدامة فعلاً (حاجة ريّ + إجهاد + مخاطرة).
    expect(out.explanation?.signals.some((s) => s.key === 'needs_irrigation')).toBe(true);
    expect(out.explanation?.signals.some((s) => s.label_ar === 'إجهاد حراريّ')).toBe(true);
    expect(out.explanation?.final['الريّ']).toBe('اروِ غداً');
  });

  it('قرار غير مُدام (decision=null في النَّسَب) ⇒ found=false (لا اختلاق)', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 404 } });
    mockGet.mockResolvedValueOnce({
      data: { decision_id: 'dec_x', decision: null, outcomes: [], outcome_count: 0, stages_present: [] },
    });
    const out = await fetchDecisionExplain('dec_x');
    expect(out.found).toBe(false);
    expect(out.explanation).toBeNull();
  });

  it('خطأ غير 404 (503) يُرفع — لا ارتداد (حالة خطأ صادقة)', async () => {
    mockGet.mockRejectedValueOnce({ response: { status: 503 } });
    await expect(fetchDecisionExplain('dec_3')).rejects.toMatchObject({ response: { status: 503 } });
    expect(mockGet).toHaveBeenCalledTimes(1); // لم يُستدعَ /lineage
  });
});

describe('سلوك DecisionStudioPage', () => {
  const base = { isLoading: false, isError: false, isFetching: false, refetch: vi.fn(), error: null, isSuccess: true };
  function stub(over: Record<string, unknown>) {
    vi.spyOn(useApiModule, 'useDecisionExplain').mockReturnValue({
      ...base, data: undefined, ...over,
    } as unknown as ReturnType<typeof useApiModule.useDecisionExplain>);
  }

  it('فارغ ابتداءً: يطلب إدخال معرّف قرار', () => {
    stub({});
    render(<DecisionStudioPage />, { wrapper });
    expect(screen.getByText(/أدخِل معرّف قرار لشرحه/)).toBeInTheDocument();
  });

  it('بيانات: يعرض مراحل الإشارات/السياسة/القيود/القرار النهائيّ + إبراز غير مُعايَر', () => {
    stub({
      data: {
        decision_id: 'dec_1', decision_type: 'crop_decision', found: true, source: 'lineage_derived',
        explanation: {
          confidence: 0.7, calibrated: false,
          signals: [{ key: 'a', label_ar: 'إشارة أ', value: 1, status: 'ok' }],
          policy: { resolved: 'p', applied: 'p', auto: true, reasons_ar: ['سبب'] },
          constraints: [{ key: 'c', label_ar: 'قيد', value: 2 }],
          final: { الريّ: 'ابدأ' }, warnings_ar: [],
        },
        outcomes: [], evidence: null,
      } as DecisionExplainResult,
    });
    render(<DecisionStudioPage />, { wrapper });
    expect(screen.getByText('الإشارات')).toBeInTheDocument();
    expect(screen.getByText('السياسة')).toBeInTheDocument();
    expect(screen.getByText('القيود')).toBeInTheDocument();
    expect(screen.getByText('القرار النهائيّ')).toBeInTheDocument();
    expect(screen.getByText(/غير مُعايَر/)).toBeInTheDocument();
  });

  it('قرار غير مُدام: يعرض «غير متاح» لا اختلاق', () => {
    stub({
      data: {
        decision_id: 'dec_x', decision_type: '—', found: false, source: 'lineage_derived',
        explanation: null, outcomes: [], evidence: null,
      } as DecisionExplainResult,
    });
    render(<DecisionStudioPage />, { wrapper });
    expect(screen.getByText(/شرح القرار غير متاح/)).toBeInTheDocument();
  });

  it('error: بعد إدخال معرّف وفشل الجلب ⇒ حالة خطأ صادقة', () => {
    stub({ isError: true, isSuccess: false, error: new Error('503') });
    render(<DecisionStudioPage />, { wrapper });
    // أدخِل معرّفاً وأرسِل النموذج كي يُثبَّت decisionId فتُعرَض حالة الخطأ.
    fireEvent.change(screen.getByPlaceholderText('dec_...'), { target: { value: 'dec_err' } });
    fireEvent.submit(screen.getByPlaceholderText('dec_...').closest('form')!);
    expect(screen.getByText(/تعذّر جلب شرح القرار/)).toBeInTheDocument();
  });
});
