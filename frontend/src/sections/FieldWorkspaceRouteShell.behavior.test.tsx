import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router';

const selected = vi.hoisted(() => ({ fieldId: '' }));
vi.mock('../hooks/useSelectedField', () => ({ useSelectedField: () => selected }));
// Observe the rendered component boundary, not source text or a dead import.
// Map/network internals have their own FieldWorkspaceMapCard.test.tsx coverage.
vi.mock('./FieldWorkspaceMapCard', () => ({
  default: ({ fieldId, showPicker }: { fieldId: string; showPicker?: boolean }) => (
    <section aria-label="rendered field map" data-field={fieldId} data-picker={String(showPicker)} />
  ),
}));
vi.mock('./FieldWorkspaceDataPanels', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceTimelinePanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspacePriorityPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceOperationsPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceRecommendationsPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceReportsPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceImageryPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceWeatherPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceIrrigationPanel', () => ({ default: () => null }));
vi.mock('./FieldWorkspaceContextBanner', () => ({ default: () => null }));

import FieldWorkspaceRouteShell from './FieldWorkspaceRouteShell';

function mount(url: string) {
  render(<MemoryRouter initialEntries={[url]}><Routes>
    <Route path="/fields/:fieldId?" element={<FieldWorkspaceRouteShell />} />
  </Routes></MemoryRouter>);
}

// تنقّل خارجيّ (رابط/سجلّ/موجِّه) إلى نفس المسار باستعلام مختلف — المكوّن نفسه يبقى مركَّباً.
function ExternalNav({ to }: { to: string }) {
  const navigate = useNavigate();
  return <button type="button" onClick={() => navigate(to)}>external-nav</button>;
}

function mountWithNav(url: string, to: string) {
  render(<MemoryRouter initialEntries={[url]}>
    <ExternalNav to={to} />
    <Routes>
      <Route path="/fields/:fieldId?" element={<FieldWorkspaceRouteShell />} />
    </Routes>
  </MemoryRouter>);
}

beforeEach(() => { cleanup(); selected.fieldId = ''; });

describe('TEXT-GUARD: live workspace map binding', () => {
  it.each(['overview', 'map'])('renders the route field in %s without a second picker', (tab) => {
    selected.fieldId = 'another-selected-field';
    mount(`/fields/yemen-field?tab=${tab}`);
    const map = screen.getByRole('region', { name: 'rendered field map' });
    expect(map).toHaveAttribute('data-field', 'yemen-field');
    expect(map).toHaveAttribute('data-picker', 'false');
  });

  it('uses the selected field when the route has none', () => {
    selected.fieldId = 'selected-field';
    mount('/fields');
    expect(screen.getByRole('region', { name: 'rendered field map' })).toHaveAttribute('data-field', 'selected-field');
  });

  it('does not mount a map without field context', () => {
    mount('/fields');
    expect(screen.getByText('لا يوجد حقل نشط')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'rendered field map' })).not.toBeInTheDocument();
  });

  it('mounts the card after changing from weather to the map tab', () => {
    mount('/fields/yemen-field?tab=weather');
    expect(screen.queryByRole('region', { name: 'rendered field map' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'الخريطة' }));
    expect(screen.getByRole('region', { name: 'rendered field map' })).toHaveAttribute('data-field', 'yemen-field');
  });
});

// UI-W1: التبويب النشط يُشتقّ من الرابط — تغيير ?tab بعد التركيب يغيّر المحتوى لا العنوان وحده.
describe('UI-W1: workspace tab follows the URL after mount', () => {
  it('switches content when ?tab changes externally on the mounted route', () => {
    mountWithNav('/fields/yemen-field?tab=weather', '/fields/yemen-field?tab=map');
    expect(screen.queryByRole('region', { name: 'rendered field map' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'external-nav' }));
    expect(screen.getByRole('region', { name: 'rendered field map' })).toHaveAttribute('data-field', 'yemen-field');
    expect(screen.getByRole('button', { name: 'الخريطة' })).toHaveAttribute('aria-current', 'page');
  });

  it('back to a URL without tab falls back to overview (no stale local tab)', () => {
    mountWithNav('/fields/yemen-field?tab=map', '/fields/yemen-field');
    fireEvent.click(screen.getByRole('button', { name: 'external-nav' }));
    expect(screen.getByRole('button', { name: 'نظرة عامة' })).toHaveAttribute('aria-current', 'page');
  });
});
