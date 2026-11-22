import type { DrawFeature } from './drawing';

export function drawFeatureStyle(feature: DrawFeature) {
  if (feature.kind === 'prescription-zone') {
    return { color: '#f59e0b', weight: 2, fillColor: '#f59e0b', fillOpacity: 0.20, dashArray: '3 5' };
  }
  if (feature.kind === 'management-zone') {
    return { color: '#22c55e', weight: 2, fillColor: '#22c55e', fillOpacity: 0.16, dashArray: '8 4' };
  }
  if (feature.kind === 'exclusion-zone') {
    return { color: '#ef4444', weight: 2, fillColor: '#ef4444', fillOpacity: 0.18, dashArray: '2 4' };
  }
  return { color: '#38bdf8', weight: 2, fillColor: '#38bdf8', fillOpacity: 0.18, dashArray: '6 4' };
}
