// ═══════════════════════════════════════════════════════════════
// SAHOOL — services/api/season.ts
// عميل واجهة إدخال سجلّ الموسم المُدار (SEASON-RECORD-ENTRY-01 شريحة 3c).
//
// النقاط الستّ يملكها scout-ingest ويُوجَّه إليها عبر البوّابة على البادئة
// النسبيّة ``/api/v1/seasons*`` (nginx يعيد كتابتها إلى المسار الداخليّ للخدمة،
// يحقن توكن الخدمة + المستأجِر الموثّق، ويوقّع تصديق الحافّة على مسار القبول).
// من المتصفّح لا نضيف أيّ ترويسة ثقة — الكوكي sahool_at يُرسَل تلقائيّاً، وkongApi
// يُلحِق Authorization + X-Tenant-ID؛ nginx يجرّد ما لا يثق به ويعيد حقن الموثّق.
//
// القبول (POST .../accept) هو الفعل الحسّاس: البوّابة توقّع هويّة المُراجِع (HMAC
// مقيَّد الوجهة) ولا يمرّ إلّا لدور owner/expert (season-reviewer). الواجهة لا تملك
// السرّ ولا توقّع شيئاً — تُصدِر الطلب فقط، والبوّابة+الخدمة تفرضان الأمان.
// ═══════════════════════════════════════════════════════════════
import { kongApi } from './client';

// ── أنواع الطلب/الردّ (تطابق نماذج season_api.py الخلفيّة) ────────────────────────
export type SowingPrecision = 'day' | 'month' | 'season';
export type SeasonTrustStatus = 'untrusted' | 'accepted' | 'quarantined';

export interface SeasonCropIn {
  variety_name: string;
  crop_registry_ref?: string | null;
  sowing_date: string; // YYYY-MM-DD
  sowing_precision?: SowingPrecision;
  seed_rate_kg_ha?: number | null;
}

export interface SeasonDraftIn {
  field_id: string;
  observed_at_from: string; // YYYY-MM-DD
  observed_at_to: string; // YYYY-MM-DD
  season_label?: string | null;
  source?: string;
  notes?: string | null;
  draft_key?: string | null;
  crop?: SeasonCropIn | null;
}

export interface SeasonPatchIn {
  season_label?: string | null;
  observed_at_from?: string | null;
  observed_at_to?: string | null;
  notes?: string | null;
}

export interface SeasonDraftCreated {
  season_id: string;
  idempotent: boolean;
}

export interface SeasonListRow {
  id: string;
  field_id: string;
  season_label: string | null;
  observed_at_from: string;
  observed_at_to: string;
  trust_status: SeasonTrustStatus;
  has_logbook: boolean;
  accepted_by: string | null;
  accepted_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface SeasonAcceptResult {
  season_id: string;
  trust_status: 'accepted';
  accepted_by: string;
}

// ── ١) إنشاء مسودّة (idempotent على draft_key) ──────────────────────────────────
export const createSeasonDraft = (body: SeasonDraftIn) =>
  kongApi.post<SeasonDraftCreated>('/api/v1/seasons', body).then((r) => r.data);

// ── ٢) تحديث المسودّة (accepted ⇒ 409) ──────────────────────────────────────────
export const patchSeasonDraft = (seasonId: string, body: SeasonPatchIn) =>
  kongApi
    .patch<{ season_id: string; updated: string[] }>(
      `/api/v1/seasons/${encodeURIComponent(seasonId)}`,
      body,
    )
    .then((r) => r.data);

// ── ٣) رفع مرفق الدفتر (الجسم = بايتات الملفّ الخام؛ الخدمة تفحص magic bytes) ─────
// نرسل الملفّ خاماً (لا تغليف multipart): النقطة الخلفيّة تقرأ التدفّق وتكشف النوع من أوّل البايتات
// (JPEG/PNG/PDF) لا من الامتداد. نمرّر File مباشرةً بنوعه كي تصل البايتات كما هي.
export const uploadSeasonLogbook = (seasonId: string, file: File) =>
  kongApi
    .post<{ season_id: string; content_type: string; bytes: number }>(
      `/api/v1/seasons/${encodeURIComponent(seasonId)}/logbook`,
      file,
      { headers: { 'Content-Type': file.type || 'application/octet-stream' } },
    )
    .then((r) => r.data);

// ── ٤) رابط معاينة الدفتر (presigned قصير العمر) ────────────────────────────────
export const getSeasonLogbookUrl = (seasonId: string) =>
  kongApi
    .get<{ url: string; expires_in: number }>(
      `/api/v1/seasons/${encodeURIComponent(seasonId)}/logbook`,
    )
    .then((r) => r.data);

// ── ٥) القبول (الفعل الحسّاس — البوّابة توقّع، الخدمة تتحقّق) ─────────────────────
export const acceptSeason = (seasonId: string) =>
  kongApi
    .post<SeasonAcceptResult>(`/api/v1/seasons/${encodeURIComponent(seasonId)}/accept`)
    .then((r) => r.data);

// ── ٦) قائمة المواسم حسب الحالة (استئناف المسودّات) ─────────────────────────────
export const listSeasons = (status: SeasonTrustStatus = 'untrusted') =>
  kongApi
    .get<{ seasons: SeasonListRow[]; count: number }>('/api/v1/seasons', {
      params: { status },
    })
    .then((r) => r.data);

// ── SEASON-ENTRY-EVENTS-UI: الأبناء (أحداث/حصاد/تكاليف) — تفتح مسار SIM-GOLDEN ──────
export type SeasonEventType =
  | 'tillage'
  | 'land_prep'
  | 'irrigation'
  | 'fert_organic'
  | 'fert_chemical'
  | 'pesticide'
  | 'energy'
  | 'other';

export interface SeasonEventIn {
  event_type: SeasonEventType;
  event_date: string; // YYYY-MM-DD
  date_precision?: SowingPrecision;
  growth_stage?: string | null;
  amount_kg_ha?: number | null;
  amount_mm?: number | null;
  duration_hours?: number | null;
  machinery_hours?: number | null;
  fuel_liters?: number | null;
  energy_kwh?: number | null;
  low_confidence?: boolean;
  npk_composition?: string | null;
  active_ingredient?: string | null;
  description?: string | null;
}

export interface SeasonHarvestIn {
  harvest_date: string; // YYYY-MM-DD
  harvest_precision?: SowingPrecision;
  yield_kg_ha?: number | null;
}

export interface SeasonCostIn {
  item_label: string;
  amount: number;
  currency?: string; // ISO 4217; YER افتراضيّة
  cost_date?: string | null;
  linked_event_id?: string | null;
}

// ٧) إضافة حدث/مدخل (untrusted فقط) — يعيد low_confidence المُوسَّم خادميّاً
export const addSeasonEvent = (seasonId: string, body: SeasonEventIn) =>
  kongApi
    .post<{ season_id: string; event_id: string; low_confidence: boolean }>(
      `/api/v1/seasons/${encodeURIComponent(seasonId)}/events`,
      body,
    )
    .then((r) => r.data);

// ٨) ضبط الحصاد (1:1، upsert) — نقطة المعايرة الذهبيّة
export const setSeasonHarvest = (seasonId: string, body: SeasonHarvestIn) =>
  kongApi
    .post<{ season_id: string; harvest_set: boolean }>(
      `/api/v1/seasons/${encodeURIComponent(seasonId)}/harvest`,
      body,
    )
    .then((r) => r.data);

// ٩) إضافة بند تكلفة (تعدّد عملات آمن)
export const addSeasonCost = (seasonId: string, body: SeasonCostIn) =>
  kongApi
    .post<{ season_id: string; cost_item_id: string }>(
      `/api/v1/seasons/${encodeURIComponent(seasonId)}/costs`,
      body,
    )
    .then((r) => r.data);

export interface SeasonDetail {
  season: Record<string, unknown>;
  crop: Record<string, unknown> | null;
  events: Record<string, unknown>[];
  harvest: Record<string, unknown> | null;
  costs: Record<string, unknown>[];
  calibration_eligible: boolean;
}

// ١٠) تجميعة الموسم + أهليّة المعايرة (للمراجعة/الاستئناف؛ يُظهر هل يُغذّي SIM-GOLDEN)
export const getSeasonDetail = (seasonId: string) =>
  kongApi
    .get<SeasonDetail>(`/api/v1/seasons/${encodeURIComponent(seasonId)}/detail`)
    .then((r) => r.data);
