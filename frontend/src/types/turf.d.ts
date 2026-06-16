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
