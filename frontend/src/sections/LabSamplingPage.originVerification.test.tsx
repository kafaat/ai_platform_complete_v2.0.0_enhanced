import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

// Gap P6: the server stores the plan origin soil-service resolves from its stored plan copy.
// The page sends the collection position and an optional deviation reason, shows the server's
// origin and deviation, and names each typed refusal instead of a generic failure.
const state = vi.hoisted(() => ({ save: vi.fn(), samples: [] as unknown[] }));
const origin = { point_id: 'ss-1-1', zone_id: 'A', longitude: 44.2, latitude: 16.1, indicators: ['ndvi'] };
vi.mock('../hooks/useSelectedField', () => ({ useSelectedField: () => ({ fieldId: 'a', options: [{ id: 'a', name: 'A' }], setFieldId: vi.fn() }) }));
vi.mock('../hooks/useApi', () => ({
  useLabSamples: () => ({ data: state.samples, isLoading: false, isError: false, refetch: vi.fn() }),
  useLabDecisionContext: () => ({ isLoading: false, isError: false, data: undefined, refetch: vi.fn() }),
  useCreateLabSample: () => ({ mutateAsync: state.save, isPending: false }),
  useSubmitSoilLabResult: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('react-router', () => ({
  useLocation: () => ({ state: { fieldId: 'a', planId: 'ssp-1', origin, depth: [0, 30] } }),
  useNavigate: () => vi.fn(),
}));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('react-leaflet', () => ({ MapContainer: ({ children }: any) => <div>{children}</div>, TileLayer: () => null, Polygon: () => null, Marker: () => null, CircleMarker: () => null, Tooltip: () => null, useMapEvents: () => ({}) }));
import { useAuthStore } from '../hooks/useAuth';
import LabSamplingPage from './LabSamplingPage';

beforeEach(() => {
  cleanup(); vi.clearAllMocks(); sessionStorage.clear(); state.samples = [];
  useAuthStore.setState({ tenantId: 't1', user: { id: 1, email: 'm@example.org', full_name: 'm', role: 'manager' } });
  state.save.mockResolvedValue({});
});

async function submit(reason?: string) {
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Latitude' }), { target: { value: '16.7' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: 'Longitude' }), { target: { value: '44.2' } });
  if (reason !== undefined) fireEvent.change(screen.getByRole('textbox', { name: /سبب الابتعاد/ }), { target: { value: reason } });
  const form = screen.getByRole('spinbutton', { name: 'Latitude' }).closest('form')!;
  await act(async () => { form.requestSubmit(); await new Promise((r) => setTimeout(r, 0)); });
}

describe('server-resolved plan origin', () => {
  it('sends the deviation reason typed for a plan point', async () => {
    render(<LabSamplingPage />);
    await submit('rock outcrop');
    await waitFor(() => expect(state.save).toHaveBeenCalledTimes(1));
    expect(state.save.mock.calls[0][0]).toMatchObject({ sampling_plan_id: 'ssp-1', deviation_reason: 'rock outcrop', latitude: 16.7 });
  });

  it('names the out-of-tolerance refusal with the measured distance', async () => {
    state.save.mockRejectedValue({ response: { status: 422, data: { detail: { code: 'sampling_origin_out_of_tolerance', deviation_m: 66713.4, tolerance_m: 30 } } } });
    render(<LabSamplingPage />);
    await submit();
    await waitFor(() => expect(screen.getByText(/يبعد 66713.4 م عن نقطة الخطة/)).toBeInTheDocument());
    expect(state.save.mock.calls[0][0]).not.toHaveProperty('deviation_reason');
  });

  it('says a plan the server does not hold is not recorded as a plan sample', async () => {
    state.save.mockRejectedValue({ response: { status: 422, data: { detail: { code: 'sampling_plan_not_found' } } } });
    render(<LabSamplingPage />);
    await submit();
    await waitFor(() => expect(screen.getByText(/الخطة غير محفوظة لدى الخادم/)).toBeInTheDocument());
  });

  it('shows the stored origin and the recorded deviation', () => {
    state.samples = [{
      sample_id: 's-1', field_id: 'a', kind: 'soil', latitude: 16.101, longitude: 44.2, status: 'sampled',
      sampling_origin: {
        ...origin, verification: 'stored_plan', plan_id: 'ssp-1',
        collection: { latitude: 16.101, longitude: 44.2, deviation_m: 111.2, tolerance_m: 30, on_plan: false, deviation_reason: 'rock outcrop' },
      },
    }];
    render(<LabSamplingPage />);
    expect(screen.getByText(/أصل العينة من الخطة المحفوظة/)).toBeInTheDocument();
    expect(screen.getByText(/الانحراف 111.2 م/)).toHaveTextContent('خارج الخطة: rock outcrop');
  });
});
