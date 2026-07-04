// Decision Deep Console — يعكس نقاط القرار العميقة اليتيمة (P0 في UI_DEBT_MAP) في
// الواجهة: القرار الموحّد (unified) + قرار الموقع (for-location) + الشرح (explain)
// + الاقتصاد (economics) + استشارة السياسات (policies/resolve) + إدامة القرار
// (record) + التنفيذ المحروس (dispatch/execute). صدق: أحكام الخادم (state/
// halt_reasons/reason_ar/notes_ar) تمرّ كما هي دون تعديل؛ القيمة الغائبة تُعرَض
// «—» ولا تُختلَق صفراً؛ الميزات خلف SAHOOL_DECISION_DISPATCH تُكشَف 404 ⇒ حالة
// «غير مُفعَّلة» صادقة. المسارات والأشكال منقولة حرفيّاً من الخادم:
// services/sahool-platform/api/routers/{decision,decision_dispatch,decision_impact,
// decision_policies,decision_record}.py — لا حقول مُخترَعة.

// ── القرار الموحّد (POST /api/v1/decision/unified — معاينة dry-run، لا تنفيذ) ──

/** إشارة مجال واحدة كما يقبلها الخادم (DomainSignalIn). */
export interface UnifiedSignalInput {
  domain: string; // weather | soil | irrigation | pest | economics | yield
  action: string; // irrigate | spray | reduce_water | … | none
  urgency: string; // none|low|moderate|high|critical (مرادفات يطبّعها الخادم)
  params: Record<string, unknown>;
  halt: boolean;
  reason_ar: string;
  confidence: number;
}

export interface UnifiedDecisionInput {
  field_id: string;
  signals: UnifiedSignalInput[];
  min_mm_for_yield?: number;
  water_budget_mm?: number;
}

export interface UnifiedPlannedAction {
  action: string;
  domains: string[];
  urgency: string;
  params: Record<string, unknown>;
  rationale_ar: string;
  optimization?: Record<string, unknown>; // يظهر فقط عند تفعيل أمثَلة الماء
}

export interface UnifiedDecisionResult {
  field_id: string;
  state: 'ready' | 'blocked' | string;
  action_plan: UnifiedPlannedAction[];
  halt_reasons: string[];
  reconciliations_ar: string[];
  confidence: number;
  rationale_ar: string;
  reconciled_by?: string;
  dry_run?: boolean; // الخادم يعلنها true — معاينة فقط
}

// ── قرار الموقع + الشرح (GET /for-location · GET /explain) ──

/** معاملات الاستعلام المشتركة للنقطتين (نفس توقيع الخادم). */
export interface ForLocationParams {
  location?: string;
  lat?: number;
  lon?: number;
  elevation_m?: number;
  soil_ph?: number;
  soil_ec_dsm?: number;
  area_ha?: number;
}

/** ناتج decide_for_location — كلّ الحقول اختياريّة عدا supported (الخادم يبنيها
 *  تدريجيّاً حسب المتوفّر؛ الغائب غياب صادق لا يُملأ). */
export interface DecisionForLocationResult {
  supported: boolean;
  message_ar?: string;
  needs_clarification_ar?: string;
  example_districts_ar?: string[];
  steps_ar?: string[];
  location_ar?: Record<string, unknown>;
  location_warning_ar?: string;
  suited_crops_ar?: string[];
  avoid_ar?: string[];
  water_strategy_ar?: string;
  rainfed_possible?: boolean;
  seasonal_risks_ar?: { high_severity_ar?: string[]; advice_ar?: string };
  chill_hours_ar?: { estimated?: number; verdict_ar?: string };
  salinity_alert_ar?: string;
  alkalinity_alert_ar?: string;
  area_note_ar?: string;
  decision_summary_ar?: string;
  next_actions_ar?: string[];
  disclaimer_ar?: string;
  [k: string]: unknown;
}

/** ناتج explain_decision — الشرح يُعرَض حرفيّاً كما صاغه الخادم. */
export interface DecisionExplainDeepResult {
  supported: boolean;
  explanation_ar: string;
  explanation_source: 'ai' | 'rule_based_offline' | string;
  rag_used: boolean;
  note_ar: string;
  prompt_for_server: string | null;
  disclaimer_ar: string;
}

// ── الاقتصاد (GET /api/v1/decision/economics — خلف SAHOOL_DECISION_DISPATCH) ──

export interface DecisionEconomicsResult {
  currency: string;
  executed_decisions: number;
  success_rate: number; // [0,1]
  water_saved_mm: number;
  water_saved_m3: number | null; // يُحسَب فقط مع المساحة — وإلّا null (لا تلفيق)
  water_cost_avoided: number | null; // يُحسَب فقط مع التكلفة — وإلّا null
  notes_ar: string[] | null;
  impact?: {
    total_decisions: number;
    executed: number;
    failed: number;
    success_rate: number;
    water_requested_mm: number;
    water_applied_mm: number;
    water_saved_mm: number;
    water_records: number;
    by_action: Record<string, { executed: number; failed: number; water_saved_mm: number }>;
  };
  disabled?: boolean; // 404 ⇒ العلم مُطفأ (تُضيفها الواجهة، ليست من الخادم)
}

// ── استشارة السياسات (POST /api/v1/decision/policies/resolve — dry-run نقيّ) ──

export interface PolicyResolveInput {
  action_type?: string;
  risk_level?: string;
  crop?: string;
}

export interface PolicyResolveResult {
  auto_block: boolean;
  require_approvals: number;
  water_cap_pct: number | null;
  applied_policy_ids: string[];
  reasons_ar: string[];
  context: PolicyResolveInput;
  dry_run: boolean;
}

// ── إدامة القرار (POST /api/v1/decision/record) ──

export interface DecisionRecordInput {
  decision_type: string; // crop_twin | irrigation_plan | profit_aware …
  decision_value: Record<string, unknown>; // يُدام كما هو (JSONB)
  field_id?: string;
  region?: string;
  confidence?: number;
  decision_id?: string;
}

export interface DecisionRecordResult {
  decision_id: string;
  lineage: Record<string, unknown>;
  persisted: boolean;
  recorded_by: string;
}

// ── التنفيذ المحروس (POST /api/v1/decision/dispatch/execute) ──

/** نفس عقد الخادم (DispatchExecuteRequest): مدخلات المعاينة + هدف التنفيذ.
 *  device_id/command إلزاميّان فعليّاً فقط عند قرار READY (وإلّا 422 من الخادم). */
export interface DispatchExecuteInput {
  recommendation_id: string;
  action_type: string;
  risk_level: string; // مجهول ⇒ الخادم يعامله CRITICAL (fail-closed)
  field_id?: string | null;
  approvals_collected?: number;
  has_governing_data?: boolean;
  pesticide_phi_satisfied?: boolean | null;
  device_id?: string | null;
  command?: string | null;
  params?: Record<string, unknown>;
}

/** حكم الخادم بعد التنفيذ — يُعرَض حرفيّاً (بما فيه أسباب الحجب/الإيقاف). */
export interface DispatchExecuteResult {
  status: 'queued' | 'not_executed' | string;
  dispatch_state: string; // blocked | pending_approval | ready
  command: Record<string, unknown> | null;
  reason_ar: string;
  decision_id?: string;
  replayed?: boolean; // صدق: أُعيد قرار حيّ قائم — لم يُدرَج جديد
  audit?: {
    state?: string;
    risk_level?: string;
    required_approvals?: number;
    approvals_collected?: number;
    halt_breaches?: unknown[];
    warn_breaches?: unknown[];
    reason_ar?: string;
    executable?: boolean;
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

// ═══ مساعِدات نقيّة (مُختبَرة وحدويّاً) ═══

/** «—» للغائب — لا نحوّل null إلى 0 (اختلاق). الأرقام تُقرَّب لمنزلتين. */
export function numLabel(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return String(Math.round(v * 100) / 100);
}

/** قيمة نقديّة بعملة الخادم — الغائبة «—» (الخادم يشرح السبب في notes_ar). */
export function moneyLabel(v: number | null | undefined, currency: string): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return `${Math.round(v * 100) / 100} ${currency}`;
}

/** نسبة [0..1] ⇒ «75٪» — الغائبة «—» لا «0٪» مُختلقة. */
export function percentLabel(rate: number | null | undefined): string {
  if (rate == null || !Number.isFinite(rate)) return '—';
  return `${Math.round(rate * 100)}٪`;
}

// حالات القرار الموحّد المعروفة فقط تُترجَم/تُلوَّن — المجهولة تمرّ كما هي بلون محايد.
const UNIFIED_STATE_AR: Record<string, string> = { ready: 'جاهز', blocked: 'محجوب' };

export function unifiedStateLabel(state: string | null | undefined): string {
  return state ? (UNIFIED_STATE_AR[state] ?? state) : '—';
}

export function unifiedStateColor(state: string | null | undefined): string {
  if (state === 'ready') return '#86efac';
  if (state === 'blocked') return '#fca5a5';
  return '#64748b';
}

// مآل التنفيذ (ExecutionStatus في الخادم): queued | not_executed — لا غير.
const EXEC_STATUS_AR: Record<string, string> = {
  queued: 'أُدرِج في الطابور',
  not_executed: 'لم يُنفَّذ (سُجِّل فقط)',
};

export function executionStatusLabel(status: string | null | undefined): string {
  return status ? (EXEC_STATUS_AR[status] ?? status) : '—';
}

export function executionStatusColor(status: string | null | undefined): string {
  if (status === 'queued') return '#86efac';
  if (status === 'not_executed') return '#fdba74';
  return '#64748b';
}

// إلحاح الإشارة (Urgency في الخادم) — المعروف فقط يُترجَم، المجهول يمرّ كما هو.
const URGENCY_AR: Record<string, string> = {
  none: 'بلا إلحاح',
  low: 'منخفض',
  moderate: 'متوسّط',
  high: 'عالٍ',
  critical: 'حرج',
};

export function urgencyLabel(u: string | null | undefined): string {
  return u ? (URGENCY_AR[u] ?? u) : '—';
}

// مصدر الشرح (explanation_source) — قيمتا الخادم المعروفتان فقط.
const EXPLAIN_SOURCE_AR: Record<string, string> = {
  ai: 'ذكاء اصطناعيّ (صياغة فقط — القرار من القواعد)',
  rule_based_offline: 'نظام القواعد (يعمل دون إنترنت)',
};

export function explainSourceLabel(src: string | null | undefined): string {
  return src ? (EXPLAIN_SOURCE_AR[src] ?? src) : '—';
}

/** رقم من نصّ نموذج — الفراغ/غير الرقميّ يبقى غائباً (لا يتحوّل صفراً). */
export function numFromText(v: string | undefined): number | undefined {
  const t = String(v ?? '').trim();
  if (t === '') return undefined;
  const n = Number(t);
  return Number.isFinite(n) ? n : undefined;
}

/** يبني معاملات for-location/explain من نصوص النموذج — المُدخَل فقط يُرسَل. */
export function buildForLocationParams(fields: {
  location?: string;
  lat?: string;
  lon?: string;
  elevationM?: string;
  soilPh?: string;
  soilEcDsm?: string;
  areaHa?: string;
}): ForLocationParams {
  const p: ForLocationParams = {};
  if (fields.location?.trim()) p.location = fields.location.trim();
  const lat = numFromText(fields.lat);
  if (lat !== undefined) p.lat = lat;
  const lon = numFromText(fields.lon);
  if (lon !== undefined) p.lon = lon;
  const el = numFromText(fields.elevationM);
  if (el !== undefined) p.elevation_m = el;
  const ph = numFromText(fields.soilPh);
  if (ph !== undefined) p.soil_ph = ph;
  const ec = numFromText(fields.soilEcDsm);
  if (ec !== undefined) p.soil_ec_dsm = ec;
  const area = numFromText(fields.areaHa);
  if (area !== undefined) p.area_ha = area;
  return p;
}

/** هل تكفي المعاملات لطلب قرار موقع؟ (اسم موقع أو زوج إحداثيّات كامل —
 *  نفس شرط الخادم الذي يردّ supported=false بدونهما). */
export function hasLocationInput(p: ForLocationParams): boolean {
  return !!p.location || (p.lat != null && p.lon != null);
}

/** يبني طلب القرار الموحّد — القيَم الاختياريّة الفارغة تُحذَف (لا صفر مُختلق). */
export function buildUnifiedRequest(fields: {
  fieldId: string;
  signals: UnifiedSignalInput[];
  minMmForYield?: string;
  waterBudgetMm?: string;
}): UnifiedDecisionInput {
  const req: UnifiedDecisionInput = { field_id: fields.fieldId.trim(), signals: fields.signals };
  const minMm = numFromText(fields.minMmForYield);
  if (minMm !== undefined) req.min_mm_for_yield = minMm;
  const budget = numFromText(fields.waterBudgetMm);
  if (budget !== undefined) req.water_budget_mm = budget;
  return req;
}

/** يفكّ decision_value من نصّ JSON — كائن فقط (الخادم يتوقّع dict)، والخطأ
 *  يُعاد نصّاً صادقاً بدل إرسال حمولة مكسورة. */
export function parseDecisionValue(
  text: string,
): { ok: true; value: Record<string, unknown> } | { ok: false; error_ar: string } {
  const t = text.trim();
  if (!t) return { ok: false, error_ar: 'أدخِل قيمة القرار (JSON) — لا تُدام قيمة فارغة.' };
  try {
    const parsed: unknown = JSON.parse(t);
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { ok: false, error_ar: 'قيمة القرار يجب أن تكون كائن JSON (‎{…}‎) لا قائمة/قيمة مفردة.' };
    }
    return { ok: true, value: parsed as Record<string, unknown> };
  } catch {
    return { ok: false, error_ar: 'JSON غير صالح — صحّح الصياغة قبل الإدامة.' };
  }
}

// التأكيد المكتوب قبل التنفيذ المحروس — حرفيّاً، لا اجتهاد في المطابقة.
export const EXECUTE_CONFIRM_PHRASE = 'نفّذ';

/** هل أكّد المستخدم التنفيذ بكتابة العبارة حرفيّاً؟ */
export function executeConfirmed(text: string | null | undefined): boolean {
  return (text ?? '').trim() === EXECUTE_CONFIRM_PHRASE;
}

/** رمز حالة HTTP من خطأ axios — null إن غاب (خطأ شبكة/غير HTTP). */
export function httpStatusOf(e: unknown): number | null {
  const status = (e as { response?: { status?: number } })?.response?.status;
  return typeof status === 'number' ? status : null;
}

/** 404 على نقاط SAHOOL_DECISION_DISPATCH يعني «الميزة مُطفأة» لا «غير موجود». */
export function isFeatureDisabled404(e: unknown): boolean {
  return httpStatusOf(e) === 404;
}
