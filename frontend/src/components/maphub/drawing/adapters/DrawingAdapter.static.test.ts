// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const adapterDir = join(root, 'src/components/maphub/drawing/adapters');
const leafletDrawSrc = readFileSync(join(adapterDir, 'LeafletDrawAdapter.ts'), 'utf8');
const geomanSrc = readFileSync(join(adapterDir, 'LeafletGeomanAdapter.ts'), 'utf8');

const CONTRACT_METHODS = ['start(', 'stop(', 'setFeatures(', 'getFeatures(', 'on('];

describe('Drawing adapters — DrawingAdapter contract (static)', () => {
  it('ships both adapter source files', () => {
    expect(existsSync(join(adapterDir, 'LeafletDrawAdapter.ts'))).toBe(true);
    expect(existsSync(join(adapterDir, 'LeafletGeomanAdapter.ts'))).toBe(true);
  });

  it('each adapter declares `implements DrawingAdapter`', () => {
    expect(leafletDrawSrc).toContain('class LeafletDrawAdapter implements DrawingAdapter');
    expect(geomanSrc).toContain('class LeafletGeomanAdapter implements DrawingAdapter');
  });

  it('each adapter exposes the full contract surface', () => {
    for (const method of CONTRACT_METHODS) {
      expect(leafletDrawSrc).toContain(method);
      expect(geomanSrc).toContain(method);
    }
  });

  it('each adapter emits unified events via createDrawingEvent', () => {
    expect(leafletDrawSrc).toContain('createDrawingEvent');
    expect(leafletDrawSrc).toContain("'draw:created'");
    expect(leafletDrawSrc).toContain("'draw:measurement-change'");
    expect(leafletDrawSrc).toContain("'draw:validated'");
    expect(geomanSrc).toContain('createDrawingEvent');
    expect(geomanSrc).toContain("'draw:created'");
    expect(geomanSrc).toContain("'draw:edited'");
    expect(geomanSrc).toContain("'draw:deleted'");
    expect(geomanSrc).toContain("'draw:vertex-change'");
  });

  it('each adapter reuses the shared measurement + validation helpers', () => {
    for (const src of [leafletDrawSrc, geomanSrc]) {
      expect(src).toContain('measureDrawFeature');
      expect(src).toContain('validateDrawFeature');
    }
  });

  it('LeafletDrawAdapter uses raw leaflet-draw, NOT react-leaflet-draw', () => {
    expect(leafletDrawSrc).toContain("import 'leaflet-draw'");
    expect(leafletDrawSrc).not.toContain('react-leaflet-draw');
  });
});
