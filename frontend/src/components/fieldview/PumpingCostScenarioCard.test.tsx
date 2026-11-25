import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PumpingCostScenarioCard from './PumpingCostScenarioCard';

const mocks = vi.hoisted(() => ({ post: vi.fn(), scope: vi.fn() }));
vi.mock('../../services/api/client', () => ({ kongApi: { post: mocks.post } }));
vi.mock('../../lib/authStorage', () => ({ getAuthScope: mocks.scope }));

function fillGrid() {
  const fields = [
    ['مرجع التقدير', 'fixture:pivot-a'],
    ['الغلة المتوقعة (طن/هكتار)', '4'],
    ['سعر الطن المتوقع (عملة تقديرك)', '300'],
    ['حجم الضخ الموسمي (م³/هكتار)', '3000'],
    ['عمق البئر المستخدم في التقدير (م)', '100'],
    ['سعر الكهرباء (USD/kWh)', '0.2'],
    ['كفاءة الضخ (0–1)', '0.8'],
  ];
  for (const [label, value] of fields) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  fireEvent.change(screen.getByLabelText('نوع المدخلات'), { target: { value: 'synthetic' } });
}

const response = { data: { water_cost_scenario: {
  status: 'estimated', currency: 'USD', scope: 'well_pumping_only', included_in_feasibility: false,
  estimate: { total_m3: 150000, cost_low_usd: 9195, cost_mid_usd: 10215, cost_high_usd: 12255 },
} } };

describe('pumping cost scenario', () => {
  beforeEach(() => {
    mocks.post.mockReset();
    mocks.scope.mockReset().mockReturnValue('tenant-a:user-a');
  });

  it('requires explicit values and displays a separate server estimate', async () => {
    mocks.post.mockResolvedValue(response);
    render(<PumpingCostScenarioCard areaHa={50} authScope="tenant-a:user-a" />);
    fireEvent.click(screen.getByText('احسب تكلفة الضخ'));
    expect(mocks.post).not.toHaveBeenCalled();
    fillGrid();
    fireEvent.click(screen.getByText('احسب تكلفة الضخ'));
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('10215'));
    expect(mocks.post).toHaveBeenCalledWith('/api/v1/economics/feasibility', {
      area_ha: 50, yield_t_per_ha: 4, price_per_t: 300,
      water_cost_scenario: {
        pumped_m3_per_ha: 3000, well_depth_m: 100, pump_type: 'grid',
        grid_price_usd_per_kwh: 0.2, grid_efficiency: 0.8, input_basis: 'synthetic',
        source_ref: 'fixture:pivot-a',
      },
    }, { expectedAuthScope: 'tenant-a:user-a' });
    fireEvent.change(screen.getByLabelText('مصدر الطاقة'), { target: { value: 'solar' } });
    expect(screen.queryByRole('status')).toBeNull();
    expect(screen.queryByLabelText('سعر الكهرباء (USD/kWh)')).toBeNull();
  });

  it('does not submit after the authenticated scope changes', () => {
    render(<PumpingCostScenarioCard areaHa={50} authScope="tenant-a:user-a" />);
    fillGrid();
    mocks.scope.mockReturnValue('tenant-b:user-b');
    fireEvent.click(screen.getByText('احسب تكلفة الضخ'));
    expect(mocks.post).not.toHaveBeenCalled();
  });

  it('does not display a response that arrives after an input edit', async () => {
    let complete!: (value: typeof response) => void;
    mocks.post.mockReturnValue(new Promise(resolve => { complete = resolve; }));
    render(<PumpingCostScenarioCard areaHa={50} authScope="tenant-a:user-a" />);
    fillGrid();
    fireEvent.click(screen.getByText('احسب تكلفة الضخ'));
    fireEvent.change(screen.getByLabelText('مرجع التقدير'), { target: { value: 'fixture:pivot-b' } });
    complete(response);
    await waitFor(() => expect(screen.getByText('احسب تكلفة الضخ')).toBeTruthy());
    expect(screen.queryByRole('status')).toBeNull();
  });
});
