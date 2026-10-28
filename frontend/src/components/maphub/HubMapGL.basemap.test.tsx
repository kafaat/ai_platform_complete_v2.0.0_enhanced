// ═══════════════════════════════════════════════════════════════
// UI-G1 — تبديل خريطة الأساس في MapLibre GL يحترم عمر المصدر/الطبقة.
// ───────────────────────────────────────────────────────────────
// خريطة مُظلَّلة «ذات حالة» تُحاكي قواعد MapLibre 6 (style.ts) حرفيّاً:
//   • removeSource لمصدر تستعمله طبقة ⇒ حدث error ويبقى المصدر (لا إزالة).
//   • addSource لمعرّف قائم ⇒ يرمي Error («already exists»).
//   • addLayer لمعرّف قائم ⇒ حدث error ولا إضافة.
// فإن أزال المكوّن المصدر قبل طبقته التابعة سقط تبديل الأساس (رمي داخل الأثر)
// وبقيت طبقات الحقول محذوفة. هذا تظليل منطق لا خريطة WebGL حقيقيّة.
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';
import type { FieldOption } from '../../lib/fields';

type Layer = { id: string; source?: string };
const mockState = vi.hoisted(() => ({
  maps: [] as unknown[],
  errors: [] as string[],
}));

vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));

vi.mock('maplibre-gl', () => {
  class StatefulMap {
    sources = new Map<string, Record<string, unknown>>();
    layers: Layer[] = [];
    handlers: Record<string, Array<(...a: unknown[]) => void>> = {};
    constructor(opts: { style?: { sources?: Record<string, Record<string, unknown>>; layers?: Layer[] } }) {
      for (const [id, src] of Object.entries(opts?.style?.sources ?? {})) this.sources.set(id, src);
      this.layers = [...(opts?.style?.layers ?? [])];
      mockState.maps.push(this);
    }
    private emitError(message: string) { mockState.errors.push(message); }
    on(type: string, layerOrCb: unknown, cb?: (...a: unknown[]) => void) {
      const fn = (typeof layerOrCb === 'function' ? layerOrCb : cb) as ((...a: unknown[]) => void) | undefined;
      if (!fn) return this;
      (this.handlers[type] ||= []).push(fn);
      if (type === 'load') fn();
      return this;
    }
    addControl() { return this; }
    addSource(id: string, src: Record<string, unknown>) {
      if (this.sources.has(id)) throw new Error(`Source "${id}" already exists.`);
      this.sources.set(id, { ...src, setData() {} });
      return this;
    }
    getSource(id: string) { return this.sources.get(id); }
    removeSource(id: string) {
      if (!this.sources.has(id)) throw new Error(`There is no source with this ID=${id}`);
      const user = this.layers.find((l) => l.source === id);
      if (user) { this.emitError(`Source "${id}" cannot be removed while layer "${user.id}" is using it.`); return this; }
      this.sources.delete(id);
      return this;
    }
    addLayer(layer: Layer, beforeId?: string) {
      if (this.getLayer(layer.id)) { this.emitError(`Layer "${layer.id}" already exists on this map.`); return this; }
      const idx = beforeId ? this.layers.findIndex((l) => l.id === beforeId) : -1;
      if (idx >= 0) this.layers.splice(idx, 0, layer); else this.layers.push(layer);
      return this;
    }
    getLayer(id: string) { return this.layers.find((l) => l.id === id); }
    removeLayer(id: string) { this.layers = this.layers.filter((l) => l.id !== id); return this; }
    moveLayer(id: string, beforeId?: string) {
      const layer = this.getLayer(id);
      if (!layer) return this;
      this.removeLayer(id);
      return this.addLayer(layer, beforeId);
    }
    getStyle() { return { layers: this.layers.map((l) => ({ ...l })) }; }
    setFilter() { return this; }
    fitBounds() { return this; }
    jumpTo() { return this; }
    getCanvas() { return { style: {} as Record<string, string> }; }
    getCenter() { return { lat: 15, lng: 44 }; }
    getZoom() { return 10; }
    resize() { return this; }
    remove() { return this; }
  }
  class Noop { setLngLat() { return this; } setText() { return this; } setPopup() { return this; } addTo() { return this; } remove() { return this; } }
  const api = {
    Map: StatefulMap,
    Marker: Noop,
    Popup: Noop,
    NavigationControl: class {},
    LngLatBounds: class {},
    supported: () => true,
  };
  return { __esModule: true, default: api, ...api };
});

vi.mock('terra-draw', () => ({
  TerraDraw: class { start() {} setMode() {} on() {} getSnapshot() { return []; } clear() {} stop() {} },
  TerraDrawPolygonMode: class {},
  TerraDrawLineStringMode: class {},
  TerraDrawSelectMode: class {},
}));
vi.mock('terra-draw-maplibre-gl-adapter', () => ({ TerraDrawMapLibreGLAdapter: class {} }));

import HubMapGL from './HubMapGL';

type StatefulMapT = { layers: Layer[]; sources: Map<string, { tiles?: string[] }> };

const FIELD: FieldOption = {
  id: 'f1', name: 'حقل ١', lat: 15, lon: 44, area: 10, crop: 'قمح',
  geometry: { type: 'Polygon', coordinates: [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.0]]] },
};
const PROPS = {
  fields: [FIELD], selectedId: 'f1', onSelect: () => {},
  indicatorId: null as string | null, indicatorOpacity: 0.7,
};

beforeEach(() => { mockState.maps.length = 0; mockState.errors.length = 0; });

describe('UI-G1: تبديل الأساس يُزيل الطبقة التابعة قبل مصدرها', () => {
  it('يستبدل مصدر الأساس بلا خطأ، ويُبقي الأساس أسفل الطبقات، ويُعيد طبقات الحقول', () => {
    const { rerender } = render(<HubMapGL {...PROPS} basemapId="satellite" />);
    const map = mockState.maps[0] as StatefulMapT;
    const before = map.sources.get('sahool-basemap')?.tiles?.[0];

    expect(() => rerender(<HubMapGL {...PROPS} basemapId="light" />)).not.toThrow();

    expect(mockState.errors).toEqual([]);
    const after = map.sources.get('sahool-basemap')?.tiles?.[0];
    expect(after).toBeTruthy();
    expect(after).not.toEqual(before);
    const ids = map.layers.map((l) => l.id);
    expect(ids.filter((id) => id === 'sahool-basemap-layer')).toHaveLength(1);
    expect(ids[0]).toBe('sahool-basemap-layer');
    expect(ids).toEqual(expect.arrayContaining(['sahool-fields-fill', 'sahool-fields-line', 'sahool-fields-selected']));
  });
});
