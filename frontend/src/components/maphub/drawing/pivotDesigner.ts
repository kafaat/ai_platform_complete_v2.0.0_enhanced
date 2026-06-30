import type { DrawFeature, DrawMeasurements, Position } from './drawingTypes';
import { validateDrawFeature, type DrawingValidationOptions } from './drawingValidation';

const EARTH_RADIUS_M = 6378137;

export interface PivotDesignInput {
  center: Position;
  radiusM: number;
  startAngleDeg?: number;
  endAngleDeg?: number;
  vertices?: number;
  ringCount?: number;
  spanCount?: number;
  name?: string;
  fieldId?: string;
  seasonId?: string;
}

export interface PivotDesignSummary {
  center: Position;
  radiusM: number;
  startAngleDeg: number;
  endAngleDeg: number;
  sweepDeg: number;
  areaHa: number;
  circumferenceM: number;
  ringCount: number;
  spanCount: number;
  valid: boolean;
  issues: string[];
}

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function toDeg(rad: number): number {
  return (rad * 180) / Math.PI;
}

export function normalizeBearingDeg(value: number | undefined, fallback = 0): number {
  const raw = typeof value === 'number' && Number.isFinite(value) ? value : fallback;
  return ((raw % 360) + 360) % 360;
}

export function clockwiseSweepDeg(startDeg = 0, endDeg = 360): number {
  const start = normalizeBearingDeg(startDeg);
  const end = normalizeBearingDeg(endDeg, 360);
  if (Math.abs((endDeg ?? 360) - (startDeg ?? 0)) >= 360) return 360;
  const sweep = (end - start + 360) % 360;
  return sweep === 0 ? 360 : sweep;
}

export function destinationPoint(center: Position, bearingDeg: number, distanceM: number): Position {
  const [lon, lat] = center;
  const brng = toRad(bearingDeg);
  const lat1 = toRad(lat);
  const lon1 = toRad(lon);
  const d = distanceM / EARTH_RADIUS_M;
  const lat2 = Math.asin(
    Math.sin(lat1) * Math.cos(d) + Math.cos(lat1) * Math.sin(d) * Math.cos(brng),
  );
  const lon2 = lon1 + Math.atan2(
    Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
    Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
  );
  return [toDeg(lon2), toDeg(lat2)];
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

export function summarizePivotDesign(input: PivotDesignInput): PivotDesignSummary {
  const startAngleDeg = normalizeBearingDeg(input.startAngleDeg, 0);
  const endAngleDeg = input.endAngleDeg === undefined ? 360 : normalizeBearingDeg(input.endAngleDeg, 360);
  const sweepDeg = clockwiseSweepDeg(input.startAngleDeg ?? 0, input.endAngleDeg ?? 360);
  const ringCount = Math.max(1, Math.round(input.ringCount ?? 1));
  const spanCount = Math.max(1, Math.round(input.spanCount ?? 1));
  const issues: string[] = [];
  if (!isPosition(input.center)) issues.push('invalid-center');
  if (!Number.isFinite(input.radiusM) || input.radiusM <= 0) issues.push('invalid-radius');
  if (input.radiusM > 2500) issues.push('radius-too-large');
  if (sweepDeg <= 0 || sweepDeg > 360) issues.push('invalid-sector');
  const areaHa = (Math.PI * input.radiusM ** 2 * (sweepDeg / 360)) / 10000;
  const circumferenceM = 2 * Math.PI * input.radiusM * (sweepDeg / 360);
  return {
    center: input.center,
    radiusM: input.radiusM,
    startAngleDeg,
    endAngleDeg,
    sweepDeg,
    areaHa,
    circumferenceM,
    ringCount,
    spanCount,
    valid: issues.length === 0,
    issues,
  };
}

export function buildPivotSectorRing(input: PivotDesignInput): Position[] {
  const summary = summarizePivotDesign(input);
  const vertices = Math.max(12, Math.min(180, Math.round(input.vertices ?? 72)));
  const steps = Math.max(2, Math.ceil(vertices * (summary.sweepDeg / 360)));
  const ring: Position[] = [input.center];
  for (let i = 0; i <= steps; i += 1) {
    const bearing = summary.startAngleDeg + (summary.sweepDeg * i) / steps;
    ring.push(destinationPoint(input.center, bearing, input.radiusM));
  }
  ring.push(input.center);
  return ring;
}

export function buildPivotDrawFeature(input: PivotDesignInput): DrawFeature {
  const summary = summarizePivotDesign(input);
  const measurements: DrawMeasurements = {
    areaHa: summary.areaHa,
    perimeterM: summary.circumferenceM + (summary.sweepDeg < 360 ? input.radiusM * 2 : 0),
    radiusM: input.radiusM,
    sectorStartDeg: summary.startAngleDeg,
    sectorEndDeg: summary.endAngleDeg,
    ringCount: summary.ringCount,
  };
  const feature: DrawFeature = {
    id: `pivot-${Date.now().toString(36)}`,
    kind: 'pivot',
    geometry: {
      type: 'Polygon',
      coordinates: [buildPivotSectorRing(input)],
    },
    properties: {
      name: input.name,
      fieldId: input.fieldId,
      seasonId: input.seasonId,
      workflow: 'design-pivot',
      pivot: {
        center: { lon: input.center[0], lat: input.center[1] },
        radius_m: input.radiusM,
        start_angle_deg: summary.startAngleDeg,
        end_angle_deg: summary.endAngleDeg,
        ring_count: summary.ringCount,
        span_count: summary.spanCount,
      },
    },
    measurements,
    version: 1,
    draft: true,
    createdAt: new Date().toISOString(),
  };
  feature.validation = validateDrawFeature(feature, defaultPivotValidationOptions());
  return feature;
}

export function defaultPivotValidationOptions(): DrawingValidationOptions {
  return { minRadiusM: 30, maxRadiusM: 2500, minAreaHa: 0.05, maxAreaHa: 2500 };
}

export function buildPivotRings(input: PivotDesignInput): DrawFeature[] {
  const ringCount = Math.max(1, Math.round(input.ringCount ?? 1));
  const output: DrawFeature[] = [];
  for (let ring = 1; ring <= ringCount; ring += 1) {
    const outer = (input.radiusM * ring) / ringCount;
    const inner = (input.radiusM * (ring - 1)) / ringCount;
    const feature = buildPivotDrawFeature({ ...input, radiusM: outer, name: `${input.name ?? 'Pivot'} R${ring}` });
    feature.id = `pivot-ring-${ring}-${Date.now().toString(36)}`;
    feature.properties.ringIndex = ring;
    feature.properties.innerRadiusM = inner;
    feature.properties.outerRadiusM = outer;
    output.push(feature);
  }
  return output;
}
