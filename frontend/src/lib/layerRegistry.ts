// ═══════════════════════════════════════════════════════════════
// SAHOOL — سجلّ طبقات الخريطة (Layer Registry) · بيانات لا كود
// ───────────────────────────────────────────────────────────────
// مصدر **وحيد** لتعريف طبقات الخريطة (المؤشّرات الطيفيّة، خرائط الأساس،
// حدود الحقل، الرادار). اليوم تُعرّف الطبقات بأسلوب موضعيّ داخل المكوّنات:
//   • FieldMapCenter.tsx — مصفوفة LAYERS الداخليّة (ndvi/ndmi/salinity)
//   • SatellitePage.tsx — IND_META + FALLBACK_RENDERABLE (قائمة المؤشّرات)
//   • components/ds/tokens.ts — CMAP (لوحات الألوان: ndvi/moisture/ec…)
//   • FieldIndicatorMap.tsx — BASEMAP_SAT / BASEMAP_LIGHT (خرائط الأساس)
// فكلّ طبقة جديدة تعني تعديل كود في عدّة مكوّنات معاً. هذا السجلّ يحوّل
// تعريف الطبقة إلى **بيانات** (metadata):
//
//   • كلّ طبقة تُعلَن مرّة واحدة هنا (المعرّف، الاسم، النوع، المصدر، اللوحة،
//     الشفافيّة، الظهور الافتراضيّ، الوصف).
//   • أيّ واجهة تَمُرّ على listLayers() تعرض الطبقات تلقائيّاً ⇒ إضافة طبقة
//     جديدة (مثلاً مؤشّر جديد من سجلّ المؤشّرات الخلفيّ Index Registry) =
//     إدخال سطر بيانات واحد هنا فيظهر تلقائيّاً («أضف طبقةً → تظهر»).
//
// يُماثل هذا مفهوم سجلّ المؤشّرات الخلفيّ
// (services/sahool-platform/api/index_registry.py): توحيد الوصف كبيانات.
//
// نطاق هذا الإصدار (PR):
//   • يُسلّم **السجلّ + البيانات الوصفيّة + المساعِدات** فقط (TypeScript صرف،
//     بلا React).
//   • ربط المكوّنات القائمة لتستهلك هذا السجلّ (FieldMapCenter/SatellitePage/
//     LayerSwitcher) **متابعة لاحقة** — اليوم لا تزال تعرّف طبقاتها موضعيّاً.
//
// أمانة البيانات:
//   • المؤشّرات (ndvi/ndmi/salinity) مطابقة لما يقبله raster-service عبر
//     المُعامل index= ولما تعرضه FieldMapCenter/SatellitePage فعليّاً.
//   • معرّفات colormap مطابقة لمفاتيح CMAP في components/ds/tokens.ts فقط.
//   • مصادر خرائط الأساس مطابقة لـ BASEMAP_SAT/BASEMAP_LIGHT في
//     FieldIndicatorMap.tsx.
//   • طبقة الحدود تَصِف تراكب مضلّع حدود الحقل (Leaflet Polygon) المُشتقّ من
//     هندسة الحقل (geomToPolygon) — لا بلاطات.
//   • طبقة الرادار مُعلَنة كطبقة توفّر (غير ظاهرة افتراضيّاً) دون مصدر بلاطات
//     مُختلَق: المنصّة لا تُنتج بلاطات رادار اصطناعيّ اليوم (تنبيه: «SAR» في
//     IrrigationWaterPage هو نسبة امتزاز الصوديوم في الماء، لا رادار). تبقى
//     هنا كنقطة تمديد موثّقة لربط مصدر حقيقيّ لاحقاً.
// ═══════════════════════════════════════════════════════════════

/**
 * وصف طبقة خريطة واحدة (بيانات وصفيّة).
 * - id: معرّف فريد مختصر (مثل "ndvi"). للمؤشّرات يطابق ما يقبله raster-service.
 * - labelAr: الاسم المعروض بالعربيّة.
 * - kind: نوع الطبقة — مؤشّر | خريطة أساس | حدود | رادار.
 * - source: مصدر الطبقة (معرّف index لـraster-service، أو رابط بلاطات الأساس،
 *   أو واصف مشتقّ مثل "field-geometry").
 * - colormap: معرّف لوحة ألوان من CMAP (components/ds/tokens.ts) — للمؤشّرات.
 * - opacity: شفافيّة افتراضيّة [0..1].
 * - defaultVisible: هل تظهر الطبقة افتراضيّاً عند فتح الخريطة.
 * - description: وصف عربيّ موجز (دلالة الطبقة / ملاحظة المصدر).
 */
export type MapLayer = {
  id: string;
  labelAr: string;
  kind: 'index' | 'basemap' | 'boundary' | 'radar';
  source: string;
  colormap?: string;
  opacity?: number;
  defaultVisible?: boolean;
  description?: string;
};

/**
 * سجلّ طبقات الخريطة — المصدر الوحيد. كلّ مدخل = طبقة واحدة.
 * (as const satisfies readonly MapLayer[]) للتحقّق النوعيّ مع إبقاء القيم حرفيّة.
 */
export const LAYER_REGISTRY = [
  // ── خرائط الأساس (Basemaps) — مطابقة لـFieldIndicatorMap.tsx ──
  {
    id: 'satellite',
    labelAr: 'صور الأقمار الصناعيّة',
    kind: 'basemap',
    // BASEMAP_SAT — ArcGIS World Imagery (FieldIndicatorMap.tsx)
    source: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    opacity: 1,
    defaultVisible: true,
    description: 'خريطة أساس بصور جوّيّة (ArcGIS World Imagery).',
  },
  {
    id: 'light',
    labelAr: 'خريطة فاتحة',
    kind: 'basemap',
    // BASEMAP_LIGHT — Carto light_all (FieldIndicatorMap.tsx / AddFieldWithMap.tsx)
    source: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    opacity: 1,
    defaultVisible: false,
    description: 'خريطة أساس فاتحة (CARTO light) — بديل للصور الجوّيّة.',
  },

  // ── حدود الحقل (Boundary) — تراكب مضلّع من هندسة الحقل ──
  {
    id: 'field-boundary',
    labelAr: 'حدود الحقل',
    kind: 'boundary',
    // مشتقّ من هندسة الحقل عبر geomToPolygon (lib/geo) ويُرسم كـLeaflet Polygon.
    source: 'field-geometry',
    opacity: 0.9,
    defaultVisible: true,
    description: 'تراكب مضلّع حدود الحقل المشتقّ من هندسة الحقل (لا بلاطات).',
  },

  // ── صورة الحقل الخام (TrueColor) — البلاطة الافتراضيّة عند فتح الحقل ──
  {
    id: 'truecolor',
    labelAr: 'صورة الحقل الخام (TrueColor)',
    kind: 'index',
    source: 'truecolor',
    opacity: 1,
    defaultVisible: true,
    description: 'صورة Sentinel-2 خام بألوان طبيعية داخل حدود الحقل؛ ليست مؤشّراً ملوّناً ولا تحتاج scale legend.',
  },

  // ── المؤشّرات الطيفيّة (Indices) — بلاطات raster-service فوق حدود الحقل ──
  // المصدر = معرّف index لـraster-service · colormap = مفتاح CMAP (DS).
  {
    id: 'ndvi',
    labelAr: 'مؤشّر الغطاء النباتيّ (NDVI)',
    kind: 'index',
    source: 'ndvi',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'صحّة الغطاء النباتيّ — إجهاد (منخفض) إلى كثيف (مرتفع).',
  },
  {
    id: 'ndmi',
    labelAr: 'مؤشّر الرطوبة (NDMI)',
    kind: 'index',
    source: 'ndmi',
    // أقرب لوحة دلاليّاً في CMAP (الرطوبة) — مطابق لاختيار FieldMapCenter.
    colormap: 'moisture',
    opacity: 0.85,
    defaultVisible: false,
    description: 'محتوى الرطوبة في الغطاء النباتيّ — جافّ إلى رطب.',
  },
  {
    id: 'salinity',
    labelAr: 'مؤشّر الملوحة',
    kind: 'index',
    source: 'salinity',
    // أقرب لوحة دلاليّاً في CMAP (التوصيل الكهربيّ ec) — مطابق لـFieldMapCenter.
    colormap: 'ec',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر ملوحة التربة/الغطاء — منخفضة إلى مرتفعة.',
  },
  // مؤشّرات إضافيّة يحسبها raster-service (CDSE INDEX_EXPR) — أُضيفت للقائمة المنسدلة.
  // المصدر = معرّف index لـraster-service مباشرةً · colormap = أقرب لوحة CMAP دلاليّاً
  // (للمفتاح/الـlegend؛ ألوان البلاطة نفسها تُحسَب خادميّاً). 'moisture' المكافئ لـNDMI
  // (نفس الصيغة) مُستثنى تفادياً للتكرار.
  {
    id: 'evi',
    labelAr: 'مؤشّر الغطاء النباتيّ المحسّن (EVI)',
    kind: 'index',
    source: 'evi',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'غطاء نباتيّ محسّن (يقلّل أثر التربة/الغلاف الجوّيّ) — إجهاد إلى كثيف.',
  },
  {
    id: 'savi',
    labelAr: 'مؤشّر الغطاء المُعدَّل للتربة (SAVI)',
    kind: 'index',
    source: 'savi',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'غطاء نباتيّ مُعدَّل لأثر التربة — مفيد للغطاء المتفرّق.',
  },
  {
    id: 'msavi',
    labelAr: 'مؤشّر الغطاء المُعدَّل المُحسَّن (MSAVI)',
    kind: 'index',
    source: 'msavi',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'تعديل ذاتيّ لأثر التربة — أدقّ في مراحل النموّ المبكّرة.',
  },
  {
    id: 'ndwi',
    labelAr: 'مؤشّر المياه (NDWI)',
    kind: 'index',
    source: 'ndwi',
    colormap: 'moisture',
    opacity: 0.85,
    defaultVisible: false,
    description: 'محتوى الماء السطحيّ/الغطائيّ — جافّ إلى مائيّ.',
  },
  {
    id: 'gndvi',
    labelAr: 'مؤشّر الغطاء الأخضر (GNDVI)',
    kind: 'index',
    source: 'gndvi',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'حساسيّة أعلى للكلوروفيل — منخفض إلى مرتفع.',
  },
  {
    id: 'ndre',
    labelAr: 'مؤشّر الحافّة الحمراء (NDRE)',
    kind: 'index',
    source: 'ndre',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'الحافّة الحمراء — مؤشّر النيتروجين/الكلوروفيل للغطاء الكثيف.',
  },
  {
    id: 'msi',
    labelAr: 'مؤشّر الإجهاد المائيّ (MSI)',
    kind: 'index',
    source: 'msi',
    colormap: 'moisture',
    opacity: 0.85,
    defaultVisible: false,
    description: 'إجهاد مائيّ (SWIR/NIR) — قيمة أعلى = إجهاد أكبر.',
  },

  // ── الرادار (Radar) — طبقة توفّر بلا مصدر بلاطات مُختلَق (نقطة تمديد) ──
  {
    id: 'radar',
    labelAr: 'الرادار (غير متوفّر)',
    kind: 'radar',
    // لا تُنتج المنصّة بلاطات رادار اصطناعيّ اليوم — واصف صريح لا رابط ملفّق.
    source: 'unavailable',
    opacity: 0.7,
    defaultVisible: false,
    description: 'طبقة رادار اصطناعيّ (SAR) — غير منتَجة بعد؛ نقطة تمديد موثّقة.',
  },
] as const satisfies readonly MapLayer[];

// ── المساعِدات (قراءة فقط) ──────────────────────────────────────

/** كلّ الطبقات (نسخة قابلة للتكرار). */
export function listLayers(): MapLayer[] {
  return [...LAYER_REGISTRY];
}

/** طبقة بمعرّفها، أو undefined إن لم توجد. */
export function getLayer(id: string): MapLayer | undefined {
  return LAYER_REGISTRY.find((l) => l.id === id);
}

/** طبقات من نوع مُعطى (مؤشّر/أساس/حدود/رادار). */
export function layersOfKind(kind: MapLayer['kind']): MapLayer[] {
  return LAYER_REGISTRY.filter((l) => l.kind === kind);
}

/** الطبقات الظاهرة افتراضيّاً عند فتح الخريطة. */
export function defaultVisibleLayers(): MapLayer[] {
  return LAYER_REGISTRY.filter((l) => l.defaultVisible);
}
