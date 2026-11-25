import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const api = vi.hoisted(() => ({ calculateReservoirBoosterNetwork: vi.fn() }));
vi.mock('../services/api/irrigationNetworkCalculator', () => api);
vi.mock('../hooks/useAuth', () => ({ useTenantId: () => 'tenant-a' }));

import ReservoirBoosterNetworkCalculator from './ReservoirBoosterNetworkCalculator';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('reservoir balance forecast', () => {
  it('sends explicit losses, renders server forecast and clears it on field change', async () => {
    api.calculateReservoirBoosterNetwork.mockResolvedValue({
      status: 'pass', machine_mode: 'none', selected_machines: [],
      reservoir_balance: {
        net_change_m3_h: -12, forecast_end_volume_m3: 6070,
        forecast_excess_inflow_m3: 0, forecast_shortfall_to_minimum_m3: 0,
      },
      booster: { requested_energy_kwh: 450 }, blocking_constraints: [], warnings: [], content_digest: 'synthetic',
    });
    const { rerender } = render(<ReservoirBoosterNetworkCalculator fieldId="a" />);
    fireEvent.change(screen.getByLabelText(/فاقد التبخر/), { target: { value: '1' } });
    fireEvent.change(screen.getByLabelText(/فاقد التسرب/), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: 'احسب الشبكة' }));
    expect(api.calculateReservoirBoosterNetwork).toHaveBeenCalledWith(expect.objectContaining({
      tenantId: 'tenant-a', fieldId: 'a', reservoirEvaporationM3h: 1, reservoirSeepageM3h: 2,
    }));
    expect(await screen.findByText('6070.00 م³')).toBeInTheDocument();
    expect(screen.getByText('450.00 kWh')).toBeInTheDocument();
    rerender(<ReservoirBoosterNetworkCalculator fieldId="b" />);
    expect(screen.queryByText('450.00 kWh')).not.toBeInTheDocument();
    expect(screen.queryByText('6070.00 م³')).not.toBeInTheDocument();
  });
});
