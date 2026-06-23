// إعلان أنواع لوحدات turf المستخدمة في القياس (geo.ts).
// السبب: @turf/area@6.5 و@turf/length@6.5 يعرّفان types في dist/js/index.d.ts
// لكنّ حقل package.json "exports" لا يتضمّن شرط "types"، فلا يحلّها TS تحت
// moduleResolution: bundler (يتجاهل الحقل العلويّ types عند وجود exports).
// نعلن التوقيعات يدويّاً (مطابقة لتعريفات turf الرسميّة) — لا any مُبهَم.
declare module '@turf/area' {
  // مساحة هندسة GeoJSON بالمتر المربّع (م²).
  export default function area(geojson: GeoJSON.Feature | GeoJSON.Geometry): number;
}

declare module '@turf/length' {
  // طول خطّ GeoJSON؛ الوحدة افتراضيّاً كيلومتر، نمرّر units: 'meters' للأمتار.
  export default function length(
    geojson: GeoJSON.Feature | GeoJSON.Geometry,
    options?: { units?: string },
  ): number;
}

// وحدات دمج/تقسيم الحقول (fieldGeometryOps.ts) — نفس سبب الإعلان اليدويّ أعلاه:
// @turf/{helpers,union,intersect,difference}@6.5 تعرّف types في dist لكن "exports"
// لا يتضمّن شرط "types" فلا يحلّها TS تحت moduleResolution: bundler. التوقيعات
// مطابقة لتعريفات turf v6 الرسميّة (لا any مُبهَم).
declare module '@turf/helpers' {
  import type { Feature, Polygon, MultiPolygon, Position } from 'geojson';
  export function polygon<P = Record<string, unknown>>(
    coordinates: Position[][],
    properties?: P,
  ): Feature<Polygon, P>;
  export function multiPolygon<P = Record<string, unknown>>(
    coordinates: Position[][][],
    properties?: P,
  ): Feature<MultiPolygon, P>;
}

declare module '@turf/union' {
  import type { Feature, Polygon, MultiPolygon } from 'geojson';
  // اتّحاد مضلّعين؛ يُرجِع Polygon أو MultiPolygon (عند عدم التجاور)، أو null.
  export default function union(
    poly1: Feature<Polygon | MultiPolygon> | Polygon | MultiPolygon,
    poly2: Feature<Polygon | MultiPolygon> | Polygon | MultiPolygon,
    options?: { properties?: Record<string, unknown> },
  ): Feature<Polygon | MultiPolygon> | null;
}

declare module '@turf/intersect' {
  import type { Feature, Polygon, MultiPolygon } from 'geojson';
  // تقاطع مضلّعين؛ يُرجِع الجزء المشترك (Polygon/MultiPolygon) أو null إن لم يتقاطعا.
  export default function intersect(
    poly1: Feature<Polygon | MultiPolygon> | Polygon | MultiPolygon,
    poly2: Feature<Polygon | MultiPolygon> | Polygon | MultiPolygon,
    options?: { properties?: Record<string, unknown> },
  ): Feature<Polygon | MultiPolygon> | null;
}

declare module '@turf/difference' {
  import type { Feature, Polygon, MultiPolygon } from 'geojson';
  // فرق مضلّعين (poly1 ناقص poly2)؛ يُرجِع الباقي أو null إن فرغ.
  export default function difference(
    poly1: Feature<Polygon | MultiPolygon> | Polygon | MultiPolygon,
    poly2: Feature<Polygon | MultiPolygon> | Polygon | MultiPolygon,
  ): Feature<Polygon | MultiPolygon> | null;
}

declare module '@turf/buffer' {
  import type { Feature, Geometry, Polygon, MultiPolygon } from 'geojson';
  // حِزام حول هندسة بمسافة radius (وحدة options.units)؛ قد يُرجِع undefined إن
  // أفنى حِزامٌ سالب الهندسةَ كاملاً. التوقيع مطابق لتعريف turf v6 الرسميّ.
  export default function buffer(
    feature: Feature<Geometry> | Geometry,
    radius?: number,
    options?: { units?: string; steps?: number },
  ): Feature<Polygon | MultiPolygon> | undefined;
}

declare module '@turf/simplify' {
  // تبسيط هندسة GeoJSON (Douglas–Peucker)؛ يُرجِع نفس نوع المُدخَل T (لا يزيد الرؤوس).
  export default function simplify<T>(
    geojson: T,
    options?: { tolerance?: number; highQuality?: boolean; mutate?: boolean },
  ): T;
}
