import type { DrawFeature, DrawValidationIssue, DrawValidationResult, Position } from './drawingTypes';

interface BBox { minX: number; minY: number; maxX: number; maxY: number }

export interface TopologyValidationOptions {
  parentBoundary?: DrawFeature;
  siblingFeatures?: DrawFeature[];
  requireInsideParent?: boolean;
  allowOverlap?: boolean;
  requireNoGaps?: boolean;
}

function issue(code: DrawValidationIssue['code'], severity: DrawValidationIssue['severity'], message: string): DrawValidationIssue {
  return { code, severity, message };
}

function isPosition(value: unknown): value is Position {
  return Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number';
}

export function outerRing(feature: DrawFeature): Position[] {
  const geom = feature.geometry;
  if (geom.type === 'Polygon' && Array.isArray(geom.coordinates)) {
    const ring = geom.coordinates[0];
    return Array.isArray(ring) && ring.every(isPosition) ? ring : [];
  }
  if (geom.type === 'MultiPolygon' && Array.isArray(geom.coordinates)) {
    const firstPoly = geom.coordinates[0];
    const ring = Array.isArray(firstPoly) ? firstPoly[0] : undefined;
    return Array.isArray(ring) && ring.every(isPosition) ? ring : [];
  }
  return [];
}

export function bboxOfFeature(feature: DrawFeature): BBox | null {
  const ring = outerRing(feature);
  if (ring.length === 0) return null;
  return ring.reduce<BBox>((acc, [x, y]) => ({
    minX: Math.min(acc.minX, x),
    minY: Math.min(acc.minY, y),
    maxX: Math.max(acc.maxX, x),
    maxY: Math.max(acc.maxY, y),
  }), { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity });
}

function bboxContains(a: BBox, b: BBox): boolean {
  return b.minX >= a.minX && b.maxX <= a.maxX && b.minY >= a.minY && b.maxY <= a.maxY;
}

function bboxIntersects(a: BBox, b: BBox): boolean {
  return a.minX <= b.maxX && a.maxX >= b.minX && a.minY <= b.maxY && a.maxY >= b.minY;
}

export function pointInRing(point: Position, ring: Position[]): boolean {
  const [x, y] = point;
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i, i += 1) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const intersect = ((yi > y) !== (yj > y))
      && (x < ((xj - xi) * (y - yi)) / ((yj - yi) || Number.EPSILON) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}

function orientation(a: Position, b: Position, c: Position): number {
  return (b[1] - a[1]) * (c[0] - b[0]) - (b[0] - a[0]) * (c[1] - b[1]);
}

function segmentsIntersect(a: Position, b: Position, c: Position, d: Position): boolean {
  const o1 = orientation(a, b, c);
  const o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a);
  const o4 = orientation(c, d, b);
  return (o1 > 0) !== (o2 > 0) && (o3 > 0) !== (o4 > 0);
}

export function ringsIntersect(a: Position[], b: Position[]): boolean {
  for (let i = 1; i < a.length; i += 1) {
    for (let j = 1; j < b.length; j += 1) {
      if (segmentsIntersect(a[i - 1], a[i], b[j - 1], b[j])) return true;
    }
  }
  return false;
}

export function validateTopology(feature: DrawFeature, options: TopologyValidationOptions = {}): DrawValidationResult {
  const issues: DrawValidationIssue[] = [];
  const featureBox = bboxOfFeature(feature);
  const ring = outerRing(feature);

  if (!featureBox || ring.length === 0) return { valid: true, issues };

  if (options.requireInsideParent && options.parentBoundary) {
    const parentBox = bboxOfFeature(options.parentBoundary);
    const parentRing = outerRing(options.parentBoundary);
    const allVerticesInside = parentRing.length > 0 && ring.every((p) => pointInRing(p, parentRing) || parentRing.some((q) => q[0] === p[0] && q[1] === p[1]));
    if (!parentBox || !bboxContains(parentBox, featureBox) || !allVerticesInside) {
      issues.push(issue('outside-parent-boundary', 'error', 'الشكل خارج حدود الحقل/المزرعة الأب.'));
    }
  }

  if (!options.allowOverlap && options.siblingFeatures?.length) {
    for (const sibling of options.siblingFeatures) {
      const siblingBox = bboxOfFeature(sibling);
      if (!siblingBox || !bboxIntersects(featureBox, siblingBox)) continue;
      const siblingRing = outerRing(sibling);
      if (ringsIntersect(ring, siblingRing) || ring.some((p) => pointInRing(p, siblingRing)) || siblingRing.some((p) => pointInRing(p, ring))) {
        issues.push(issue('overlap-not-allowed', 'error', 'يوجد تداخل غير مسموح مع منطقة مرسومة أخرى.'));
        break;
      }
    }
  }

  if (options.requireNoGaps) {
    issues.push(issue('gap-not-allowed', 'info', 'فحص الفجوات النهائي يجب أن يُنفذ في PostGIS قبل الاعتماد.'));
  }

  return { valid: !issues.some((i) => i.severity === 'error'), issues };
}
