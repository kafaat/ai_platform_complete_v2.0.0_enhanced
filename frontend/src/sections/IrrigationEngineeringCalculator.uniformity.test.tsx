import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';

const api = vi.hoisted(() => ({ calculateInteractiveIrrigation: vi.fn() }));
vi.mock('../services/api/irrigationEngineeringCalculator', () => api);
vi.mock('../hooks/useAuth', () => ({ useTenantId: () => 'tenant-a' }));

import IrrigationEngineeringCalculator from './IrrigationEngineeringCalculator';

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('interactive irrigation survey', () => {
  it('submits the optional evidence and displays only the server result, clearing it on field change', async () => {
    api.calculateInteractiveIrrigation.mockResolvedValue({
      status: 'pass', calculations: {}, water_demand: {}, pump_energy: {}, feasibility: {},
      warnings: [], blocking_constraints: [], explanations: [], assumptions: [], input_quality: {},
      content_digest: 'abc123',
      hydraulics: { uniformity: {
        method: 'area_weighted_cu_du_lq.v1', evidence_ref: 'synthetic:pivot-a', sample_count: 4,
        input_quality: 'operator_supplied_unverified', status: 'calculated', compliance_status: 'not_evaluated',
        mean_depth_mm: 10, cu_pct: 60, du_low_quarter_pct: 40, reason: null,
      } },
    });
    const { rerender } = render(<IrrigationEngineeringCalculator fieldId="a" />);
    fireEvent.change(screen.getByLabelText('مرجع دليل القياس'), { target: { value: 'synthetic:pivot-a' } });
    fireEvent.change(screen.getByLabelText('عينات القياس (المعرّف، العمق، المساحة)'), {
      target: { value: 'a,4,125000\nb,8,125000\nc,12,125000\nd,16,125000' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'احسب الكمية والضغط' }));
    expect(api.calculateInteractiveIrrigation).toHaveBeenCalledWith(expect.objectContaining({
      tenantId: 'tenant-a', fieldId: 'a',
      uniformitySurvey: { evidence_ref: 'synthetic:pivot-a', samples: [4, 8, 12, 16].map((depth_mm, i) => ({
        sample_id: 'abcd'[i], depth_mm, represented_area_m2: 125000,
      })) },
    }));
    expect(await screen.findByText('60.00 %')).toBeInTheDocument();
    expect(screen.getByText('40.00 %')).toBeInTheDocument();
    rerender(<IrrigationEngineeringCalculator fieldId="b" />);
    expect(screen.queryByText('60.00 %')).not.toBeInTheDocument();
    expect(screen.getByLabelText('مرجع دليل القياس')).toHaveValue('');
  });
});
