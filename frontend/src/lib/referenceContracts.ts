// referenceContracts — شكلُ استجابات المراجع المعرفيّة كما تُصدِرها المنصّة فعلاً.
//
// FRONTEND-REFERENCE-LISTS-CALL-MAP-ON-AN-ENVELOPE-01: مسارات التقاويم والنظائر المناخيّة
// تُعيد **غلافاً** (``{mansions:[…]}`` · ``{months:[…]}`` · ``{regions:[…]}`` · ``{crops:{…}}``)،
// والواجهة كانت تستدعي ``.map`` على الغلاف نفسه فتنهار الصفحة.
//
// القاعدة: يُفكّ الغلافُ المعروف وحدَه. أيُّ شكلٍ آخر يرمي ``ApiShapeError`` فيظهر للمستخدم
// «تعذّر التحميل» — **لا** قائمةً فارغة، لأنّ القائمة الفارغة تقول «لا بيانات» وهي كاذبة هنا
// وتُخفي انحرافَ العقد بين الخادم والواجهة.

export class ApiShapeError extends Error {
  readonly endpoint: string;

  constructor(endpoint: string, expected: string) {
    super(`استجابة غير متوقّعة من ${endpoint}: المتوقّع ${expected}`);
    this.name = "ApiShapeError";
    this.endpoint = endpoint;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** يفكّ ``{<key>: [...]}``؛ وغيرُه خطأُ عقدٍ لا قائمةٌ فارغة. العناصرُ ``unknown`` حتّى تُفحَص. */
export function unwrapList(
  data: unknown,
  key: string,
  endpoint: string,
): unknown[] {
  if (isRecord(data) && Array.isArray(data[key])) return data[key] as unknown[];
  throw new ApiShapeError(endpoint, `كائناً فيه مصفوفة «${key}»`);
}

type FieldKind = "number" | "string";

function hasField(
  item: Record<string, unknown>,
  field: string,
  kind: FieldKind,
): boolean {
  const value = item[field];
  return kind === "number"
    ? typeof value === "number" && Number.isFinite(value)
    : typeof value === "string" && value.trim() !== "";
}

/**
 * يفكّ الغلاف ثمّ يفحص كلَّ عنصرٍ بحقول الخادم الإلزاميّة. فحصُ الغلاف وحده كان يقبل
 * ``{mansions:[null]}`` فتنهار اللوحةُ عند ``m.order``، و``{months:[{index:1}]}`` فيختفي
 * الحقلُ المُعاد تسميتُه خلف بدائل العرض — والعنصرُ المنحرف انحرافُ عقدٍ كالغلاف المنحرف.
 */
function itemsWith<T>(
  data: unknown,
  key: string,
  endpoint: string,
  required: Record<string, FieldKind>,
): T[] {
  const fields = Object.keys(required).join(" و");
  return unwrapList(data, key, endpoint).map((item) => {
    if (
      !isRecord(item) ||
      !Object.entries(required).every(([field, kind]) =>
        hasField(item, field, kind),
      )
    ) {
      throw new ApiShapeError(endpoint, `عناصرَ فيها ${fields}`);
    }
    return item as T;
  });
}

// ── التقاويم (/api/v1/calendars/*) ────────────────────────────────────────────

export interface LunarMansion {
  order?: number;
  name_ar?: string;
  approx_start_ar?: string;
  duration_days?: number;
  season_ar?: string;
  note_ar?: string;
  [k: string]: unknown;
}

export interface HimyariteMonth {
  order?: number;
  name_ar?: string;
  approx_gregorian_ar?: string;
  meaning_ar?: string;
  season_himyari_ar?: string;
  [k: string]: unknown;
}

export interface RegionalProfile {
  region_ar?: string;
  governorates_ar?: string[];
  primary_system_ar?: string;
  [k: string]: unknown;
}

export const parseLunarMansions = (data: unknown): LunarMansion[] =>
  itemsWith<LunarMansion>(
    data,
    "mansions",
    "/api/v1/calendars/lunar-mansions",
    {
      order: "number",
      name_ar: "string",
    },
  );

export const parseHimyariteMonths = (data: unknown): HimyariteMonth[] =>
  itemsWith<HimyariteMonth>(
    data,
    "months",
    "/api/v1/calendars/himyarite-months",
    {
      order: "number",
      name_ar: "string",
    },
  );

export const parseRegionalProfiles = (data: unknown): RegionalProfile[] =>
  itemsWith<RegionalProfile>(
    data,
    "profiles",
    "/api/v1/calendars/regional-profiles",
    {
      region_ar: "string",
    },
  );

// ── النظائر المناخيّة (/api/v1/climate-analogs/*) ─────────────────────────────

/** منطقةٌ نظيرة بالصيغة التي تعرضها اللوحة. ``region`` هو ما يُمرَّر لمسار التفصيل. */
export interface ClimateAnalogRegion {
  region: string;
  name_ar: string;
  country_ar?: string;
  /** كسرٌ بين 0 و1 (الخادم يُرسل نسبةً مئويّة). */
  similarity?: number;
  [k: string]: unknown;
}

export function parseClimateAnalogRegions(
  data: unknown,
): ClimateAnalogRegion[] {
  const endpoint = "/api/v1/climate-analogs/list";
  return unwrapList(data, "regions", endpoint).map((raw) => {
    if (
      !isRecord(raw) ||
      typeof raw.region_ar !== "string" ||
      !raw.region_ar.trim()
    ) {
      throw new ApiShapeError(endpoint, "منطقةً فيها region_ar");
    }
    const pct = raw.similarity_pct;
    return {
      ...raw,
      region: raw.region_ar,
      name_ar: raw.region_ar,
      country_ar:
        typeof raw.country_ar === "string" ? raw.country_ar : undefined,
      similarity:
        typeof pct === "number" && Number.isFinite(pct) ? pct / 100 : undefined,
    };
  });
}

export interface DesertCrop {
  crop: string;
  name_ar: string;
  /** تقييمُ الملاءمة كما يكتبه الخادم («ممتاز»، «متحمّل»…). */
  rating?: string;
  /** الفئة حين يُطلب الكلّ (أشجار · موسميّة · حديثة). */
  category?: string;
}

const CATEGORY_AR: Record<string, string> = {
  trees_ar: "أشجار",
  seasonal_ar: "موسميّة",
  modern_ar: "حديثة",
};

function cropsFromMap(
  map: unknown,
  endpoint: string,
  category?: string,
): DesertCrop[] {
  if (!isRecord(map))
    throw new ApiShapeError(endpoint, "خريطةَ «محصول ← تقييم»");
  return Object.entries(map).map(([name, rating]) => ({
    crop: name,
    name_ar: name,
    rating: typeof rating === "string" ? rating : undefined,
    category,
  }));
}

/** ``{crops:{…}}`` لفئةٍ واحدة، أو ``{all_categories:{trees_ar:{…},…}}`` للكلّ. */
export function parseDesertCrops(data: unknown): DesertCrop[] {
  const endpoint = "/api/v1/climate-analogs/desert-crops";
  if (isRecord(data) && "crops" in data)
    return cropsFromMap(data.crops, endpoint);
  if (isRecord(data) && isRecord(data.all_categories)) {
    return Object.entries(data.all_categories).flatMap(([key, map]) =>
      cropsFromMap(map, endpoint, CATEGORY_AR[key] ?? key),
    );
  }
  throw new ApiShapeError(endpoint, "كائناً فيه crops أو all_categories");
}
