import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, render, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import MyFieldsPage from './MyFieldsPage';

const query = vi.hoisted(() => ({ data: { fields: [] as Record<string, unknown>[] } }));
vi.mock('../hooks/useApi', () => ({
  useFields: () => ({ data: query.data, isLoading: false, isError: false }),
}));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'viewer' } }) }));
afterEach(cleanup);

it.each([
  ['numeric zero', 0, '0.00'], ['string zero', '0', '0.00'],
  ['lower bound', -1, '-1.00'], ['upper bound', '1', '1.00'], ['negative value', '-0.25', '-0.25'],
  ['above range', 1.01, '—'], ['below range', '-1.01', '—'], ['missing', null, '—'],
  ['blank', '  ', '—'], ['non-finite', Infinity, '—'], ['boolean', false, '—'],
  ['array masquerading as zero', [0], '—'],
])('renders %s consistently on desktop and mobile after refresh', (_label, value, expected) => {
  const field = { field_id: 'plot', name_ar: 'محور القمح', area_ha: 50 };
  query.data = { fields: [{ ...field, ndvi: 0.72 }] };
  const view = render(<MemoryRouter><MyFieldsPage /></MemoryRouter>);

  function readings() {
    const row = view.container.querySelector('tbody tr')!;
    const card = view.getAllByRole('button', { name: /محور القمح/ }).find(button => button.tagName === 'BUTTON')!;
    return [row.querySelectorAll('td')[3].textContent, within(card).getByText('NDVI').nextElementSibling?.textContent];
  }

  expect(readings()).toEqual(['0.72', '0.72']);
  query.data = { fields: [{ ...field, ndvi: value }] };
  view.rerender(<MemoryRouter><MyFieldsPage /></MemoryRouter>);
  expect(readings()).toEqual([expected, expected]);
});
