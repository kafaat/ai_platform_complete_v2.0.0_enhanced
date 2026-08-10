// ══════════════════════════════════════════════════════
// SAHOOL — services/api/reports.ts
// تقارير وتحليلات (حيّة، tenant-scoped + RBAC). مُستخرجة من api.ts (تفكيك تدريجيّ؛ سلوك محفوظ).
// ══════════════════════════════════════════════════════
import { kongApi } from './client';

// ══════════════════════════════════════════════════════════════════
// REPORTS — تقارير وتحليلات (حيّة، tenant-scoped + RBAC field:view)
// تجميع من جداول قائمة (مزارع/حقول/مواسم/عمليّات/تنبيهات) عبر COUNT/SUM/GROUP BY.
// لا fallback وهميّ — الخطأ (503 DB / 404 / 403) يُرفع لتعرض الواجهة حالة صادقة.
// ══════════════════════════════════════════════════════════════════
export interface AreaByCrop {
  crop:    string;
  area_ha: number;
}
export interface FarmSummary {
  farms_count:          number;
  fields_count:         number;
  total_area_ha:        number;
  active_seasons_count: number;
  activities_total:     number;
  activities_by_status: Record<string, number>;
  open_alerts_count:    number;
  area_by_crop:         AreaByCrop[];
}
export const getFarmSummary = (): Promise<FarmSummary> =>
  kongApi.get<FarmSummary>('/api/v1/reports/farm-summary').then(r => r.data);

export interface ReportAlert {
  alert_id:   string;
  field_id:   string | null;
  alert_type: string;
  severity:   string;
  title_ar:   string | null;
  message_ar: string | null;
  status:     string;
  created_at: string | null;
}
export interface FieldReportSeason {
  season_id:   string;
  crops:       string[];
  cultivar:    string | null;
  sowing_date: string | null;
  season_end:  string | null;
  status:      string;
}
export interface FieldReportSummary {
  field_id:             string;
  name:                 string;
  area_ha:              number;
  crop:                 string | null;
  soil_type:            string | null;
  current_season:       FieldReportSeason | null;
  activities_total:     number;
  activities_by_type:   Record<string, number>;
  activities_by_status: Record<string, number>;
  recent_alerts:        ReportAlert[];
}
export const getFieldReportSummary = (fieldId: string): Promise<FieldReportSummary> =>
  kongApi.get<FieldReportSummary>(`/api/v1/reports/field/${fieldId}/summary`).then(r => r.data);

export interface SeasonReportSummary {
  season_id:        string;
  field_id:         string;
  crops:            string[];
  cultivar:         string | null;
  irrigation_type:  string | null;
  sowing_date:      string | null;
  season_end:       string | null;
  status:           string;
  stage_count:      number;
  activities_count: number;
}
export const getSeasonReportSummary = (seasonId: string): Promise<SeasonReportSummary> =>
  kongApi.get<SeasonReportSummary>(`/api/v1/reports/season/${seasonId}/summary`).then(r => r.data);

// ── محاكاة الموسم (Crop-model simulation, RUE/FAO-56) — v39 ──────────
// تقديرات نموذجيّة (إنتاج/GDD/LAI/ماء) بنطاق وثقة صريحة — لا أرقام قاطعة.
export interface SeasonSimResult {
  season_id:           string;
  crop:                string;
  crop_recognized:     boolean;
  days_simulated:      number;
  gdd_total:           number;
  gdd_to_maturity:     number;
  maturity_reached:    boolean;
  lai_max:             number;
  biomass_kg_ha:       number;
  yield_kg_ha:         number;
  yield_low_kg_ha:     number;
  yield_high_kg_ha:    number;
  water_need_mm:       number;
  water_supply_mm:     number | null;
  water_stress_factor: number;
  confidence:          number;
  rationale_ar:        string;
  assumptions_ar:      string[];
  warnings_ar:         string[];
  sim_ran_at:          string;
}
// يشغّل محاكاة محصوليّة للموسم ويحفظ ناتجها على الخادم (FIELD_EDIT). 503 عند تعذّر
// الطقس/القاعدة، 404 إن غاب الموسم عن المستأجِر.
export const simulateSeason = (seasonId: string): Promise<SeasonSimResult> =>
  kongApi.post<SeasonSimResult>(`/api/v1/seasons/${seasonId}/simulate`).then(r => r.data);

// ── مواسم الحقل (مع نتائج المحاكاة المُخزَّنة sim_*) — حيّة عبر البوّابة ──
// GET /api/v1/fields/{field_id}/seasons (SeasonSummary[]، الأحدث أولاً، tenant-scoped
// + FIELD_VIEW). حقول sim_* تكون مملوءة فقط بعد تشغيل /simulate (تقديريّة)، وإلّا null
// ⇒ تعرضها الواجهة كحالة "—" صادقة لا أرقاماً مُلفَّقة. لا fallback وهميّ.
export interface SeasonSummary {
  season_id:        string;
  field_id:         string;
  crops:            string[];
  cultivar:         string | null;
  irrigation_type:  string | null;
  seed_rate_kg_ha:  number | null;
  land_leveling_date: string | null;
  plowing_date:     string | null;
  sowing_date:      string | null;
  season_end:       string | null;
  stages:           Record<string, unknown>[];
  status:           string; // active | closed | ...
  created_at:       string | null;
  // مؤشّرات الموسم الزراعيّة (v42) — تُدخَل عند الإنشاء/التحديث، وإلّا null
  target_yield_kg_ha:  number | null; // الغلّة المستهدفة كجم/هـ
  plant_density:       number | null; // كثافة النبات (نبتة/م²)
  row_spacing_cm:      number | null; // المسافة بين الخطوط (سم)
  seed_variety_source: string | null; // مصدر/صنف البذور
  // حقول أغرونوميّة (v52) — اختياريّة، وإلّا null
  maturity:            string | null; // فترة النضج (early/medium/late)
  tillage_type:        string | null; // نوع الحراثة
  actual_yield_kg_ha:  number | null; // الغلّة الفعليّة بعد الحصاد كجم/هـ
  notes_ar:            string | null; // ملاحظات
  // نتائج المحاكاة (تُملأ عند تشغيل /simulate، وإلّا null — تقديريّة بنطاق وثقة)
  sim_yield_kg_ha:   number | null;
  sim_biomass_kg_ha: number | null;
  sim_gdd_total:     number | null;
  sim_lai_max:       number | null;
  sim_water_mm:      number | null;
  sim_ran_at:        string | null;
}

export const fetchSeasons = (fieldId: string): Promise<SeasonSummary[]> =>
  kongApi.get<SeasonSummary[]>(`/api/v1/fields/${fieldId}/seasons`).then(r => (Array.isArray(r.data) ? r.data : []));

