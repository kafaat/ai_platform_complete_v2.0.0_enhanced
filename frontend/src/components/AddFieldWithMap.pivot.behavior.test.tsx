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
  const map = { getCenter: () => L.latLng(16.1, 44.8), getZoom: () => 15, invalidateSize: vi.fn(), on: vi.fn(), off: vi.fn(), getContainer: () => document.createElement('div') };
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

// G-PIVOT-1 (تدقيق RS 2026-10-27): لقطة التاريخ يجب أن تحمل نموذج pivot كاملاً (مركز + نصف قطر)
// مع الحلقة. كان applySnapshot يُعيد الحلقة الأقدم ويُبقي pivotPayload من تحرير لاحق، فيُرسِل
// الحفظ دائرة 250م مع pivot.radius_m لدائرة أكبر (أو يُسقط pivot عند التراجع إلى الدائرة).
describe('G-PIVOT-1: undo/redo restores the full pivot model with the polygon', () => {
  type SavePayload = {
    pivot?: { radius_m: number; center: { lat: number; lon: number } };
    irrigation_type?: string;
    geometry: { coordinates: number[][][] };
  };
  async function saveAndCapture(onSave: ReturnType<typeof vi.fn>): Promise<SavePayload> {
    fireEvent.change(screen.getByPlaceholderText('مثال: حقل وادي سبأ'), { target: { value: 'حقل' } });
    fireEvent.change(screen.getByPlaceholderText('اسم المسؤول'), { target: { value: 'مدير' } });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /حفظ الحقل/ })); });
    expect(onSave).toHaveBeenCalledTimes(1);
    return onSave.mock.calls[0][0] as SavePayload;
  }
  // نصف قطر الحلقة المُرسَلة مقيساً من المركز القانونيّ المُرسَل (اتّساق الهندسة مع pivot).
  const ringRadiusM = (p: SavePayload) => {
    const ring = p.geometry.coordinates[0];
    const c = L.latLng(p.pivot!.center.lat, p.pivot!.center.lon);
    return c.distanceTo(L.latLng(ring[0][1], ring[0][0]));
  };
  function createCircle250() {
    fireEvent.change(screen.getByPlaceholderText('مثال: 250'), { target: { value: '250' } });
    fireEvent.click(screen.getByRole('button', { name: 'إنشاء دائرة' }));
  }
  const undo = () => fireEvent.click(screen.getByRole('button', { name: /تراجع من لوحة النموذج/ }));
  const redo = () => fireEvent.click(screen.getByRole('button', { name: /إعادة من لوحة النموذج/ }));

  it('undo after a radius resize sends the 250 m pivot with the 250 m ring', async () => {
    const onSave = vi.fn(async () => {});
    render(<AddFieldWithMap onSave={onSave} onCancel={() => {}} existingFields={[]} />);
    createCircle250();
    const radius = observed.markers[1];
    act(() => {
      radius.setLatLng(L.latLng(16.106, 44.8));
      radius.fire('drag'); radius.fire('dragend');
    });
    undo();
    const payload = await saveAndCapture(onSave);
    expect(payload.irrigation_type).toBe('pivot');
    expect(payload.pivot?.radius_m).toBeCloseTo(250, 0);
    expect(Math.abs(ringRadiusM(payload) - payload.pivot!.radius_m)).toBeLessThan(1);
  });

  it('undo from a simplified (non-pivot) boundary back to the circle restores the pivot model', async () => {
    const onSave = vi.fn(async () => {});
    render(<AddFieldWithMap onSave={onSave} onCancel={() => {}} existingFields={[]} />);
    createCircle250();
    fireEvent.click(screen.getByRole('button', { name: /قوي 5م/ }));
    undo();
    const payload = await saveAndCapture(onSave);
    expect(payload.irrigation_type).toBe('pivot');
    expect(payload.pivot?.radius_m).toBeCloseTo(250, 0);
    expect(Math.abs(ringRadiusM(payload) - 250)).toBeLessThan(1);
  });

  it('redo to the simplified boundary drops the pivot model again', async () => {
    const onSave = vi.fn(async () => {});
    render(<AddFieldWithMap onSave={onSave} onCancel={() => {}} existingFields={[]} />);
    createCircle250();
    fireEvent.click(screen.getByRole('button', { name: /قوي 5م/ }));
    undo();
    redo();
    const payload = await saveAndCapture(onSave);
    expect(payload.pivot).toBeUndefined();
    expect(payload.irrigation_type).toBeUndefined();
  });
});
