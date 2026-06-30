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

function ringSelfIntersectionRisk(ring: Position[]): boolean {
  // Lightweight guard: duplicate non-adjacent vertices often indicate accidental crossing.
  const seen = new Map<string, number>();
  for (let i = 0; i < ring.length - 1; i += 1) {
    const key = `${ring[i][0].toFixed(7)},${ring[i][1].toFixed(7)}`;
    const prev = seen.get(key);
    if (prev !== undefined && Math.abs(prev - i) > 1) return true;
    seen.set(key, i);
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
