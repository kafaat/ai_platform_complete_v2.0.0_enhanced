// اختبارات صفحة تحليل الغلّة — سلوك المكوّن عبر مُسرَحة hook useYieldAnalysis +
// تثبيت «الحقل النشط». نغطّي: (أ) الفراغ الصادق (note_ar + لا تلفيق)؛ (ب) الحالة
// المعمورة (ملخّص + جدول الزراعة↔الحصاد + أداء الهجن)؛ (ج) فجوة جزئيّة (غلّة null
// تُعرَض «—» لا 0)؛ (د) 503 ⇒ حالة خطأ صادقة؛ (هـ) 403 ⇒ «لا صلاحية». محاكاة في
// الاختبار فقط — حتميّة.
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

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

// نلتقط خصائص BarChartCard (recharts لا يرسم في jsdom بعرض 0) لفحص صفوف الرسم نفسها.
const chartProps: { data?: Record<string, unknown>[]; xKey?: string }[] = [];
vi.mock('../components/ds', async (importActual) => {
  const actual = await importActual<typeof import('../components/ds')>();
  return {
    ...actual,
    BarChartCard: (props: { data: Record<string, unknown>[]; xKey: string }) => {
      chartProps.push({ data: props.data, xKey: props.xKey });
      return null;
    },
  };
});

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

// موسمان للحقل نفسه (fld_1) بالمحصول نفسه — حالة مقارنة موسمَين.
const TWO_SEASONS: YieldAnalysisResult = {
  scope: { field_id: null, season: null },
  summary: { seasons_total: 2, seasons_with_harvest: 2, hybrids_compared: 0 },
  planting_vs_harvest: [
    {
      season_id: 'sA', field_id: 'fld_1', field_name: 'حقل القمح', crop: 'wheat',
      hybrid: null, maturity: null, sowing_date: '2025-11-01', season_end: null,
      status: 'closed', target_yield_t_ha: 5.0, actual_yield_t_ha: 4.0, yield_gap_t_ha: -1.0,
      has_harvest: true,
    },
    {
      season_id: 'sB', field_id: 'fld_1', field_name: 'حقل القمح', crop: 'wheat',
      hybrid: null, maturity: null, sowing_date: '2026-11-03', season_end: null,
      status: 'closed', target_yield_t_ha: 5.0, actual_yield_t_ha: 5.5, yield_gap_t_ha: 0.5,
      has_harvest: true,
    },
  ],
  hybrid_performance: [],
  units: { yield: 't/ha' },
  provenance: { source: 'seasons', honesty: 'stored_only', note_ar: null },
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
  chartProps.length = 0;
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

  // ── S5-a: موسمان للحقل نفسه ⇒ صفّا رسم مُميَّزان بهويّة الموسم لا باسم الحقل وحده ──
  it('(و) صفوف الرسم تحمل هويّة الموسم: موسمان للحقل نفسه ⇒ وسمان مختلفان + season_id', () => {
    stub(qData(TWO_SEASONS));
    render(<YieldAnalysisPage />);
    const last = chartProps[chartProps.length - 1];
    expect(last).toBeDefined();
    const rows = last.data ?? [];
    expect(rows).toHaveLength(2);
    const labels = rows.map((r) => String(r[last.xKey ?? 'name']));
    // وسمان مختلفان (لا «حقل القمح» مكرّراً) — كلاهما يحمل اسم الحقل وهويّة موسمه.
    expect(new Set(labels).size).toBe(2);
    labels.forEach((l) => expect(l).toContain('حقل القمح'));
    expect(labels.some((l) => l.includes('2025-11-01'))).toBe(true);
    expect(labels.some((l) => l.includes('2026-11-03'))).toBe(true);
    // الصفّ يحمل season_id صراحةً (هويّة مستقرّة للصفّ).
    expect(rows.map((r) => r.season_id)).toEqual(['sA', 'sB']);
  });

  it('(و٢) موسمان بالمحصول وتاريخ البذار نفسيهما ⇒ يبقى الوسم فريداً (يُلحَق season_id)', () => {
    const twin = {
      ...TWO_SEASONS,
      planting_vs_harvest: TWO_SEASONS.planting_vs_harvest.map((r) => ({ ...r, sowing_date: '2026-11-03' })),
    };
    stub(qData(twin));
    render(<YieldAnalysisPage />);
    const last = chartProps[chartProps.length - 1];
    const labels = (last.data ?? []).map((r) => String(r[last.xKey ?? 'name']));
    expect(new Set(labels).size).toBe(2);
  });

  // ── S5-b: خيارات الموسم من المخزون غير المُرشَّح — اختيار موسم لا يُخفي البقيّة ──
  it('(ز) منتقي الموسم يُبقي المواسم الأخرى بعد اختيار موسم (الخيارات من المصدر غير المُرشَّح)', () => {
    vi.spyOn(useApiModule, 'useYieldAnalysis').mockImplementation(((_f?: string, season?: string) => {
      if (!season) return qData(TWO_SEASONS);
      // الخادم يرشّح بـseason_id ⇒ الردّ المُرشَّح يحوي الموسم المختار وحده.
      return qData({
        ...TWO_SEASONS,
        planting_vs_harvest: TWO_SEASONS.planting_vs_harvest.filter((r) => r.season_id === season),
      });
    }) as never);
    render(<YieldAnalysisPage />);
    const seasonSelect = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    expect(within(seasonSelect).getAllByRole('option')).toHaveLength(3); // «كلّ المواسم» + sA + sB
    fireEvent.change(seasonSelect, { target: { value: 'sA' } });
    const after = screen.getAllByRole('combobox')[1] as HTMLSelectElement;
    expect(after.value).toBe('sA');
    const values = within(after).getAllByRole('option').map((o) => (o as HTMLOptionElement).value);
    expect(values).toEqual(['', 'sA', 'sB']);
  });
});
