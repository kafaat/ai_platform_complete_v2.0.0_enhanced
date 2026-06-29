import { describe, expect, it } from 'vitest';
import { buildGeometryRevisionOptions, compareGeometryRevisions, normalizeTimelineGeometry, revisionLabel } from './fieldGeometryTimeline';

const poly = (lon: number, lat: number, size = 0.01) => ({
  type: 'Polygon' as const,
  coordinates: [[[lon, lat], [lon + size, lat], [lon + size, lat + size], [lon, lat + size], [lon, lat]]],
});

const multi = {
  type: 'MultiPolygon' as const,
  coordinates: [poly(44.95, 16.09).coordinates, poly(45.05, 16.19).coordinates],
};

describe('fieldGeometryTimeline', () => {
  it('normalizes Polygon and MultiPolygon timeline geometries without dropping parts', () => {
    expect(normalizeTimelineGeometry(poly(44.9, 16.1))?.type).toBe('Polygon');
    const g = normalizeTimelineGeometry(multi);
    expect(g?.type).toBe('MultiPolygon');
    expect(g && g.type === 'MultiPolygon' ? g.coordinates.length : 0).toBe(2);
  });

  it('prepends the current geometry and sorts historical revisions newest first', () => {
    const options = buildGeometryRevisionOptions(poly(44.9, 16.1), [
      { revision: 1, geometry: poly(44.91, 16.1), changed_at: '2026-01-01T00:00:00Z' },
      { revision: 3, geometry: poly(44.93, 16.1), changed_at: '2026-01-03T00:00:00Z' },
    ]);
    expect(options.map((o) => o.revision)).toEqual([0, 3, 1]);
  });

  it('computes area and vertex deltas for comparison mode', () => {
    const c = compareGeometryRevisions(
      { revision: 1, geometry: poly(44.9, 16.1, 0.01) },
      { revision: 'current', geometry: poly(44.9, 16.1, 0.02) },
    );
    expect(c).not.toBeNull();
    expect(c!.compareAreaM2).toBeGreaterThan(c!.baseAreaM2);
    expect(c!.areaDeltaPct).toBeGreaterThan(250);
    expect(c!.verticesDelta).toBe(0);
  });

  it('labels current and numbered revisions for RTL UI', () => {
    expect(revisionLabel(0)).toBe('الحالي');
    expect(revisionLabel(12)).toBe('مراجعة 12');
  });
});
