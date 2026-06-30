// ═══════════════════════════════════════════════════════════════
// SAHOOL — DrawingCore contract
// محايد عن محرّك الخريطة: Leaflet/Geoman/TerraDraw/MapLibre.
// الهدف: ألّا تنتشر تفاصيل leaflet-draw داخل الشاشات الزراعية.
// ═══════════════════════════════════════════════════════════════

export type DrawingEngineId = 'leaflet-draw' | 'leaflet-geoman' | 'terra-draw' | 'maplibre-terra-draw';

export type DrawFeatureKind =
  | 'field'
  | 'pivot'
  | 'management-zone'
  | 'prescription-zone'
  | 'exclusion-zone'
  | 'scout-pin'
  | 'path'
  | 'measurement';

export type DrawWorkflow =
  | 'create-field'
  | 'design-pivot'
  | 'split-field'
  | 'merge-fields'
  | 'create-management-zone'
  | 'create-prescription-zone'
  | 'create-exclusion-zone'
  | 'measure-area'
  | 'measure-distance';

export type GeometryType = 'Point' | 'LineString' | 'Polygon' | 'MultiPolygon';
export type Position = [longitude: number, latitude: number];

export interface GeoJsonGeometry {
  type: GeometryType;
  coordinates: unknown;
}

export interface DrawMeasurements {
  areaHa?: number;
  perimeterM?: number;
  lengthM?: number;
  radiusM?: number;
  bearingDeg?: number;
  sectorStartDeg?: number;
  sectorEndDeg?: number;
  ringCount?: number;
}

export interface DrawValidationIssue {
  code:
    | 'empty-geometry'
    | 'unsupported-geometry'
    | 'invalid-coordinate'
    | 'ring-not-closed'
    | 'too-few-vertices'
    | 'self-intersection-risk'
    | 'outside-parent-boundary'
    | 'overlap-not-allowed'
    | 'gap-not-allowed'
    | 'pivot-radius-invalid'
    | 'area-out-of-range';
  severity: 'info' | 'warning' | 'error';
  message: string;
}

export interface DrawValidationResult {
  valid: boolean;
  issues: DrawValidationIssue[];
}

export interface DrawFeatureProperties {
  name?: string;
  crop?: string;
  seasonId?: string;
  fieldId?: string;
  farmId?: string;
  operationId?: string;
  sourceLayer?: string;
  confidence?: number;
  engine?: DrawingEngineId;
  workflow?: DrawWorkflow;
  [key: string]: unknown;
}

export interface DrawFeature {
  id: string;
  kind: DrawFeatureKind;
  geometry: GeoJsonGeometry;
  properties: DrawFeatureProperties;
  measurements?: DrawMeasurements;
  validation?: DrawValidationResult;
  version: number;
  draft: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface DrawEngineCapabilities {
  drawPolygon: boolean;
  drawLine: boolean;
  drawPoint: boolean;
  drawCircle: boolean;
  drawRectangle: boolean;
  editVertices: boolean;
  dragFeature: boolean;
  rotateFeature: boolean;
  cutPolygon: boolean;
  splitPolygon: boolean;
  snapping: boolean;
  measurements: boolean;
  undoRedo: boolean;
  mobileTouch: boolean;
  mapLibreReady: boolean;
}

export const DRAW_ENGINE_CAPABILITIES: Record<DrawingEngineId, DrawEngineCapabilities> = {
  'leaflet-draw': {
    drawPolygon: true,
    drawLine: true,
    drawPoint: true,
    drawCircle: true,
    drawRectangle: true,
    editVertices: true,
    dragFeature: false,
    rotateFeature: false,
    cutPolygon: false,
    splitPolygon: false,
    snapping: false,
    measurements: false,
    undoRedo: false,
    mobileTouch: true,
    mapLibreReady: false,
  },
  'leaflet-geoman': {
    drawPolygon: true,
    drawLine: true,
    drawPoint: true,
    drawCircle: true,
    drawRectangle: true,
    editVertices: true,
    dragFeature: true,
    rotateFeature: true,
    cutPolygon: true,
    splitPolygon: true,
    snapping: true,
    measurements: true,
    undoRedo: true,
    mobileTouch: true,
    mapLibreReady: false,
  },
  'terra-draw': {
    drawPolygon: true,
    drawLine: true,
    drawPoint: true,
    drawCircle: true,
    drawRectangle: true,
    editVertices: true,
    dragFeature: true,
    rotateFeature: false,
    cutPolygon: false,
    splitPolygon: false,
    snapping: true,
    measurements: false,
    undoRedo: true,
    mobileTouch: true,
    mapLibreReady: true,
  },
  'maplibre-terra-draw': {
    drawPolygon: true,
    drawLine: true,
    drawPoint: true,
    drawCircle: true,
    drawRectangle: true,
    editVertices: true,
    dragFeature: true,
    rotateFeature: false,
    cutPolygon: false,
    splitPolygon: false,
    snapping: true,
    measurements: false,
    undoRedo: true,
    mobileTouch: true,
    mapLibreReady: true,
  },
};

export function getPreferredEngineForWorkflow(workflow: DrawWorkflow): DrawingEngineId {
  if (workflow === 'design-pivot') return 'leaflet-geoman';
  if (workflow === 'create-management-zone' || workflow === 'create-prescription-zone') return 'leaflet-geoman';
  if (workflow === 'measure-area' || workflow === 'measure-distance') return 'leaflet-geoman';
  return 'leaflet-draw';
}
