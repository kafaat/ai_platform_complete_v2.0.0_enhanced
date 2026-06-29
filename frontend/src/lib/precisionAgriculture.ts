export type BoundaryExtractRequest = {
  field_id: string;
  seed_geometry?: GeoJSON.Geometry;
  imagery_id?: string;
  imagery_bbox?: [number, number, number, number];
  model?: string;
  simplify_tolerance_m?: number;
  human_review_required?: boolean;
};

export type ZoneSample = Record<string, number | string | null | undefined> & { id?: string };

export type ManagementZonesRequest = {
  samples: ZoneSample[];
  n_zones?: number;
  feature_keys?: string[];
  weights?: Record<string, number>;
};

export type PrescriptionRequest = {
  zone_features: Array<Record<string, unknown>>;
  crop: string;
  prescription_type: 'nitrogen' | 'seed' | 'irrigation' | 'phosphorus' | 'potassium' | string;
  target_yield_t_ha?: number;
};

export const precisionAgricultureEndpoints = {
  boundaryExtract: '/api/v1/gis/cloud-native/phase6/boundaries/extract',
  managementZones: '/api/v1/gis/cloud-native/phase6/management-zones/generate',
  prescriptions: '/api/v1/gis/cloud-native/phase6/prescriptions/generate',
  yieldStability: '/api/v1/gis/cloud-native/phase6/yield-stability',
  profitabilityMap: '/api/v1/gis/cloud-native/phase6/profitability-map',
  digitalTwinSnapshot: '/api/v1/gis/cloud-native/phase6/digital-twin/snapshot',
} as const;

export function classifyZoneLabel(label: string): 'stress' | 'medium' | 'high' | 'other' {
  if (label === 'stress' || label === 'low') return 'stress';
  if (label === 'medium') return 'medium';
  if (label === 'high_potential' || label === 'high') return 'high';
  return 'other';
}
