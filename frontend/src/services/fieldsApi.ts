// ═══════════════════════════════════════════════════════════════
// fieldsApi.ts — دوالّ مجال الحقول (مُستخرَجة من api.ts)
// تفاصيل الحقل + التحديث الجزئيّ · الوصفات اليدويّة · استيراد الحدود ·
// دمج/انقسام الحقول · مساحة عمل الحقل. وحدة ورقة (leaf module): تستورد العميل
// kongApi من ./apiClients بلا دورة استيراد. api.ts يعيد التصدير عبر `export *`
// فيبقى كلّ import من '.../services/api' يعمل دون تغيير. السلوك محفوظ: نسخ حرفيّ.
// ═══════════════════════════════════════════════════════════════

import { kongApi } from './apiClients';

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
}

/** يستورد حقلاً من ملفّ/نقاط GPS. يُرجع FieldSummary المُنشأ من ردّ الخادم. */
export const importField = (payload: FieldImportInput): Promise<unknown> =>
  kongApi.post('/api/v1/fields/import', payload).then(r => r.data);

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

// ══════════════════════════════════════════════════════════════════
// FIELD WORKSPACE — مساحة عمل الحقل (المصدر الأساسيّ لكرت «Field Workspace Map»)
// GET /api/v1/fields/{field_id}/workspace (fields.py:508 ⇒ assemble_workspace):
// ملخّص الحقل + كتالوج طبقات قابلة للتبديل (كلّ طبقة تُعلن توفّرها بصدق:
// available/on_demand/missing) + تفسير التضاريس + خطّ زمنيّ من أحداث مسجّلة فقط.
// عرض صرف (display_only) — لا قرار مفروض. لا fallback وهميّ: عند الخطأ (404 حقل
// ليس للمستأجِر / 503 DB) يُرمى ليعرض الـUI حالة صادقة. الحدود (geometry) تُجلب
// عبر fetchFieldDetail، وطبقة NDVI الحقيقيّة من خدمة الراستر (rasterApi) عند الطلب.
// ══════════════════════════════════════════════════════════════════

/** حالة توفّر طبقة كما يُعلنها الخادم بصدق. */
export type WorkspaceLayerStatus = 'available' | 'on_demand' | 'missing';

/** طبقة عرض واحدة في كتالوج مساحة العمل (display_only — لا تفرض قراراً). */
export interface WorkspaceLayer {
  key:          string;
  label_ar:     string;
  category:     string; // vegetation | terrain | soil | water
  available:    boolean;
  status:       WorkspaceLayerStatus | string;
  display_only: boolean;
  note_ar:      string;
}

/** ملخّص الحقل المُضمَّن في مساحة العمل (مأخوذ من أعمدة الحقل، قد يكون null). */
export interface WorkspaceFieldSummary {
  name_ar:   string | null;
  crop:      string | null;
  area_ha:   number | null;
  soil_type: string | null;
}

/** بطاقة خطّ زمنيّ واحدة (من أحداث مسجّلة فقط — لا تاريخ مخترَع). */
export interface WorkspaceTimelineCard {
  occurred_at: string;
  event_type:  string;
  op_ar:       string;
  category:    string;
  issue_tags:  string[];
}

/** تفسير التضاريس المُضمَّن (enrich_terrain) — شكل مفتوح، اختياريّ بالكامل. */
export interface WorkspaceTerrain {
  field_id?:        string;
  elevation_m?:     number | null;
  slope_pct?:       number | null;
  aspect?:          string | null;
  [k: string]:      unknown;
}

/** مساحة عمل الحقل الكاملة (GET /workspace) — عرض صرف. */
export interface FieldWorkspace {
  field_id:               string | null;
  display_only:           boolean;
  field:                  WorkspaceFieldSummary;
  layers:                 WorkspaceLayer[];
  available_layer_count:  number;
  terrain:                WorkspaceTerrain | null;
  timeline:               WorkspaceTimelineCard[];
  timeline_total:         number;
  honesty_note_ar:        string;
}

/** يجلب مساحة عمل الحقل (field:view). 404 لو ليس للمستأجِر، 503 عند تعطيل DB.
 *  لا fallback وهميّ — الخطأ يُرمى ليعرض الـUI حالة صادقة. */
export const fetchFieldWorkspace = (
  fieldId: string,
  timelineLimit = 50,
): Promise<FieldWorkspace> =>
  kongApi
    .get<FieldWorkspace>(`/api/v1/fields/${fieldId}/workspace`, {
      params: { timeline_limit: timelineLimit },
    })
    .then(r => r.data);
