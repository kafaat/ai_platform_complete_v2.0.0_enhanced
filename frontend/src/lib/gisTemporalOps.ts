// gisTemporalOps — مساعِدات نقيّة لعمليّات نواة GIS الهندسيّة + التحكيم الزمني +
// محاكاة ماذا-لو + مخاطر المرحلة الموسميّة + إعادة البناء من الأحداث + رابط النَّسَب +
// تحليل التجارب الحقليّة. هذه نقاط backend يتيمة (P3, agronomist) بلا قارئ واجهة.
//
// صدق صارم: كلّ حكم/نصّ من الخادم يُعرَض حرفيّاً — هذه الدوالّ لا تحسب هندسة ولا
// تُصدِر أحكاماً؛ فقط (١) حارس تفكيك JSON يُعيد خطأً صادقاً لا يرمي استثناءً،
// و(٢) تلخيص للهندسة التي أعادها الخادم (نوع/عدد رؤوس/أجزاء — لا مساحة مُختلَقة)،
// و(٣) استخراج حقائق العرض من ردود الخادم كما هي. الغائب «—» لا صفراً.

/** حقيقة عرض صغيرة (تسمية: قيمة) — نفس أسلوب بطاقات fieldview الأخرى. */
export interface OpFact {
  label: string;
  value: string;
}

/** تنسيق رقم منتهٍ بمنازل محدّدة؛ غير الرقم/غير المنتهي ⇒ «—» (لا اختلاق). */
export function fmtNum(v: unknown, digits = 2): string {
  return typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';
}

// ─── حارس تفكيك JSON (لا يرمي) ────────────────────────────────────
// نمط مطابق لحارس GeoJSON في AgronomyConsistencyCard، لكن مُستخرَج كدالّة نقيّة
// مُختبَرة: النصّ الفارغ حالة محايدة (لا خطأ)، والفاسد يُعيد رسالة عربيّة صادقة.

/** يفكّك نصّاً إلى كائن JSON بأمان: {obj, error}. الفارغ ⇒ {null,null}؛ الفاسد/غير الكائن ⇒ error. */
export function parseJsonObject(text: string): { obj: Record<string, unknown> | null; error: string | null } {
  const t = (text ?? '').trim();
  if (t === '') return { obj: null, error: null };
  let parsed: unknown;
  try {
    parsed = JSON.parse(t);
  } catch {
    return { obj: null, error: 'JSON غير صالح — تحقّق من الصيغة.' };
  }
  if (parsed == null || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return { obj: null, error: 'المُدخَل ليس كائن JSON (object).' };
  }
  return { obj: parsed as Record<string, unknown>, error: null };
}

// ─── تلخيص الهندسة التي أعادها الخادم ─────────────────────────────
// لا محرّر خريطة كامل — فقط حقائق النتيجة (النوع + عدد الرؤوس + الأجزاء). العدّ
// نقيّ من إحداثيّات GeoJSON التي أرجعها PostGIS (لا نخترع مساحة لا يُرجِعها الخادم).

/** يعدّ المواضِع (positions) داخل مصفوفة إحداثيّات GeoJSON متداخلة — نقيّ ومتعدٍّ. */
export function countPositions(coords: unknown): number {
  if (!Array.isArray(coords)) return 0;
  // موضِع = مصفوفة تبدأ برقمين ([lng, lat, …]).
  if (coords.length >= 2 && typeof coords[0] === 'number' && typeof coords[1] === 'number') {
    return 1;
  }
  return coords.reduce<number>((sum, c) => sum + countPositions(c), 0);
}

export interface GeometrySummary {
  type: string;
  vertices: number;
  parts: number;
}

/** ملخّص هندسة GeoJSON أرجعها الخادم: النوع + عدد الرؤوس + الأجزاء. null إن لم تكن هندسة. */
export function geometrySummary(geom: unknown): GeometrySummary | null {
  if (geom == null || typeof geom !== 'object' || Array.isArray(geom)) return null;
  const g = geom as Record<string, unknown>;
  const type = typeof g.type === 'string' ? g.type : null;
  if (!type) return null;
  if (type === 'GeometryCollection') {
    const members = Array.isArray(g.geometries) ? g.geometries : [];
    const vertices = members.reduce<number>(
      (sum, m) => sum + countPositions((m as Record<string, unknown> | null)?.coordinates),
      0,
    );
    return { type, vertices, parts: members.length };
  }
  return { type, vertices: countPositions(g.coordinates), parts: 1 };
}

/** سطر عرض موجز لهندسة (النوع · رؤوس · أجزاء) أو «—» عند غيابها. */
export function geometryLabel(geom: unknown): string {
  const s = geometrySummary(geom);
  if (!s) return '—';
  const parts = s.parts > 1 ? ` · ${s.parts} جزء` : '';
  return `${s.type} · ${s.vertices} رأس${parts}`;
}

// ─── ألوان الشدّة (للقيم المعروفة فقط — المجهول محايد) ───────────────
const SEVERITY_COLOR: Record<string, string> = {
  info: '#7dd3fc',
  low: '#86efac',
  medium: '#fde68a',
  high: '#fdba74',
  critical: '#fca5a5',
};

/** لون شدّة معروفة (issue/hazard) — المجهول/الغائب رماديّ محايد. */
export function severityColor(sev: string | null | undefined): string {
  return sev ? (SEVERITY_COLOR[sev.toLowerCase()] ?? '#64748b') : '#64748b';
}

// ─── ردود الخادم (الحقول كما يُرجِعها المعالِج حرفيّاً) ────────────────

/** علم «الميزة غير مُفعَّلة» (404) — مُشترَك في كلّ ردّ محروس بعَلَم. */
export interface Disableable {
  disabled?: boolean;
}

export interface GisBufferResult extends Disableable {
  operation?: string;
  dry_run?: boolean;
  distance_m?: number;
  result?: unknown;
}
export interface GisUnionResult extends Disableable {
  operation?: string;
  dry_run?: boolean;
  result?: unknown;
}
export interface GisSplitResult extends Disableable {
  operation?: string;
  dry_run?: boolean;
  part_count?: number;
  result?: unknown;
}
export interface GisValidateResult extends Disableable {
  operation?: string;
  dry_run?: boolean;
  is_valid?: boolean;
  reason?: string | null;
  repaired?: unknown;
}

/** حقائق فحص الطوبولوجيا: السبب (نصّ ST_IsValidReason) + ملخّص الهندسة المُصلَّحة. */
export function validateFacts(r: GisValidateResult | undefined): OpFact[] {
  if (!r) return [];
  const facts: OpFact[] = [];
  if (r.reason) facts.push({ label: 'السبب', value: r.reason });
  if (r.repaired != null) facts.push({ label: 'المُصلَّحة', value: geometryLabel(r.repaired) });
  return facts;
}

/** حقائق الـbuffer: المسافة (م) + ملخّص الهندسة المُوسَّعة. */
export function bufferFacts(r: GisBufferResult | undefined): OpFact[] {
  if (!r) return [];
  const facts: OpFact[] = [];
  if (typeof r.distance_m === 'number') facts.push({ label: 'المسافة (م)', value: fmtNum(r.distance_m, 1) });
  if (r.result != null) facts.push({ label: 'النتيجة', value: geometryLabel(r.result) });
  return facts;
}

/** حقائق الـsplit: عدد الأجزاء (من الخادم) + ملخّص المجموعة. */
export function splitFacts(r: GisSplitResult | undefined): OpFact[] {
  if (!r) return [];
  const facts: OpFact[] = [];
  if (typeof r.part_count === 'number') facts.push({ label: 'عدد الأجزاء', value: String(r.part_count) });
  if (r.result != null) facts.push({ label: 'المجموعة', value: geometryLabel(r.result) });
  return facts;
}

/** حقائق الـunion: ملخّص الهندسة المُوحَّدة. */
export function unionFacts(r: GisUnionResult | undefined): OpFact[] {
  if (!r?.result) return [];
  return [{ label: 'المُوحَّدة', value: geometryLabel(r.result) }];
}

export interface TemporalIssue {
  severity?: string;
  code?: string;
  message_ar?: string;
}
export interface TemporalCheckResult extends Disableable {
  valid?: boolean;
  age_span_days?: number | null;
  issues?: TemporalIssue[];
}

/** حقائق التحكيم الزمني: صلاحيّة + مدى العمر (أيّام). */
export function temporalCheckFacts(r: TemporalCheckResult | undefined): OpFact[] {
  if (!r) return [];
  const facts: OpFact[] = [];
  if (typeof r.age_span_days === 'number') facts.push({ label: 'مدى العمر (يوم)', value: fmtNum(r.age_span_days, 1) });
  return facts;
}

/** قائمة قضايا الاتّساق الزمني (شدّة/رمز/رسالة) كما أرجعها الخادم. */
export function temporalCheckIssues(r: TemporalCheckResult | undefined): TemporalIssue[] {
  return Array.isArray(r?.issues) ? r!.issues : [];
}

export interface CoherenceResult extends Disableable {
  context?: {
    iso?: string;
    day_of_year?: number;
    days_since_planting?: number | null;
    planting_date?: string | null;
  };
  coherence?: {
    coherent?: boolean;
    detail_ar?: string;
  };
}

/** حقائق المرجع الزمني الموحّد: اليوم/السنة + أيّام منذ الزراعة. */
export function coherenceFacts(r: CoherenceResult | undefined): OpFact[] {
  if (!r?.context) return [];
  const c = r.context;
  const facts: OpFact[] = [];
  if (typeof c.day_of_year === 'number') facts.push({ label: 'اليوم/السنة', value: String(c.day_of_year) });
  if (typeof c.days_since_planting === 'number') facts.push({ label: 'أيّام منذ الزراعة', value: String(c.days_since_planting) });
  return facts;
}

export interface WhatIfResult extends Disableable {
  field_id?: string;
  available?: boolean;
  note_ar?: string;
  error?: string;
  scenario?: string;
  baseline_yield_t_ha?: number | null;
  action_yield_t_ha?: number | null;
  no_action_yield_t_ha?: number | null;
  water_saved_mm?: number | null;
  recommended_action_helps?: boolean | null;
}

/** حقائق المحاكاة: محصول خطّ الأساس/الإجراء + توفير الماء (كلّها من الخادم). */
export function whatIfFacts(r: WhatIfResult | undefined): OpFact[] {
  if (!r?.available) return [];
  const facts: OpFact[] = [];
  if (r.baseline_yield_t_ha != null) facts.push({ label: 'خطّ الأساس (بلا إجراء) ط/هـ', value: fmtNum(r.baseline_yield_t_ha, 2) });
  if (r.action_yield_t_ha != null) facts.push({ label: 'الإجراء المقترَح ط/هـ', value: fmtNum(r.action_yield_t_ha, 2) });
  if (r.water_saved_mm != null) facts.push({ label: 'توفير الماء (مم)', value: fmtNum(r.water_saved_mm, 1) });
  return facts;
}

export interface SeasonalHazard {
  hazard_ar?: string;
  season_ar?: string;
  risk_to_ar?: string;
  severity?: string;
}
export interface StageCheckResult extends Disableable {
  supported?: boolean;
  zone_name_ar?: string;
  stage_ar?: string;
  relevant_hazards?: SeasonalHazard[];
  risk_level_ar?: string;
  advice_ar?: string;
  disclaimer_ar?: string;
  message_ar?: string;
}

/** المخاطر المتّصلة بالمرحلة كما أرجعها الخادم (قائمة قد تكون فارغة = لا مخاطر بارزة). */
export function stageCheckHazards(r: StageCheckResult | undefined): SeasonalHazard[] {
  return Array.isArray(r?.relevant_hazards) ? r!.relevant_hazards : [];
}

export interface ReplayStateResult extends Disableable {
  entity_id?: string;
  entity_type?: string;
  field_name?: string | null;
  lifecycle_stage?: string | null;
  area_ha?: number | null;
  crop?: string | null;
  planting_date?: string | null;
  harvest_date?: string | null;
  irrigation_count?: number | null;
  fertilizer_count?: number | null;
  last_ndvi?: number | null;
  total_events?: number | null;
  last_event_at?: string | null;
}

/** حقائق الحالة المُعاد بناؤها من الأحداث (الحقول من الخادم؛ الغائب يُتخطّى). */
export function replayFacts(r: ReplayStateResult | undefined): OpFact[] {
  if (!r) return [];
  const facts: OpFact[] = [];
  if (r.lifecycle_stage) facts.push({ label: 'الطور', value: r.lifecycle_stage });
  if (r.crop) facts.push({ label: 'المحصول', value: r.crop });
  if (r.area_ha != null) facts.push({ label: 'المساحة (هـ)', value: fmtNum(r.area_ha, 2) });
  if (r.irrigation_count != null) facts.push({ label: 'مرّات الريّ', value: String(r.irrigation_count) });
  if (r.fertilizer_count != null) facts.push({ label: 'مرّات التسميد', value: String(r.fertilizer_count) });
  if (r.last_ndvi != null) facts.push({ label: 'آخر NDVI', value: fmtNum(r.last_ndvi, 3) });
  if (r.total_events != null) facts.push({ label: 'إجماليّ الأحداث', value: String(r.total_events) });
  return facts;
}

export interface TrialVerdictResult extends Disableable {
  n_blocks?: number;
  treatment_mean?: number;
  control_mean?: number;
  mean_difference?: number;
  t_statistic?: number;
  df?: number;
  p_value?: number;
  confidence_level?: number;
  lsd?: number;
  is_significant?: boolean;
  ci_lower?: number;
  ci_upper?: number;
  percent_change?: number;
  verdict_ar?: string;
  recommendation_ar?: string;
}

/** حقائق حكم التجربة (متوسّطات/فرق/p/LSD/تغيّر ٪) — أرقام الخادم كما هي. */
export function trialFacts(r: TrialVerdictResult | undefined): OpFact[] {
  if (!r || r.disabled) return [];
  const facts: OpFact[] = [];
  if (r.n_blocks != null) facts.push({ label: 'الكتل', value: String(r.n_blocks) });
  if (r.treatment_mean != null) facts.push({ label: 'متوسّط المعالجة', value: fmtNum(r.treatment_mean, 3) });
  if (r.control_mean != null) facts.push({ label: 'متوسّط الشاهد', value: fmtNum(r.control_mean, 3) });
  if (r.mean_difference != null) facts.push({ label: 'الفرق', value: fmtNum(r.mean_difference, 3) });
  if (r.percent_change != null) facts.push({ label: 'التغيّر ٪', value: fmtNum(r.percent_change, 2) });
  if (r.p_value != null) facts.push({ label: 'p', value: fmtNum(r.p_value, 5) });
  if (r.lsd != null) facts.push({ label: 'LSD', value: fmtNum(r.lsd, 4) });
  if (r.ci_lower != null && r.ci_upper != null) {
    facts.push({ label: 'فترة الثقة', value: `[${fmtNum(r.ci_lower, 3)}, ${fmtNum(r.ci_upper, 3)}]` });
  }
  return facts;
}
