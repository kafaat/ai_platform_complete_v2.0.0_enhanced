import { areaSqMeters, lengthMeters } from '../../../lib/geo';
import type { DrawFeature, DrawFeatureKind, DrawWorkflow, GeoJsonGeometry } from './drawingTypes';
import { validateDrawFeature } from './drawingValidation';

export type AgriculturalZoneKind = 'management-zone' | 'prescription-zone' | 'exclusion-zone';

export interface ZoneDesignInput {
  id?: string;
  kind: AgriculturalZoneKind;
  geometry: GeoJsonGeometry;
  fieldId: string;
  seasonId?: string;
  name?: string;
  crop?: string;
  sourceLayer?: string;
  rate?: number;
  rateUnit?: string;
  recommendationId?: string;
  confidence?: number;
  draft?: boolean;
}

export const ZONE_WORKFLOW_BY_KIND: Record<AgriculturalZoneKind, DrawWorkflow> = {
  'management-zone': 'create-management-zone',
  'prescription-zone': 'create-prescription-zone',
  'exclusion-zone': 'create-exclusion-zone',
};

export function normalizeFieldGeometryForZone(geometry: unknown): GeoJsonGeometry | null {
  const g = geometry as { type?: unknown; coordinates?: unknown } | null | undefined;
  if (!g || (g.type !== 'Polygon' && g.type !== 'MultiPolygon')) return null;
  if (!Array.isArray(g.coordinates)) return null;
  return { type: g.type, coordinates: g.coordinates } as GeoJsonGeometry;
}

export function buildAgriculturalZoneFeature(input: ZoneDesignInput): DrawFeature {
  const now = new Date().toISOString();
  const measurementGeometry = { type: 'Feature', properties: {}, geometry: input.geometry };
  const areaM2 = areaSqMeters(measurementGeometry);
  const perimeterM = lengthMeters(measurementGeometry);
  const feature: DrawFeature = {
    id: input.id ?? `${input.kind}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    kind: input.kind as DrawFeatureKind,
    geometry: input.geometry,
    properties: {
      name: input.name ?? defaultZoneName(input.kind),
      fieldId: input.fieldId,
      seasonId: input.seasonId,
      crop: input.crop,
      sourceLayer: input.sourceLayer,
      rate: input.rate,
      rateUnit: input.rateUnit,
      recommendationId: input.recommendationId,
      confidence: input.confidence ?? 0.75,
      workflow: ZONE_WORKFLOW_BY_KIND[input.kind],
      engine: 'leaflet-geoman',
    },
    measurements: {
      areaHa: areaM2 / 10000,
      perimeterM,
    },
    version: 1,
    draft: input.draft ?? false,
    createdAt: now,
    updatedAt: now,
  };
  feature.validation = validateDrawFeature(feature, { minAreaHa: 0.001, maxAreaHa: 100000 });
  return feature;
}

export function defaultZoneName(kind: AgriculturalZoneKind): string {
  if (kind === 'prescription-zone') return 'منطقة وصفة';
  if (kind === 'exclusion-zone') return 'منطقة استبعاد';
  return 'منطقة إدارة';
}

export function zoneKindLabel(kind: AgriculturalZoneKind): string {
  if (kind === 'prescription-zone') return 'وصفة';
  if (kind === 'exclusion-zone') return 'استبعاد';
  return 'إدارة';
}
