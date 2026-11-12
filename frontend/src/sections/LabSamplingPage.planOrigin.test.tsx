import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
const state = vi.hoisted(() => ({ save: vi.fn(), navigate: vi.fn() }));
const origin = { point_id: 'ss-1-1', zone_id: 'A', longitude: 44.2, latitude: 16.1, indicators: ['ndvi'] };
vi.mock('../hooks/useSelectedField', () => ({ useSelectedField: () => ({ fieldId: 'a', options: [{ id: 'a', name: 'A' }], setFieldId: vi.fn() }) }));
vi.mock('../hooks/useApi', () => ({
  useLabSamples: () => ({ data: [], isLoading: false, isError: false, refetch: vi.fn() }),
  useLabDecisionContext: () => ({ isLoading: false, isError: false, data: undefined, refetch: vi.fn() }),
  useCreateLabSample: () => ({ mutateAsync: state.save, isPending: false }),
  useSubmitSoilLabResult: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('react-router', () => ({
  useLocation: () => ({ state: { fieldId: 'a', planId: 'ssp-1', origin, depth: [0, 30] } }),
  useNavigate: () => state.navigate,
}));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('react-leaflet', () => ({ MapContainer: ({ children }: any) => <div>{children}</div>, TileLayer: () => null, Polygon: () => null, Marker: () => null, useMapEvents: () => ({}) }));
import LabSamplingPage from './LabSamplingPage';
beforeEach(() => { cleanup(); vi.clearAllMocks(); state.save.mockResolvedValue({}); });

async function saveSample() {
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Latitude' }), { target: { value: '16.10001' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Longitude' }), { target: { value: '44.2' } });
  const form = screen.getByRole('spinbutton', { name: 'Latitude' }).closest('form')!;
  await act(async () => {
    form.requestSubmit();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

describe('plan point origin', () => {
  it('tags only the first sample saved from a plan point', async () => {
    render(<LabSamplingPage />);
    await saveSample();
    await waitFor(() => expect(state.save).toHaveBeenCalledTimes(1));
    expect(state.save.mock.calls[0][0]).toMatchObject({ sampling_plan_id: 'ssp-1', sampling_origin: origin, depth_cm_from: 0, depth_cm_to: 30 });
    await waitFor(() => expect(state.navigate).toHaveBeenCalledWith('.', { replace: true, state: { fieldId: 'a' } }));
    await waitFor(() => expect(screen.queryByText(/نقطة الخطة ss-1-1/)).toBeNull());
    fireEvent.change(screen.getByRole('spinbutton', { name: /إلى عمق/ }), { target: { value: '30' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: /من عمق/ }), { target: { value: '0' } });
    await saveSample();
    await waitFor(() => expect(screen.getByText(/تم حفظ نقطة العينة/)).toBeInTheDocument());
    expect(state.save).toHaveBeenCalledTimes(2);
    expect(state.save.mock.calls[1][0]).not.toHaveProperty('sampling_origin');
    expect(state.save.mock.calls[1][0]).not.toHaveProperty('sampling_plan_id');
  });
});
