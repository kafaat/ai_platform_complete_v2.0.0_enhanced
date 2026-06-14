// geo.ts — أدوات هندسيّة مشتركة (مصدر واحد للحقيقة الهندسيّة).
// كان geomToPolygon مكرّراً حرفيّاً في SatellitePage و FieldMapCenter؛ وُحِّد هنا
// كي تتبدّل معالجة الحلقة (MultiPolygon، ترتيب الإحداثيّات، الثقوب) في مكان واحد.

// مضلّع Leaflet: قائمة رؤوس [lat, lng].
export type LatLngPolygon = [number, number][];

// هندسة GeoJSON Polygon (إحداثيّات [lon, lat]) → مضلّع Leaflet [lat, lng].
// تُرجع undefined إن غابت الحلقة أو قصُرت عن ثلاثة رؤوس (لا مضلّع يُرسَم).
export function geomToPolygon(geometry: any): LatLngPolygon | undefined {
  const ring = geometry?.coordinates?.[0];
  if (!Array.isArray(ring) || ring.length < 3) return undefined;
  return ring
    .filter((c: any) => Array.isArray(c) && c.length >= 2)
    .map((c: number[]) => [c[1], c[0]] as [number, number]);
}
