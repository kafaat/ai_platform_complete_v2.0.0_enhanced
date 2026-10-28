import type { DrawFeature, DrawValidationIssue, DrawValidationResult, Position } from './drawingTypes';
import { measureDrawFeature } from './drawingMeasurements';

function issue(code: DrawValidationIssue['code'], severity: DrawValidationIssue['severity'], message: string): DrawValidationIssue {
  return { code, severity, message };
}

function isPosition(value: unknown): value is Position {
  return Array.isArray(value)
    && value.length >= 2
    && typeof value[0] === 'number'
    && typeof value[1] === 'number'
    && Number.isFinite(value[0])
    && Number.isFinite(value[1])
    && Math.abs(value[0]) <= 180
    && Math.abs(value[1]) <= 90;
}

function samePosition(a: Position, b: Position): boolean {
  return Math.abs(a[0] - b[0]) < 1e-12 && Math.abs(a[1] - b[1]) < 1e-12;
}

function orientation(a: Position, b: Position, c: Position): number {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
}

function onSegment(a: Position, b: Position, p: Position): boolean {
  return Math.min(a[0], b[0]) <= p[0] && p[0] <= Math.max(a[0], b[0])
    && Math.min(a[1], b[1]) <= p[1] && p[1] <= Math.max(a[1], b[1]);
}

// Closed-segment intersection: proper crossings plus touching/collinear overlap
// (a vertex resting on a non-adjacent edge is also invalid under OGC simple-feature rules).
function segmentsIntersect(a: Position, b: Position, c: Position, d: Position): boolean {
  const o1 = orientation(a, b, c);
  const o2 = orientation(a, b, d);
  const o3 = orientation(c, d, a);
  const o4 = orientation(c, d, b);
  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) return true;
  return (o1 === 0 && onSegment(a, b, c))
    || (o2 === 0 && onSegment(a, b, d))
    || (o3 === 0 && onSegment(c, d, a))
    || (o4 === 0 && onSegment(c, d, b));
}

function ringSelfIntersectionRisk(ring: Position[]): boolean {
  // (1) duplicate non-adjacent vertices (e.g. SAM2 pixel-stair rings collapsing after reprojection).
  const seen = new Map<string, number>();
  for (let i = 0; i < ring.length - 1; i += 1) {
    const key = `${ring[i][0].toFixed(7)},${ring[i][1].toFixed(7)}`;
    const prev = seen.get(key);
    if (prev !== undefined && Math.abs(prev - i) > 1) return true;
    seen.set(key, i);
  }
  // (2) any two non-adjacent edges intersect (a bowtie has four distinct vertices, so (1) misses it).
  // Same pairwise rule as backend geospatial_integrity.has_self_intersection; PostGIS stays authoritative.
  // Consecutive repeats (double-click finish) are zero-length edges, not crossings: drop them first.
  const pts = ring.filter((p, i) => i === 0 || !samePosition(p, ring[i - 1]));
  const n = pts.length - 1; // edges of the closed ring: (i, i+1) for i in [0, n)
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 2; j < n; j += 1) {
      if (i === 0 && j === n - 1) continue; // first and closing edge share the start vertex
      if (segmentsIntersect(pts[i], pts[i + 1], pts[j], pts[j + 1])) return true;
    }
  }
  return false;
}

export interface DrawingValidationOptions {
  minAreaHa?: number;
  maxAreaHa?: number;
  minRadiusM?: number;
  maxRadiusM?: number;
}

export function validateDrawFeature(feature: DrawFeature, options: DrawingValidationOptions = {}): DrawValidationResult {
  const issues: DrawValidationIssue[] = [];
  const geom = feature.geometry;

  if (!geom || !geom.type) {
    issues.push(issue('empty-geometry', 'error', 'الهندسة فارغة.'));
    return { valid: false, issues };
  }

  if (!['Point', 'LineString', 'Polygon', 'MultiPolygon'].includes(geom.type)) {
    issues.push(issue('unsupported-geometry', 'error', `نوع الهندسة غير مدعوم: ${geom.type}`));
  }

  if (geom.type === 'Point') {
    if (!isPosition(geom.coordinates)) issues.push(issue('invalid-coordinate', 'error', 'إحداثيات النقطة غير صالحة.'));
  }

  if (geom.type === 'LineString') {
    const line = geom.coordinates;
    if (!Array.isArray(line) || line.length < 2 || !line.every(isPosition)) {
      issues.push(issue('invalid-coordinate', 'error', 'خط الرسم يحتاج نقطتين صالحتين على الأقل.'));
    }
  }

  if (geom.type === 'Polygon') {
    const polygon = geom.coordinates;
    const ring = Array.isArray(polygon) ? polygon[0] : undefined;
    if (!Array.isArray(ring) || ring.length < 4 || !ring.every(isPosition)) {
      issues.push(issue('too-few-vertices', 'error', 'المضلّع يحتاج 3 رؤوس وإغلاقاً صالحاً.'));
    } else {
      if (!samePosition(ring[0], ring[ring.length - 1])) {
        issues.push(issue('ring-not-closed', 'error', 'حلقة المضلّع غير مغلقة.'));
      }
      if (ringSelfIntersectionRisk(ring)) {
        issues.push(issue('self-intersection-risk', 'warning', 'يوجد مؤشر تقاطع ذاتي أو رأس مكرر داخل المضلّع.'));
      }
      const measurements = measureDrawFeature(feature);
      if (options.minAreaHa !== undefined && (measurements.areaHa ?? 0) < options.minAreaHa) {
        issues.push(issue('area-out-of-range', 'error', `مساحة الشكل أقل من الحد الأدنى ${options.minAreaHa} ha.`));
      }
      if (options.maxAreaHa !== undefined && (measurements.areaHa ?? 0) > options.maxAreaHa) {
        issues.push(issue('area-out-of-range', 'error', `مساحة الشكل أكبر من الحد الأقصى ${options.maxAreaHa} ha.`));
      }
    }
  }

  if (feature.kind === 'pivot') {
    const radius = feature.measurements?.radiusM;
    if (typeof radius !== 'number' || !Number.isFinite(radius)) {
      issues.push(issue('pivot-radius-invalid', 'error', 'تصميم Pivot يحتاج نصف قطر واضح بالمتر.'));
    } else {
      if (options.minRadiusM !== undefined && radius < options.minRadiusM) {
        issues.push(issue('pivot-radius-invalid', 'error', `نصف قطر Pivot أقل من ${options.minRadiusM}m.`));
      }
      if (options.maxRadiusM !== undefined && radius > options.maxRadiusM) {
        issues.push(issue('pivot-radius-invalid', 'error', `نصف قطر Pivot أكبر من ${options.maxRadiusM}m.`));
      }
    }
  }

  return { valid: !issues.some((i) => i.severity === 'error'), issues };
}
