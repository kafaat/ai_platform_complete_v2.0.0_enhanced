// F-U02: spatial proposal cards in the advisor chat must not show an action they cannot perform.
// The chat has no save/review API for these proposal types, so each card is read-only there.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const api = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn(),
}));

vi.mock('../services/api', () => ({ kongApi: api }));
vi.mock('../hooks/useApi', () => ({
  useFields: () => ({ data: [] }),
  useWeatherForecast: () => ({ data: undefined }),
}));
vi.mock('../hooks/useSelectedField', () => ({ useSelectedField: () => ({ fieldId: 'field-1' }) }));

import { ChatbotPage } from './ChatbotPage';

const POLYGON = { type: 'Polygon', coordinates: [[[44.1, 15.3], [44.2, 15.3], [44.2, 15.4], [44.1, 15.3]]] };

const TOOL_CALLS = [
  { tool: 'detect_field_boundaries', outcome: 'ok', data: {
    field_id: 'field-1', source: 'truecolor',
    proposed_boundaries: [{ geometry: POLYGON, confidence: 0.6, area_ha: 2, method: 'deterministic_bbox_fallback' }],
  } },
  { tool: 'generate_productivity_zones', outcome: 'ok', data: {
    method: 'kmeans', zones: [{ zone_id: 'z1', productivity_class: 'high', confidence: 0.7 }],
  } },
  { tool: 'plan_soil_sampling', outcome: 'ok', data: {
    field_id: 'field-1', soil_sampling_plan: { plan_id: 'plan-1' },
    sample_points: [{ sample_id: 's1', zone_id: 'z1', point: { coordinates: [44.15, 15.35] }, depth_cm: [0, 30] }],
  } },
  { tool: 'generate_vra_prescription', outcome: 'ok', data: {
    vra_prescription: { product_type: 'fertilizer' },
    prescription_zones: [{ zone_id: 'z1', productivity_class: 'high' }],
    readiness_gate: { status: 'proposal_only' },
  } },
];

const PANELS = [
  'field-boundary-proposal-panel',
  'productivity-zones-panel',
  'soil-sampling-planner-panel',
  'vra-prescription-panel',
];

const ACTIONS = [
  'field-boundary-accept', 'field-boundary-edit', 'field-boundary-reject',
  'productivity-zones-accept', 'productivity-zones-soil-sampling', 'productivity-zones-reject',
  'soil-sampling-accept', 'soil-sampling-vra-next', 'soil-sampling-reject',
  'vra-approve', 'vra-refine', 'vra-reject',
];

async function askAdvisor() {
  const view = render(<MemoryRouter><ChatbotPage /></MemoryRouter>);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'اقترح حدود الحقل' } });
  fireEvent.submit(view.container.querySelector('form')!);
  await screen.findByTestId('vra-prescription-panel');
  return view;
}

describe('ChatbotPage — spatial proposal cards (F-U02)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn(); // jsdom does not implement it
    api.get.mockResolvedValue({ data: {} });
    api.post.mockResolvedValue({ data: { answer_ar: 'مقترحات للعرض', harness: { tool_calls: TOOL_CALLS } } });
  });

  it('renders the four cards from the tool results', async () => {
    await askAdvisor();
    for (const panel of PANELS) expect(screen.getByTestId(panel)).toBeInTheDocument();
  });

  it('shows no accept / approve / navigate control that has no handler behind it', async () => {
    await askAdvisor();
    for (const action of ACTIONS) expect(screen.queryByTestId(action), action).toBeNull();
  });

  it('says on every card that the proposal was not saved or approved', async () => {
    await askAdvisor();
    for (const panel of PANELS) {
      expect(within(screen.getByTestId(panel)).getByRole('status').textContent, panel).toContain('لم يُحفظ المقترح أو يُعتمد');
    }
  });

  it('writes nothing: the only request sent is the chat question itself', async () => {
    await askAdvisor();
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
    expect(api.post.mock.calls[0][0]).toBe('/api/ai-agronomist/chat');
    expect(api.put).not.toHaveBeenCalled();
    expect(api.patch).not.toHaveBeenCalled();
    expect(api.delete).not.toHaveBeenCalled();
  });

  it('keeps the working link that records a sample from a planned point', async () => {
    await askAdvisor();
    const link = within(screen.getByTestId('soil-sampling-planner-panel')).getByRole('link');
    expect(link).toHaveAttribute('href', '/health/lab-sampling');
  });
});
