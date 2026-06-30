import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(__dirname, '../../../..');
const zoneDesigner = readFileSync(resolve(root, 'src/components/maphub/drawing/zoneDesigner.ts'), 'utf8');
const mapHub = readFileSync(resolve(root, 'src/sections/MapHub.tsx'), 'utf8');
const hubMap = readFileSync(resolve(root, 'src/components/maphub/HubMap.tsx'), 'utf8');
const api = readFileSync(resolve(root, 'src/components/maphub/drawing/drawingFeatureApi.ts'), 'utf8');
const barrel = readFileSync(resolve(root, 'src/components/maphub/drawing/index.ts'), 'utf8');

describe('v40 Management/Prescription Zone UI contract', () => {
  it('ships a zone designer builder with agricultural workflows and prescription metadata', () => {
    expect(zoneDesigner).toContain('buildAgriculturalZoneFeature');
    expect(zoneDesigner).toContain('management-zone');
    expect(zoneDesigner).toContain('prescription-zone');
    expect(zoneDesigner).toContain('exclusion-zone');
    expect(zoneDesigner).toContain('rateUnit');
    expect(zoneDesigner).toContain('sourceLayer');
    expect(zoneDesigner).toContain('create-prescription-zone');
  });

  it('wires the zone workflow into MapHub without reusing pin or pivot click modes', () => {
    expect(mapHub).toContain('btn-zone-designer');
    expect(mapHub).toContain('zone-designer-panel');
    expect(mapHub).toContain('handleCreateZoneFromField');
    expect(mapHub).toContain('setPivotDesigner(false)');
    expect(mapHub).toContain('setPinMode(false)');
    expect(mapHub).toContain('createDrawingFeature(feature)');
  });

  it('renders persisted zones on the same drawing overlay channel with kind-specific styling', () => {
    expect(mapHub).toContain('...zonePersisted');
    expect(hubMap).toContain("feature.kind === 'prescription-zone'");
    expect(hubMap).toContain("feature.kind === 'management-zone'");
    expect(hubMap).toContain("feature.kind === 'exclusion-zone'");
    expect(hubMap).toContain('drawFeatureLabel');
  });

  it('exports zone tools and topology validation API from DrawingCore', () => {
    expect(api).toContain('validateDrawingFeatureTopology');
    expect(api).toContain('/api/v1/drawing-features/validate');
    expect(barrel).toContain("export * from './zoneDesigner'");
  });
});
