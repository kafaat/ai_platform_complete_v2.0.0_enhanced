// F-U01: the mounted indicators screen (page id `hybrid-index`) shows the stored sim_* values of
// each field's season, and must also be where a permitted user can run the simulation that fills
// them. Runs the real hooks against a mocked network layer.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const api = vi.hoisted(() => ({ fetchSeasons: vi.fn(), simulateSeason: vi.fn() }));
vi.mock('@/services/api', async (orig) => {
  const real = await orig<typeof import('@/services/api')>();
  return { ...real, ...api };
});
vi.mock('@/hooks/useIndicators', () => ({
  useDashboardKPIs: () => ({
    data: { kpis: [], alerts: [], fields_summary: [{ field_id: 'fld_1', field_name: 'حقل القمح', crop: 'قمح' }] },
    isLoading: false, error: null, refetch: vi.fn(),
  }),
}));
vi.mock('recharts', () => {
  const Null = () => null;
  return {
    BarChart: Null, Bar: Null, XAxis: Null, YAxis: Null, CartesianGrid: Null,
    Tooltip: Null, ResponsiveContainer: Null, Cell: Null,
  };
});

import { useAuthStore } from '@/hooks/useAuth';
import { HybridIndexPage } from './HybridIndexPage';

const SEASON = {
  season_id: 'ssn_1', field_id: 'fld_1', crops: ['قمح'], cultivar: 'بحوث 13',
  irrigation_type: 'drip', seed_rate_kg_ha: null, land_leveling_date: null, plowing_date: null,
  sowing_date: '2026-10-10', season_end: null, stages: [], status: 'active', created_at: null,
  target_yield_kg_ha: null, plant_density: null, row_spacing_cm: null, seed_variety_source: null,
  maturity: null, tillage_type: null, actual_yield_kg_ha: null, notes_ar: null,
  sim_yield_kg_ha: null, sim_biomass_kg_ha: null, sim_gdd_total: null, sim_lai_max: null,
  sim_water_mm: null, sim_ran_at: null,
};
const RESULT = {
  season_id: 'ssn_1', crop: 'wheat', crop_recognized: true, days_simulated: 40,
  gdd_total: 612, gdd_to_maturity: 2100, maturity_reached: false, lai_max: 1.8,
  biomass_kg_ha: 2100, yield_kg_ha: 3000, yield_low_kg_ha: 2400, yield_high_kg_ha: 3600,
  yield_status: 'estimated', limitations: ['SIM_WINDOW_TRUNCATED'], water_need_mm: 180,
  water_supply_mm: null, water_stress_factor: null, confidence: 0.4,
  rationale_ar: 'نصّ الخادم', assumptions_ar: ['افتراض من الخادم'], warnings_ar: ['تحذير من الخادم'],
  sim_ran_at: '2026-11-22T10:00:00Z',
  estimate_disclaimer_ar: 'تنبيه التقدير كما عاد من الخادم',
  simulation_engine: 'rue-fao56', canonical_yield_engine: 'pcse_wofost',
  truncated: true, window_days_requested: 400, window_days_simulated: 40,
  manual_irrigation_used: false, observed_fapar_used: false, geometry_basis: 'current_boundary',
};

function renderPage(role: string) {
  useAuthStore.setState({ user: { role } as never, tenantId: 't1' });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><HybridIndexPage /></QueryClientProvider>);
}
const runButton = () => screen.findByRole('button', { name: /تشغيل المحاكاة/ });
const queryRunButton = () => screen.queryByRole('button', { name: /تشغيل المحاكاة/ });

afterEach(() => { cleanup(); vi.clearAllMocks(); useAuthStore.setState({ user: null, tenantId: null }); });

describe('HybridIndexPage offers the season simulation run (F-U01)', () => {
  it('lets a manager open the run for the season in the row and states inputs and limits first', async () => {
    api.fetchSeasons.mockResolvedValue([SEASON]);
    renderPage('manager');
    fireEvent.click(await runButton());

    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('2026-10-10')).toBeInTheDocument();
    expect(within(dialog).getByText(/بحوث 13/)).toBeInTheDocument();
    expect(within(dialog).getByText(/ليست توصية/)).toBeInTheDocument();
    expect(within(dialog).getByText(/يُحفَظ الناتج على الموسم/)).toBeInTheDocument();
    expect(within(dialog).getByText('نهاية الموسم').nextSibling).toHaveTextContent('غير مسجَّلة');
    expect(api.simulateSeason).not.toHaveBeenCalled();
  });

  it('posts the run for that season, shows what the server returned and refetches the seasons', async () => {
    api.fetchSeasons.mockResolvedValue([SEASON]);
    api.simulateSeason.mockResolvedValue(RESULT);
    renderPage('owner');
    fireEvent.click(await runButton());
    const dialog = screen.getByRole('dialog');
    expect(api.fetchSeasons).toHaveBeenCalledTimes(1);

    fireEvent.click(within(dialog).getByRole('button', { name: 'تشغيل المحاكاة' }));

    await within(dialog).findByText('تنبيه التقدير كما عاد من الخادم');
    expect(api.simulateSeason).toHaveBeenCalledTimes(1);
    expect(api.simulateSeason.mock.calls[0][0]).toBe('ssn_1');
    expect(within(dialog).getByText('تحذير من الخادم')).toBeInTheDocument();
    expect(within(dialog).getByText(/SIM_WINDOW_TRUNCATED/)).toBeInTheDocument();
    expect(within(dialog).getByText(/40 من 400 مطلوبة \(النافذة قُصَّت\)/)).toBeInTheDocument();
    expect(within(dialog).getByText(/rue-fao56/)).toBeInTheDocument();
    await waitFor(() => expect(api.fetchSeasons).toHaveBeenCalledTimes(2));
    expect(api.fetchSeasons).toHaveBeenLastCalledWith('fld_1');
  });

  it('labels the adequate-irrigation what-if as a scenario when irrigation is unrecorded', async () => {
    api.fetchSeasons.mockResolvedValue([SEASON]);
    api.simulateSeason.mockResolvedValue({
      ...RESULT, yield_kg_ha: null, yield_low_kg_ha: null, yield_high_kg_ha: null,
      yield_status: 'unavailable_unknown_irrigation', limitations: ['IRRIGATION_SUPPLY_UNKNOWN'],
      confidence: 0, scenario_yield_kg_ha: 3000, scenario_basis: 'adequate_irrigation_assumed',
      rationale_ar: 'محاكاة 40 يوم: الإنتاج غير متاح (unavailable_unknown_irrigation). الثقة غير متاحة — تقدير نموذجي.',
    });
    renderPage('owner');
    fireEvent.click(await runButton());
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'تشغيل المحاكاة' }));

    await within(dialog).findByText(/سيناريو «لو كان الريّ كافياً»/);
    expect(within(dialog).getByText(/ليس تقديراً للموسم/)).toBeInTheDocument();
    expect(within(dialog).getByText('الإنتاج المُقدَّر (kg/ha)').parentElement).toHaveTextContent('غير متاح');
    // The stats line and the server rationale both state confidence; neither may say 0.
    expect(within(dialog).getByText(/الكتلة الحيويّة/)).toHaveTextContent('الثقة غير متاحة');
    expect(within(dialog).getByText(/محاكاة 40 يوم/)).toHaveTextContent('الثقة غير متاحة');
    // Both percent signs: a server rationale with a Latin "%" must not slip past the check.
    expect(within(dialog).queryByText(/الثقة\s*0\s*[٪%]/)).toBeNull();
  });

  it.each(['agronomist', 'worker', 'viewer', undefined])(
    'offers no run to role %s (the server grants field:edit to owner and manager only)',
    async (role) => {
      api.fetchSeasons.mockResolvedValue([SEASON]);
      renderPage(role as string);
      await screen.findByText('لم تُحاكَ بعد');
      expect(queryRunButton()).toBeNull();
      expect(api.simulateSeason).not.toHaveBeenCalled();
    },
  );

  it('offers no run for a field without a season', async () => {
    api.fetchSeasons.mockResolvedValue([]);
    renderPage('owner');
    await screen.findByText('لا موسم مُسجَّل');
    expect(queryRunButton()).toBeNull();
  });

  it.each([
    ['a text detail', { response: { status: 422, data: { detail: 'الموسم متعدد المحاصيل — رفض الخادم' } } }, /الموسم متعدد المحاصيل — رفض الخادم/],
    ['an object detail', { response: { status: 503, data: { detail: { message_ar: 'القاعدة غير متاحة' } } } }, /القاعدة غير متاحة/],
    ['a 403', { response: { status: 403, data: { detail: 'Permission denied: field:edit' } } }, /Permission denied: field:edit/],
  ])('shows a server refusal with %s as it came and no results', async (_n, error, text) => {
    api.fetchSeasons.mockResolvedValue([SEASON]);
    api.simulateSeason.mockRejectedValue(error);
    renderPage('manager');
    fireEvent.click(await runButton());
    const dialog = screen.getByRole('dialog');
    fireEvent.click(within(dialog).getByRole('button', { name: 'تشغيل المحاكاة' }));

    const alert = await within(dialog).findByRole('alert');
    expect(alert).toHaveTextContent(text);
    expect(alert).toHaveTextContent(/لا نتيجة تُعرَض/);
    expect(within(dialog).queryByText(/الإنتاج المُقدَّر/)).toBeNull();
    expect(within(dialog).getByRole('button', { name: 'تشغيل المحاكاة' })).toBeEnabled();
  });
});
