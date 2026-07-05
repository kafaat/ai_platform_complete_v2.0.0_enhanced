// Manager Console — مساعِدات نقيّة لكونسول المدير الذي يعكس نقاط backend اليتيمة
// (P3) الموجَّهة للإدارة: جدوى اقتصاديّة + بنود تكلفة + تكلفة/حقل · إسقاطات دفتر
// العمليّات (ERP/مخزون/معاينة كتابة) · حوكمة الصلاحيّات (من-يقدر/مصفوفة/معاينة
// تغيير دور) · فجوة السوق/جاهزيّة التصنيف · بناء تقرير · أمر عمل من توصية · مفتاح
// مشاركة · إعدادات · قرينة كاميرا · اكتمال بيانات · فحص فشل.
//
// صدق صارم: القيم من الخادم كما هي؛ الخرائط المعروفة فقط تُترجَم (المجهول يُعرَض
// خاماً لا يُخترَع)، وnull ⇒ «—» (لا صفر مُلفَّق). كلّ الحسابات هنا نقيّة (تُختبَر
// بلا خدمات) — القرارات الحقيقيّة تبقى على الخادم (require_permission يفرضها؛
// canManage في الواجهة تلميح صادق لا حارس أمنيّ).

import type { Tone } from '../components/ds/tokens';

// ─── أشكال ردود الخادم (الحقول المعروضة فقط — لا اختراع حقل) ──────────────────

/** جدوى المحصول — POST /api/v1/economics/feasibility (api/farm_economics.py:feasibility). */
export interface FeasibilityResult {
  supported: boolean;
  complete?: boolean;
  area_ha?: number;
  expected_yield_t?: number;
  expected_revenue?: number;
  total_cost?: number;
  net_profit?: number;
  profit_margin_pct?: number;
  verdict_ar?: string;
  message_ar?: string;
  disabled?: boolean;
}

/** بنود التكلفة القياسيّة — GET /api/v1/economics/cost-categories. */
export interface CostCategoriesResult {
  categories?: { key: string; name_ar: string }[];
  note_ar?: string;
  disabled?: boolean;
}

/** تكلفة المهامّ لكلّ حقل — GET /api/v1/analytics/costs/by-field. */
export interface FieldCostRow {
  field_id: string;
  total_usd: number;
}

/** معاينة تغيير الدور — GET /api/v1/rbac/preview-role-change (core/rbac_governance.py). */
export interface RoleChangePreview {
  from_role?: string;
  to_role?: string;
  gained_permissions?: string[];
  lost_permissions?: string[];
  gained_count?: number;
  lost_count?: number;
  is_escalation?: boolean;
  gained_safety_critical?: string[];
  lost_safety_critical?: string[];
  warning_ar?: string;
  error_ar?: string;
  disabled?: boolean;
}

/** الاستعلام العكسي «من يقدر على X؟» — GET /api/v1/rbac/who-can. */
export interface WhoCanResult {
  permission?: string;
  roles_with_permission?: string[];
  role_count?: number;
  is_safety_critical?: boolean;
  note_ar?: string;
  disabled?: boolean;
}

/** صفّ إعداد مستأجِر — GET /api/v1/settings (api/routers/settings.py). */
export interface SettingRow {
  setting_id: string;
  scope: string;
  key: string;
  value: Record<string, unknown>;
  updated_by: string;
}

/** ملخّص اكتمال البيانات — GET/POST؛ نُلخّص المستوى + المتاح/المحجوب. */
export interface ReadinessLike {
  highest_complete_level?: number;
  available_recommendations?: unknown[];
  blocked_recommendations?: unknown[];
}

// ─── مساعِد عامّ: null ⇒ «—» (لا قيمة مُلفَّقة) ────────────────────────────────

/** يعرض القيمة أو «—» عند غيابها (null/undefined/'') — صدق لا صفر مخترَع. */
export function dash(v: string | number | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—';
  return String(v);
}

/** رقم مُنسَّق أو «—» عند الغياب — للمبالغ (بلا افتراض عملة على الخادم). */
export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—';
  return v.toLocaleString('en-US', { maximumFractionDigits: digits });
}

// ─── خرائط ترجمة معروفة (المجهول خام لا مُخترَع؛ null ⇒ «—») ───────────────────

// نطاقات الإعدادات المعتمدة خادميّاً (setting_models.py: platform|farm|irrigation|
// notification). المفتاح المجهول يُعرَض كما هو (لا نُخفي إعداداً لا نعرف تسميته).
const SETTING_SCOPE_AR: Record<string, string> = {
  platform: 'المنصّة',
  farm: 'المزرعة',
  irrigation: 'الريّ',
  notification: 'الإشعارات',
};
export function settingScopeLabelAr(scope: string | null | undefined): string {
  if (scope === null || scope === undefined || scope === '') return '—';
  return SETTING_SCOPE_AR[scope] ?? scope; // مجهول ⇒ خام (لا اختراع)
}

// أنواع الطرف الثالث لمفتاح المشاركة (api_models.py: advisor|dealer|ministry|
// researcher|other). null (لا طرف) ⇒ «—»؛ المجهول خام.
const THIRD_PARTY_AR: Record<string, string> = {
  advisor: 'مستشار',
  dealer: 'تاجر/موزّع',
  ministry: 'جهة حكوميّة',
  researcher: 'باحث',
  other: 'أخرى',
};
export function thirdPartyTypeLabelAr(t: string | null | undefined): string {
  if (t === null || t === undefined || t === '') return '—';
  return THIRD_PARTY_AR[t] ?? t;
}

// نطاق مفتاح المشاركة (ShareKeyRequest: read|read_write). المجهول خام.
const SHARE_SCOPE_AR: Record<string, string> = {
  read: 'قراءة',
  read_write: 'قراءة وكتابة',
};
export function sharingScopeLabelAr(scope: string | null | undefined): string {
  if (scope === null || scope === undefined || scope === '') return '—';
  return SHARE_SCOPE_AR[scope] ?? scope;
}

// ─── نغمات القرار (للتلوين — تُغذّي toneColors في ds؛ المجهول محايد) ───────────

/** نغمة الجدوى: ربح بهامش جيّد ⇒ ok · ربح محدود/غير مكتمل ⇒ warn · خسارة ⇒ danger
 *  · غير مدعوم/غائب ⇒ محايد. (لا حكم بلا بيانات — نعتمد صافي الربح والهامش من الخادم.) */
export function feasibilityTone(res: FeasibilityResult | null | undefined): Tone {
  if (!res || res.supported === false || res.disabled) return 'neutral';
  if (res.complete !== true || res.net_profit === undefined) return 'warn';
  if (res.net_profit < 0) return 'danger';
  if (res.net_profit > 0 && (res.profit_margin_pct ?? 0) >= 30) return 'ok';
  return 'warn'; // ربح بهامش محدود أو تعادل — حذر
}

/** نغمة معاينة تغيير الدور: اكتساب صلاحيّة حرجة/خطأ ⇒ danger · تصعيد عاديّ ⇒ warn
 *  · غير ذلك ⇒ محايد. (يطابق تنبيه warning_ar من الخادم دون تكراره.) */
export function roleChangeTone(res: RoleChangePreview | null | undefined): Tone {
  if (!res || res.disabled) return 'neutral';
  if (res.error_ar) return 'danger';
  if ((res.gained_safety_critical?.length ?? 0) > 0) return 'danger';
  if (res.is_escalation) return 'warn';
  return 'neutral';
}

/** نغمة «من يقدر»: الصلاحيّة الحرجة (سلامة) ⇒ warn (راجِع من يملكها) · غيرها محايد. */
export function whoCanTone(res: WhoCanResult | null | undefined): Tone {
  if (!res || res.disabled) return 'neutral';
  return res.is_safety_critical ? 'warn' : 'neutral';
}

// ─── تجميعات نقيّة ─────────────────────────────────────────────────────────────

/** إجماليّ تكلفة كلّ الحقول (مجموع total_usd) — تجميع نقيّ للعرض في الترويسة. */
export function costsByFieldTotal(rows: FieldCostRow[] | null | undefined): number {
  return (rows ?? []).reduce((sum, r) => sum + (Number(r.total_usd) || 0), 0);
}

/** ملخّص اكتمال البيانات: أعلى مستوى + عدد المتاح/المحجوب (للعرض الموجز). */
export function readinessSummary(
  res: ReadinessLike | null | undefined,
): { level: number; available: number; blocked: number } {
  return {
    level: res?.highest_complete_level ?? 0,
    available: res?.available_recommendations?.length ?? 0,
    blocked: res?.blocked_recommendations?.length ?? 0,
  };
}

/** عرّي معرّف إعداد كسلسلة نطاق·مفتاح للفرز/العرض الثابت. */
export function settingLabel(row: SettingRow): string {
  return `${settingScopeLabelAr(row.scope)} · ${row.key}`;
}
