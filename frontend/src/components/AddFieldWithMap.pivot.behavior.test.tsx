import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { forwardRef, useImperativeHandle, type ReactNode } from 'react';
import type * as Leaflet from 'leaflet';
import L from 'leaflet';

type Editable = Leaflet.Polygon & { editing: { enable: ReturnType<typeof vi.fn>; disable: ReturnType<typeof vi.fn> } };
const observed = vi.hoisted(() => ({
  polygons: [] as Editable[], markers: [] as Leaflet.Marker[],
  onCreated: null as null | ((event: unknown) => void),
}));
vi.mock('leaflet', async (importOriginal) => {
  const actual = await importOriginal<typeof import('leaflet')>();
  return { ...actual, default: { ...actual,
    polygon: (...args: Parameters<typeof actual.polygon>) => {
      const polygon = actual.polygon(...args) as Editable;
      polygon.editing = { enable: vi.fn(), disable: vi.fn() };
      observed.polygons.push(polygon);
      return polygon;
    },
    marker: (...args: Parameters<typeof actual.marker>) => {
      const marker = actual.marker(...args);
      vi.spyOn(marker, 'addTo').mockReturnValue(marker);
      observed.markers.push(marker);
      return marker;
    },
  } };
});
vi.mock('./maphub/DrawControl', () => ({ default: ({ onCreated }: { onCreated: (event: unknown) => void }) => {
  observed.onCreated = onCreated;
  return null;
} }));
vi.mock('./maphub/InteractiveDrawLayer', () => ({ default: () => null }));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('shpjs', () => ({ default: vi.fn() }));
vi.mock('../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/api')>(),
  kongApi: { get: vi.fn().mockRejectedValue(new Error('test: no network')) },
}));
vi.mock('react-leaflet', () => {
  const map = { getCenter: () => L.latLng(16.1, 44.8), invalidateSize: vi.fn(), on: vi.fn(), off: vi.fn(), getContainer: () => document.createElement('div') };
  const MapContainer = forwardRef<unknown, { children?: ReactNode }>(({ children }, ref) => {
    useImperativeHandle(ref, () => map, []);
    return <div>{children}</div>;
  });
  const FeatureGroup = forwardRef<unknown, { children?: ReactNode }>(({ children }, ref) => {
    useImperativeHandle(ref, () => ({ clearLayers: vi.fn(), addLayer: vi.fn() }), []);
    return <div>{children}</div>;
  });
  return { MapContainer, FeatureGroup, TileLayer: () => null, useMap: () => map };
});

import AddFieldWithMap from './AddFieldWithMap';

beforeEach(() => {
  cleanup(); observed.polygons.length = 0; observed.markers.length = 0; observed.onCreated = null;
});

function mount() {
  render(<AddFieldWithMap onSave={async () => {}} onCancel={() => {}} existingFields={[]} />);
}

describe('TEXT-GUARD: pivot editing at the executing component', () => {
  it('keeps vertex editing off during creation, center movement and radius resize', () => {
    mount();
    fireEvent.change(screen.getByPlaceholderText('مثال: 250'), { target: { value: '250' } });
    fireEvent.click(screen.getByRole('button', { name: 'إنشاء دائرة' }));
    expect(observed.polygons).toHaveLength(1);
    const polygon = observed.polygons[0];
    expect(polygon.editing.enable).not.toHaveBeenCalled();
    expect(observed.markers).toHaveLength(2);
    const [center, radius] = observed.markers;
    const initial = (polygon.getLatLngs()[0] as Leaflet.LatLng[])[0];
    act(() => {
      center.fire('dragstart');
      center.setLatLng(L.latLng(16.101, 44.801));
      center.fire('drag'); center.fire('dragend');
    });
    expect((polygon.getLatLngs()[0] as Leaflet.LatLng[])[0].equals(initial)).toBe(false);
    expect(polygon.editing.enable).not.toHaveBeenCalled();
    const beforeResize = (polygon.getLatLngs()[0] as Leaflet.LatLng[])[0];
    act(() => {
      radius.setLatLng(L.latLng(16.106, 44.801));
      radius.fire('drag'); radius.fire('dragend');
    });
    expect((polygon.getLatLngs()[0] as Leaflet.LatLng[])[0].equals(beforeResize)).toBe(false);
    expect(polygon.editing.enable).not.toHaveBeenCalled();
  });

  it('enables ordinary polygon vertices and restores them after center dragging', () => {
    mount();
    const ring = [[16.1, 44.8], [16.1, 44.81], [16.11, 44.81]].map(([lat, lng]) => L.latLng(lat, lng));
    expect(observed.onCreated).toBeTypeOf('function');
    act(() => observed.onCreated?.({ layerType: 'polygon', layer: { getLatLngs: () => [ring] } }));
    const polygon = observed.polygons[0];
    expect(polygon.editing.enable).toHaveBeenCalledTimes(1);
    expect(observed.markers).toHaveLength(1);
    act(() => observed.markers[0].fire('dragstart'));
    expect(polygon.editing.disable).toHaveBeenCalledTimes(1);
    act(() => observed.markers[0].fire('dragend'));
    expect(polygon.editing.enable).toHaveBeenCalledTimes(2);
  });
});
