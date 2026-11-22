// ═══════════════════════════════════════════════════════════════
// F-U03 — محرّك MapLibre GL يرسم مناطق الإدارة/الوصفات/الاستبعاد وتصاميم pivot
// التي تصله في `pivotDrafts`، كما يرسمها محرّك Leaflet (HubMap.tsx).
// ───────────────────────────────────────────────────────────────
// خريطة مُظلَّلة «ذات حالة» بقواعد MapLibre (معرّف مكرّر ⇒ خطأ، مصدر مستعمَل لا يُزال)
// تسجّل المصادر وترتيب الطبقات ومُعالِجات الأحداث. هذا تظليل منطق/أسلاك لا تصيير WebGL:
// يُثبت ما يُسلَّم إلى MapLibre (GeoJSON + طبقات + ترتيب)، لا البكسلات على الشاشة.
// وصف الطبقات نفسه يُفحَص بمواصفة نمط MapLibre الحقيقيّة (غير مُظلَّلة).
// ═══════════════════════════════════════════════════════════════
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { render } from '@testing-library/react';
import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import type { FieldOption } from '../../lib/fields';
import type { DrawFeature, DrawFeatureKind } from './drawing';

type Layer = { id: string; type?: string; source?: string; paint?: Record<string, unknown> };
type Handler = { type: string; layer: string | null; fn: (...a: unknown[]) => void };
type Source = { type?: string; data?: GeoJSON.FeatureCollection; setData?: (d: GeoJSON.FeatureCollection) => void };

const mockState = vi.hoisted(() => ({
  maps: [] as unknown[],
  errors: [] as string[],
  popupTexts: [] as string[],
  popupRemovals: 0,
  popupOptions: [] as Array<{ className?: string }>,
}));

vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}));

vi.mock('maplibre-gl', () => {
  class StatefulMap {
    sources = new Map<string, Source>();
    layers: Layer[] = [];
    handlers: Handler[] = [];
    constructor(opts: { style?: { sources?: Record<string, Source>; layers?: Layer[] } }) {
      for (const [id, src] of Object.entries(opts?.style?.sources ?? {})) this.sources.set(id, src);
      this.layers = [...(opts?.style?.layers ?? [])];
      mockState.maps.push(this);
    }
    private emitError(message: string) { mockState.errors.push(message); }
    on(type: string, layerOrCb: unknown, cb?: (...a: unknown[]) => void) {
      const fn = (typeof layerOrCb === 'function' ? layerOrCb : cb) as ((...a: unknown[]) => void) | undefined;
      if (!fn) return this;
      this.handlers.push({ type, layer: typeof layerOrCb === 'string' ? layerOrCb : null, fn });
      if (type === 'load') fn();
      return this;
    }
    addControl() { return this; }
    addSource(id: string, src: Source) {
      if (this.sources.has(id)) throw new Error(`Source "${id}" already exists.`);
      const stored: Source = { ...src };
      stored.setData = (data) => { stored.data = data; };
      this.sources.set(id, stored);
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
      if (layer.source && !this.sources.has(layer.source)) { this.emitError(`Source "${layer.source}" not found.`); return this; }
      const idx = beforeId ? this.layers.findIndex((l) => l.id === beforeId) : -1;
      if (idx >= 0) this.layers.splice(idx, 0, layer); else this.layers.push(layer);
      return this;
    }
    getLayer(id: string) { return this.layers.find((l) => l.id === id); }
    removeLayer(id: string) {
      if (!this.getLayer(id)) { this.emitError(`Cannot remove non-existing layer "${id}".`); return this; }
      this.layers = this.layers.filter((l) => l.id !== id);
      return this;
    }
    moveLayer(id: string, beforeId?: string) {
      const layer = this.getLayer(id);
      if (!layer) { this.emitError(`Cannot move non-existing layer "${id}".`); return this; }
      this.layers = this.layers.filter((l) => l.id !== id);
      const idx = beforeId ? this.layers.findIndex((l) => l.id === beforeId) : -1;
      if (idx >= 0) this.layers.splice(idx, 0, layer); else this.layers.push(layer);
      return this;
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
  class FakePopup {
    constructor(options: { className?: string }) { mockState.popupOptions.push(options); }
    setLngLat() { return this; }
    setText(text: string) { mockState.popupTexts.push(text); return this; }
    addTo() { return this; }
    remove() { mockState.popupRemovals += 1; return this; }
  }
  class Noop { setLngLat() { return this; } setPopup() { return this; } addTo() { return this; } remove() { return this; } }
  const api = {
    Map: StatefulMap,
    Marker: Noop,
    Popup: FakePopup,
    NavigationControl: class {},
    LngLatBounds: class {},
    setWorkerUrl: vi.fn(),
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

type StatefulMapT = { layers: Layer[]; sources: Map<string, Source>; handlers: Handler[] };

const SRC = 'sahool-draw-overlays';
const FILL = 'sahool-draw-overlays-fill';
const LINE = 'sahool-draw-overlays-line';

const FIELD: FieldOption = {
  id: 'f1', name: 'حقل ١', lat: 15, lon: 44, area: 10, crop: 'قمح',
  geometry: { type: 'Polygon', coordinates: [[[44.0, 15.0], [44.1, 15.0], [44.1, 15.1], [44.0, 15.0]]] },
};
const PROPS = {
  fields: [FIELD], selectedId: 'f1', onSelect: () => {}, basemapId: 'satellite',
  indicatorId: null as string | null, indicatorOpacity: 0.7,
};

const RING = [[44.01, 15.01], [44.05, 15.01], [44.05, 15.05], [44.01, 15.05], [44.01, 15.01]];

function zone(id: string, kind: DrawFeatureKind, extra: Partial<DrawFeature> = {}): DrawFeature {
  return {
    id, kind, version: 1, draft: false,
    geometry: { type: 'Polygon', coordinates: [RING] },
    properties: { fieldId: 'f1' },
    ...extra,
  };
}

const SAVED: DrawFeature[] = [
  zone('z-mgmt', 'management-zone', { properties: { fieldId: 'f1', name: 'منطقة أ' }, measurements: { areaHa: 1.5 } }),
  zone('z-rx', 'prescription-zone', { properties: { fieldId: 'f1', name: 'وصفة ب', rate: 120, rateUnit: 'kg/ha' }, measurements: { areaHa: 2 } }),
  zone('z-excl', 'exclusion-zone'),
  zone('p-1', 'pivot'),
];

const theMap = () => mockState.maps[0] as StatefulMapT;
const overlayFeatures = () => theMap().sources.get(SRC)?.data?.features ?? [];
const layerIds = () => theMap().layers.map((l) => l.id);

beforeEach(() => {
  mockState.maps.length = 0;
  mockState.errors.length = 0;
  mockState.popupTexts.length = 0;
  mockState.popupRemovals = 0;
  mockState.popupOptions.length = 0;
});

describe('F-U03: HubMapGL يرسم ما يصله في pivotDrafts', () => {
  it('يضيف مصدر GeoJSON واحداً بمضلّع لكلّ منطقة/تصميم محفوظ وطبقتَي تعبئة وحدّ', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);

    const feats = overlayFeatures();
    expect(feats.map((f) => f.properties?.id)).toEqual(['z-mgmt', 'z-rx', 'z-excl', 'p-1']);
    expect(feats.map((f) => f.properties?.kind)).toEqual(['management-zone', 'prescription-zone', 'exclusion-zone', 'pivot']);
    for (const f of feats) {
      expect(f.geometry.type).toBe('Polygon');
      // إحداثيّات GeoJSON [lng, lat] كما حُفظت — بلا قلب محاور.
      expect((f.geometry as GeoJSON.Polygon).coordinates).toEqual([RING]);
    }
    const fill = theMap().layers.find((l) => l.id === FILL);
    const line = theMap().layers.find((l) => l.id === LINE);
    expect(fill).toMatchObject({ type: 'fill', source: SRC });
    expect(line).toMatchObject({ type: 'line', source: SRC });
    expect(mockState.errors).toEqual([]);
  });

  it('يرسمها فوق حدود الحقول وإبراز الحقل المختار لا تحتها', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    const ids = layerIds();
    expect(ids.indexOf(FILL)).toBeGreaterThan(ids.indexOf('sahool-fields-selected'));
    expect(ids.indexOf(LINE)).toBeGreaterThan(ids.indexOf(FILL));
  });

  it('يحمل كلّ مضلّع لون نوعه وتسميته كما في Leaflet (الاسم · المساحة · المعدّل)', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    const byId = Object.fromEntries(overlayFeatures().map((f) => [f.properties?.id, f.properties]));
    expect(byId['z-mgmt']).toMatchObject({ color: '#22c55e', fillOpacity: 0.16, label: 'منطقة أ · 1.50 هـ' });
    expect(byId['z-rx']).toMatchObject({ color: '#f59e0b', fillOpacity: 0.2, label: 'وصفة ب · 2.00 هـ · 120 kg/ha' });
    expect(byId['z-excl']).toMatchObject({ color: '#ef4444', fillOpacity: 0.18, label: 'exclusion-zone' });
    expect(byId['p-1']).toMatchObject({ color: '#38bdf8', fillOpacity: 0.18, label: 'Pivot' });
  });

  it('ألوان الأنواع مطابقة لما يرسمه محرّك Leaflet في HubMap.tsx', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    const leaflet = readFileSync(join(process.cwd(), 'src/components/maphub/HubMap.tsx'), 'utf8');
    const start = leaflet.indexOf('function drawFeatureStyle');
    const body = leaflet.slice(start, leaflet.indexOf('\n}\n', start));
    const leafletStyle = (kind: string) => {
      const at = kind === 'pivot' ? body.lastIndexOf('return {') : body.indexOf('return {', body.indexOf(`'${kind}'`));
      const ret = body.slice(at, body.indexOf('}', at));
      return {
        color: /color: '(#[0-9a-f]{6})'/.exec(ret)?.[1],
        fillOpacity: Number(/fillOpacity: ([0-9.]+)/.exec(ret)?.[1]),
      };
    };
    for (const f of overlayFeatures()) {
      const expected = leafletStyle(String(f.properties?.kind));
      expect(expected.color).toMatch(/^#[0-9a-f]{6}$/);
      expect({ color: f.properties?.color, fillOpacity: f.properties?.fillOpacity }).toEqual(expected);
    }
  });

  it('وصف الطبقتين صالح بمواصفة نمط MapLibre الحقيقيّة', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    const layers = theMap().layers.filter((l) => l.source === SRC);
    expect(layers).toHaveLength(2);
    const problems = validateStyleMin({
      version: 8,
      sources: { [SRC]: { type: 'geojson', data: theMap().sources.get(SRC)?.data as GeoJSON.FeatureCollection } },
      layers,
    } as never);
    expect(problems.map((p) => p.message)).toEqual([]);
  });
});

describe('F-U03: مسارات الرفض — لا يُرسَم ما ليس مضلّعاً صالحاً', () => {
  it('لا مصدر ولا طبقات حين لا يصله شيء (الخاصّيّة غائبة أو قائمة فارغة)', () => {
    render(<HubMapGL {...PROPS} />);
    expect(theMap().sources.has(SRC)).toBe(false);
    expect(layerIds()).not.toContain(FILL);
    expect(layerIds()).not.toContain(LINE);
    expect(mockState.errors).toEqual([]);
  });

  it('يتخطّى الهندسات غير المضلّعة والحلقات الناقصة والإحداثيّات غير الرقميّة', () => {
    const bad: DrawFeature[] = [
      zone('pt', 'management-zone', { geometry: { type: 'Point', coordinates: [44.02, 15.02] } }),
      zone('ln', 'management-zone', { geometry: { type: 'LineString', coordinates: RING } }),
      zone('multi', 'management-zone', { geometry: { type: 'MultiPolygon', coordinates: [[RING]] } }),
      zone('short', 'management-zone', { geometry: { type: 'Polygon', coordinates: [[[44.0, 15.0], [44.1, 15.0]]] } }),
      zone('nan', 'management-zone', { geometry: { type: 'Polygon', coordinates: [[[44.0, 15.0], ['x', 15.0], [44.1, 15.1], [44.0, 15.0]]] } }),
      zone('inf', 'management-zone', { geometry: { type: 'Polygon', coordinates: [[[44.0, 15.0], [Infinity, 15.0], [44.1, 15.1], [44.0, 15.0]]] } }),
      zone('empty', 'management-zone', { geometry: { type: 'Polygon', coordinates: null } }),
    ];
    render(<HubMapGL {...PROPS} pivotDrafts={[...bad, SAVED[0]]} />);
    expect(overlayFeatures().map((f) => f.properties?.id)).toEqual(['z-mgmt']);
    expect(mockState.errors).toEqual([]);
  });

  it('لا يضيف مصدراً ولا طبقة حين كلّ ما وصله غير قابل للرسم', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={[zone('pt', 'pivot', { geometry: { type: 'Point', coordinates: [44, 15] } })]} />);
    expect(theMap().sources.has(SRC)).toBe(false);
    expect(layerIds()).not.toContain(FILL);
  });

  it('يزيل الطبقتين والمصدر حين تُفرَّغ القائمة (إخفاء المناطق) بلا خطأ MapLibre', () => {
    const { rerender } = render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    expect(theMap().sources.has(SRC)).toBe(true);
    rerender(<HubMapGL {...PROPS} pivotDrafts={[]} />);
    expect(theMap().sources.has(SRC)).toBe(false);
    expect(layerIds()).not.toContain(FILL);
    expect(layerIds()).not.toContain(LINE);
    expect(mockState.errors).toEqual([]);
  });
});

describe('F-U03: التحديث وتبديل الأساس والتسمية', () => {
  it('يحدّث البيانات في مكانها عند تغيّر القائمة دون تكرار مصدر أو طبقة', () => {
    const { rerender } = render(<HubMapGL {...PROPS} pivotDrafts={SAVED.slice(0, 1)} />);
    expect(overlayFeatures()).toHaveLength(1);
    expect(() => rerender(<HubMapGL {...PROPS} pivotDrafts={SAVED} />)).not.toThrow();
    expect(overlayFeatures()).toHaveLength(4);
    expect(layerIds().filter((id) => id === FILL || id === LINE)).toEqual([FILL, LINE]);
    expect(mockState.errors).toEqual([]);
  });

  it('تبقى فوق طبقات الحقول بعد تبديل خريطة الأساس', () => {
    const { rerender } = render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    expect(() => rerender(<HubMapGL {...PROPS} basemapId="light" pivotDrafts={SAVED} />)).not.toThrow();
    const ids = layerIds();
    expect(ids[0]).toBe('sahool-basemap-layer');
    expect(ids.indexOf(FILL)).toBeGreaterThan(ids.indexOf('sahool-fields-selected'));
    expect(ids.indexOf(LINE)).toBeGreaterThan(ids.indexOf(FILL));
    expect(overlayFeatures()).toHaveLength(4);
    expect(mockState.errors).toEqual([]);
  });

  it('المرور فوق منطقة يعرض تسميتها، ومغادرتها تُخفيها، ووضع الدبابيس يقمعها', () => {
    const { rerender } = render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    const move = theMap().handlers.find((h) => h.type === 'mousemove' && h.layer === FILL);
    const leave = theMap().handlers.find((h) => h.type === 'mouseleave' && h.layer === FILL);
    expect(move).toBeDefined();
    expect(leave).toBeDefined();
    const event = { lngLat: { lng: 44.02, lat: 15.02 }, features: [{ properties: { label: 'منطقة أ · 1.50 هـ' } }] };

    move?.fn(event);
    expect(mockState.popupTexts).toEqual(['منطقة أ · 1.50 هـ']);
    const removalsBefore = mockState.popupRemovals;
    leave?.fn();
    expect(mockState.popupRemovals).toBe(removalsBefore + 1);

    rerender(<HubMapGL {...PROPS} pivotDrafts={SAVED} pinMode />);
    move?.fn(event);
    expect(mockState.popupTexts).toEqual(['منطقة أ · 1.50 هـ']);
  });

  it('نافذة التسمية بنصّ داكن: خلفيّتها بيضاء ولون النصّ الموروث من السمة الداكنة أبيض', () => {
    render(<HubMapGL {...PROPS} pivotDrafts={SAVED} />);
    expect(mockState.popupOptions).toHaveLength(1);
    expect(mockState.popupOptions[0].className).toBe('text-slate-900');
  });
});
