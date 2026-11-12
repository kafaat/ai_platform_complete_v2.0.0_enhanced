import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const state = vi.hoisted(() => ({ save: vi.fn(), samples: [] as unknown[], post: vi.fn() }));
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
vi.mock('../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../services/api')>();
  return { ...actual, kongApi: { ...actual.kongApi, post: state.post } };
});
import { useAuthStore } from '../hooks/useAuth';
import { useSubmitWaterLabResult } from '../hooks/useWaterFieldOps';
import LabSamplingPage from './LabSamplingPage';
import { LabSampleReview } from './LabSampleReview';

beforeEach(() => {
  cleanup(); vi.clearAllMocks(); sessionStorage.clear(); state.samples = [];
  useAuthStore.setState({ tenantId: 't1', user: { id: 1, email: 'm@example.org', full_name: 'm', role: 'manager' } });
  state.save.mockResolvedValue({});
});

describe('server-resolved plan origin', () => {
  it('sends the deviation reason typed for a plan point', async () => {
    render(<LabSamplingPage />);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Latitude' }), { target: { value: '16.103' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Longitude' }), { target: { value: '44.2' } });
    fireEvent.change(screen.getByRole('textbox', { name: /سبب الابتعاد/ }), { target: { value: 'rock outcrop' } });
    const form = screen.getByRole('spinbutton', { name: 'Latitude' }).closest('form')!;
    await act(async () => { form.requestSubmit(); await new Promise((r) => setTimeout(r, 0)); });
    await waitFor(() => expect(state.save).toHaveBeenCalledTimes(1));
    expect(state.save.mock.calls[0][0]).toMatchObject({ deviation_reason: 'rock outcrop', latitude: 16.103 });
  });

  it('shows an unverified origin and the recorded deviation, not an on-plan claim', () => {
    state.samples = [{
      sample_id: 's-1', field_id: 'a', kind: 'soil', latitude: 16.103, longitude: 44.2, status: 'sampled',
      sampling_origin: {
        ...origin, indicator_sources: { ndvi: { scene_id: 'FAKE', acquisition_date: '2026-01-01' } },
        verification: 'unverified', plan_verification: 'plan_not_stored', layer_verification: { ndvi: 'unverified' },
        collection: { latitude: 16.103, longitude: 44.2, deviation_m: 333.6, tolerance_m: 30, on_plan: false, deviation_reason: null },
      },
    }];
    render(<LabSamplingPage />);
    expect(screen.getByText(/أصل العينة غير موثّق/)).toBeInTheDocument();
    expect(screen.getByText(/طبقة غير موثّقة/)).toBeInTheDocument();
    expect(screen.getByText(/الانحراف 333.6 م/)).toHaveTextContent('خارج الخطة، بلا سبب مذكور');
  });
});

describe('water lab review and submission', () => {
  it('offers review for a water sample with a received result', () => {
    render(<LabSampleReview sample={{ sample_id: 'w-1', field_id: 'a', kind: 'water', latitude: 1, longitude: 1, status: 'result_received' }} />);
    expect(screen.getByText('عرض التحاليل ومراجعتها')).toBeInTheDocument();
  });

  it('reuses one Idempotency-Key for the same measurement and a new one for another', async () => {
    state.post.mockRejectedValueOnce(new Error('network lost')).mockResolvedValue({ data: {} });
    const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useSubmitWaterLabResult(), { wrapper });
    const body = { sample_id: 'w-1', ec_dsm: 0.5 };
    await act(async () => { await result.current.mutateAsync(body).catch(() => undefined); });
    await act(async () => { await result.current.mutateAsync({ ...body }); });
    await act(async () => { await result.current.mutateAsync({ ...body, ec_dsm: 0.7 }); });
    const keys = state.post.mock.calls.map((call) => call[2].headers['Idempotency-Key']);
    expect(keys[0]).toBeTruthy();
    expect(keys[1]).toBe(keys[0]);
    expect(keys[2]).not.toBe(keys[0]);
  });
});
