// ═══════════════════════════════════════════════════════════════
// Regression — GEO-01: request shape of assisted segmentation (auto/hybrid)
// ───────────────────────────────────────────────────────────────
// خلفيّة SAM2 تقرأ صورتها المُرجَعة جغرافيّاً للـbbox وتطبّق ExG عليها خادميّاً؛ لقطة
// الخريطة من المتصفّح بلا مرجع جغرافيّ. كانت الواجهة تُرفق image_base64 دائماً فيردّ
// field-segmentation (SEGMENTATION_BACKEND=sam2) بـ422 على كلّ نقرة. يثبّت هذا الاختبار
// الحمولة التي يرسلها المكوّن فعلاً: bbox + mode + preprocessing (+ hints للهجين) ولا صورة،
// حتى حين يستطيع المتصفّح تصيير لقطة (canvas مُتاح).
// ═══════════════════════════════════════════════════════════════
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { forwardRef, useImperativeHandle, type ReactNode } from 'react';
import L from 'leaflet';

const hoisted = vi.hoisted(() => ({ segmentField: vi.fn() }));

vi.mock('./maphub/DrawControl', () => ({ default: () => null }));
vi.mock('./maphub/InteractiveDrawLayer', () => ({ default: () => null }));
vi.mock('../lib/leafletSetup', () => ({}));
vi.mock('shpjs', () => ({ default: vi.fn() }));
vi.mock('../services/api', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/api')>(),
  kongApi: { get: vi.fn().mockRejectedValue(new Error('test: no network')) },
  segmentField: hoisted.segmentField,
}));
vi.mock('react-leaflet', () => {
  const container = document.createElement('div');
  const tile = document.createElement('img');
  tile.className = 'leaflet-tile';
  container.appendChild(tile);
  const map = {
    getCenter: () => L.latLng(15.35, 44.2),
    getBounds: () => L.latLngBounds(L.latLng(15.3, 44.1), L.latLng(15.4, 44.3)),
    getZoom: () => 14,
    invalidateSize: vi.fn(), on: vi.fn(), off: vi.fn(),
    getContainer: () => container,
    latLngToContainerPoint: () => L.point(0, 0),
    latLngToLayerPoint: () => L.point(0, 0),
  };
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

const GEOMETRY = {
  type: 'Polygon' as const,
  coordinates: [[[44.15, 15.32], [44.16, 15.32], [44.16, 15.33], [44.15, 15.32]]],
};

beforeEach(() => {
  cleanup();
  hoisted.segmentField.mockReset();
  hoisted.segmentField.mockResolvedValue({
    geometry: GEOMETRY, mode: 'auto', source: 'sam2', confidence: 0.8,
    metadata: { preprocessing: 'exg', low_confidence: false },
  });
  // متصفّح قادر على تصيير لقطة: لو عادت الواجهة لالتقاط الخريطة لظهرت image_base64.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
    { drawImage: vi.fn(), globalAlpha: 1 } as unknown as CanvasRenderingContext2D,
  );
  vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,iVBORw0KGgo=');
});

afterEach(() => { vi.restoreAllMocks(); });

async function segment(name: RegExp) {
  render(<AddFieldWithMap onSave={async () => {}} onCancel={() => {}} existingFields={[]} />);
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
  expect(hoisted.segmentField).toHaveBeenCalledTimes(1);
  return hoisted.segmentField.mock.calls[0][0] as Record<string, unknown>;
}

describe('GEO-01: segmentation request carries no un-georeferenced client imagery', () => {
  it('auto sends bbox + server-side ExG request only', async () => {
    const payload = await segment(/تلقائيّ/);
    expect(payload).toEqual({
      mode: 'auto',
      bbox: [44.1, 15.3, 44.3, 15.4],
      preprocessing: 'exg',
      fallback_to_original_on_low_exg: true,
    });
    expect(payload).not.toHaveProperty('image_base64');
  });

  it('hybrid adds the map centre as a single [lon, lat] hint', async () => {
    const payload = await segment(/هجين/);
    expect(payload).toEqual({
      mode: 'hybrid',
      bbox: [44.1, 15.3, 44.3, 15.4],
      preprocessing: 'exg',
      fallback_to_original_on_low_exg: true,
      hints: [[44.2, 15.35]],
    });
    expect(payload).not.toHaveProperty('image_base64');
  });
});
