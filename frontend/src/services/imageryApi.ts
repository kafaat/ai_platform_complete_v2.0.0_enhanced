// ═══════════════════════════════════════════════════════════════
// imageryApi.ts — دوالّ مجال الصور/المؤشّرات المكانيّة (مُستخرَجة من api.ts)
// تعتمد فقط على عملاء HTTP من apiClients (بلا mocks/حالة). api.ts يعيد التصدير
// عبر `export *` فيبقى أيّ import { ... } from '.../services/api' يعمل دون تغيير.
// السلوك محفوظ: نسخ حرفيّ للدوالّ/الأنواع.
// ═══════════════════════════════════════════════════════════════

import { kongApi, rasterApi } from './apiClients';

/** قاعدة عنوان خدمة الراستر (بلا شرطة لاحقة) — لبناء رابط قالب بلاطات NDVI
 *  الحقيقيّة ({z}/{x}/{y}) التي يفسّرها Leaflet. نفس مصدر FieldIndicatorMap. */
export const rasterBaseUrl = (): string =>
  (rasterApi.defaults.baseURL || '').replace(/\/+$/, '');


export const normalizeIndicatorIndex = (index?: string | null): string => {
  const key = (index || 'ndvi').trim().toLowerCase().replace(/[\s-]+/g, '_');
  const aliases: Record<string, string> = {
    ndvu: 'ndvi',
    vegetation: 'ndvi',
    moisture: 'ndmi',
    salinity: 'salinity',
    salt: 'salinity',
    soil_salinity: 'salinity',
  };
  return aliases[key] || key;
};

/** رابط قالب بلاطات مؤشّر حقل من خدمة الراستر (NDVI افتراضيّاً). نُبقي
 *  {z}/{x}/{y} حرفيّاً ليفسّرها Leaflet. لا تلوين مفبرك: إن لم تتوفّر صورة COG
 *  صافية للحقل/التاريخ تُرجِع الخدمة بلاطات فارغة (لا طبقة مُختلَقة). */
export const fieldIndicatorTileUrl = (
  fieldId: string,
  index = 'ndvi',
  date = 'latest',
  tenantId?: string | null,
  cacheVersion?: string | number | null,
): string => {
  const params = new URLSearchParams({ index: normalizeIndicatorIndex(index), date });
  if (tenantId) params.set('tid', tenantId);
  if (cacheVersion !== undefined && cacheVersion !== null && String(cacheVersion) !== '') params.set('v', String(cacheVersion));
  const qs = params.toString();
  // eslint-disable-next-line no-template-curly-in-string
  return `${rasterBaseUrl()}/v1/fields/${fieldId}/tiles/{z}/{x}/{y}.png?${qs}`;
};


/** تشغيل معالجة صور Sentinel-2 الحقيقيّة للحقل عبر المنصّة/raster-service. */
export const refreshFieldImagery = (fieldId: string, date?: string | null) =>
  kongApi.post(`/api/v1/fields/${fieldId}/imagery/refresh`, date && date !== 'latest' ? { date } : undefined).then(r => r.data);


export interface FieldImageryDateOption {
  date: string;
  cloud_pct?: number | null;
  cloud_cover?: number | null;
  has_cog?: boolean;
  scene_id?: string | null;
}

/** تواريخ Sentinel/CDSE المتاحة للحقل؛ تُستخدم لربط زر التاريخ فعلياً برابط البلاطات. */
export const fetchFieldImageryAvailableDates = (fieldId: string): Promise<FieldImageryDateOption[]> =>
  kongApi.get(`/api/v1/fields/${fieldId}/available-dates`).then((r) => {
    const raw = r.data?.dates ?? r.data?.items ?? r.data ?? [];
    if (!Array.isArray(raw)) return [];
    return raw
      .map((x: unknown) => {
        if (typeof x === 'string') return { date: x } as FieldImageryDateOption;
        if (!x || typeof x !== 'object') return null;
        const obj = x as Record<string, unknown>;
        const date = String(obj.date ?? obj.acquisition_date ?? obj.datetime ?? '').slice(0, 10);
        if (!date) return null;
        return {
          date,
          cloud_pct: typeof obj.cloud_pct === 'number' ? obj.cloud_pct : (typeof obj.cloud_cover === 'number' ? obj.cloud_cover : null),
          cloud_cover: typeof obj.cloud_cover === 'number' ? obj.cloud_cover : null,
          has_cog: Boolean(obj.has_cog ?? obj.ready ?? false),
          scene_id: typeof obj.scene_id === 'string' ? obj.scene_id : null,
        } as FieldImageryDateOption;
      })
      .filter(Boolean) as FieldImageryDateOption[];
  }).catch(() => []);


export type ImageryBackfillPreset = 'auto_12_months' | 'extended_3_years' | 'research_5_years' | 'custom';

export interface HistoricalImageryBackfillPayload {
  preset?: ImageryBackfillPreset;
  from_date?: string;
  to_date?: string;
  months?: number;
  indices?: string[];
  max_cloud_pct?: number;
  limit_per_month?: number;
  apply_cloud_mask?: boolean;
  clip_polygon_geojson?: unknown;
  dry_run?: boolean;
}

/** خيارات قابلة للتبديل لسحب الصور التاريخية: 12 شهر/3 سنوات/5 سنوات/مخصص. */
export const fetchImageryBackfillPolicy = () =>
  rasterApi.get('/v1/imagery/backfill/policy').then(r => r.data);

/** إنشاء خطة/مهمة backfill تاريخية للحقل. dry_run=true يعطي تقدير تكلفة/عدد مشاهد قبل التشغيل.
 *  يمرّ عبر المنصّة (kongApi) لا raster مباشرةً: نقطة raster محروسة بتوكن خدمة لا يحقنه
 *  المتصفّح، والمنصّة تحقن التوكن + هندسة الحقل المُتحقَّقة كحدود قصّ. */
export const runHistoricalImageryBackfill = (fieldId: string, payload: HistoricalImageryBackfillPayload) =>
  kongApi.post(`/api/v1/fields/${fieldId}/imagery/backfill`, payload).then(r => r.data);
