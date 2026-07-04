// GIS Expert Catalog — كونسول قراءة لطبقة GIS السحابيّة-الأصل (STAC · OGC · COG):
// كتالوج STAC (بوّابة/مجموعات/عناصر بحث)، مطابقة OGC ومجموعاتها، وخطّة كاش
// البلاطات — مسارات خلفيّة قائمة بلا أيّ واجهة قارئة. صدق: قيم الخادم تمرّ كما
// هي، الغائب يُعرَض «—» لا صفراً، الحقول الناقصة تُسقَط لا تُختلَق، وحقول الوصف
// (description/title/reason) تُعرَض نصّاً كما وردت.
//
// الأشكال منسوخة حرفيّاً من الخلفيّة:
//   services/sahool-platform/api/routers/gis_cloud_native.py
//   shared/gis/phase5_runtime.py (stac_landing_page · stac_collections_response ·
//     OGC_CONFORMANCE · ogc_collections · tile_cache_plan)
//   shared/gis/cloud_native_runtime.py (stac_item_from_record)

// ── أنواع STAC ───────────────────────────────────────────────────

export interface StacLink {
  rel: string;
  href: string;
  type?: string;
  method?: string;
  title?: string;
}

/** GET /api/v1/gis/cloud-native/stac — phase5_runtime.stac_landing_page() */
export interface StacLandingPage {
  type: string; // "Catalog"
  stac_version: string;
  id: string;
  title: string;
  description: string;
  conformsTo: string[];
  links: StacLink[];
}

export interface StacExtent {
  spatial: { bbox: (number | null)[][] };
  temporal: { interval: (string | null)[][] };
}

export interface StacCollection {
  type: string; // "Collection"
  stac_version: string;
  id: string; // "sahool-<index_type>"
  title: string;
  description: string;
  license?: string;
  extent: StacExtent;
  links: StacLink[];
}

/** GET /api/v1/gis/cloud-native/stac/collections — stac_collections_response() */
export interface StacCollectionsResponse {
  collections: StacCollection[];
  links: StacLink[];
}

export interface StacAsset {
  href: string;
  type?: string;
  roles?: string[];
  title?: string;
}

/** خصائص عنصر STAC — cloud_native_runtime.stac_item_from_record() */
export interface StacItemProperties {
  datetime: string | null;
  'sahool:tenant_id': string;
  'sahool:field_id': string | null;
  'sahool:raster_id': string;
  'sahool:index_type': string;
  'eo:cloud_cover': number;
  'sahool:quality_score': number | null;
  gsd: number;
}

export interface StacItem {
  type: string; // "Feature"
  stac_version: string;
  id: string;
  collection: string;
  bbox: number[] | null;
  geometry: unknown | null;
  properties: StacItemProperties;
  assets: Record<string, StacAsset>;
  links: StacLink[];
}

/** GET /api/v1/gis/cloud-native/stac/search — FeatureCollection من الراوتر */
export interface StacSearchResponse {
  type: string; // "FeatureCollection"
  features: StacItem[];
  numberMatched: number;
}

// ── أنواع OGC ───────────────────────────────────────────────────

/** GET /api/v1/gis/cloud-native/ogc/conformance — {"conformsTo": OGC_CONFORMANCE} */
export interface OgcConformanceResponse {
  conformsTo: string[];
}

export interface OgcCollection {
  id: string;
  title: string;
  itemType: string; // "feature" | "coverage" (قيمة الخادم تمرّ كما هي)
  crs: string[];
  links: StacLink[];
}

/** GET /api/v1/gis/cloud-native/ogc/collections — phase5_runtime.ogc_collections() */
export interface OgcCollectionsResponse {
  collections: OgcCollection[];
}

// ── أنواع خطّة كاش البلاطات ─────────────────────────────────────

export interface TileCachePlanEntry {
  raster_id: string;
  index_type: string;
  cache_key: string;
  minzoom: number;
  maxzoom: number;
  ttl_seconds: number;
}

/** GET /api/v1/gis/cloud-native/tile-cache-plan — phase5_runtime.tile_cache_plan() */
export interface TileCachePlan {
  strategy: string; // "cdn+nginx+redis"
  entries: TileCachePlanEntry[];
  purge_on: string[];
}

// ── مساعدات عرض صرفة ────────────────────────────────────────────

/** الغائب (null/undefined/'') يُعرَض «—» — لا صفر مُختلَق ولا نصّ فارغ. */
export function dash(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—';
  return String(value);
}

/**
 * شارة قصيرة من رابط مطابقة (conformance URI) — للعرض فقط؛ الرابط الكامل يبقى
 * متاحاً كـtitle. STAC: «STAC <الجزء الأخير> v<الإصدار>»، OGC: «<ogcapi-…>/<الأخير>»،
 * وغير المعروف يمرّ كما ورد (لا اختراع).
 */
export function conformanceBadge(uri: string): string {
  const parts = uri.split('/').filter(Boolean);
  if (uri.includes('stacspec.org')) {
    const last = parts[parts.length - 1];
    const version = parts.find((p) => /^v\d/.test(p));
    return version ? `STAC ${last} ${version}` : `STAC ${last}`;
  }
  const ogcPart = parts.find((p) => p.startsWith('ogcapi'));
  if (ogcPart) return `${ogcPart}/${parts[parts.length - 1]}`;
  return uri; // قيمة الخادم كما هي
}

/**
 * تسمية المدى الزمنيّ لمجموعة STAC من extent.temporal.interval — الفترة الأولى
 * «من → إلى»؛ حدود null (شكل الخادم عند غياب التواريخ) ⇒ «—».
 */
export function temporalExtentLabel(interval: (string | null)[][] | null | undefined): string {
  const first = interval?.[0];
  if (!first || (first[0] == null && first[1] == null)) return '—';
  return `${first[0] ?? '—'} → ${first[1] ?? '—'}`;
}

export interface CollectionRow {
  id: string;
  title: string;
  description: string;
  temporal: string;
  license?: string;
}

/** صفوف عرض مجموعات STAC — description/license تُمرَّر كما وردت؛ license الغائب يُسقَط. */
export function collectionRows(resp: StacCollectionsResponse | null | undefined): CollectionRow[] {
  return (resp?.collections ?? []).map((c) => {
    const row: CollectionRow = {
      id: c.id,
      title: c.title,
      description: c.description,
      temporal: temporalExtentLabel(c.extent?.temporal?.interval),
    };
    if (c.license !== undefined) row.license = c.license;
    return row;
  });
}

export interface ItemsQualitySummary {
  count: number;
  /** متوسّط الغيوم من القيم الرقميّة فقط — لا قيم ⇒ null (يُعرَض «—» لا 0). */
  avgCloudPct: number | null;
  minQuality: number | null;
  maxQuality: number | null;
  indexTypes: string[];
}

/** ملخّص جودة عناصر بحث STAC — الحقول غير الرقميّة تُسقَط من الحساب لا تُصفَّر. */
export function itemsQualitySummary(items: StacItem[] | null | undefined): ItemsQualitySummary {
  const list = items ?? [];
  const clouds = list
    .map((i) => i.properties?.['eo:cloud_cover'])
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const qualities = list
    .map((i) => i.properties?.['sahool:quality_score'])
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  const indexTypes = [...new Set(
    list.map((i) => i.properties?.['sahool:index_type']).filter((v): v is string => !!v),
  )].sort();
  return {
    count: list.length,
    avgCloudPct: clouds.length
      ? Math.round((clouds.reduce((a, b) => a + b, 0) / clouds.length) * 10) / 10
      : null,
    minQuality: qualities.length ? Math.min(...qualities) : null,
    maxQuality: qualities.length ? Math.max(...qualities) : null,
    indexTypes,
  };
}

export interface CachePlanSummary {
  strategy: string;
  totalEntries: number;
  /** إدخالات TTL يوم كامل (86400ث — جودة ≥70 حسب منطق الخادم). */
  longTtl: number;
  /** إدخالات TTL أقصر (6 ساعات — جودة أدنى). */
  shortTtl: number;
  purgeOn: string[];
}

/** ملخّص خطّة كاش البلاطات — العتبة 86400ث من الخادم نفسه (tile_cache_plan). */
export function cachePlanSummary(plan: TileCachePlan | null | undefined): CachePlanSummary | null {
  if (!plan) return null;
  const entries = plan.entries ?? [];
  const longTtl = entries.filter((e) => e.ttl_seconds >= 86400).length;
  return {
    strategy: plan.strategy,
    totalEntries: entries.length,
    longTtl,
    shortTtl: entries.length - longTtl,
    purgeOn: plan.purge_on ?? [],
  };
}

/** تسمية عربيّة لنوع عناصر مجموعة OGC — غير المعروف يمرّ كما ورد من الخادم. */
export function ogcItemTypeLabel(itemType: string): string {
  if (itemType === 'feature') return 'معالم (feature)';
  if (itemType === 'coverage') return 'تغطية (coverage)';
  return itemType;
}
