import type { ReactNode } from 'react';
import { render, cleanup } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import L from 'leaflet';
import FieldIndicatorMap from './FieldIndicatorMap';
import ScoutingMap from './fieldhealth/ScoutingMap';
import { fieldBoundary, boundaryBounds, type MapBoundary } from '../lib/fieldBoundary';
import { cdseClipParams, fieldCdseTileUrl, fieldCdseThumbnailUrl } from '../services/api';

const ui = vi.hoisted(() => ({ polygon: vi.fn(), fitBounds: vi.fn() }));
vi.mock('react-leaflet', () => ({
  MapContainer: ({children}: {children: ReactNode}) => <>{children}</>,
  TileLayer: () => null, FeatureGroup: () => null, Popup: () => null, CircleMarker: () => null,
  Polygon: ({positions}: {positions: MapBoundary}) => { ui.polygon(positions); return null; },
  useMap: () => ui, useMapEvents: () => ui,
}));
vi.mock('./maphub/DrawControl', () => ({ default: () => null }));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('../services/api', async original => ({
  ...await original<typeof import('../services/api')>(), rasterApi: {get: () => new Promise(() => {})},
}));

const outer = [[40,10],[44,10],[44,14],[40,14],[40,10]];
const hole = [[41,11],[42,11],[42,12],[41,12],[41,11]];
const other = [[47,16],[48,16],[48,17],[47,17],[47,16]];
const field = {type: 'MultiPolygon', coordinates: [[outer, hole], [other]]};
const enc = (r: number[][]) => r.map(p => p.join(',')).join(';');

afterEach(() => { cleanup(); vi.clearAllMocks(); });
it.each(['indicator','scouting'])('preserves all boundaries and fits their combined extent on %s', mode => {
  const parts = fieldBoundary(field)!;
  const props = {fieldId:'f', index:'ndvi', date:'2025-03-14', fieldPolygon:parts};
  render(mode === 'indicator' ? <FieldIndicatorMap {...props}/> :
    <ScoutingMap {...props} pins={[]} onDropPin={vi.fn()} onRemovePin={vi.fn()}/>);
  const [positions] = ui.polygon.mock.calls[0];
  expect(L.polygon(positions).toGeoJSON().geometry).toEqual(field);
  const [bounds] = ui.fitBounds.mock.calls[0];
  expect(bounds.toBBoxString()).toBe('40,10,48,17');
});
it('uses identical full clips for manifests, tile URLs and thumbnails; retains legacy simple-ring wire format', () => {
  const expected = enc(outer) + '|' + enc(hole) + '!' + enc(other);
  for (const url of [fieldCdseTileUrl('f','ndvi','latest',null,null,field),
    fieldCdseThumbnailUrl('f','truecolor','latest',null,field)]) {
    expect(new URL(url,'https://example.test').searchParams.get('poly')).toBe(expected);
  }
  expect(cdseClipParams(field).poly).toBe(expected);
  expect(cdseClipParams({type:'Polygon',coordinates:[outer,hole]}).poly).toBe(enc(outer)+'|'+enc(hole));
  expect(cdseClipParams({type:'Polygon',coordinates:[outer]}).poly).toBe(enc(outer));
});
it('accepts Feature wrappers, normal rings, and rejects invalid geometry without dropping its hole', () => {
  expect(fieldBoundary({type:'Feature',geometry:field})).toEqual(fieldBoundary(field));
  expect(boundaryBounds([[10,40],[14,44],[11,43]])).toEqual([40,10,44,14]);
  expect(fieldBoundary({type:'Polygon',coordinates:[outer,[[1,2]]]})).toBeUndefined();
});
