import L from 'leaflet';

export const PIVOT_VERTEX_COUNT = 96;
export function circleToPolygon(center: L.LatLng, radiusM: number): L.LatLng[] {
  // توليد دائرة جيوديسية حقيقية حول المركز بدل تقريب degree-per-meter.
  // هذا يقلل الإزاحة/التشوّه في الحقول المحورية الكبيرة ويحافظ على نصف القطر بالمتر.
  const R = 6378137; // WGS84 radius, meters
  const lat1 = center.lat * Math.PI / 180;
  const lon1 = center.lng * Math.PI / 180;
  const d = radiusM / R;
  const pts: L.LatLng[] = [];
  for (let i = 0; i < PIVOT_VERTEX_COUNT; i++) {
    const brng = (i / PIVOT_VERTEX_COUNT) * 2 * Math.PI;
    const lat2 = Math.asin(
      Math.sin(lat1) * Math.cos(d) +
      Math.cos(lat1) * Math.sin(d) * Math.cos(brng),
    );
    const lon2 = lon1 + Math.atan2(
      Math.sin(brng) * Math.sin(d) * Math.cos(lat1),
      Math.cos(d) - Math.sin(lat1) * Math.sin(lat2),
    );
    pts.push(L.latLng(lat2 * 180 / Math.PI, lon2 * 180 / Math.PI));
  }
  return pts;
}
