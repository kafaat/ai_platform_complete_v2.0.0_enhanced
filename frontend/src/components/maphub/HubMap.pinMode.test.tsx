// UI-G3 — في وضع الدبابيس لا يُغيّر النقر على حقل (Leaflet) الاختيار، كما في GL
// (HubMapGL: «if (pinModeRef.current) return» على LYR_FILL). نقرة المضلّع تنتشر إلى
// الخريطة فيُضاف الدبّوس؛ تغيير الحقل المختار معها يُطلق FitToFields ويحرّك الكاميرا.
// نُظلّل react-leaflet: المضلّع/الدائرة زرّ يستدعي eventHandlers.click كما يفعل Leaflet.
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import type { FieldOption } from '../../lib/fields';

type Handlers = { eventHandlers?: { click?: () => void }; children?: ReactNode };
vi.mock('react-leaflet', () => {
  const Pass = ({ children }: { children?: ReactNode }) => <>{children}</>;
  const Clickable = (role: string) => ({ eventHandlers }: Handlers) => (
    <button type="button" data-testid={role} onClick={() => eventHandlers?.click?.()} />
  );
  const map = {
    fitBounds: vi.fn(), flyTo: vi.fn(), setView: vi.fn(), invalidateSize: vi.fn(),
    getContainer: () => document.createElement('div'),
    getCenter: () => ({ lat: 15, lng: 44 }), getZoom: () => 10, on: vi.fn(), off: vi.fn(),
  };
  return {
    MapContainer: Pass, FeatureGroup: Pass, Tooltip: () => null, TileLayer: () => null,
    GeoJSON: () => null, Marker: () => null,
    Polygon: Clickable('field-polygon'), CircleMarker: Clickable('field-point'),
    useMap: () => map, useMapEvents: () => map,
  };
});
vi.mock('../../lib/leafletSetup', () => ({}));
vi.mock('./DrawControl', () => ({ default: () => null }));
vi.mock('./OverlayMarkers', () => ({
  AlertOverlay: () => null, DeviceOverlay: () => null, WeatherOverlay: () => null,
  WeatherRasterOverlay: () => null, OperationalOverlay: () => null,
}));

import HubMap from './HubMap';

const POLY: FieldOption = {
  id: 'poly', name: 'مضلّع', lat: 15, lon: 44, area: 1, crop: 'قمح',
  geometry: { type: 'Polygon', coordinates: [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.0]]] },
};
const POINT: FieldOption = { id: 'pt', name: 'نقطة', lat: 15.2, lon: 44.2, area: 1, crop: 'ذرة', geometry: null };

function mount(pinMode: boolean, onSelect: (id: string) => void) {
  render(
    <HubMap
      fields={[POLY, POINT]} selectedId="other" onSelect={onSelect}
      basemapId="satellite" indicatorId={null} indicatorOpacity={0.7}
      drawTools={false} pinMode={pinMode} pins={[]} onAddPin={() => {}}
    />,
  );
}

afterEach(cleanup);

describe('UI-G3: Leaflet لا يُغيّر الحقل المختار أثناء وضع الدبابيس', () => {
  it('في وضع الدبابيس: النقر على مضلّع/نقطة حقل لا يستدعي onSelect', () => {
    const onSelect = vi.fn();
    mount(true, onSelect);
    fireEvent.click(screen.getByTestId('field-polygon'));
    fireEvent.click(screen.getByTestId('field-point'));
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('خارج وضع الدبابيس: النقر يختار الحقل كالمعتاد', () => {
    const onSelect = vi.fn();
    mount(false, onSelect);
    fireEvent.click(screen.getByTestId('field-polygon'));
    fireEvent.click(screen.getByTestId('field-point'));
    expect(onSelect.mock.calls).toEqual([['poly'], ['pt']]);
  });
});
