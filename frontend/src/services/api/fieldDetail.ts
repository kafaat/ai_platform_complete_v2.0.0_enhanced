// ══════════════════════════════════════════════════════
// SAHOOL — services/api/fieldDetail.ts
// تفاصيل الحقل المتقدّمة (كيمياء/مناخ دقيق/ملكيّة). مُستخرجة من api.ts (تفكيك تدريجيّ؛ سلوك محفوظ).
// ══════════════════════════════════════════════════════
import { kongApi } from './client';

// ══════════════════════════════════════════════════════════════════
// FIELD DETAIL — تفاصيل الحقل المتقدّمة (sahool-platform v37). ملء تدريجيّ
// بعد الإنشاء: كيمياء التربة + المناخ الدقيق + الملكيّة. ربط حيّ بلا تلفيق —
// field:view للقراءة (GET /fields/{id})، field:edit للتحديث الجزئيّ (PATCH).
// عند الخطأ (503 DB / 404 حقل / 403 RBAC) يُرمى ليعرض الـUI حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export interface FieldDetail {
  field_id:        string;
  farm_id:         string;
  name_ar:         string;
  crop:            string;
  area_ha:         number;
  quality_grade:   string;
  health_summary_ar: string;
  soil_type?:      string | null;
  manager?:        string | null;
  field_code?:     string | null;
  description?:    string | null;
  water_source?:   string | null;
  ownership_type?: string | null;
  country?:        string | null;
  region?:         string | null;
  lat?:            number | null;
  lon?:            number | null;
  geometry?:       Record<string, unknown> | null;
  // كيمياء التربة (نتائج مختبر)
  soil_ph?:        number | null;
  soil_ec?:        number | null;
  soil_om?:        number | null; // المادّة العضويّة %
  soil_n?:         number | null;
  soil_p?:         number | null;
  soil_k?:         number | null;
  // المناخ الدقيق / التضاريس
  elevation_m?:        number | null;
  slope_pct?:          number | null;
  aspect?:             string | null;
  climate_zone?:       string | null;
  annual_rainfall_mm?: number | null;
  // تفاصيل الملكيّة
  owner_name?:     string | null;
  lease_years?:    number | null;
  registry_no?:    string | null;
  // ملفّ الريّ/المياه التفصيليّ (v41) — يعيدها الخادم؛ تُعرَض للقراءة بحالة "—" صادقة
  irrigation_type?:           string | null;
  irrigation_efficiency_pct?: number | null;
  flow_rate_m3h?:             number | null; // تدفّق المضخّة م³/ساعة
  pump_type?:                 string | null;
  well_depth_m?:              number | null;
  water_ec?:                  number | null; // ملوحة الماء dS/m
  zone_key?:                  string | null; // مفتاح الإقليم القانوني (v49)
  manager_user_id?:           number | null; // FK إلى users(id) (v47)
}

// تحديث جزئيّ: كلّ الحقول اختياريّة — تُرسَل المُعدَّلة فقط (الخادم يحدّثها فقط).
export interface FieldUpdatePatch {
  soil_ph?:            number | null;
  soil_ec?:            number | null;
  soil_om?:            number | null;
  soil_n?:             number | null;
  soil_p?:             number | null;
  soil_k?:             number | null;
  elevation_m?:        number | null;
  slope_pct?:          number | null;
  aspect?:             string | null;
  climate_zone?:       string | null;
  annual_rainfall_mm?: number | null;
  owner_name?:         string | null;
  lease_years?:        number | null;
  registry_no?:        string | null;
}

/** تفاصيل حقل كاملة (field:view). 404 لو ليس للمستأجِر، 503 عند تعطيل DB. */
export const fetchFieldDetail = (fieldId: string): Promise<FieldDetail> =>
  kongApi.get<FieldDetail>(`/api/v1/fields/${fieldId}`).then(r => r.data);

/** تحديث جزئيّ لتفاصيل حقل (field:edit). تُرسَل الحقول المُعدَّلة فقط. */
export const updateField = (fieldId: string, patch: FieldUpdatePatch): Promise<FieldDetail> =>
  kongApi.patch<FieldDetail>(`/api/v1/fields/${fieldId}`, patch).then(r => r.data);

// ── وصفات المعدّل المتغيّر اليدويّة (Manual VRT Prescriptions، v95) ──
// FieldView "manual prescriptions": وصفة **يدويّة** صرفة — المستخدِم يرسم المناطق
// (geometry GeoJSON) ويضبط لكلّ منطقة معدّلاً + وحدة، ثمّ يحفظها (tenant-scoped، RLS).
// لا توليد agronomic آليّ هنا. التصدير (GeoJSON/CSV) يتمّ في الواجهة (Blob/URL).
export interface SavedPrescriptionZone {
  geometry: unknown;   // GeoJSON Polygon (يرسمه المستخدِم)
  rate:     number;    // المعدّل (seeds/m² أو kg/ha)
  unit:     string;    // الوحدة
}

export interface SavedPrescription {
  prescription_id: string;
  field_id:        string;
  name:            string;
  product_type:    'seed' | 'fertility';
  zones:           SavedPrescriptionZone[];
  created_by?:     string | null;
  created_at?:     string;
}

export interface PrescriptionCreateInput {
  prescription_id: string;
  name:            string;
  product_type:    'seed' | 'fertility';
  zones:           SavedPrescriptionZone[];
}

export interface PrescriptionListResponse {
  field_id:      string;
  prescriptions: SavedPrescription[];
  total:         number;
  note_ar?:      string;   // سبب صادق حين القائمة فارغة (DB مُعطَّلة)
}

/** سرد الوصفات المحفوظة لحقل (field:view). 503 عند تعطّل DB، فارغ صادق حين لا وصفات. */
export const fetchPrescriptions = (fieldId: string): Promise<PrescriptionListResponse> =>
  kongApi.get<PrescriptionListResponse>(`/api/v1/fields/${fieldId}/prescriptions`).then(r => r.data);

/** حفظ وصفة يدويّة (field:edit). 422 نوع منتج غير مدعوم، 503 عند تعطّل DB. */
export const createPrescription = (
  fieldId: string,
  payload: PrescriptionCreateInput,
): Promise<SavedPrescription & { persisted: boolean }> =>
  kongApi.post<SavedPrescription & { persisted: boolean }>(
    `/api/v1/fields/${fieldId}/prescriptions`, payload,
  ).then(r => r.data);

// ── استيراد حدّ حقل من ملفّ (GeoJSON/KML) أو نقاط GPS (field:create) ──
// بدل الرسم اليدويّ: نرسل نصّ الملفّ (content) أو نقاط GPS (points) للخادم،
// الذي يحلّلها إلى GeoJSON Polygon ثمّ يعيد استخدام نفس مسار التحقّق/الحفظ
// كإنشاء حقل مرسوم. 400 = تحليل تالف، 422 = هندسة غير صالحة (يُعرَضان بصدق).
export interface FieldImportInput {
  format:        'geojson' | 'kml' | 'gps';
  content?:      string;          // نصّ ملفّ GeoJSON/KML
  points?:       number[][];      // مسار GPS [[lon,lat],...]
  name:          string;
  crop?:         string;
  soil_type?:    string;
  manager?:      string;
  field_code?:   string;
  water_source?: string;
  country?:      string;
  region?:       string;
  boundary_metadata?: Record<string, unknown>;
  idempotency_key?: string;
}

/** يستورد حقلاً من ملفّ/نقاط GPS. يُرجع FieldSummary المُنشأ من ردّ الخادم. */
export const importField = (payload: FieldImportInput): Promise<unknown> => {
  const { idempotency_key, ...body } = payload;
  const config = idempotency_key ? { headers: { 'Idempotency-Key': idempotency_key } } : undefined;
  return kongApi.post('/api/v1/fields/import', body, config).then(r => r.data);
};

// ── دمج/انقسام الحقول ذرّيّاً (POST /merge · /split) — معاملة خادميّة واحدة ──
// تستبدل لاذرّيّة الواجهة (POST جديد + حلقة DELETE) التي كانت تُخلّف حقولاً يتيمة
// عند فشل الحذف. الخادم يُنشئ المدموج/الأطفال ويحذف المصادر في معاملة واحدة (الكلّ
// أو لا شيء)؛ الخطأ (404/409/422/503) يُرمى ليُعرَض بصدق. الهندسة محسوبة @turf في
// الواجهة ويتحقّق منها الخادم (guard_field_geometry).
export interface FieldMergeInput {
  source_field_ids: string[];     // ≥2 معرّفات الحقول المصدر
  name:             string;       // اسم الحقل المدموج
  geometry:         unknown;      // GeoJSON Polygon المدموج (اتّحاد @turf)
  crop?:            string | null;
  soil_type?:       string | null;
  manager?:         string | null;
  farm_id?:         string | null;
  field_code?:      string | null;
  description?:     string | null;
  water_source?:    string | null;
  irrigation_type?: string | null;
  ownership_type?:  string | null;
  gov?:             string | null;
  country?:         string | null;
  region?:          string | null;
}

export interface SplitChildInput {
  name:             string;
  geometry:         unknown;      // GeoJSON Polygon للجزء (محسوب @turf)
  crop?:            string | null;
  soil_type?:       string | null;
  manager?:         string | null;
  field_code?:      string | null;
  description?:     string | null;
  water_source?:    string | null;
  irrigation_type?: string | null;
  ownership_type?:  string | null;
}

export interface FieldSplitInput {
  source_field_id: string;
  children:        SplitChildInput[];   // 2..10 حقول وليدة
}

/** يدمج حقولاً مصدر في حقل واحد ذرّيّاً (field:create). يُرجِع FieldSummary المدموج. */
export const mergeFields = (payload: FieldMergeInput): Promise<unknown> =>
  kongApi.post('/api/v1/fields/merge', payload).then(r => r.data);

/** يقسّم حقلاً إلى حقول وليدة ذرّيّاً (field:create). يُرجِع قائمة FieldSummary للأطفال. */
export const splitField = (payload: FieldSplitInput): Promise<unknown> =>
  kongApi.post('/api/v1/fields/split', payload).then(r => r.data);

