import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const mapHub = readFileSync(join(root, 'src/sections/MapHub.tsx'), 'utf8');
const hubMap = readFileSync(join(root, 'src/components/maphub/HubMap.tsx'), 'utf8');

describe('MapHub v36 pivot designer activation', () => {
  it('exposes a visible Pivot Designer toggle and keeps click modes mutually exclusive', () => {
    expect(mapHub).toContain('btn-pivot-designer');
    expect(mapHub).toContain('تصميم Pivot');
    expect(mapHub).toContain('setPinMode(false)');
    expect(mapHub).toContain('setDrawTools(false)');
    expect(mapHub).toContain('setCompare(false)');
  });

  it('binds pivot controls to radius, sector angles, rings, and spans', () => {
    expect(mapHub).toContain('pivotRadiusM');
    expect(mapHub).toContain('pivotStartAngleDeg');
    expect(mapHub).toContain('pivotEndAngleDeg');
    expect(mapHub).toContain('pivotRingCount');
    expect(mapHub).toContain('pivotSpanCount');
    expect(mapHub).toContain('pivot-designer-panel');
  });

  it('creates local DrawFeature pivot drafts through the shared pivotDesigner primitive', () => {
    expect(mapHub).toContain('buildPivotDrawFeature');
    expect(mapHub).toContain('handleAddPivotDraft');
    expect(mapHub).toContain('draft=true');
    expect(mapHub).toContain('setPivotDrafts');
  });

  it('passes pivot designer props into HubMap for map-click center selection', () => {
    expect(mapHub).toContain('pivotDesignerEnabled={pivotDesigner}');
    expect(mapHub).toContain('onAddPivotDraft={handleAddPivotDraft}');
    expect(mapHub).toContain('pivotDrafts={showPivots ? [...pivotPersisted');
  });

  it('renders pivot draft polygons and a map-click hint inside HubMap', () => {
    expect(hubMap).toContain('PivotDesignerClickHandler');
    expect(hubMap).toContain('drawFeaturePolygonPositions');
    expect(hubMap).toContain('pivot-designer-map-hint');
    expect(hubMap).toContain('pivotDrafts.map');
  });
});
