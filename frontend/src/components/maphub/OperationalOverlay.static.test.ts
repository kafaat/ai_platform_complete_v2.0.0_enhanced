import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const overlay = readFileSync(join(root, 'src/components/maphub/OverlayMarkers.tsx'), 'utf8');
// UI7: أدوات الطبقات استُخرجت إلى maphub/OperationalOverlayControls.tsx — نقرأ المُركَّب.
const hub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8')
  + readFileSync(join(root, 'src/sections/maphub/OperationalOverlayControls.tsx'), 'utf8');
const gl = readFileSync(join(root, 'src/components/maphub/HubMapGL.tsx'), 'utf8');

describe('unified operational map overlays', () => {
  it('defines operational markers for equipment, tasks, and pivots', () => {
    expect(overlay).toContain("kind: 'equipment' | 'task' | 'pivot'");
    expect(overlay).toContain('export function OperationalOverlay');
    expect(overlay).toContain('sahool-operational-marker');
  });

  it('connects operational overlays to both Leaflet and MapLibre engines', () => {
    expect(hub).toContain('operationalMarkers={operationalMarkers}');
    expect(gl).toContain('operationalMarkers?: OperationalMarker[]');
    expect(gl).toContain('for (const o of operationalMarkers)');
  });

  it('keeps unplaceable operational records off the map instead of inventing coordinates', () => {
    expect(hub).toContain('equipmentUnplaceable');
    expect(hub).toContain('tasksUnplaceable');
    expect(hub).toContain('بلا حقل/هندسة');
  });
});
