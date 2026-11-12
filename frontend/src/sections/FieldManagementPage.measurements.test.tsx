import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import FieldManagementPage from './FieldManagementPage';

const query = vi.hoisted(() => ({ data: { fields: [] as Record<string, unknown>[] } }));
vi.mock('../hooks/useApi', () => ({
  useFields: () => ({ data: query.data, isLoading: false, isError: false, refetch: vi.fn() }),
  useSimulateSeason: () => ({}),
}));
vi.mock('../hooks/useAuth', () => ({ useAuthStore: () => ({ user: { role: 'viewer' } }) }));
vi.mock('../components/AddFieldWithMap', () => ({ default: () => null }));
vi.mock('../components/AddSeasonWithStages', () => ({ default: () => null }));
vi.mock('../components/FieldDetailPanel', () => ({ default: () => null }));
vi.mock('../components/FieldIndicatorMap', () => ({ default: () => null }));
afterEach(cleanup);

function field(id: string, values: Record<string, unknown> = {}) {
  return { field_id: id, name_ar: id, crop: 'قمح', ...values };
}

function summary() {
  return screen.getByText(/متوسط NDVI/).querySelector('span')?.textContent;
}

function cells(name: string) {
  const row = screen.getByRole('row', { name: new RegExp(name) });
  return within(row).getAllByRole('cell').map(cell => cell.textContent);
}

it('shows missing cards distinctly and averages only measured fields, including numeric zero', async () => {
  query.data = { fields: [field('missing'), field('zero', { ndvi: '0', gdd: 0, yield_est: 0 }), field('measured', { ndvi: '0.6' })] };
  render(<FieldManagementPage />);
  await screen.findByText('missing');
  expect(summary()).toBe('0.300');
  const cardNDVI = screen.getAllByText('NDVI').map(label => label.nextElementSibling?.textContent);
  expect(cardNDVI).toEqual(['—', '0', '0.6']);
  fireEvent.click(screen.getByRole('button', { name: 'جدول' }));
  expect(cells('missing').slice(3, 8)).toEqual(['—', 'غير مقيس', '—', '—', '—']);
  expect(cells('zero').slice(3, 8)).toEqual(['0', 'منخفض', '—', '0', '0']);
  fireEvent.change(screen.getAllByRole('combobox')[0], { target: { value: 'unknown' } });
  expect(screen.getByText('missing')).toBeInTheDocument();
  expect(screen.queryByText('zero')).not.toBeInTheDocument();
});

it('replaces measured, invalid and absent rows on authoritative list refresh', async () => {
  query.data = { fields: [field('plot', { ndvi: -0.2 })] };
  const view = render(<FieldManagementPage />);
  await screen.findByText('plot');
  expect(summary()).toBe('-0.200');
  fireEvent.click(screen.getByRole('button', { name: 'جدول' }));
  for (const ndvi of [null, undefined, '', '   ', 'bad', true, Infinity, NaN, -1.1, 1.1]) {
    query.data = { fields: [field('plot', { ndvi })] };
    view.rerender(<FieldManagementPage />);
    expect(cells('plot').slice(3, 5)).toEqual(['—', 'غير مقيس']);
    expect(summary()).toBe('—');
  }
  query.data = { fields: [field('plot', { ndvi: 0, health: 'good' })] };
  view.rerender(<FieldManagementPage />);
  expect(cells('plot').slice(3, 5)).toEqual(['0', 'جيد']);
  expect(summary()).toBe('0.000');
  query.data = { fields: [] };
  view.rerender(<FieldManagementPage />);
  expect(summary()).toBe('—');
  expect(screen.queryByText('plot')).not.toBeInTheDocument();
});
