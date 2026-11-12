import type { ReactNode } from 'react';
import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FieldIndicatorMap from './FieldIndicatorMap';

const mocks = vi.hoisted(() => ({
  get: vi.fn(), renderTile: vi.fn(),
  events: {} as { click?: (event: {latlng: {lat: number; lng: number}}) => void },
  map: { fitBounds: vi.fn() },
}));
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: {children: ReactNode}) => <div>{children}</div>,
  Popup: ({ children }: {children: ReactNode}) => <div>{children}</div>,
  TileLayer: ({ url }: {url: string}) => { mocks.renderTile(url); return null; },
  Polygon: () => null, FeatureGroup: () => null,
  useMap: () => mocks.map, useMapEvents: (events: typeof mocks.events) => { mocks.events = events; },
}));
vi.mock('./maphub/DrawControl', () => ({ default: () => null }));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('../services/api', async (original) => ({
  ...await original<typeof import('../services/api')>(), rasterApi: { get: mocks.get },
}));
function pending() {
  let finish!: (data: object) => void;
  const promise = new Promise(resolve => { finish = data => resolve({data}); });
  mocks.get.mockReturnValueOnce(promise);
  return async (data: object) => { await act(async () => finish(data)); };
}
const tile = (version: string, date: string) => ({available: true, cache_version: version, resolved_date: date});
const map = (fieldId: string, date: string, index = 'ndvi', segment = 'tiles') => (
  <FieldIndicatorMap fieldId={fieldId} date={date} index={index} tileSegment={segment} />
);
beforeEach(() => { vi.clearAllMocks(); mocks.events = {}; });
afterEach(cleanup);

it('never renders a new date with the previous acquisition cache tag while its manifest is pending', async () => {
  const first = pending();
  const view = render(map('a', '2024-10-23'));
  await first(tile('old-version', '2024-10-23'));
  expect(mocks.renderTile.mock.calls.flat()).toContainEqual(expect.stringContaining('old-version'));
  mocks.renderTile.mockClear();
  const second = pending();
  view.rerender(map('a', '2025-10-23'));
  expect(mocks.renderTile.mock.calls.flat().filter(url => url.includes('/tiles/'))).toEqual([]);
  const third = pending();
  view.rerender(map('b', '2026-10-23', 'ndre'));
  await third(tile('new-version', '2026-10-23'));
  await second({ available: false });
  expect(screen.getByText('متاح: NDRE')).toBeTruthy();
  expect(mocks.renderTile.mock.calls.flat()).toContainEqual(expect.stringContaining('new-version'));
});

function click(lat: number, lng: number) {
  act(() => { mocks.events.click?.({ latlng: {lat, lng} }); });
}
const response = (value: number | null) => ({
  field_id: 'a', index: 'ndvi', date: '2025-10-23', valid: value !== null, value,
});

it('pins latest tiles and pixel requests to the acquisition, preserves zero, and separates NoData', async () => {
  const manifest = pending();
  render(map('a', 'latest'));
  await manifest(tile('version', '2025-10-23'));
  expect(mocks.renderTile.mock.calls.flat()).toContainEqual(expect.stringContaining('date=2025-10-23'));
  const first = pending(); click(16.1, 45.2);
  expect(mocks.get).toHaveBeenLastCalledWith('/v1/fields/a/pixel', expect.objectContaining({
    params: { lat: 16.1, lon: 45.2, index: 'ndvi', date: '2025-10-23', v: 'version' },
  }));
  const second = pending(); click(16.2, 45.3);
  await second(response(0));
  await first(response(0.72));
  expect(screen.getByText('NDVI · 0.0000 · 2025-10-23')).toBeTruthy();
  const third = pending(); click(16.3, 45.4);
  await third(response(null));
  expect(screen.getByText('لا توجد قراءة صالحة في هذا البكسل.')).toBeTruthy();
  expect(screen.queryByText(/0\.0000/)).toBeNull();
});

it('discards pixel reads after switching layers and rejects responses for a different field', async () => {
  const manifest = pending();
  const view = render(map('a', '2025-10-23'));
  await manifest(tile('a1', '2025-10-23'));
  const oldRead = pending(); click(16, 45);
  const secondManifest = pending();
  view.rerender(map('b', '2026-10-23', 'ndmi'));
  await oldRead(response(0.9));
  expect(screen.queryByText(/0\.9000/)).toBeNull();
  await secondManifest(tile('b1', '2026-10-23'));
  const wrongRead = pending(); click(16, 45);
  await wrongRead(response(0.9));
  expect(screen.getByText('تعذرت قراءة البكسل في هذا الموقع.')).toBeTruthy();
});

it.each([['truecolor', 'tiles'], ['ndvi', 'cdse-tiles']])(
  'does not query the stored scalar endpoint for %s from %s', async (index, segment) => {
    const manifest = pending();
    render(map('a', '2025-10-23', index, segment));
    await manifest(tile('tag', '2025-10-23'));
    click(16, 45);
    expect(mocks.get).toHaveBeenCalledTimes(1);
  },
);

it('rejects malformed manifests and preserves provider unavailability messages', async () => {
  const first = pending();
  const view = render(map('a', '2025-10-23'));
  await first({});
  expect(screen.getByText('غير متاح: NDVI')).toBeTruthy();
  const second = pending();
  view.rerender(map('b', '2025-10-23', 'ndvi', 'cdse-tiles'));
  await second({ available: false, user_message: 'لا توجد صورة.' });
  expect(screen.getByText(/لا توجد صورة/)).toBeTruthy();
  expect(mocks.renderTile.mock.calls.flat().filter(url => url.includes('/tiles/'))).toEqual([]);
});

it.each([
  ['2025-10-24T00:10:00+03:00', true],
  ['2025-10-22T23:10:00-03:00', true],
  ['2025-10-23T00:10:00+03:00', false],
  ['2025-10-23T23:10:00-03:00', false],
  ['2025-10-23T23:10:00', true],
  ['2025-10-23invalid', false],
])('validates the UTC acquisition day for pixel timestamp %s', async (timestamp, matches) => {
  const manifest = pending();
  render(map('a', '2025-10-23'));
  await manifest(tile('tag', '2025-10-23'));
  const read = pending(); click(16, 45);
  await read({...response(0.25), date: timestamp});
  expect(screen.getByText(matches ? 'NDVI · 0.2500 · 2025-10-23' : 'تعذرت قراءة البكسل في هذا الموقع.')).toBeTruthy();
});
