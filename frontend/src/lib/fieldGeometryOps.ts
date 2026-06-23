// ═══════════════════════════════════════════════════════════════
// SAHOOL — lib/fieldGeometryOps.ts
// عمليّات هندسيّة نقيّة لدمج/تقسيم حدود الحقول (Split & Merge).
// ───────────────────────────────────────────────────────────────
// دوالّ صرفة بلا React/Leaflet: تأخذ هندسة GeoJSON (Polygon/MultiPolygon) كما
// يخزّنها الخادم، وتُجري الاتّحاد (merge) أو التقاطع/الفرق (split) عبر turf v6،
// ثمّ تُرجِع هندسة GeoJSON صافية أو null عند غياب نتيجة حقيقيّة.
//
// أمانة صارمة (لا اختراع هندسة):
//   • merge: اتّحاد حقلين فأكثر؛ عند عدم التجاور يردّ turf مضلّعاً متعدّد الأجزاء
//     (MultiPolygon) — نُعيده كما هو ونترك القرار للمستدعي (الـUI يحذّر؛ الخادم
//     قد لا يقبل MultiPolygon فيُحجَب صراحةً). لا نُسقِط أجزاءً بصمت.
//   • split: child A = تقاطع(الحقل، القصّ)، child B = فرق(الحقل، القصّ). إن خلا
//     أحدهما (القصّ لا يتقاطع، أو يبتلع الحقل كاملاً) ⇒ null (يَفشل التقسيم بصدق).
//
// تُستعمَل @turf/union/intersect/difference (v6) المطابقة لإصدار @turf/area@^6.5.0.
// ═══════════════════════════════════════════════════════════════
import { polygon as turfPolygon, multiPolygon as turfMultiPolygon } from '@turf/helpers';
import turfUnion from '@turf/union';
import turfIntersect from '@turf/intersect';
import turfDifference from '@turf/difference';
import turfBuffer from '@turf/buffer';
import turfSimplify from '@turf/simplify';
import type { Feature, Polygon, MultiPolygon, Position } from 'geojson';

// هندسة GeoJSON المساحيّة كما يقبلها هذا المنطق (مُدخَلاً ومُخرَجاً).
export type PolygonGeometry = { type: 'Polygon'; coordinates: Position[][] };
export type MultiPolygonGeometry = { type: 'MultiPolygon'; coordinates: Position[][][] };
export type ArealGeometry = PolygonGeometry | MultiPolygonGeometry;

// قراءة دفاعيّة: هل القيمة هندسة GeoJSON مساحيّة (Polygon/MultiPolygon) صالحة بنيويّاً؟
// لا نفترض شكلاً صلباً — مصدر الهندسة خارجيّ (خادم) وقد يصل ناقصاً.
function isPolygonGeometry(g: unknown): g is PolygonGeometry {
  const o = g as { type?: unknown; coordinates?: unknown } | null | undefined;
  return !!o && o.type === 'Polygon' && Array.isArray(o.coordinates) && Array.isArray(o.coordinates[0]);
}
function isMultiPolygonGeometry(g: unknown): g is MultiPolygonGeometry {
  const o = g as { type?: unknown; coordinates?: unknown } | null | undefined;
  return !!o && o.type === 'MultiPolygon' && Array.isArray(o.coordinates) && Array.isArray(o.coordinates[0]);
}

/**
 * يحوّل هندسة GeoJSON مساحيّة (Polygon/MultiPolygon) إلى Feature لـturf.
 * يُرجِع null إن لم تكن هندسة مساحيّة صالحة (لا نُلفِّق رؤوساً ناقصة).
 */
export function toTurfFeature(geometry: unknown): Feature<Polygon | MultiPolygon> | null {
  try {
    if (isPolygonGeometry(geometry)) {
      const ring = geometry.coordinates[0];
      if (!Array.isArray(ring) || ring.length < 4) return null; // حلقة مغلقة ≥ 4 نقاط
      return turfPolygon(geometry.coordinates as Position[][]);
    }
    if (isMultiPolygonGeometry(geometry)) {
      if (!geometry.coordinates.length) return null;
      return turfMultiPolygon(geometry.coordinates as Position[][][]);
    }
  } catch {
    return null;
  }
  return null;
}

/** يستخرج هندسة GeoJSON صافية (Polygon|MultiPolygon) من Feature turf، أو null. */
export function featureToGeometry(
  feature: Feature<Polygon | MultiPolygon> | null,
): ArealGeometry | null {
  const geom = feature?.geometry;
  if (!geom) return null;
  if (geom.type === 'Polygon') {
    return { type: 'Polygon', coordinates: geom.coordinates };
  }
  if (geom.type === 'MultiPolygon') {
    // MultiPolygon بجزء واحد ⇒ نبسّطه إلى Polygon (الخادم يخزّن Polygon).
    if (geom.coordinates.length === 1) {
      return { type: 'Polygon', coordinates: geom.coordinates[0] };
    }
    return { type: 'MultiPolygon', coordinates: geom.coordinates };
  }
  return null;
}

/**
 * يدمج هندسات حقلين فأكثر باتّحاد (UNION) حقيقيّ.
 * يُرجِع Polygon إن كانت الحقول متجاورة، وMultiPolygon إن كانت منفصلة (لا نُسقِط
 * أجزاءً)، وnull إن لم تتوفّر هندستان مساحيّتان صالحتان على الأقلّ.
 */
export function mergeFieldGeometries(geometries: ReadonlyArray<unknown>): ArealGeometry | null {
  const features = geometries
    .map(toTurfFeature)
    .filter((f): f is Feature<Polygon | MultiPolygon> => f != null);
  if (features.length < 2) return null; // الدمج يتطلّب حقلين صالحين على الأقلّ

  let acc: Feature<Polygon | MultiPolygon> | null = features[0];
  for (let i = 1; i < features.length; i++) {
    if (!acc) return null;
    acc = turfUnion(acc, features[i]);
  }
  return featureToGeometry(acc);
}

/**
 * يقسّم حقلاً بمضلّع قصّ:
 *   partA = تقاطع(الحقل، القصّ)   — الجزء الواقع داخل القصّ
 *   partB = فرق(الحقل، القصّ)      — الباقي خارج القصّ
 * يُرجِع null إن لم يتقاطع القصّ مع الحقل (partA فارغ)، أو إن ابتلع القصّ الحقل
 * كاملاً (partB فارغ) ⇒ لا تقسيم حقيقيّ إلى جزأين. أمانة: لا جزء مُختلَق.
 */
export function splitFieldGeometry(
  fieldGeom: unknown,
  cutGeom: unknown,
): { partA: ArealGeometry; partB: ArealGeometry } | null {
  const field = toTurfFeature(fieldGeom);
  const cut = toTurfFeature(cutGeom);
  if (!field || !cut) return null;

  const interFeature = turfIntersect(field, cut);
  const diffFeature = turfDifference(field, cut);
  const partA = featureToGeometry(interFeature);
  const partB = featureToGeometry(diffFeature);
  // كلا الجزأين يجب أن يكونا هندسة صالحة لتقسيم حقيقيّ (لا جزء فارغ).
  if (!partA || !partB) return null;
  return { partA, partB };
}

/**
 * يُنشئ حِزاماً (BUFFER) حول هندسة الحقل بمسافة بالأمتار (موجبة ⇒ توسيع، سالبة ⇒
 * تقليص). يستعمل @turf/buffer بوحدة 'meters' على القطع الإهليلجيّ WGS84 — لا أرقام
 * مُفبركة. يُرجِع هندسة مساحيّة صافية أو null عند:
 *   • مُدخَل غير مساحيّ صالح (toTurfFeature ⇒ null)،
 *   • مسافة غير محدودة (NaN/∞)،
 *   • أو حِزام سالب يبتلع الهندسة كاملاً (turf يردّ undefined) ⇒ لا نتيجة حقيقيّة.
 * أمانة: معاينة هندسيّة محض في المتصفّح — لا حفظ في الخادم (المستدعي/الـUI يوضّح ذلك).
 */
export function bufferFieldGeometry(geometry: unknown, meters: number): ArealGeometry | null {
  if (!Number.isFinite(meters)) return null;
  const feature = toTurfFeature(geometry);
  if (!feature) return null;
  try {
    // turf v6: buffer(feature, radius, { units }) — قد يردّ undefined إذا أفنى
    // الحِزام السالب الهندسة. نعامله كـnull (لا اختراع هندسة فارغة).
    const buffered = turfBuffer(feature, meters, { units: 'meters' });
    return featureToGeometry((buffered ?? null) as Feature<Polygon | MultiPolygon> | null);
  } catch {
    return null;
  }
}

/**
 * يبسّط (SIMPLIFY) هندسة الحقل بإزالة رؤوس زائدة عبر Douglas–Peucker (@turf/simplify)
 * بعتبة tolerance (بدرجات الإحداثيّات — كلّما زادت زاد التبسيط). يحافظ على البنية العامّة
 * ولا يزيد عدد الرؤوس. mutate=false كي لا نعدّل مُدخَل المستدعي. يُرجِع هندسة مساحيّة
 * صافية أو null عند مُدخَل غير صالح أو عتبة غير محدودة. معاينة محض — لا حفظ.
 */
export function simplifyFieldGeometry(geometry: unknown, tolerance: number): ArealGeometry | null {
  if (!Number.isFinite(tolerance) || tolerance < 0) return null;
  const feature = toTurfFeature(geometry);
  if (!feature) return null;
  try {
    const simplified = turfSimplify(feature, { tolerance, highQuality: true, mutate: false });
    return featureToGeometry(simplified as Feature<Polygon | MultiPolygon>);
  } catch {
    return null;
  }
}

/** يَعُدّ رؤوس هندسة مساحيّة (مجموع نقاط كلّ الحلقات) — لمقارنة قبل/بعد التبسيط. */
export function countVertices(geometry: ArealGeometry | null | undefined): number {
  if (!geometry) return 0;
  if (geometry.type === 'Polygon') {
    return geometry.coordinates.reduce((n, ring) => n + ring.length, 0);
  }
  // MultiPolygon: مجموع رؤوس كلّ حلقات كلّ المضلّعات.
  return geometry.coordinates.reduce(
    (n, poly) => n + poly.reduce((m, ring) => m + ring.length, 0),
    0,
  );
}

/** هل الهندسة الناتجة متعدّدة الأجزاء (MultiPolygon)؟ — للتحذير في الـUI/الحجب. */
export function isMultiPolygon(geometry: ArealGeometry | null | undefined): boolean {
  return !!geometry && geometry.type === 'MultiPolygon';
}
