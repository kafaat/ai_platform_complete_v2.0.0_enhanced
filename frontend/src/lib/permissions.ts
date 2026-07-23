// permissions.ts — تطبيق الأدوار (RBAC) فعليّاً في الواجهة.
// الخلفيّة تدعم 5 أدوار، لكن الواجهة كانت تَعرض الدور دون تقييد. هذا الملفّ
// يوحّد سياسة الوصول: أيّ صفحات يفتحها كلّ دور + صلاحيّة التعديل/الإدارة.
// fail-closed: الدور المجهول يُعامَل كـviewer (أقلّ صلاحيّة) لا كمالك.
import type { PageId } from '../App';

export type Role = 'owner' | 'manager' | 'agronomist' | 'worker' | 'viewer';

// تطبيع الأسماء القديمة/المرادفة لأدوار النظام الخمسة المعتمدة.
const ROLE_ALIASES: Record<string, Role> = {
  owner: 'owner', admin: 'owner',
  manager: 'manager',
  agronomist: 'agronomist', expert: 'agronomist',
  worker: 'worker', farmer: 'worker',
  viewer: 'viewer',
};

export function normalizeRole(role?: string | null): Role {
  return ROLE_ALIASES[(role ?? '').toLowerCase()] ?? 'viewer'; // fail-closed
}

// كلّ الصفحات (مرجع). owner/manager/agronomist: وصول كامل.
// ملاحظة: `as const satisfies readonly PageId[]` يحفظ الأنواع الحرفيّة لكلّ عنصر
// (كي يعمل حارس الاكتمال أدناه)، وفي الوقت نفسه يضمن أنّ كلّ عنصر هو PageId صالح
// (الاتّجاه العكسيّ مغطّى بـ`satisfies` — لا حاجة لشيفرة إضافيّة له).
export const ALL_PAGES = [
  'dashboard', 'unified-cabin', 'command', 'map-center', 'tasks-cabin', 'rec-flow', 'hybrid-monitor', 'analyze-cabin', 'setup-cabin', 'field-app', 'hybrid-index', 'satellite', 'fields', 'farm-map', 'field-workspace', 'recommendations',
  'irrigation', 'irrigation-plan', 'water-twin', 'etc-dual', 'crop-state', 'scenario-compare', 'nl-gis', 'sql-workspace', 'gis-tools', 'gis-expert', 'portfolio', 'portfolio-command', 'calibration', 'calibration-workbench', 'lineage', 'evidence-map', 'replay-map', 'learning-dashboard', 'decision-studio', 'decision-confidence', 'decision-runtime', 'execution-feedback', 'agronomic-timeline', 'weather-advice', 'irrigation-ops', 'irrigation-network', 'irrigation-engineering', 'pest-escalation', 'field-intelligence',
  'spatial-indicators', 'lab-sampling', 'devices', 'device-twin', 'inventory', 'farm-book', 'equipment',
  'tasks', 'activities', 'field-ranking', 'problem-fields', 'economics', 'yield-analysis', 'phenology', 'scouting', 'prescriptions', 'advisory-report', 'analytics', 'alerts', 'reports', 'master-data', 'documents', 'governance', 'admin-runtime', 'approvals-console', 'manager-console', 'chatbot', 'settings',
  'operations-wall', 'agro-zones', 'yemeni-calendars', 'climate-analogs', 'season-record-entry',
] as const satisfies readonly PageId[];

// حارس وقت-التصريف: كلّ معرّف في اتّحاد PageId يجب أن يظهر في ALL_PAGES،
// وإلّا فالصفحة غير قابلة للوصول. أيّ نقص يُفشل `npm run typecheck`.
type _PagesMissingFromAllPages = Exclude<PageId, (typeof ALL_PAGES)[number]>;
// إن ظهر خطأ هنا: المعرّف(ات) الظاهرة في النوع ناقصة من ALL_PAGES أعلاه.
const _assertAllPagesComplete: _PagesMissingFromAllPages extends never ? true : never = true;
void _assertAllPagesComplete;

// worker (مزارع/عامل): الصفحات التشغيليّة فقط (وفق سياسة الإعدادات الموثّقة:
// لوحة + أقمار + حقول + مهام، مع التنبيهات/المستشار/المكانيّة + أدوات حقله).
const WORKER_PAGES: PageId[] = [
  // 'recommendations'/'hybrid-index': عرض تشغيليّ يراه العامل (والمُشاهِد قراءةً) —
  // أُضيفا كي تبقى شبكة الرتب أحاديّة (viewer ⊆ worker) بلا حرمان الوصول المشروع؛
  // بينما sql-workspace/calibration-workbench/settings تبقى خارج worker (agronomist+).
  'dashboard', 'unified-cabin', 'command', 'map-center', 'tasks-cabin', 'rec-flow', 'recommendations', 'hybrid-monitor', 'hybrid-index', 'analyze-cabin', 'setup-cabin', 'field-app', 'satellite', 'fields', 'farm-map', 'field-workspace', 'tasks', 'activities', 'field-ranking', 'problem-fields', 'economics', 'phenology', 'scouting', 'prescriptions', 'advisory-report', 'alerts', 'chatbot', 'spatial-indicators', 'lab-sampling',
  'irrigation', 'irrigation-plan', 'water-twin', 'etc-dual', 'crop-state', 'scenario-compare', 'nl-gis', 'gis-tools', 'gis-expert', 'portfolio', 'portfolio-command', 'calibration', 'lineage', 'evidence-map', 'replay-map', 'learning-dashboard', 'decision-studio', 'decision-confidence', 'execution-feedback', 'agronomic-timeline', 'weather-advice', 'pest-escalation', 'field-intelligence',
  'inventory', 'farm-book', 'equipment', 'devices', 'device-twin', 'irrigation-ops', 'irrigation-network', 'irrigation-engineering',
  'agro-zones', 'yemeni-calendars', 'climate-analogs',
];

// صفحات إداريّة (owner/manager فقط): البيانات المرجعيّة + الوثائق.
// لا تظهر لـagronomist/viewer حتى لو كان الخادم سيردّ 403 — منعٌ من المصدر في الواجهة.
const MANAGEMENT_ONLY_PAGES: PageId[] = ['master-data', 'documents', 'governance', 'admin-runtime', 'approvals-console', 'manager-console'];

// كلّ ما عدا الصفحات الإداريّة (لـagronomist). يحافظ على وصوله الكامل للصفحات
// التشغيليّة/التحليليّة، مع استبعاد الإداريّة فقط.
const NON_MANAGEMENT_PAGES: PageId[] = ALL_PAGES.filter(
  (p) => !MANAGEMENT_ONLY_PAGES.includes(p),
);

// المُشاهِد (viewer): عرض تشغيليّ قراءةً فقط. يُحجَب عنه إضافةً الماليّ/التحليليّ/
// التقارير — مواءمةً مع RBAC الخلفيّة التي لا تمنح VIEWER صلاحيّات
// ANALYTICS_VIEW/AUDIT_VIEW ولا أيّ صلاحيّة ماليّة (core/authorization.py: VIEWER
// = 12 صلاحيّة عرض فقط). قائمة قابلة للضبط من المنتَج بمصفوفة واحدة.
const VIEWER_BLOCKED_PAGES: PageId[] = [
  'economics', 'farm-book', 'yield-analysis', 'analytics', 'reports', 'advisory-report', 'field-ranking', 'problem-fields',
  // منشئ الوصفات أداة كتابة (الحفظ يتطلّب FIELD_EDIT في الخلفيّة) — لا يُمنَح للمُشاهِد.
  'prescriptions',
  // جدار مركز العمليّات شاشة قيادة — owner/manager/agronomist فقط (لا worker ولا viewer).
  'operations-wall',
  // كونسول تشغيل القرار: طابور/سياسات/معاينة — ليس للمُشاهِد.
  'decision-runtime',
];
// المُشاهِد ⊆ العامل (شبكة رتب أحاديّة الاتّجاه — F-UI-31): يُشتقّ من صفحات العامل
// (لا من كامل غير-الإداريّة) ثمّ يُطرَح المحجوب عن المُشاهِد. هكذا لا يفتح viewer أبداً
// صفحةً لا يفتحها worker (سابقاً كان المكمّل يمنح viewer صفحات ينقصها worker مثل
// sql-workspace/calibration-workbench/hybrid-index/recommendations/settings — تسريب
// امتياز + سطح تصدير مجمّع للمُشاهِد عبر SQL workspace، F-UI-32).
const VIEWER_PAGES: PageId[] = WORKER_PAGES.filter(
  (p) => !VIEWER_BLOCKED_PAGES.includes(p),
);

const ROLE_PAGES: Record<Role, readonly PageId[]> = {
  owner: ALL_PAGES,
  manager: ALL_PAGES,
  agronomist: NON_MANAGEMENT_PAGES, // وصول كامل عدا الصفحات الإداريّة
  worker: WORKER_PAGES,
  viewer: VIEWER_PAGES, // عرض تشغيليّ فقط (عدا الإداريّة والماليّة/التحليليّة) — قراءةً (canMutate)
};

/** هل يحقّ للدور فتح هذه الصفحة؟ */
export function canAccess(role: string | undefined, page: PageId): boolean {
  return ROLE_PAGES[normalizeRole(role)].includes(page);
}

// ── طبقة القدرات الدقيقة (FE-06) ───────────────────────────────────
// سابقاً كانت `canMutate(role)` بوّابةً عالميّةً واحدة: علمٌ منطقيّ يفتح كلّ
// أنواع التعديل (إنشاء/تعديل/حذف/إقرار) دفعةً واحدة — «رائحة» تصميميّة تُخفي
// أنّ الحذف/الإقرار/تغيير الأدوار أخطر من مجرّد الإنشاء/التعديل. هنا نميّز
// الفعل (Capability) وأحياناً المورد (ResourceArea) مع الإبقاء على التوافق
// الخلفيّ: نداء `canMutate(role)` المجرّد يظلّ الفحص الخشن نفسه.
//
// القرار قائم على «رتبة» الدور، وهي كافية لصون أحاديّة الشبكة
// (viewer ⊆ worker ⊆ agronomist ⊆ manager ⊆ owner): بما أنّ القدرة تُمنَح
// حين `rank(role) >= threshold`، فإنّ أيّ دور أعلى يملك حتماً كلّ قدرات ما
// دونه (عتبة مونوتونيّة — لا يمكن أن يُمنَح الأدنى قدرةً يُحرَمها الأعلى).
export type Capability = 'create' | 'edit' | 'delete' | 'approve' | 'manage';
export type ResourceArea =
  | 'field' | 'farm' | 'user' | 'task' | 'activity' | 'irrigation'
  | 'equipment' | 'inventory' | 'device' | 'recommendation'
  | 'master-data' | 'governance' | 'approval';

// رتبة الدور — أساس المونوتونيّة. تفصيل داخليّ لا يُصدَّر (لا يعتمد عليه أحد خارجاً).
const ROLE_RANK: Record<Role, number> = {
  viewer: 0, worker: 1, agronomist: 2, manager: 3, owner: 4,
};

// أدنى رتبة لكلّ فعل (بلا مورد) — الأساس العامّ:
//  • create/edit: العامل فأعلى (= دلالة canMutate القديمة: أيّ دور غير viewer).
//  • delete: أخطر من التعديل — مهندس زراعيّ فأعلى افتراضاً (لا يحذف العاملُ السجلّات).
//  • approve/manage: إداريّ — مدير/مالك فقط (= دلالة canManage).
const CAPABILITY_MIN_RANK: Record<Capability, number> = {
  create: ROLE_RANK.worker,
  edit: ROLE_RANK.worker,
  delete: ROLE_RANK.agronomist,
  approve: ROLE_RANK.manager,
  manage: ROLE_RANK.manager,
};

// تجاوزات دقيقة لكلّ (فعل:مورد) حيث تفرض RBAC الخلفيّة/عقد الواجهة قيداً أشدّ.
// لا قيمة بلا مصدر:
const RESOURCE_OVERRIDES: Record<string, number> = {
  'create:farm': ROLE_RANK.owner,   // = canCreateFarm (FARM_CREATE مقصور على OWNER في الخلفيّة)
  'delete:field': ROLE_RANK.owner,  // = roleUiContract.delete_field (owner فقط) — الحذف الحقليّ للمالك
  'manage:user': ROLE_RANK.manager, // تغيير الأدوار/الدعوات: owner/manager (= canManage)
  'delete:user': ROLE_RANK.owner,   // إزالة مستخدم: المالك فقط
};

function requiredRank(action: Capability, resource?: ResourceArea): number {
  if (resource !== undefined) {
    const override = RESOURCE_OVERRIDES[`${action}:${resource}`];
    if (override !== undefined) return override;
  }
  return CAPABILITY_MIN_RANK[action];
}

/** القدرة الدقيقة: هل يملك الدور تنفيذ هذا الفعل (على هذا المورد إن حُدِّد)؟
 *  fail-closed (المجهول = viewer). أحاديّة مضمونة: عتبة رتبة مونوتونيّة. */
export function can(role: string | undefined, action: Capability, resource?: ResourceArea): boolean {
  return ROLE_RANK[normalizeRole(role)] >= requiredRank(action, resource);
}

/** صلاحيّة التعديل. بلا مورد: الفحص الخشن (أيّ دور غير viewer) — توافق خلفيّ
 *  مع كلّ نقاط النداء القائمة. بمورد: يفوّض إلى `can(role,'edit',resource)`
 *  فيضيّق حين يفرض المورد قيداً أشدّ. لا يستبدل `can` للحذف/الإقرار. */
export function canMutate(role: string | undefined, resource?: ResourceArea): boolean {
  if (resource === undefined) return normalizeRole(role) !== 'viewer';
  return can(role, 'edit', resource);
}

/** صلاحيّة الإدارة الحسّاسة (إدارة مستخدمين/إعدادات حرجة): owner/manager فقط.
 *  مُعبَّر عنها الآن بالرتبة (مصدر واحد للحقيقة = عتبة الفعل الإداريّ). */
export function canManage(role: string | undefined): boolean {
  return ROLE_RANK[normalizeRole(role)] >= ROLE_RANK.manager;
}

/** صلاحيّة إنشاء مزرعة (farm:create) — owner فقط (يطابق RBAC الخلفيّة:
 *  FARM_CREATE مقصور على OWNER). تُستخدم لبوّابة الـonboarding كي لا يُحبَس
 *  غير المالك (manager/agronomist/worker/viewer) في شاشة إنشاء مزرعة لا
 *  يستطيع إكمالها (POST /api/v1/farms يردّ 403 لهم). */
export function canCreateFarm(role: string | undefined): boolean {
  return can(role, 'create', 'farm');
}

/** تسمية عربيّة موحّدة للدور. */
export const ROLE_LABEL_AR: Record<Role, string> = {
  owner: 'مالك',
  manager: 'مدير',
  agronomist: 'مهندس زراعيّ',
  worker: 'عامل',
  viewer: 'مُشاهِد',
};
