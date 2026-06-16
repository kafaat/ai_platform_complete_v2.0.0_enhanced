// geo.ts — أدوات هندسيّة مشتركة (مصدر واحد للحقيقة الهندسيّة).
// كان geomToPolygon مكرّراً حرفيّاً في SatellitePage و FieldMapCenter؛ وُحِّد هنا
// كي تتبدّل معالجة الحلقة (MultiPolygon، ترتيب الإحداثيّات، الثقوب) في مكان واحد.

// مضلّع Leaflet: قائمة رؤوس [lat, lng].
export type LatLngPolygon = [number, number][];

// هندسة GeoJSON Polygon (إحداثيّات [lon, lat]) → مضلّع Leaflet [lat, lng].
// تُرجع undefined إن غابت الحلقة أو قصُرت عن ثلاثة رؤوس (لا مضلّع يُرسَم).
// المُدخَل قد يكون هندسة GeoJSON صالحة أو شيئاً ناقصاً/غائباً (مصدر خارجيّ) —
// لذا unknown مع قراءة دفاعيّة، لا any: لا نفترض شكلاً ثمّ نصدمه وقت التشغيل.
export function geomToPolygon(geometry: unknown): LatLngPolygon | undefined {
  const coordinates = (geometry as { coordinates?: unknown } | null | undefined)?.coordinates;
  const ring = Array.isArray(coordinates) ? coordinates[0] : undefined;
  if (!Array.isArray(ring) || ring.length < 3) return undefined;
  return ring
    .filter((c: unknown): c is number[] => Array.isArray(c) && c.length >= 2)
    .map((c: number[]) => [c[1], c[0]] as [number, number]);
}

// ── قياسات على هندسة GeoJSON حقيقيّة (turf) ─────────────────────────
// تُستعمل لأدوات القياس على الخريطة (FieldIndicatorMap · tools): تستقبل
// مباشرةً ناتج layer.toGeoJSON() من leaflet-draw فتُحسَب من الرؤوس الفعليّة.
import turfArea from '@turf/area';
import turfLength from '@turf/length';

// مساحة مضلّع GeoJSON (Feature/Geometry) بالمتر المربّع (م²). turf يُرجع م²
// على القطع الإهليلجيّ WGS84 — لا أرقام مُفبركة. صفر عند غياب هندسة صالحة.
// تتسامح مع مُدخَل غير صالح (تُرجِع صفراً، لا ترمي)؛ unknown يعكس ذلك بأمانة.
export function areaSqMeters(geojson: unknown): number {
  try {
    const v = turfArea(geojson as GeoJSON.Feature | GeoJSON.Geometry);
    return Number.isFinite(v) ? v : 0;
  } catch {
    return 0;
  }
}

// طول خطّ GeoJSON (LineString) بالمتر (م). turf.length يُرجع بالكيلومتر
// افتراضيّاً؛ نطلب الأمتار صراحةً. صفر عند غياب هندسة صالحة.
export function lengthMeters(geojson: unknown): number {
  try {
    const v = turfLength(geojson as GeoJSON.Feature | GeoJSON.Geometry, { units: 'meters' });
    return Number.isFinite(v) ? v : 0;
  } catch {
    return 0;
  }
}
