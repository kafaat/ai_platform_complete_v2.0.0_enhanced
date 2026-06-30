import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  DRAW_ENGINE_CAPABILITIES,
  getPreferredEngineForWorkflow,
  measureDrawFeature,
  resolveDrawingEngine,
  validateDrawFeature,
  type DrawFeature,
} from './index';

const root = process.cwd();
const packageJson = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
const drawingTypes = readFileSync(join(root, 'src/components/maphub/drawing/drawingTypes.ts'), 'utf8');
const adr = readFileSync(join(root, '../docs/adr/ADR-0031-drawing-tools-engine-strategy.md'), 'utf8');

describe('DrawingCore — engine strategy contract', () => {
  it('keeps the current default engine stable while allowing future adapters', () => {
    expect(resolveDrawingEngine(undefined)).toBe('leaflet-draw');
    expect(resolveDrawingEngine('leaflet-geoman')).toBe('leaflet-geoman');
    expect(resolveDrawingEngine('terra-draw')).toBe('terra-draw');
    expect(resolveDrawingEngine('bad-value')).toBe('leaflet-draw');
  });

  it('tracks capabilities for leaflet-draw, Leaflet-Geoman, Terra Draw, and MapLibre', () => {
    expect(Object.keys(DRAW_ENGINE_CAPABILITIES)).toEqual([
      'leaflet-draw',
      'leaflet-geoman',
      'terra-draw',
      'maplibre-terra-draw',
    ]);
    expect(DRAW_ENGINE_CAPABILITIES['leaflet-geoman'].snapping).toBe(true);
    expect(DRAW_ENGINE_CAPABILITIES['leaflet-geoman'].cutPolygon).toBe(true);
    expect(DRAW_ENGINE_CAPABILITIES['terra-draw'].mapLibreReady).toBe(true);
  });

  it('recommends stronger engines for pivot and zone workflows', () => {
    expect(getPreferredEngineForWorkflow('design-pivot')).toBe('leaflet-geoman');
    expect(getPreferredEngineForWorkflow('create-management-zone')).toBe('leaflet-geoman');
    expect(getPreferredEngineForWorkflow('create-field')).toBe('leaflet-draw');
  });

  it('keeps engine deps available while Geoman stays an opt-in adapter (ADR-0031 Phase 2)', () => {
    expect(packageJson.dependencies['terra-draw']).toBeTruthy();
    expect(packageJson.dependencies['maplibre-gl']).toBeTruthy();
    // Geoman is now installed (Phase 2 adapter) but remains opt-in: it is imported
    // ONLY by LeafletGeomanAdapter and is never wired into a live screen, so it is
    // tree-shaken out of the default bundle (see GeomanAdapter.static.test.ts).
    expect(packageJson.dependencies['@geoman-io/leaflet-geoman-free']).toBeTruthy();
  });

  it('documents Valley/FieldView-inspired workflows without tying them to one library', () => {
    expect(drawingTypes).toContain("'design-pivot'");
    expect(drawingTypes).toContain("'create-prescription-zone'");
    expect(adr).toContain('Valley-style pivot');
    expect(adr).toContain('FieldView-style prescription');
  });
});

describe('DrawingCore — geometry validation and measurement contract', () => {
  const polygon: DrawFeature = {
    id: 'field-1',
    kind: 'field',
    geometry: {
      type: 'Polygon',
      coordinates: [[
        [44.0, 15.0],
        [44.01, 15.0],
        [44.01, 15.01],
        [44.0, 15.01],
        [44.0, 15.0],
      ]],
    },
    properties: { workflow: 'create-field' },
    version: 1,
    draft: true,
  };

  it('measures polygons and lines for UI feedback', () => {
    const measurements = measureDrawFeature(polygon);
    expect(measurements.areaHa).toBeGreaterThan(100);
    expect(measurements.perimeterM).toBeGreaterThan(1000);
  });

  it('validates closed polygons and catches unclosed rings', () => {
    expect(validateDrawFeature(polygon).valid).toBe(true);
    const broken: DrawFeature = {
      ...polygon,
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [44.0, 15.0],
          [44.01, 15.0],
          [44.01, 15.01],
          [44.0, 15.01],
        ]],
      },
    };
    expect(validateDrawFeature(broken).issues.some((i) => i.code === 'ring-not-closed')).toBe(true);
  });

  it('validates pivot radius as a first-class agricultural drawing rule', () => {
    const pivot: DrawFeature = {
      id: 'pivot-1',
      kind: 'pivot',
      geometry: { type: 'Point', coordinates: [44.0, 15.0] },
      properties: { workflow: 'design-pivot' },
      measurements: { radiusM: 12 },
      version: 1,
      draft: true,
    };
    expect(validateDrawFeature(pivot, { minRadiusM: 50 }).valid).toBe(false);
  });
});
