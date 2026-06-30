// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { selectDrawingEngine } from './createDrawingAdapter';

describe('selectDrawingEngine — pure flag resolution', () => {
  it("normalizes the 'geoman' alias to 'leaflet-geoman'", () => {
    expect(selectDrawingEngine('geoman')).toBe('leaflet-geoman');
  });

  it("passes through 'leaflet-geoman' unchanged", () => {
    expect(selectDrawingEngine('leaflet-geoman')).toBe('leaflet-geoman');
  });

  it("passes through 'terra-draw' unchanged", () => {
    expect(selectDrawingEngine('terra-draw')).toBe('terra-draw');
  });

  it("passes through 'maplibre-terra-draw' unchanged", () => {
    expect(selectDrawingEngine('maplibre-terra-draw')).toBe('maplibre-terra-draw');
  });

  it("defaults undefined to 'leaflet-draw'", () => {
    expect(selectDrawingEngine(undefined)).toBe('leaflet-draw');
  });

  it("defaults null to 'leaflet-draw'", () => {
    expect(selectDrawingEngine(null)).toBe('leaflet-draw');
  });

  it("defaults garbage values to 'leaflet-draw' (fallback present)", () => {
    expect(selectDrawingEngine('not-a-real-engine')).toBe('leaflet-draw');
    expect(selectDrawingEngine('')).toBe('leaflet-draw');
  });
});
