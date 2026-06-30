// @vitest-environment node
import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const pivot = readFileSync(join(root, 'src/components/maphub/drawing/pivotDesigner.ts'), 'utf8');
const topology = readFileSync(join(root, 'src/components/maphub/drawing/topologyValidation.ts'), 'utf8');
const workflows = readFileSync(join(root, 'src/components/maphub/drawing/workflows/agriculturalDrawingWorkflows.ts'), 'utf8');
const exportsFile = readFileSync(join(root, 'src/components/maphub/drawing/index.ts'), 'utf8');

describe('remaining drawing phases static contract', () => {
  it('ships the Pivot Designer primitives needed before UI wiring', () => {
    expect(pivot).toContain('buildPivotDrawFeature');
    expect(pivot).toContain('buildPivotRings');
    expect(pivot).toContain('clockwiseSweepDeg');
    expect(pivot).toContain('sectorStartDeg');
    expect(pivot).toContain('radius_m');
  });

  it('ships topology validation hooks before backend PostGIS authority', () => {
    expect(topology).toContain('validateTopology');
    expect(topology).toContain('outside-parent-boundary');
    expect(topology).toContain('overlap-not-allowed');
    expect(topology).toContain('PostGIS');
  });

  it('ships agricultural drawing workflows for FieldView-style zones', () => {
    expect(workflows).toContain('create-management-zone');
    expect(workflows).toContain('create-prescription-zone');
    expect(workflows).toContain('auditEvent');
    expect(workflows).toContain('sourceLayer');
  });

  it('exports all new contracts from the drawing barrel', () => {
    expect(exportsFile).toContain("export * from './pivotDesigner'");
    expect(exportsFile).toContain("export * from './topologyValidation'");
    expect(exportsFile).toContain("export * from './workflows'");
  });
});
