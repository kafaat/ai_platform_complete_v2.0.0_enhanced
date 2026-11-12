type Point = [number, number];
type Ring = Point[];
export type FieldBoundary = Ring[][];
export type MapBoundary = Ring | FieldBoundary;

// Keep parts and interior rings grouped; changing their nesting changes the area.
export function fieldBoundary(geometry: unknown): FieldBoundary | undefined {
  if (!geometry || typeof geometry !== 'object') return undefined;
  const g = geometry as { type?: string; coordinates?: unknown; geometry?: unknown };
  if (g.type === 'Feature') return fieldBoundary(g.geometry);
  const parts = g.type === 'MultiPolygon' ? g.coordinates : g.type === 'Polygon' ? [g.coordinates] : undefined;
  if (!Array.isArray(parts) || !parts.length) return undefined;
  const result: FieldBoundary = [];
  for (const part of parts) {
    if (!Array.isArray(part) || !part.length) return undefined;
    const polygon: Ring[] = [];
    for (const ring of part) {
      if (!Array.isArray(ring) || ring.length < 3) return undefined;
      const points: Ring = [];
      for (const p of ring) {
        if (!Array.isArray(p) || !Number.isFinite(p[0]) || !Number.isFinite(p[1]) ||
            Math.abs(p[0]) > 180 || Math.abs(p[1]) > 90) return undefined;
        points.push([p[1], p[0]]);
      }
      polygon.push(points);
    }
    result.push(polygon);
  }
  return result;
}

export function boundaryBounds(boundary?: MapBoundary): [number, number, number, number] | undefined {
  if (!boundary?.length) return undefined;
  const rings = typeof boundary[0][0] === 'number'
    ? [boundary as Ring]
    : (boundary as FieldBoundary).map(part => part[0]);
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  for (const ring of rings) {
    for (const [lat, lon] of ring) {
      west = Math.min(west, lon); east = Math.max(east, lon);
      south = Math.min(south, lat); north = Math.max(north, lat);
    }
  }
  return [west, south, east, north];
}
