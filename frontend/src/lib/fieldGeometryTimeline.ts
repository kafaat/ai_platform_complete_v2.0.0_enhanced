// SAHOOL — fieldGeometryTimeline.ts
// أدوات نقية لبناء Timeline + Comparison Mode لهندسة الحقول.
// لا تحفظ ولا تغيّر الخادم: تقارن مراجعتين من سجل /geometry/history أو الأصل الحالي.
import { areaSqMeters } from './geo';
import { countVertices, featureToGeometry, toTurfFeature, type ArealGeometry } from './fieldGeometryOps';

export interface GeometryRevision {
  revision: number;
  geometry: unknown;
  changed_by?: string | null;
  changed_at?: string | null;
  reason?: string | null;
  source?: string | null;
  metadata?: Record<string, unknown>;
}

export interface GeometryComparison {
  baseRevision: number | 'current';
  compareRevision: number | 'current';
  baseAreaM2: number;
  compareAreaM2: number;
  areaDeltaM2: number;
  areaDeltaPct: number | null;
  baseVertices: number;
  compareVertices: number;
  verticesDelta: number;
  baseType: 'Polygon' | 'MultiPolygon' | null;
  compareType: 'Polygon' | 'MultiPolygon' | null;
}

export function normalizeTimelineGeometry(geometry: unknown): ArealGeometry | null {
  return featureToGeometry(toTurfFeature(geometry));
}

export function buildGeometryRevisionOptions(
  currentGeometry: unknown,
  revisions: ReadonlyArray<GeometryRevision>,
): GeometryRevision[] {
  const current = normalizeTimelineGeometry(currentGeometry);
  const normalized = revisions
    .map((r) => ({ ...r, geometry: normalizeTimelineGeometry(r.geometry) }))
    .filter((r): r is GeometryRevision & { geometry: ArealGeometry } => !!r.geometry)
    .sort((a, b) => b.revision - a.revision);
  return current
    ? [{ revision: 0, geometry: current, reason: 'current', source: 'field.current' }, ...normalized]
    : normalized;
}

export function compareGeometryRevisions(
  base: { revision: number | 'current'; geometry: unknown },
  compare: { revision: number | 'current'; geometry: unknown },
): GeometryComparison | null {
  const baseGeom = normalizeTimelineGeometry(base.geometry);
  const compareGeom = normalizeTimelineGeometry(compare.geometry);
  if (!baseGeom || !compareGeom) return null;

  const baseAreaM2 = areaSqMeters(baseGeom);
  const compareAreaM2 = areaSqMeters(compareGeom);
  const areaDeltaM2 = compareAreaM2 - baseAreaM2;
  const areaDeltaPct = baseAreaM2 > 0 ? (areaDeltaM2 / baseAreaM2) * 100 : null;
  const baseVertices = countVertices(baseGeom);
  const compareVertices = countVertices(compareGeom);

  return {
    baseRevision: base.revision,
    compareRevision: compare.revision,
    baseAreaM2,
    compareAreaM2,
    areaDeltaM2,
    areaDeltaPct,
    baseVertices,
    compareVertices,
    verticesDelta: compareVertices - baseVertices,
    baseType: baseGeom.type,
    compareType: compareGeom.type,
  };
}

export function revisionLabel(revision: number): string {
  return revision === 0 ? 'الحالي' : `مراجعة ${revision}`;
}
