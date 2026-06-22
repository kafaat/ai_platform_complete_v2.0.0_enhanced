// reports.ts — تجميع تقارير الملخّص (طراز FieldView) من بيانات حقيقيّة فقط.
// منطق نقيّ (لا React/شبكة) ⇒ قابل للاختبار. مصادر الحقيقة:
//   • المواسم (SeasonSummary) — المحصول/الصنف/تاريخ البذار/الغلّة المستهدفة والفعليّة.
//   • العمليّات (Activity) — العدّ حسب النوع/الحالة.
//   • خيارات الحقل (FieldOption) — المساحة/اسم الحقل.
// صدق: لا أرقام مُلفَّقة. الغلّة غير المُسجَّلة null ⇒ تُعرَض «—» لا 0.
import type { SeasonSummary, Activity } from '../services/api';
import type { FieldOption } from './fields';

// كجم/هـ → طن/هـ (الغلّة المُخزَّنة بالكيلوغرام، تُعرَض FieldView-style بالطن).
export const kgHaToTHa = (v: number | null | undefined): number | null =>
  v == null ? null : v / 1000;

// صفّ ملخّص الزراعة: موسم واحد × حقله. area من خيارات الحقل (قد تكون 0 ⇒ «—»).
export interface PlantingRow {
  season_id:   string;
  field_id:    string;
  field_name:  string;
  crop:        string;        // أوّل محصول للموسم أو «—»
  cultivar:    string | null; // الهجين/الصنف
  sowing_date: string | null;
  area_ha:     number | null; // من FieldOption (null إن 0/غائبة)
  status:      string;
}

// صفّ ملخّص الحصاد: غلّة فعليّة مقابل مستهدفة (طن/هـ) + الفجوة. كلّها قد تكون null.
export interface HarvestRow {
  season_id:    string;
  field_id:     string;
  field_name:   string;
  crop:         string;
  actual_t_ha:  number | null; // null ⇒ لا حصاد بعد ⇒ «—»
  target_t_ha:  number | null;
  gap_t_ha:     number | null; // actual - target (null إن أحدهما غائب)
  has_harvest:  boolean;
  status:       string;
}

// تجميع العمليّات: عدّ حسب النوع وحسب الحالة (من البيانات الفعليّة فقط).
export interface ActivitySummary {
  total:       number;
  by_type:     Record<string, number>;
  by_status:   Record<string, number>;
}

const firstCrop = (s: SeasonSummary): string =>
  (Array.isArray(s.crops) && s.crops.length > 0 ? s.crops[0] : null) ?? '—';

const fieldName = (fieldId: string, fields: ReadonlyArray<FieldOption>): string =>
  fields.find((f) => f.id === fieldId)?.name ?? fieldId;

const fieldArea = (fieldId: string, fields: ReadonlyArray<FieldOption>): number | null => {
  const a = fields.find((f) => f.id === fieldId)?.area ?? 0;
  return a > 0 ? a : null;
};

/** صفوف ملخّص الزراعة — موسم لكلّ صفّ، مُثرى باسم/مساحة الحقل. */
export function buildPlantingRows(
  seasons: ReadonlyArray<SeasonSummary>,
  fields: ReadonlyArray<FieldOption>,
): PlantingRow[] {
  return seasons.map((s) => ({
    season_id:   s.season_id,
    field_id:    s.field_id,
    field_name:  fieldName(s.field_id, fields),
    crop:        firstCrop(s),
    cultivar:    s.cultivar,
    sowing_date: s.sowing_date,
    area_ha:     fieldArea(s.field_id, fields),
    status:      s.status,
  }));
}

/** صفوف ملخّص الحصاد — الغلّة الفعليّة/المستهدفة بالطن/هـ + الفجوة الصادقة. */
export function buildHarvestRows(
  seasons: ReadonlyArray<SeasonSummary>,
  fields: ReadonlyArray<FieldOption>,
): HarvestRow[] {
  return seasons.map((s) => {
    const actual = kgHaToTHa(s.actual_yield_kg_ha);
    const target = kgHaToTHa(s.target_yield_kg_ha);
    const gap = actual != null && target != null ? actual - target : null;
    return {
      season_id:   s.season_id,
      field_id:    s.field_id,
      field_name:  fieldName(s.field_id, fields),
      crop:        firstCrop(s),
      actual_t_ha: actual,
      target_t_ha: target,
      gap_t_ha:    gap,
      has_harvest: actual != null,
      status:      s.status,
    };
  });
}

/** تجميع العمليّات حسب النوع/الحالة (من العمليّات الفعليّة، لا تلفيق). */
export function summarizeActivities(activities: ReadonlyArray<Activity>): ActivitySummary {
  const by_type: Record<string, number> = {};
  const by_status: Record<string, number> = {};
  for (const a of activities) {
    const t = a.activity_type || 'unknown';
    const st = a.status || 'unknown';
    by_type[t] = (by_type[t] ?? 0) + 1;
    by_status[st] = (by_status[st] ?? 0) + 1;
  }
  return { total: activities.length, by_type, by_status };
}

// عدد المواسم التي سُجِّلت لها غلّة فعليّة (لِبطاقة الملخّص — لا تلفيق).
export const harvestedCount = (rows: ReadonlyArray<HarvestRow>): number =>
  rows.reduce((n, r) => n + (r.has_harvest ? 1 : 0), 0);

// عرض رقم اختياريّ بطن/هـ (منزلتان) أو «—» الصادقة عند الغياب.
export const tHa = (v: number | null | undefined): string =>
  v == null ? '—' : v.toFixed(2);
