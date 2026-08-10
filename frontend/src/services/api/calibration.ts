// ══════════════════════════════════════════════════════
// SAHOOL — services/api/calibration.ts
// منضدة المعايرة الإقليميّة + منضدة الخبير (calibration.py). مُستخرجة من api.ts حفاظاً
// على تفكيك طبقة الواجهة تدريجيّاً؛ السلوك محفوظ والتصدير مُعاد عبر api.ts.
// ══════════════════════════════════════════════════════
import { kongApi } from './client';

// ── حالة المعايرة الإقليميّة (GET /api/v1/calibration) — قراءة فقط ──
// يكشف لكلّ إقليم يمنيّ هل ثوابته الأغرونوميّة مُتحقَّق منها ميدانيّاً أم ما تزال
// افتراضات FAO عامّة — فيرى المستخدم أين تنقص بيانات المعايرة الحقيقيّة. صدق: لا
// تلفيق؛ الأقاليم غير المُتحقَّق منها (validated=false) ترث الافتراضات العامّة.
export interface CalibrationProfile {
  region:                string;
  region_ar:             string;
  validated:             boolean;
  source_ar:             string;
  raw_fraction:          number;
  root_depth_m:          number;
  kc_dyn_min:            number;
  kc_dyn_max:            number;
  forecast_infiltration: number;
  uptake_fractions:      Record<string, number>;
  yield_uncertainty:     number;
  price_uncertainty:     number;
  evidence_level:        'none' | 'expert_opinion' | 'field_preliminary' | 'field_verified' | string;
  sample_count:          number;
  last_evaluated_at:     string | null;
  notes_ar:              string[];
}
export interface CalibrationOverview {
  generic:         CalibrationProfile;
  regions:         CalibrationProfile[];
  validated_count: number;
  note_ar:         string;
}
export const fetchCalibration = (): Promise<CalibrationOverview> =>
  kongApi.get<CalibrationOverview>('/api/v1/calibration').then(r => r.data);

// ══════════════════════════════════════════════════════════════════
// CALIBRATION WORKBENCH — منضدة معايرة الخبير الزراعيّ (مقارنة/اقتراح/موافقة/رفض/تدقيق)
// تستهلك نقاط calibration.py الحقيقيّة: القاعدة (GET /{region}) مقابل المُدام
// (GET /{region}/resolved)، التحقّق (POST /{region}/propose-values — يقترح لا يكتب)،
// الإدامة (POST /{region}/override مع source_ar) وعكسها (DELETE /{region}/override)،
// وتطبيق التكيّف بدليل مُدام (POST /{region}/adapt-from-evidence/apply, confirm=true).
// صدق: لا قيمة بلا API؛ POST/DELETE ترمي عند الخطأ ليعرض الـUI حالة صادقة؛ لا any.
// ══════════════════════════════════════════════════════════════════

// ملفّ المنطقة بعد دمج التجاوز المُدام (GET /{region}/resolved) — يطابق
// apply_region_override: CalibrationProfile + وسما المصدر/الحقول المُطبَّقة.
export interface ResolvedCalibration extends CalibrationProfile {
  override_applied: string[];               // الحقول التي طُبِّق فيها تجاوز مُدام
  override_source:  'db_override' | 'inherited' | string;
}
/** القاعدة الموروثة لمنطقة (GET /api/v1/calibration/{region}). */
export const fetchRegionCalibration = (region: string): Promise<CalibrationProfile> =>
  kongApi
    .get<CalibrationProfile>(`/api/v1/calibration/${encodeURIComponent(region)}`)
    .then(r => r.data);
/** الملفّ المُحلّ مع التجاوز المُدام (GET /api/v1/calibration/{region}/resolved). */
export const fetchResolvedCalibration = (region: string): Promise<ResolvedCalibration> =>
  kongApi
    .get<ResolvedCalibration>(`/api/v1/calibration/${encodeURIComponent(region)}/resolved`)
    .then(r => r.data);

// نتيجة التحقّق (validate_region_calibration) — مشتركة بين propose-values/override.
export interface CalibrationRejection { field: string; value: unknown; reason_ar: string }
export interface CalibrationValidation {
  region:           string;
  accepted:         Record<string, number | Record<string, number>>;
  rejected:         CalibrationRejection[];
  override_block:   Record<string, number | Record<string, number>>;
  validated:        boolean;
  source_ar:        string | null;
  ready_to_persist: boolean;
  calibrated:       false;
  warnings_ar:      string[];
}
// مدخلات الاقتراح/الإدامة (ProposeValuesRequest) — كلّ الحقول اختياريّة؛ نرسل
// المُعرَّف فقط. source_ar إلزاميّ للإدامة (الخادم يرفض 422 بلا مصدر).
export interface CalibrationValuesInput {
  raw_fraction?:          number;
  root_depth_m?:          number;
  kc_dyn_min?:            number;
  kc_dyn_max?:            number;
  forecast_infiltration?: number;
  yield_uncertainty?:     number;
  price_uncertainty?:     number;
  uptake_fractions?:      Record<string, number>;
  source_ar?:             string;
}
/** يتحقّق من قيم مقترَحة ضدّ حدود آمنة (POST /{region}/propose-values) — يقترح لا يكتب.
 *  الخادم يُرجِع 200 مع accepted/rejected (لا 422 هنا)؛ أخطاء الشبكة/503 تُرمى. */
export const proposeCalibrationValues = (
  region: string,
  values: CalibrationValuesInput,
): Promise<CalibrationValidation> =>
  kongApi
    .post<CalibrationValidation>(
      `/api/v1/calibration/${encodeURIComponent(region)}/propose-values`,
      values,
    )
    .then(r => r.data);

// نتيجة الإدامة الناجحة (set_region_override) — يُعيد المقبول + الملفّ المُحلّ.
export interface CalibrationOverrideResult {
  region:    string;
  persisted: true;
  accepted:  Record<string, number | Record<string, number>>;
  source_ar: string | null;
  resolved:  ResolvedCalibration;
}
/** يُدِيم قيماً مُتحقَّقة لمنطقة (POST /{region}/override). source_ar إلزاميّ.
 *  يرمي عند الخطأ (422 رفض/نقص مصدر، 503 DB) ليعرض الـUI سببه بصدق. */
export const setRegionOverride = (
  region: string,
  values: CalibrationValuesInput,
): Promise<CalibrationOverrideResult> =>
  kongApi
    .post<CalibrationOverrideResult>(
      `/api/v1/calibration/${encodeURIComponent(region)}/override`,
      values,
    )
    .then(r => r.data);

/** يحذف التجاوز المُدام ويعيد المنطقة للوراثة (DELETE /{region}/override).
 *  يرمي عند الخطأ (503 DB) — لا حذف تفاؤليّ صامت. */
export const deleteRegionOverride = (
  region: string,
): Promise<{ region: string; reverted: boolean }> =>
  kongApi
    .delete<{ region: string; reverted: boolean }>(
      `/api/v1/calibration/${encodeURIComponent(region)}/override`,
    )
    .then(r => r.data);

// تطبيق التكيّف بدليل مُدام (apply_region_adaptation_from_evidence) — confirm=true
// إلزاميّ صريح. الردّ هو الاقتراح (propose_calibration_adjustment) + applied/persisted.
// الشكل دفاعيّ: غير مؤهَّل ⇒ applied=false ويُعاد الاقتراح كما هو (لا تطبيق خفيّ).
export interface AdaptProposalItem {
  parameter: string;
  current?:  number;
  proposed?: number;
  [k: string]: unknown;
}
export interface AdaptApplyResult {
  status:              string;            // auto_apply_eligible | gated | …
  applied:             boolean;           // أُدِيم فعلاً؟ (false ⇒ لم يُطبَّق)
  proposals:           AdaptProposalItem[];
  decision_id?:        string;
  evidence_used?:      Record<string, unknown>;
  source_ar?:          string | null;
  persisted_override?: Record<string, number>;
  resolved?:           ResolvedCalibration;
  warnings_ar?:        string[];
  [k: string]:         unknown;
}
export interface AdaptApplyInput {
  confirm: boolean;                       // يجب أن يكون true (الخادم يرفض 422 بلا تأكيد)
  source_ar?:          string;
  mean_stress_delta?:  number;
  decision_id?:        string;
}
/** يُطبّق تكيّف المعايرة المحروس بالدليل المُدام (POST /{region}/adapt-from-evidence/apply).
 *  confirm=true إلزاميّ. يرمي عند الخطأ (422 بلا تأكيد/خارج الأمان، 503 DB). */
export const applyAdaptFromEvidence = (
  region: string,
  input: AdaptApplyInput,
): Promise<AdaptApplyResult> =>
  kongApi
    .post<AdaptApplyResult>(
      `/api/v1/calibration/${encodeURIComponent(region)}/adapt-from-evidence/apply`,
      input,
    )
    .then(r => r.data);

// كلّ التجاوزات المُدامة للمستأجِر (GET /api/v1/calibration/overrides/all) — لإدارة
// أيّ المناطق صار لها قيم مُدامة ومصدرها/وقت تحديثها (بديل سجلّ التدقيق إن غاب).
export interface CalibrationOverrideEntry {
  region:          string;
  override_values: Record<string, number | Record<string, number>>;
  source_ar:       string | null;
  validated:       boolean;
  updated_at:      string | null;
}
export interface CalibrationOverridesResult {
  overrides: CalibrationOverrideEntry[];
  count:     number;
}
export const fetchCalibrationOverrides = (): Promise<CalibrationOverridesResult> =>
  kongApi
    .get<CalibrationOverridesResult>('/api/v1/calibration/overrides/all')
    .then(r => ({
      overrides: Array.isArray(r.data?.overrides) ? r.data.overrides : [],
      count: typeof r.data?.count === 'number' ? r.data.count : 0,
    }));

// سجلّ التدقيق لمنطقة (GET /api/v1/calibration/{region}/audit) — قد لا تتوفّر النقطة
// بعد. صدق: نستهلكها إن نجحت، ونُعيد null عند 404 (لا تلفيق) فترتدّ المنضدة إلى
// overrides/all (source_ar + updated_at). أيّ خطأ آخر يُعاد null كذلك (أفضل-جهد).
// الشكل دفاعيّ (كلّ الحقول اختياريّة) لتفادي افتراض عقد غير مُثبَّت في هذا الفرع.
export interface CalibrationAuditEntry {
  action?:     string;
  field?:      string;
  old_value?:  unknown;
  new_value?:  unknown;
  source_ar?:  string | null;
  actor?:      string | null;
  created_at?: string | null;
  [k: string]: unknown;
}
export interface CalibrationAudit {
  region:  string;
  entries: CalibrationAuditEntry[];
}
/** يجلب سجلّ تدقيق منطقة. أفضل-جهد: 404 (نقطة غير متاحة) أو أيّ خطأ ⇒ null،
 *  فترتدّ المنضدة إلى overrides/all (حالة صادقة لا تلفيق). الأحدث أوّلاً يُتوقَّع
 *  من الخادم؛ نطبّع المصفوفة دفاعيّاً إن غابت/اختلف شكلها. */
export const fetchCalibrationAudit = (region: string): Promise<CalibrationAudit | null> =>
  kongApi
    .get<{ entries?: CalibrationAuditEntry[]; audit?: CalibrationAuditEntry[] }>(
      `/api/v1/calibration/${encodeURIComponent(region)}/audit`,
    )
    .then((r) => {
      const raw = r.data ?? {};
      const entries = Array.isArray(raw.entries)
        ? raw.entries
        : Array.isArray(raw.audit)
          ? raw.audit
          : [];
      return { region, entries };
    })
    .catch(() => null);

// ── سلسلة النَّسَب المُدامة + الدليل المتراكم (قراءة فقط) ──
// تُظهر للمستخدم أثر القرار المحفوظ ونتائجه التالية (decision → outcomes)، وتراكم
// الدليل الميدانيّ لكلّ منطقة نحو التحقّق. صدق: الدليل المتراكم تقديريّ غير مُعايَر
// (calibrated=false, source=persisted_outcomes) حتى تُجمَع عيّنات كافية — تُعرَض
// warnings_ar صراحةً. لا fallback وهميّ: الخطأ (404/503) يُرفع لتعرض الواجهة حالة صادقة.
export interface LineageDecision {
  decision_id:    string;
  field_id:       string;
  decision_type:  string;
  region:         string;
  stage:          string;
  decision_value: Record<string, unknown>;
  confidence:     number | null;
  created_by:     string;
  created_at:     string;
}
export interface LineageOutcome {
  outcome_id:  string;
  decision_id: string;
  field_id:    string;
  region:      string;
  stage:       string;
  planned:     Record<string, unknown>;
  actual:      Record<string, unknown>;
  metrics:     Record<string, unknown>;
  success:     boolean | null;
  created_at:  string;
}
export interface DecisionLineage {
  decision_id:    string;
  decision:       LineageDecision | null;
  outcomes:       LineageOutcome[];
  outcome_count:  number;
  stages_present: string[];
}
export const fetchDecisionLineage = (decisionId: string): Promise<DecisionLineage> =>
  kongApi
    .get<DecisionLineage>(`/api/v1/decision/${encodeURIComponent(decisionId)}/lineage`)
    .then(r => r.data);

export type EvidenceLevel = 'none' | 'field_preliminary' | 'field_verified' | 'expert_opinion';
export interface PersistedEvidence {
  region:                     string;
  sample_count:               number;
  evidence_level:             EvidenceLevel;
  success_rate:               number | null;
  success_flag_counts:        Record<string, number>;
  last_evaluated_at:          string | null;
  field_verified_min_samples: number;
  samples_to_verified:        number;
  calibrated:                 false;
  source:                     'persisted_outcomes';
  persisted_rows:             number;
  warnings_ar:                string[];
}
export const fetchPersistedEvidence = (region: string): Promise<PersistedEvidence> =>
  kongApi
    .get<PersistedEvidence>(`/api/v1/calibration/${encodeURIComponent(region)}/evidence/persisted`)
    .then(r => r.data);
