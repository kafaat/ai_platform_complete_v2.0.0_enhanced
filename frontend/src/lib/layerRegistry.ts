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
  /** الخدمة أو المزود المسؤول عن إنتاج الطبقة، لمنع Layer Manager من استدعاء scaffolds. */
  sourceService?: 'raster-service' | 'sahool-platform' | 'basemap-provider' | 'field-geometry' | 'unavailable';
  /** هل تحتاج الطبقة تجهيزاً/Backfill قبل العرض، مثل TrueColor أو المؤشرات التاريخية. */
  requiresBackfill?: boolean;
  /** endpoint فحص التوفر runtime. يدعم {field_id} كقالب. */
  availabilityEndpoint?: string;
  /** طبقة بديلة آمنة عند عدم توفر المصدر runtime. */
  fallbackLayerId?: string;
  /** حقوق/نَسَب المزود عند عرض الطبقة. */
  attribution?: string;
  /** أقصى تكبير موصى به للطبقة. */
  maxZoom?: number;
  /** هل تحتاج الطبقة مفتاحاً عاماً من Vite قبل عرضها؟ */
  requiresToken?: boolean;
  /** اسم متغيّر البيئة العام في Vite مثل VITE_MAPBOX_TOKEN. */
  tokenEnv?: string;
  /** طبقة موثّقة لكن غير مفعّلة في الواجهة لأنها تحتاج تكاملاً رسميّاً خاصاً. */
  disabled?: boolean;
  /** سبب تعطيل الطبقة أو إخفائها من المنتقي. */
  disabledReason?: string;
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
    sourceService: 'basemap-provider',
    opacity: 1,
    defaultVisible: true,
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.esri.com/">Esri</a> — World Imagery',
    description: 'خريطة أساس بصور جوّيّة (ArcGIS World Imagery).',
  },
  {
    id: 'mapbox-satellite',
    labelAr: 'Mapbox Satellite Streets',
    kind: 'basemap',
    // يُفعَّل فقط عند وجود VITE_MAPBOX_TOKEN. لا يُستخدم للتحليل الآليّ/SAM2؛ هو خلفيّة عرض.
    source: 'https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/256/{z}/{x}/{y}@2x?access_token={token}',
    sourceService: 'basemap-provider',
    opacity: 1,
    defaultVisible: false,
    maxZoom: 22,
    attribution: '&copy; <a href="https://www.mapbox.com/">Mapbox</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    requiresToken: true,
    tokenEnv: 'VITE_MAPBOX_TOKEN',
    description: 'خريطة أساس احترافيّة عالية الوضوح. تظهر في الواجهة فقط عند ضبط VITE_MAPBOX_TOKEN.',
  },

  {
    id: 'maptiler-satellite',
    labelAr: 'MapTiler Satellite',
    kind: 'basemap',
    // يُفعَّل فقط عند وجود VITE_MAPTILER_KEY. بديل احترافي لـMapbox كخلفية عرض، لا كمدخل تحليل.
    source: 'https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key={token}',
    sourceService: 'basemap-provider',
    opacity: 1,
    defaultVisible: false,
    maxZoom: 20,
    attribution: '&copy; <a href="https://www.maptiler.com/">MapTiler</a> &copy; OpenStreetMap contributors',
    requiresToken: true,
    tokenEnv: 'VITE_MAPTILER_KEY',
    description: 'خريطة أساس احترافيّة بديلة. تظهر في الواجهة فقط عند ضبط VITE_MAPTILER_KEY.',
  },
  {
    id: 'google-satellite-official',
    labelAr: 'Google Satellite (رسمي — غير مفعّل)',
    kind: 'basemap',
    // Google Map Tiles API يحتاج session/token flow رسميّاً؛ لا نستخدم روابط tiles غير موثّقة.
    source: 'google-map-tiles-api://satellite',
    sourceService: 'basemap-provider',
    opacity: 1,
    defaultVisible: false,
    maxZoom: 22,
    attribution: 'Google Maps Platform',
    requiresToken: true,
    tokenEnv: 'VITE_GOOGLE_MAP_TILES_API_KEY',
    disabled: true,
    disabledReason: 'يتطلب تكامل Google Map Tiles API الرسمي وإنشاء جلسة بلاطات؛ لا تُستعمل روابط Google غير الرسمية.',
    description: 'موثّق كخيار لاحق فقط. Mapbox/Esri هما الطبقتان العمليّتان الآن.',
  },
  {
    id: 'light',
    labelAr: 'خريطة فاتحة',
    kind: 'basemap',
    // BASEMAP_LIGHT — Carto light_all (FieldIndicatorMap.tsx / AddFieldWithMap.tsx)
    source: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
    sourceService: 'basemap-provider',
    opacity: 1,
    defaultVisible: false,
    maxZoom: 19,
    attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
    description: 'خريطة أساس فاتحة (CARTO light) — بديل للصور الجوّيّة.',
  },

  // ── حدود الحقل (Boundary) — تراكب مضلّع من هندسة الحقل ──
  {
    id: 'field-boundary',
    labelAr: 'حدود الحقل',
    kind: 'boundary',
    // مشتقّ من هندسة الحقل عبر geomToPolygon (lib/geo) ويُرسم كـLeaflet Polygon.
    source: 'field-geometry',
    sourceService: 'field-geometry',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'satellite',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'الحافّة الحمراء — مؤشّر النيتروجين/الكلوروفيل للغطاء الكثيف.',
  },
  {
    id: 'reci',
    labelAr: 'مؤشّر الكلوروفيل بالحافّة الحمراء (RECI)',
    kind: 'index',
    source: 'reci',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر كلوروفيل متقدم يعتمد NIR/Red-edge؛ يظهر عند الطلب لا كثمبنيل افتراضي.',
  },
  {
    id: 'gci',
    labelAr: 'مؤشّر الكلوروفيل الأخضر (GCI)',
    kind: 'index',
    source: 'gci',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'تقدير حساسية الكلوروفيل عبر NIR/Green؛ تحليل متقدم.',
  },
  {
    id: 'arvi',
    labelAr: 'مؤشّر الغطاء المقاوم للغلاف الجوي (ARVI)',
    kind: 'index',
    source: 'arvi',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر نباتي يقلل أثر الغلاف الجوي باستخدام الأزرق/الأحمر.',
  },
  {
    id: 'sipi',
    labelAr: 'مؤشّر الصبغات النباتية (SIPI)',
    kind: 'index',
    source: 'sipi',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر متقدم لحالة الصبغات/الإجهاد؛ يظهر عند الطلب.',
  },
  {
    id: 'nbr',
    labelAr: 'مؤشّر الحرق/البقايا (NBR)',
    kind: 'index',
    source: 'nbr',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر NIR/SWIR2 مفيد للبقايا والحرق والجفاف الشديد.',
  },
  {
    id: 'ccci',
    labelAr: 'مؤشّر محتوى كلوروفيل المظلة (CCCI)',
    kind: 'index',
    source: 'ccci',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'نسبة NDRE إلى NDVI؛ مؤشر متقدم للكلوروفيل/النيتروجين.',
  },
  {
    id: 'vari',
    labelAr: 'مؤشّر الخضرة المرئي (VARI)',
    kind: 'index',
    source: 'vari',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر RGB مرئي؛ مفيد كتحليل متقدم لكنه أقل ثباتاً من مؤشرات NIR.',
  },
  {
    id: 'gli',
    labelAr: 'مؤشّر الورقة الخضراء (GLI)',
    kind: 'index',
    source: 'gli',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'ndvi',
    opacity: 0.85,
    defaultVisible: false,
    description: 'مؤشّر RGB للخضرة؛ تحليل متقدم عند الطلب.',
  },
  {
    id: 'bsi',
    labelAr: 'مؤشّر التربة العارية (BSI)',
    kind: 'index',
    source: 'bsi',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
    colormap: 'soil',
    opacity: 0.85,
    defaultVisible: false,
    description: 'فصل التربة العارية باستخدام BLUE/RED/NIR/SWIR2؛ مفيد قبل الزراعة وبعد الحصاد.',
  },
  {
    id: 'msi',
    labelAr: 'مؤشّر الإجهاد المائيّ (MSI)',
    kind: 'index',
    source: 'msi',
    sourceService: 'raster-service',
    requiresBackfill: true,
    availabilityEndpoint: '/api/v1/fields/{field_id}/available-dates',
    fallbackLayerId: 'truecolor',
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
    sourceService: 'unavailable',
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


/**
 * يحلّ رابط البلاطات إذا كان يحتاج token. الدالة لا تقرأ import.meta.env مباشرةً
 * حتى تبقى قابلة للاختبار؛ مرّر import.meta.env من مكوّنات Vite.
 */
export function resolveLayerSource(layer: MapLayer | undefined, env: Record<string, string | undefined> = {}): string | undefined {
  if (!layer || layer.disabled) return undefined;
  if (!layer.requiresToken) return layer.source;
  const tokenName = layer.tokenEnv;
  const token = tokenName ? env[tokenName] : undefined;
  if (!token) return undefined;
  return layer.source.replace('{token}', encodeURIComponent(token));
}

/** خرائط الأساس القابلة للعرض فعلياً في الواجهة بعد احترام tokens والتعطيل. */
export function availableBasemapLayers(env: Record<string, string | undefined> = {}): MapLayer[] {
  return layersOfKind('basemap').filter((layer) => Boolean(resolveLayerSource(layer, env)));
}

/** طبقات raster التي تحتاج backfill/availability check قبل العرض. */
export function layersRequiringBackfill(): MapLayer[] {
  // LAYER_REGISTRY هو `as const satisfies MapLayer[]` فأنواعه حرفيّة بلا المفاتيح الاختياريّة؛
  // نوسّع إلى MapLayer للوصول إلى الحقل الاختياريّ requiresBackfill.
  return (LAYER_REGISTRY as readonly MapLayer[]).filter((layer) => layer.requiresBackfill === true);
}

/** هل طبقة معيّنة يجب أن تُفحص عبر availabilityEndpoint قبل إظهارها. */
export function requiresLayerAvailabilityCheck(layerId: string): boolean {
  const layer = getLayer(layerId);
  return Boolean(layer?.requiresBackfill && layer?.availabilityEndpoint);
}


/**
 * يكيّف قالب بلاطات Leaflet إلى قالب raster صالح لـMapLibre.
 * MapLibre لا يفهم {s} ولا {r}، بينما بعض مزودي Leaflet يستعملونهما.
 */
export function toMapLibreRasterUrl(url: string): string {
  return url.replace('{s}', 'a').replace('{r}', '');
}
