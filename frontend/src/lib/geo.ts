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

// ── تنسيق عرض القياسات (مصدر واحد لمحرّكَي الخريطة Leaflet/MapLibre) ──────
// المساحة بالمتر المربّع + الهكتار؛ الطول بالمتر + الكيلومتر. أرقام حقيقيّة من turf
// (لا تفبرك). كانت مُكرَّرة حرفيّاً في HubMap وHubMapGL — وُحِّدت هنا لتُختبَر حتميّاً
// (مسار الرسم⇒القياس⇒العرض المرئيّ الذي يبقى @visual تحت SwiftShader headless).
export function formatArea(m2: number): string {
  const ha = m2 / 10000;
  return `${Math.round(m2).toLocaleString('en-US')} م² · ${ha.toFixed(2)} هكتار`;
}

export function formatLength(m: number): string {
  const km = m / 1000;
  return `${Math.round(m).toLocaleString('en-US')} م · ${km.toFixed(2)} كم`;
}

// ── التقاط الرؤوس للحدود أثناء الرسم (snap / edge-assist) ─────────────
// أثناء رسم حدّ حقل، نُلصِق الرأس المُضاف حديثاً بأقرب حدّ حقل قائم (أو رأس البداية
// لإغلاق نظيف) ضمن تسامح صغير بالمتر. هندسة حقيقيّة جهة-العميل (لا خادم، لا تلفيق):
// نسقط النقطة عموديّاً على أقرب ضلع (point-to-segment) بمسافات هافرسين ثمّ نختار
// أقربها إن كانت ضمن التسامح. دالّة نقيّة قابلة للاختبار offline — لا Leaflet.

// مسافة هافرسين بين نقطتين [lat, lng] بالمتر (نفس ثابت WGS84 المستعمل في المساحة).
function haversineM(a: readonly [number, number], b: readonly [number, number]): number {
  const R = 6378137; // نصف قطر WGS84 (م)
  const rad = Math.PI / 180;
  const dLat = (b[0] - a[0]) * rad;
  const dLng = (b[1] - a[1]) * rad;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.atan2(Math.sqrt(s), Math.sqrt(1 - s));
}

// أقرب نقطة على القطعة [a→b] للنقطة p — كلّها [lat, lng]. نُسقِط في مستوٍ محليّ
// مُتساوي المقياس (متر/درجة عند خطّ العرض) كي يصحّ الإسقاط العموديّ على المسافات
// القصيرة لحدود الحقول (لا تشويه يُذكَر دون الكيلومترات). نُقصّ المُعامِل t إلى
// [0,1] فلا نتجاوز طرفي القطعة (إسقاط على القطعة لا على امتدادها اللانهائيّ).
function nearestPointOnSegment(
  p: readonly [number, number],
  a: readonly [number, number],
  b: readonly [number, number],
): { point: [number, number]; distM: number } {
  const rad = Math.PI / 180;
  const mPerDegLat = 111320;
  const cosLat = Math.max(Math.cos(p[0] * rad), 1e-6);
  const mPerDegLng = 111320 * cosLat;
  // إحداثيّات محليّة بالمتر نسبةً إلى a.
  const ax = 0, ay = 0;
  const bx = (b[1] - a[1]) * mPerDegLng;
  const by = (b[0] - a[0]) * mPerDegLat;
  const px = (p[1] - a[1]) * mPerDegLng;
  const py = (p[0] - a[0]) * mPerDegLat;
  const dx = bx - ax, dy = by - ay;
  const lenSq = dx * dx + dy * dy;
  // قطعة منحلّة (a==b): أقرب نقطة هي a نفسها.
  let t = lenSq > 0 ? ((px - ax) * dx + (py - ay) * dy) / lenSq : 0;
  t = Math.max(0, Math.min(1, t));
  const snappedLng = a[1] + ((ax + t * dx) / mPerDegLng);
  const snappedLat = a[0] + ((ay + t * dy) / mPerDegLat);
  const point: [number, number] = [snappedLat, snappedLng];
  return { point, distM: haversineM(p, point) };
}

// حلقة/خطّ مرشَّح للالتقاط: قائمة رؤوس [lat, lng] (حدّ حقل قائم أو رؤوس الرسم الحاليّ).
export type SnapTarget = ReadonlyArray<readonly [number, number]>;

export interface SnapResult {
  point:    [number, number]; // النقطة بعد الالتقاط (أو الأصليّة إن لا التقاط)
  snapped:  boolean;          // هل التُقِطت فعلاً؟
  distM:    number;           // مسافة الالتقاط بالمتر (0 إن لا التقاط)
  kind:     'vertex' | 'edge' | 'none'; // التُقِط لرأس قائم أم لضلع أم لا شيء
}

// يلتقط النقطة p لأقرب رأس قائم (أولويّة) ثمّ لأقرب ضلع ضمن toleranceM. الرؤوس
// لها أولويّة على الأضلاع عند تساوي القرب التقريبيّ (إغلاق/تطابق دقيق مرغوب أكثر).
// targets: حدود حقول قائمة + (اختياريّاً) رؤوس الرسم الحاليّ لإغلاق البداية.
// لا التقاط ⇒ نُعيد p كما هي (snapped:false) — لا تحريك صامت خارج التسامح.
export function snapPoint(
  p: readonly [number, number],
  targets: ReadonlyArray<SnapTarget>,
  toleranceM = 8,
): SnapResult {
  if (!Array.isArray(p) || p.length < 2 || !Number.isFinite(p[0]) || !Number.isFinite(p[1])) {
    return { point: [p?.[0] ?? 0, p?.[1] ?? 0], snapped: false, distM: 0, kind: 'none' };
  }
  const tol = toleranceM > 0 ? toleranceM : 0;
  let bestVertex: { point: [number, number]; distM: number } | null = null;
  let bestEdge: { point: [number, number]; distM: number } | null = null;

  for (const ring of targets) {
    if (!Array.isArray(ring) || ring.length === 0) continue;
    // أقرب رأس
    for (const v of ring) {
      if (!v || !Number.isFinite(v[0]) || !Number.isFinite(v[1])) continue;
      const d = haversineM(p, v);
      if (d <= tol && (!bestVertex || d < bestVertex.distM)) {
        bestVertex = { point: [v[0], v[1]], distM: d };
      }
    }
    // أقرب ضلع (point-to-segment)
    for (let i = 0; i + 1 < ring.length; i++) {
      const a = ring[i], b = ring[i + 1];
      if (!a || !b || a.length < 2 || b.length < 2) continue;
      const r = nearestPointOnSegment(p, a, b);
      if (r.distM <= tol && (!bestEdge || r.distM < bestEdge.distM)) {
        bestEdge = r;
      }
    }
  }

  if (bestVertex) {
    return { point: bestVertex.point, snapped: true, distM: bestVertex.distM, kind: 'vertex' };
  }
  if (bestEdge) {
    return { point: bestEdge.point, snapped: true, distM: bestEdge.distM, kind: 'edge' };
  }
  return { point: [p[0], p[1]], snapped: false, distM: 0, kind: 'none' };
}

// يلتقط كامل حلقة رسم: لكلّ رأس يُحاول الالتقاط لحدود قائمة + لرأس بداية الرسم نفسه
// (إغلاق نظيف) دون التقاطه لجاره المباشر في نفس الرسم. يُعيد حلقةً جديدة بالرؤوس
// الملتقَطة (لا يطمس الأصليّة). آمن: مُدخَل قصير/غير صالح ⇒ يُعاد كما هو.
export function snapRing(
  ring: ReadonlyArray<readonly [number, number]>,
  existing: ReadonlyArray<SnapTarget>,
  toleranceM = 8,
): [number, number][] {
  if (!Array.isArray(ring) || ring.length === 0) return [];
  const out: [number, number][] = [];
  for (let i = 0; i < ring.length; i++) {
    const v = ring[i];
    // هدف إضافيّ: رأس بداية الرسم فقط (لإغلاق نظيف)، ولِرؤوس بعد الثالث.
    const selfTargets: SnapTarget[] =
      i >= 2 && ring.length > 2 ? [[ring[0]]] : [];
    const res = snapPoint(v, [...existing, ...selfTargets], toleranceM);
    out.push(res.snapped ? res.point : [v[0], v[1]]);
  }
  return out;
}
