// FieldView Climate Risk — يعكس ثلاث قدرات خلفيّة كانت بلا قارئ واجهة على الحقل النشط:
//   • الحساسيّة المائيّة للمراحل (/api/v1/water-sensitivity/calendar — FAO-56 + سياق يمنيّ)
//   • نوافذ المخاطر المناخيّة الموسميّة + ساعات البرودة (/api/v1/seasonal-risk/*)
//   • المناطق العالميّة المشابهة مناخيّاً (/api/v1/climate-analogs/list)
// صدق: أحكام الخادم (sensitivity/severity/verdict_ar/can_satisfy) تمرّ كما هي ولا يُعاد
// الحكم في الواجهة؛ القيمة المجهولة ⇒ null وتُعرَض «—»؛ الأقسام الغائبة تُسقَط لا تُصفَّر؛
// note_ar/disclaimer_ar/principle_ar من الخادم تُحفَظ في الأنواع وتُعرَض حرفيّاً.
// اختيار الإقليم يدويّ من المستخدم (لا استنتاج آليّ من الموقع) — كما في صفحات المعايرة.

// ── أنواع الاستجابات كما تأتي من الخادم (بنية فعليّة، لا تخمين) ──

/** مرحلة في التقويم المائي — StageSensitivity.to_dict() في crop_water_sensitivity.py */
export interface WaterStage {
  stage_key?: string;
  name_ar?: string | null;
  /** قيمة الخادم: low | moderate | high | critical — تمرّ كما هي */
  sensitivity?: string | null;
  water_share_pct?: number | null;
  note_ar?: string | null;
  is_critical_window?: boolean;
}

/** استجابة GET /api/v1/water-sensitivity/calendar?crop= */
export interface WaterCalendarResponse {
  supported: boolean;
  message_ar?: string;               // عند عدم الدعم
  crop?: string;
  crop_ar?: string | null;
  season_total_mm?: string | null;   // نطاق نصّي من الخادم مثل "350-600"
  season_ar?: string | null;
  drought_tolerance_ar?: string | null;
  critical_window_ar?: string | null;
  irrigation_frequency_ar?: string | null;
  yemen_context_ar?: string | null;
  moderate_stress_threshold_ar?: string | null;
  stages?: WaterStage[];
  disclaimer_ar?: string;
}

/** خطر مناخي موسمي — عنصر hazards في seasonal_risk.zone_risk_calendar */
export interface ZoneHazard {
  hazard_ar?: string | null;
  season_ar?: string | null;
  risk_to_ar?: string | null;
  /** قيمة الخادم: high | medium | low — تمرّ كما هي */
  severity?: string | null;
}

/** استجابة GET /api/v1/seasonal-risk/calendar?zone= */
export interface SeasonalRiskCalendarResponse {
  supported: boolean;
  message_ar?: string;
  zone?: string;
  zone_name_ar?: string | null;
  hazards?: ZoneHazard[];
  high_severity_count?: number;
  principle_ar?: string;
  advice_ar?: string;
  disclaimer_ar?: string;
  source_ar?: string;
}

/** استجابة GET /api/v1/seasonal-risk/chill-hours?zone= */
export interface ChillHoursResponse {
  supported: boolean;
  message_ar?: string;
  zone?: string;
  zone_name_ar?: string | null;
  estimated_chill_hours?: number | null;
  min_temp_c?: number | null;
  max_altitude_m?: number | null;
  /** احتياج كلّ شجرة (ساعات برودة دنيا) — مفاتيح عربيّة من الخادم */
  crops_chill_requirement?: Record<string, number>;
  /** حكم الخادم لكلّ شجرة (يكفي/لا يكفي) — لا يُعاد حسابه في الواجهة */
  can_satisfy?: Record<string, boolean>;
  verdict_ar?: string | null;
  principle_ar?: string;
  disclaimer_ar?: string;
}

/** منطقة مشابهة — عنصر regions في climate_analogs.list_analog_regions */
export interface AnalogRegion {
  region_ar?: string | null;
  country_ar?: string | null;
  similarity_pct?: number | null;    // الخادم يستعمل .get() — قد تغيب
  relevance_ar?: string | null;
  biggest_problem_ar?: string | null;
  proven_crops_ar?: string[];
}

/** استجابة GET /api/v1/climate-analogs/list */
export interface ClimateAnalogsListResponse {
  regions?: AnalogRegion[];
  count?: number;
  principle_ar?: string;
  disclaimer_ar?: string;
}

// ── خيارات الإقليم (اختيار يدويّ — المفاتيح مفاتيح الخادم في agro_climate_zones) ──

export interface ZoneOption {
  key: string;
  ar: string;
}

/** الأقاليم الستّة المدعومة في seasonal-risk (تسميات مختصرة للاختيار؛
 *  الاسم الكامل يأتي من الخادم في zone_name_ar بعد الجلب). */
export const ZONE_OPTIONS: ZoneOption[] = [
  { key: 'tihama', ar: 'تهامة' },
  { key: 'western_highlands', ar: 'المرتفعات الغربيّة' },
  { key: 'central_highlands', ar: 'المرتفعات الوسطى' },
  { key: 'eastern_plateau', ar: 'الهضبة الشرقيّة' },
  { key: 'inland_desert', ar: 'الصحراء الداخليّة' },
  { key: 'southern_coast', ar: 'الساحل الجنوبي' },
];

// ── تحويلات عرض نقيّة ──

export interface Fact {
  label: string;
  value: string;
}

export type SensitivityTone = 'critical' | 'high' | 'moderate' | 'low' | 'unknown';
export type SeverityTone = 'high' | 'medium' | 'low' | 'unknown';

/** ترجمة عرضيّة لقيم حساسيّة الخادم (الخادم يرسلها بالإنجليزيّة فقط) —
 *  قيمة غير معروفة ⇒ null وتُعرَض «—» (لا تخمين). */
const SENSITIVITY_AR: Record<string, string> = {
  critical: 'حرجة',
  high: 'عالية',
  moderate: 'متوسّطة',
  low: 'منخفضة',
};

export function sensitivityLabelAr(sensitivity: string | null | undefined): string | null {
  if (typeof sensitivity !== 'string') return null;
  return SENSITIVITY_AR[sensitivity] ?? null;
}

/** نغمة لونيّة تعكس قيمة الخادم نفسها — لا إعادة حكم، فقط تمرير للمعروف. */
export function sensitivityTone(sensitivity: string | null | undefined): SensitivityTone {
  return sensitivity === 'critical' || sensitivity === 'high' || sensitivity === 'moderate' || sensitivity === 'low'
    ? sensitivity
    : 'unknown';
}

export function severityTone(severity: string | null | undefined): SeverityTone {
  return severity === 'high' || severity === 'medium' || severity === 'low' ? severity : 'unknown';
}

export const SENSITIVITY_COLOR: Record<SensitivityTone, string> = {
  critical: '#fca5a5',
  high: '#fdba74',
  moderate: '#fde68a',
  low: '#86efac',
  unknown: '#64748b',
};

export const SEVERITY_COLOR: Record<SeverityTone, string> = {
  high: '#fca5a5',
  medium: '#fde68a',
  low: '#86efac',
  unknown: '#64748b',
};

/** حقائق التقويم المائي للعرض — الغائب يُسقَط لا يُختلَق. */
export function waterCalendarFacts(resp: WaterCalendarResponse | null | undefined): Fact[] {
  if (!resp?.supported) return [];
  const facts: Fact[] = [];
  const push = (label: string, v: string | null | undefined) => {
    if (typeof v === 'string' && v.trim() !== '') facts.push({ label, value: v });
  };
  push('الموسم', resp.season_ar);
  if (typeof resp.season_total_mm === 'string' && resp.season_total_mm.trim() !== '') {
    facts.push({ label: 'الاحتياج الموسمي', value: `${resp.season_total_mm} مم` });
  }
  push('تحمّل الجفاف', resp.drought_tolerance_ar);
  push('النافذة الحرجة', resp.critical_window_ar);
  push('وتيرة الريّ', resp.irrigation_frequency_ar);
  return facts;
}

export interface WaterStageRow {
  key: string;
  name_ar: string;
  sensitivity: string | null;      // قيمة الخادم الحرفيّة
  label_ar: string | null;         // الترجمة العرضيّة — null إن كانت القيمة مجهولة
  tone: SensitivityTone;
  share_pct: number | null;
  note_ar: string | null;
  is_critical_window: boolean;
}

/** صفوف مراحل التقويم المائي — مرحلة بلا اسم تُسقَط (لا اختلاق أسماء). */
export function waterStageRows(resp: WaterCalendarResponse | null | undefined): WaterStageRow[] {
  if (!resp?.supported || !Array.isArray(resp.stages)) return [];
  const rows: WaterStageRow[] = [];
  for (const s of resp.stages) {
    const name = typeof s?.name_ar === 'string' && s.name_ar.trim() !== '' ? s.name_ar : null;
    if (!name) continue;
    const sens = typeof s.sensitivity === 'string' ? s.sensitivity : null;
    rows.push({
      key: typeof s.stage_key === 'string' && s.stage_key !== '' ? s.stage_key : name,
      name_ar: name,
      sensitivity: sens,
      label_ar: sensitivityLabelAr(sens),
      tone: sensitivityTone(sens),
      share_pct: typeof s.water_share_pct === 'number' && Number.isFinite(s.water_share_pct) ? s.water_share_pct : null,
      note_ar: typeof s.note_ar === 'string' && s.note_ar.trim() !== '' ? s.note_ar : null,
      is_critical_window: s.is_critical_window === true,
    });
  }
  return rows;
}

export interface HazardRow {
  hazard_ar: string;
  season_ar: string | null;
  risk_to_ar: string | null;
  severity: string | null;         // قيمة الخادم الحرفيّة
  tone: SeverityTone;
}

/** صفوف المخاطر الموسميّة — خطر بلا اسم يُسقَط، والشدّة تمرّ كما حكم بها الخادم. */
export function hazardRows(resp: SeasonalRiskCalendarResponse | null | undefined): HazardRow[] {
  if (!resp?.supported || !Array.isArray(resp.hazards)) return [];
  const rows: HazardRow[] = [];
  for (const h of resp.hazards) {
    const name = typeof h?.hazard_ar === 'string' && h.hazard_ar.trim() !== '' ? h.hazard_ar : null;
    if (!name) continue;
    const sev = typeof h.severity === 'string' ? h.severity : null;
    rows.push({
      hazard_ar: name,
      season_ar: typeof h.season_ar === 'string' && h.season_ar.trim() !== '' ? h.season_ar : null,
      risk_to_ar: typeof h.risk_to_ar === 'string' && h.risk_to_ar.trim() !== '' ? h.risk_to_ar : null,
      severity: sev,
      tone: severityTone(sev),
    });
  }
  return rows;
}

/** حقائق ساعات البرودة — الصفر قيمة حقيقيّة من الخادم (سهول حارّة) وتُعرَض. */
export function chillFacts(resp: ChillHoursResponse | null | undefined): Fact[] {
  if (!resp?.supported) return [];
  const facts: Fact[] = [];
  if (typeof resp.estimated_chill_hours === 'number' && Number.isFinite(resp.estimated_chill_hours)) {
    facts.push({ label: 'ساعات البرودة المقدّرة', value: `~${resp.estimated_chill_hours} ساعة` });
  }
  if (typeof resp.min_temp_c === 'number' && Number.isFinite(resp.min_temp_c)) {
    facts.push({ label: 'أدنى متوسّط حرارة', value: `${resp.min_temp_c}°م` });
  }
  if (typeof resp.max_altitude_m === 'number' && Number.isFinite(resp.max_altitude_m)) {
    facts.push({ label: 'أعلى ارتفاع', value: `${resp.max_altitude_m} م` });
  }
  return facts;
}

export interface ChillCropFit {
  crop_ar: string;
  need_hours: number;
  /** حكم الخادم (can_satisfy) — لا يُعاد حسابه في الواجهة */
  satisfied: boolean;
}

/** ملاءمة الأشجار المتساقطة — فقط ما ورد له احتياجٌ **وحكمٌ** من الخادم معاً. */
export function chillCropFit(resp: ChillHoursResponse | null | undefined): ChillCropFit[] {
  if (!resp?.supported) return [];
  const need = resp.crops_chill_requirement;
  const can = resp.can_satisfy;
  if (!need || !can) return [];
  const out: ChillCropFit[] = [];
  for (const [crop, hours] of Object.entries(need)) {
    if (typeof hours !== 'number' || !Number.isFinite(hours)) continue;
    if (typeof can[crop] !== 'boolean') continue;
    out.push({ crop_ar: crop, need_hours: hours, satisfied: can[crop] });
  }
  return out;
}

export interface AnalogRow {
  region_ar: string;
  country_ar: string | null;
  similarity_pct: number | null;   // قد تغيب من الخادم ⇒ تُعرَض «—»
  relevance_ar: string | null;
  biggest_problem_ar: string | null;
  proven_crops_ar: string[];
}

/** صفوف المناطق المشابهة — ترتيب الخادم يُحفَظ (هو من رتّب بالتشابه، لا نعيد الترتيب). */
export function analogRows(
  resp: ClimateAnalogsListResponse | null | undefined,
  limit = 5,
): AnalogRow[] {
  if (!resp || !Array.isArray(resp.regions)) return [];
  const rows: AnalogRow[] = [];
  for (const r of resp.regions) {
    const name = typeof r?.region_ar === 'string' && r.region_ar.trim() !== '' ? r.region_ar : null;
    if (!name) continue;
    rows.push({
      region_ar: name,
      country_ar: typeof r.country_ar === 'string' && r.country_ar.trim() !== '' ? r.country_ar : null,
      similarity_pct:
        typeof r.similarity_pct === 'number' && Number.isFinite(r.similarity_pct) ? r.similarity_pct : null,
      relevance_ar: typeof r.relevance_ar === 'string' && r.relevance_ar.trim() !== '' ? r.relevance_ar : null,
      biggest_problem_ar:
        typeof r.biggest_problem_ar === 'string' && r.biggest_problem_ar.trim() !== '' ? r.biggest_problem_ar : null,
      proven_crops_ar: Array.isArray(r.proven_crops_ar)
        ? r.proven_crops_ar.filter((c): c is string => typeof c === 'string' && c.trim() !== '')
        : [],
    });
    if (rows.length >= limit) break;
  }
  return rows;
}
