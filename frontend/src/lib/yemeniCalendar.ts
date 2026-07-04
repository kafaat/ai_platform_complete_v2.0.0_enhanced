// Yemeni Agricultural Calendar — يعكس طبقة التقويم الزراعيّ/الفلكيّ اليمنيّ المُخزَّنة
// (/api/v1/calendars/today + agricultural-proverbs/for-date) في الواجهة — التميّز
// المحلّيّ لساهول. صدق صارم: الخادم يصرّح display_only=true وused_in_decision_engine=false
// والواجهة تعرض هذا التصريح حرفيّاً (سياق تراثيّ-رصديّ، لا يدخل محرّك القرار؛ التوقيت
// الفعليّ على GDD/الفيزياء)، والتواريخ تقريبيّة كما ينوّه الخادم.

export interface LunarMansion {
  order: number;
  name_ar: string;
  approx_start_ar: string;
  duration_days: number;
  season_ar: string;
  note_ar: string;
}

export interface HimyariteMonth {
  order: number;
  name_ar: string;
  approx_gregorian_ar: string;
  meaning_ar: string;
  season_himyari_ar: string;
}

export interface RegionalProfile {
  region_ar: string;
  governorates_ar: string[];
  primary_system_ar: string;
  structure_ar: string;
  source_ar: string;
  notes_ar: string;
}

export interface PlantingWindow {
  supported: boolean;
  crop_ar?: string;
  season_ar?: string;
  window_ar?: string;
  optimal_ar?: string;
  harvest_ar?: string;
  yemen_note_ar?: string;
  disclaimer_ar?: string;
  message_ar?: string;
}

export interface PlantingFit {
  supported: boolean;
  status?: 'optimal' | 'acceptable' | 'off_window' | string;
  status_ar?: string;
  advice_ar?: string;
  message_ar?: string;
}

export interface CalendarTodayContext {
  display_only: boolean;
  used_in_decision_engine: boolean;
  date_iso: string;
  active_mansion: LunarMansion | null;
  himyarite_month: HimyariteMonth | null;
  regional_profile: RegionalProfile | null;
  marker_for_proverbs?: string | null;
  disclaimer_ar?: string;
  planting?: { window: PlantingWindow; current_month_fit: PlantingFit };
  error_ar?: string;
}

export interface Proverb {
  text_ar: string;
  meaning_ar: string;
  marker_ar: string;
  source_ar?: string;
}

export interface ProverbsForDateResponse {
  proverbs: Proverb[];
  active_marker_ar?: string;
  matched_by_date?: boolean;
  date_iso?: string;
  note_bridge_ar?: string;
  error_ar?: string;
}

export interface CalendarFact {
  label: string;
  value: string;
}

/** حقائق العرض من سياق اليوم — الغائب يسقط، والخطأ يُعاد كما جاء من الخادم. */
export function calendarFacts(ctx: CalendarTodayContext | null | undefined): CalendarFact[] {
  if (!ctx || ctx.error_ar) return [];
  const facts: CalendarFact[] = [];
  const m = ctx.active_mansion;
  if (m) {
    facts.push({ label: 'المنزلة القمريّة', value: `${m.name_ar} (${m.season_ar})` });
    if (m.note_ar) facts.push({ label: 'دلالتها', value: m.note_ar });
  }
  const h = ctx.himyarite_month;
  if (h) facts.push({ label: 'الشهر الحميريّ', value: `${h.name_ar} — ${h.season_himyari_ar}` });
  const r = ctx.regional_profile;
  if (r) facts.push({ label: 'نظام المنطقة', value: `${r.region_ar}: ${r.primary_system_ar}` });
  return facts;
}

/** لون حكم ملاءمة الشهر من حالة الخادم (لا إعادة حكم). */
export function plantingFitTone(fit: PlantingFit | null | undefined): 'good' | 'ok' | 'bad' | 'unknown' {
  if (!fit?.supported || !fit.status) return 'unknown';
  if (fit.status === 'optimal') return 'good';
  if (fit.status === 'acceptable') return 'ok';
  if (fit.status === 'off_window') return 'bad';
  return 'unknown';
}

/** أوّل الأمثال المطابقة (المطابقة الزمنيّة مُفضَّلة كما يعلّمها الخادم matched_by_date). */
export function topProverbs(resp: ProverbsForDateResponse | null | undefined, limit = 2): Proverb[] {
  if (!resp || resp.error_ar || !Array.isArray(resp.proverbs)) return [];
  return resp.proverbs.slice(0, limit);
}
