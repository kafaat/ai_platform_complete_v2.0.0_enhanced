import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAuthStore } from '../hooks/useAuth';
import { FAB } from '../components/ds/atoms';
import { DsThemeProvider } from '../components/ds/theme';
import FieldRanking from './FieldRanking';
import PhenologyView from './PhenologyView';
import FarmAdvisoryReport from './FarmAdvisoryReport';
import EconomicsDashboard from './EconomicsDashboard';
import MasterDataPage from './MasterDataPage';
import TasksPage from './TasksPage';

const state = vi.hoisted(() => ({
  fieldsError: true,
  refetch: vi.fn(),
  seasons: [] as unknown[],
}));
const query = (data?: unknown) => ({ data, isLoading: false, isError: false, refetch: state.refetch });
vi.mock('../hooks/useApi', () => ({
  SOIL_ENABLED: false,
  useAllFieldsNdvi: () => ({ ...query(), isError: true }),
  useSeasons: () => query(state.seasons),
  useSoilParams: () => query(),
  useSoilNRecommendation: () => query(),
  useDiseaseRisk: () => query(),
  useCurrentNDVI: () => query(),
  useFieldReport: () => query(),
  useFarmSummary: () => query(),
  useCostAnalytics: () => query({ total_usd: 35, task_count: 1, by_source: [] }),
  useMasterData: () => query([{ md_id: 'm1', code: 'WHEAT', category: 'crop', name_ar: 'قمح' }]),
  useTasks: () => query({ tasks: [{ task_id: 't1', status: 'pending', task_type: 'scouting', estimated_cost_usd: 30 }] }),
  useCompleteTask: () => ({ mutate: vi.fn() }),
}));
vi.mock('../hooks/useScouting', () => ({ useCropScoutingIssues: () => query([]) }));
vi.mock('../hooks/useSelectedField', () => ({
  useSelectedField: () => ({
    options: [{ id: 'f1', name: 'حقل القمح', crop: 'wheat', area: 1 }],
    fieldId: state.fieldsError ? '' : 'f1', setFieldId: vi.fn(),
    isLoading: false, isError: state.fieldsError, refetch: state.refetch,
  }),
}));

function luminance(color: string) {
  const rgb = color.match(/[\d.]+/g)?.slice(0, 3).map(Number);
  if (!rgb || rgb.length !== 3) throw new Error(`Expected computed RGB color, got ${color}`);
  const linear = rgb.map(channel => {
    const value = channel / 255;
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
  });
  return linear[0] * 0.2126 + linear[1] * 0.7152 + linear[2] * 0.0722;
}

function expectReadable(element: HTMLElement) {
  let surface: HTMLElement | null = element;
  while (surface) {
    const background = getComputedStyle(surface).backgroundColor;
    if (background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)') {
      const foregroundL = luminance(getComputedStyle(element).color);
      const backgroundL = luminance(background);
      const ratio = (Math.max(foregroundL, backgroundL) + 0.05) / (Math.min(foregroundL, backgroundL) + 0.05);
      expect(ratio, element.textContent ?? '').toBeGreaterThanOrEqual(4.5);
      return;
    }
    surface = surface.parentElement;
  }
  throw new Error(`No painted background found for ${element.textContent}`);
}

beforeEach(() => {
  vi.clearAllMocks();
  state.fieldsError = true;
  state.seasons = [];
  useAuthStore.setState({ tenantId: 'test', user: { role: 'viewer', email: 'viewer@example.test' } });
});

describe('reviewed contrast pairs on their actual surfaces', () => {
  it.each(['light', 'dark'] as const)('keeps the preserved gold FAB readable and working in a %s cabin', tone => {
    const onClick = vi.fn();
    render(<DsThemeProvider tone={tone}><FAB icon={<span>+</span>} label="إضافة حقل" onClick={onClick} /></DsThemeProvider>);
    const button = screen.getByRole('button', { name: 'إضافة حقل' });
    expectReadable(button);
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledOnce();
  });

  it.each([
    ['ranking', FieldRanking], ['phenology', PhenologyView], ['advisory', FarmAdvisoryReport],
  ] as const)('keeps the %s gold retry button readable and working', (_name, Page) => {
    render(<Page />);
    const retry = screen.getByRole('button', { name: 'إعادة المحاولة' });
    expectReadable(retry);
    fireEvent.click(retry);
    expect(state.refetch).toHaveBeenCalledOnce();
  });

  it('keeps estimates and the active all-tasks filter readable on light surfaces', () => {
    render(<TasksPage />);
    expectReadable(screen.getByText('التقدير: $30'));
    expectReadable(screen.getByRole('button', { name: /الكل/ }));
  });

  it('keeps master-data codes readable on the table surface', () => {
    render(<MasterDataPage />);
    screen.getAllByText('WHEAT').forEach(expectReadable);
  });

  it('keeps the biomass figure readable inside its explicitly dark cabin', () => {
    state.fieldsError = false;
    state.seasons = [{ status: 'active', crops: ['wheat'], sim_biomass_kg_ha: 1234, stages: [] }];
    render(<FarmAdvisoryReport />);
    expectReadable(screen.getByText('1234'));
  });

  it('keeps total costs readable inside their explicitly dark cabin', () => {
    render(<EconomicsDashboard />);
    const stat = screen.getByText('إجماليّ التكلفة').parentElement!;
    expectReadable([...stat.children].find(child => child.textContent === '$35.00') as HTMLElement);
  });
});
