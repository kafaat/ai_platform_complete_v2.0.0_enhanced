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

// ── خريطة المزرعة الشاملة: نقاط الحقول للإطار والعلامات ──────────────
// حقلٌ بأقلّ ما يلزم لوضعه على خريطة عامّة (مضلّع أو نقطة احتياطيّة).
export interface MappableField {
  geometry: unknown;
  lat: number | null;
  lon: number | null;
}

// النقطة الممثِّلة للحقل على الخريطة [lat, lng]: مركز المضلّع (متوسّط الرؤوس)
// إن توفّرت هندسة، وإلّا lat/lon. null إن غاب الاثنان (لا يُرسَم). دالّة نقيّة.
export function fieldRepresentativePoint(f: MappableField): [number, number] | null {
  const poly = geomToPolygon(f.geometry);
  if (poly && poly.length) {
    const [sumLat, sumLng] = poly.reduce(
      ([a, b], [lat, lng]) => [a + lat, b + lng],
      [0, 0] as [number, number],
    );
    return [sumLat / poly.length, sumLng / poly.length];
  }
  if (f.lat != null && f.lon != null) return [f.lat, f.lon];
  return null;
}

// كلّ النقاط [lat, lng] اللازمة لضبط إطار الخريطة على جميع الحقول: رؤوس مضلّع
// كلّ حقل ذي هندسة + نقطة lat/lon لكلّ حقل بلا هندسة. تُستعمل في fitBounds.
// دالّة نقيّة (لا Leaflet) — قابلة للاختبار offline.
export function collectFieldBoundsPoints(fields: ReadonlyArray<MappableField>): [number, number][] {
  const points: [number, number][] = [];
  for (const f of fields) {
    const poly = geomToPolygon(f.geometry);
    if (poly && poly.length) {
      points.push(...poly);
    } else if (f.lat != null && f.lon != null) {
      points.push([f.lat, f.lon]);
    }
  }
  return points;
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
