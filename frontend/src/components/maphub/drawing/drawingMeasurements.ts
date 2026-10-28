import type { DrawFeature, DrawMeasurements, Position } from './drawingTypes';

const EARTH_RADIUS_M = 6371008.8;

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function haversine(a: Position, b: Position): number {
  const [lon1, lat1] = a;
  const [lon2, lat2] = b;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const rLat1 = toRad(lat1);
  const rLat2 = toRad(lat2);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rLat1) * Math.cos(rLat2) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

function ringLengthM(ring: Position[]): number {
  let total = 0;
  for (let i = 1; i < ring.length; i += 1) total += haversine(ring[i - 1], ring[i]);
  return total;
}

function ringAreaM2(ring: Position[]): number {
  // Spherical trapezoid approximation, sufficient for UI preview. Backend PostGIS remains authoritative.
  if (ring.length < 4) return 0;
  let sum = 0;
  for (let i = 0; i < ring.length - 1; i += 1) {
    const [lon1, lat1] = ring[i];
    const [lon2, lat2] = ring[i + 1];
    sum += toRad(lon2 - lon1) * (2 + Math.sin(toRad(lat1)) + Math.sin(toRad(lat2)));
  }
  return Math.abs((sum * EARTH_RADIUS_M * EARTH_RADIUS_M) / 2);
}

function isPosition(value: unknown): value is Position {
  return Array.isArray(value) && value.length >= 2 && typeof value[0] === 'number' && typeof value[1] === 'number';
}

function isRing(value: unknown): value is Position[] {
  return Array.isArray(value) && value.every(isPosition);
}

// GeoJSON Polygon = [outer, ...holes]. Net area subtracts every interior ring with the same
// spherical formula (orientation-independent via abs), matching ST_Area / Turf semantics;
// perimeter sums all rings like ST_Perimeter. Returns null when the outer ring is invalid.
function measurePolygonRings(rings: unknown): { areaM2: number; perimeterM: number } | null {
  if (!Array.isArray(rings) || !isRing(rings[0])) return null;
  const outer = rings[0];
  let areaM2 = ringAreaM2(outer);
  let perimeterM = ringLengthM(outer);
  for (const hole of rings.slice(1)) {
    if (!isRing(hole)) continue;
    areaM2 -= ringAreaM2(hole);
    perimeterM += ringLengthM(hole);
  }
  return { areaM2: Math.max(0, areaM2), perimeterM };
}

export function measureDrawFeature(feature: DrawFeature): DrawMeasurements {
  const geom = feature.geometry;
  if (geom.type === 'LineString' && Array.isArray(geom.coordinates) && geom.coordinates.every(isPosition)) {
    return { lengthM: ringLengthM(geom.coordinates) };
  }

  if (geom.type === 'Polygon') {
    const measured = measurePolygonRings(geom.coordinates);
    if (measured) {
      return {
        areaHa: measured.areaM2 / 10000,
        perimeterM: measured.perimeterM,
      };
    }
  }

  if (geom.type === 'MultiPolygon' && Array.isArray(geom.coordinates)) {
    let areaHa = 0;
    let perimeterM = 0;
    for (const polygon of geom.coordinates) {
      const measured = measurePolygonRings(polygon);
      if (measured) {
        areaHa += measured.areaM2 / 10000;
        perimeterM += measured.perimeterM;
      }
    }
    return { areaHa, perimeterM };
  }

  return {};
}
