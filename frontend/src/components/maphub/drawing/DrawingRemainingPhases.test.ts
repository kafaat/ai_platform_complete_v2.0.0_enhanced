import { describe, expect, it } from 'vitest';
import {
  applyWorkflowDefaults,
  buildPivotDrawFeature,
  buildPivotRings,
  checkWorkflowCommit,
  clockwiseSweepDeg,
  getWorkflowPolicy,
  pointInRing,
  validateTopology,
  type DrawFeature,
} from './index';

const parentField: DrawFeature = {
  id: 'field-parent',
  kind: 'field',
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [44.0, 15.0],
      [44.1, 15.0],
      [44.1, 15.1],
      [44.0, 15.1],
      [44.0, 15.0],
    ]],
  },
  properties: { workflow: 'create-field' },
  version: 1,
  draft: false,
};

const zone: DrawFeature = {
  id: 'zone-1',
  kind: 'management-zone',
  geometry: {
    type: 'Polygon',
    coordinates: [[
      [44.02, 15.02],
      [44.04, 15.02],
      [44.04, 15.04],
      [44.02, 15.04],
      [44.02, 15.02],
    ]],
  },
  properties: {
    workflow: 'create-management-zone',
    fieldId: 'field-parent',
    seasonId: 'season-2026',
    sourceLayer: 'ndvi',
  },
  version: 1,
  draft: true,
};

describe('v33/v34/v35 drawing phases — pivot, topology, agricultural workflows', () => {
  it('builds a Valley-style pivot sector with radius, angles, rings and area', () => {
    expect(clockwiseSweepDeg(270, 90)).toBe(180);
    const pivot = buildPivotDrawFeature({
      center: [44.05, 15.05],
      radiusM: 450,
      startAngleDeg: 0,
      endAngleDeg: 180,
      ringCount: 3,
      spanCount: 6,
      fieldId: 'field-parent',
      name: 'Pivot A',
    });
    expect(pivot.kind).toBe('pivot');
    expect(pivot.geometry.type).toBe('Polygon');
    expect(pivot.measurements?.radiusM).toBe(450);
    expect(pivot.measurements?.areaHa).toBeGreaterThan(30);
    expect(pivot.properties.pivot).toBeTruthy();
    expect(pivot.validation?.valid).toBe(true);
  });

  it('builds ring drafts for variable-rate pivot management', () => {
    const rings = buildPivotRings({ center: [44.05, 15.05], radiusM: 600, ringCount: 4, fieldId: 'field-parent' });
    expect(rings).toHaveLength(4);
    expect(rings[0].properties.ringIndex).toBe(1);
    expect(rings[3].properties.outerRadiusM).toBe(600);
  });

  it('checks parent containment and overlap before saving zones', () => {
    expect(pointInRing([44.03, 15.03], (parentField.geometry.coordinates as [number, number][][])[0])).toBe(true);
    expect(validateTopology(zone, { parentBoundary: parentField, requireInsideParent: true }).valid).toBe(true);

    const overlapping: DrawFeature = {
      ...zone,
      id: 'zone-overlap',
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [44.03, 15.03],
          [44.05, 15.03],
          [44.05, 15.05],
          [44.03, 15.05],
          [44.03, 15.03],
        ]],
      },
    };
    const result = validateTopology(overlapping, { siblingFeatures: [zone], allowOverlap: false });
    expect(result.valid).toBe(false);
    expect(result.issues.some((i) => i.code === 'overlap-not-allowed')).toBe(true);
  });

  it('enforces FieldView-style agricultural workflow metadata before commit', () => {
    const policy = getWorkflowPolicy('create-prescription-zone');
    expect(policy.requiresFieldId).toBe(true);
    expect(policy.requiresSeasonId).toBe(true);
    expect(policy.requiresSourceLayer).toBe(true);

    const normalized = applyWorkflowDefaults(zone, 'create-prescription-zone');
    expect(normalized.kind).toBe('prescription-zone');
    expect(normalized.properties.auditEvent).toBe('PRESCRIPTION_ZONE_DRAFTED');

    const ok = checkWorkflowCommit(normalized, 'create-prescription-zone', { parentBoundary: parentField });
    expect(ok.canCommit).toBe(true);

    const missingSeason: DrawFeature = { ...normalized, properties: { fieldId: 'field-parent', workflow: 'create-prescription-zone' } };
    const bad = checkWorkflowCommit(missingSeason, 'create-prescription-zone', { parentBoundary: parentField });
    expect(bad.canCommit).toBe(false);
    expect(bad.errors.join('\n')).toContain('seasonId');
  });
});
