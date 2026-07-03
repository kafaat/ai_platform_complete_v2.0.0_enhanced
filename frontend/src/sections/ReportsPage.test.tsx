// اختبارات ملخّصات التقارير طراز FieldView (زراعة/حصاد/عمليّات) — نُسرِح
// useQueries (المواسم/العمليّات لكلّ حقل) + useSelectedField، ونتحقّق من:
//   (أ) الفراغ الصادق لكلّ ملخّص (لا تلفيق)؛ (ب) الحالة المعمورة (صفوف/أرقام)؛
//   (ج) الغلّة غير المُسجَّلة تُعرَض «—» لا 0؛ (د) خطأ الحقول ⇒ حالة خطأ صادقة.
// محاكاة في الاختبار فقط — حتميّة بلا شبكة/QueryClient.
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import type { SeasonSummary, Activity } from '../services/api';

beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
});

// ── تثبيت متجر المصادقة (المستأجِر) ودوال الجلب (لا شبكة) ──
vi.mock('../hooks/useAuth', () => ({
  useAuthStore: (sel: (s: { tenantId: string }) => unknown) => sel({ tenantId: 'demo' }),
}));
vi.mock('../services/api', async (orig) => {
  const real = await orig<typeof import('../services/api')>();
  return { ...real, fetchSeasons: vi.fn(), fetchActivities: vi.fn() };
});

// ── تثبيت hooks التقارير الأخرى (تبويبات غير مُختبَرة هنا) ──
vi.mock('../hooks/useApi', () => ({
  useFields: () => ({ data: { fields: [] }, isLoading: false, isError: false, refetch: vi.fn() }),
  useFarmSummary: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
  useFieldReport: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
  useCostAnalytics: () => ({ data: undefined, isLoading: false, isError: false, refetch: vi.fn() }),
}));

// ── تثبيت useSelectedField + useQueries (قابل للضبط لكلّ اختبار) ──
const fieldState = {
  options: [{ id: 'fld_1', name: 'حقل القمح', area: 12.5, crop: 'wheat', lat: null, lon: null, geometry: null }],
  isLoading: false,
  isError: false,
  error: undefined as unknown,
  refetch: vi.fn(),
};
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({ ...fieldState, fieldId: fieldState.options[0]?.id ?? '', field: fieldState.options[0], setFieldId: vi.fn() }),
}));

// useQueries يُستدعى مرّتين لكلّ تصيير (المواسم أوّلاً ثمّ العمليّات). نُميّز
// النداءين بمحتوى queries.queryKey[0] ('seasons' | 'activities') لا بترتيب طابور
// (التصيير قد يتكرّر) — حتميّ ومستقرّ عبر إعادات التصيير.
let seasonsResult: { data: unknown; isLoading: boolean; isError: boolean }[] = [];
let activitiesResult: { data: unknown; isLoading: boolean; isError: boolean }[] = [];
vi.mock('@tanstack/react-query', () => ({
  useQueries: ({ queries }: { queries: { queryKey: unknown[] }[] }) => {
    const kind = (queries[0]?.queryKey?.[0] as string) ?? '';
    return kind === 'activities' ? activitiesResult : seasonsResult;
  },
}));

import { ReportsPage } from './ReportsPage';

const SEASON_FULL: SeasonSummary = {
  season_id: 's1', field_id: 'fld_1', crops: ['wheat'], cultivar: 'Pioneer-X',
  irrigation_type: null, seed_rate_kg_ha: null, land_leveling_date: null, plowing_date: null,
  sowing_date: '2026-01-15', season_end: null, stages: [], status: 'active', created_at: null,
  target_yield_kg_ha: 5000, plant_density: null, row_spacing_cm: null, seed_variety_source: null,
  maturity: null, tillage_type: null, actual_yield_kg_ha: 4200, notes_ar: null,
  sim_yield_kg_ha: null, sim_biomass_kg_ha: null, sim_gdd_total: null, sim_lai_max: null,
  sim_water_mm: null, sim_ran_at: null,
};
// موسم بلا حصاد مُسجَّل (actual = null) ⇒ يجب أن يُعرَض «—».
const SEASON_NO_HARVEST: SeasonSummary = { ...SEASON_FULL, season_id: 's2', actual_yield_kg_ha: null };

const ACT: Activity = {
  activity_id: 'a1', field_id: 'fld_1', season_id: 's1', activity_type: 'spraying',
  title_ar: 'رشّ', details: {}, scheduled_for: null, performed_on: '2026-02-01',
  status: 'done', created_at: null,
};

// يضبط نتيجتي useQueries (مواسم/عمليّات) — استعلام واحد لكلّ (حقل واحد مُثبَّت).
function setQueries(seasons: SeasonSummary[], activities: Activity[]) {
  seasonsResult = [{ data: seasons, isLoading: false, isError: false }];
  activitiesResult = [{ data: activities, isLoading: false, isError: false }];
}

beforeEach(() => {
  vi.clearAllMocks();
  fieldState.isError = false;
  seasonsResult = [];
  activitiesResult = [];
});

describe('ReportsPage — ملخّصات FieldView', () => {
  it('(أ) ملخّص الزراعة: الفراغ الصادق حين لا مواسم', () => {
    setQueries([], []);
    render(<ReportsPage />);
    expect(screen.getByText('لا مواسم مُسجَّلة بعد')).toBeInTheDocument();
  });

  it('(ب) ملخّص الزراعة: يعرض صفّ الموسم (محصول/صنف/تاريخ بذار/مساحة)', () => {
    setQueries([SEASON_FULL], []);
    render(<ReportsPage />);
    expect(screen.getAllByText('حقل القمح').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Pioneer-X')).toBeInTheDocument();
    expect(screen.getByText('2026-01-15')).toBeInTheDocument();
    expect(screen.getByText('12.5')).toBeInTheDocument();
  });

  it('(ج) ملخّص الحصاد: الفعليّة 4.20 ومستهدفة 5.00 وفجوة سالبة', () => {
    setQueries([SEASON_FULL], []);
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('ملخّص الحصاد'));
    expect(screen.getByText('4.20')).toBeInTheDocument();
    expect(screen.getByText('5.00')).toBeInTheDocument();
    expect(screen.getByText('-0.80')).toBeInTheDocument();
  });

  it('(د) ملخّص الحصاد: غلّة غير مُسجَّلة تُعرَض «—» لا 0', () => {
    setQueries([SEASON_NO_HARVEST], []);
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('ملخّص الحصاد'));
    // لا توجد قيمة فعليّة ⇒ «—» موجودة، و«0.00» ليست معروضة كغلّة مُلفَّقة.
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('0.00')).not.toBeInTheDocument();
  });

  it('(هـ) ملخّص العمليّات: يعرض الإجماليّ والنوع', () => {
    setQueries([], [ACT]);
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('ملخّص العمليّات'));
    expect(screen.getByText('إجماليّ العمليّات')).toBeInTheDocument();
    // الإجماليّ = 1 (عمليّة واحدة) معروض في بطاقة KPI.
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1);
  });

  it('(و) ملخّص العمليّات: الفراغ الصادق حين لا عمليّات', () => {
    setQueries([], []);
    render(<ReportsPage />);
    fireEvent.click(screen.getByText('ملخّص العمليّات'));
    expect(screen.getByText('لا عمليّات مُسجَّلة بعد')).toBeInTheDocument();
  });

  it('(ز) خطأ الحقول ⇒ حالة خطأ صادقة في ملخّص الزراعة', () => {
    fieldState.isError = true;
    setQueries([], []);
    render(<ReportsPage />);
    expect(screen.getByText('تعذّر تحميل ملخّص الزراعة')).toBeInTheDocument();
  });
});
