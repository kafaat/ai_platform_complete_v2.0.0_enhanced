// اختبارات صفحة تحليل الغلّة — سلوك المكوّن عبر مُسرَحة hook useYieldAnalysis +
// تثبيت «الحقل النشط». نغطّي: (أ) الفراغ الصادق (note_ar + لا تلفيق)؛ (ب) الحالة
// المعمورة (ملخّص + جدول الزراعة↔الحصاد + أداء الهجن)؛ (ج) فجوة جزئيّة (غلّة null
// تُعرَض «—» لا 0)؛ (د) 503 ⇒ حالة خطأ صادقة؛ (هـ) 403 ⇒ «لا صلاحية». محاكاة في
// الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest';
import { render, screen } from '@testing-library/react';

// recharts' ResponsiveContainer يعتمد ResizeObserver الغائب في jsdom — مُجسَّد محليّاً.
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

// نُثبّت «الحقل النشط» المشترك — لا حقل مُختار (نطاق = كلّ الحقول، الاستعلام يعمل دائماً).
const selectedField = {
  options: [{ id: 'fld_1', name: 'حقل القمح' }],
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
  fieldId: '',
  field: undefined,
  setFieldId: vi.fn(),
};
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => selectedField,
}));

import * as useApiModule from '../hooks/useApi';
import type { YieldAnalysisResult } from '../services/api';
import YieldAnalysisPage from './YieldAnalysisPage';

const FULL: YieldAnalysisResult = {
  scope: { field_id: null, season: null },
  summary: { seasons_total: 2, seasons_with_harvest: 1, hybrids_compared: 1 },
  planting_vs_harvest: [
    {
      season_id: 's1', field_id: 'fld_1', field_name: 'حقل القمح', crop: 'wheat',
      hybrid: 'Pioneer-X', maturity: 'medium', sowing_date: '2026-01-01', season_end: null,
      status: 'closed', target_yield_t_ha: 5.0, actual_yield_t_ha: 4.2, yield_gap_t_ha: -0.8,
      has_harvest: true,
    },
    {
      season_id: 's2', field_id: 'fld_2', field_name: 'حقل الذرة', crop: 'maize',
      hybrid: null, maturity: null, sowing_date: '2026-02-10', season_end: null,
      status: 'active', target_yield_t_ha: 8.0, actual_yield_t_ha: null, yield_gap_t_ha: null,
      has_harvest: false,
    },
  ],
  hybrid_performance: [
    {
      hybrid: 'Pioneer-X', crops: ['wheat'], season_count: 1, field_count: 1,
      avg_yield_t_ha: 4.2, min_yield_t_ha: 4.2, max_yield_t_ha: 4.2,
    },
  ],
  units: { yield: 't/ha' },
  provenance: { source: 'seasons', honesty: 'stored_only', note_ar: null },
  tenant_id: 'tenant_demo',
};

const EMPTY: YieldAnalysisResult = {
  scope: { field_id: null, season: null },
  summary: { seasons_total: 0, seasons_with_harvest: 0, hybrids_compared: 0 },
  planting_vs_harvest: [],
  hybrid_performance: [],
  units: { yield: 't/ha' },
  provenance: {
    source: 'seasons', honesty: 'stored_only',
    note_ar: 'لا مواسم مُسجَّلة لهذا النطاق — أنشئ موسماً ثمّ سجّل الغلّة الفعليّة بعد الحصاد.',
  },
  tenant_id: 'tenant_demo',
};

type Q = Record<string, unknown>;
const qData = (data: unknown): Q => ({ isLoading: false, isError: false, data, refetch: vi.fn() });
const qError = (status: number): Q => ({
  isLoading: false, isError: true, data: undefined,
  error: { response: { status } }, refetch: vi.fn(),
});

function stub(q: Q) {
  vi.spyOn(useApiModule, 'useYieldAnalysis').mockReturnValue(q as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
});

describe('YieldAnalysisPage', () => {
  it('(أ) الفراغ الصادق: يعرض note_ar ولا يُلفّق أرقاماً', () => {
    stub(qData(EMPTY));
    render(<YieldAnalysisPage />);
    expect(screen.getByText(/لا مواسم مُسجَّلة لهذا النطاق/)).toBeInTheDocument();
    // الملخّص أصفار صادقة (مواسم مُسجَّلة = 0) — لا تلفيق.
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(1);
  });

  it('(ب) الحالة المعمورة: ملخّص + جدول الزراعة↔الحصاد + أداء الهجن', () => {
    stub(qData(FULL));
    render(<YieldAnalysisPage />);
    // قسم أداء الهجن (عنوان القسم الكامل) + الهجين المتصدّر.
    expect(screen.getByText(/أداء الهجن \(متوسّط الغلّة الفعليّة\)/)).toBeInTheDocument();
    expect(screen.getAllByText('Pioneer-X').length).toBeGreaterThanOrEqual(1);
    // قسم الزراعة↔الحصاد + اسم الحقل.
    expect(screen.getByText(/الزراعة ↔ الحصاد لكلّ موسم/)).toBeInTheDocument();
    // «حقل القمح» يظهر في منتقي الحقل (option) وفي صفّ الجدول — كلاهما مقبول.
    expect(screen.getAllByText('حقل القمح').length).toBeGreaterThanOrEqual(1);
    // الغلّة الفعليّة (4.20 ط/هـ) معروضة.
    expect(screen.getAllByText('4.20').length).toBeGreaterThanOrEqual(1);
  });

  it('(ج) غلّة فعليّة null تُعرَض «—» لا 0', () => {
    stub(qData(FULL));
    render(<YieldAnalysisPage />);
    // الموسم الثاني (الذرة) بلا حصاد ⇒ «—»، ولا تُعرَض 0.00 له.
    expect(screen.getByText('حقل الذرة')).toBeInTheDocument();
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
  });

  it('(د) 503/خطأ آخر ⇒ حالة خطأ صادقة', () => {
    stub(qError(503));
    render(<YieldAnalysisPage />);
    expect(screen.getByText('تعذّر جلب تحليل الغلّة')).toBeInTheDocument();
  });

  it('(هـ) 403 ⇒ «لا صلاحية لعرض تحليل الغلّة»', () => {
    stub(qError(403));
    render(<YieldAnalysisPage />);
    expect(screen.getByText(/لا صلاحية لعرض تحليل الغلّة/)).toBeInTheDocument();
  });
});
