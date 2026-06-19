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
const ALL_PAGES = [
  'dashboard', 'unified-cabin', 'command', 'map-center', 'tasks-cabin', 'rec-flow', 'hybrid-monitor', 'analyze-cabin', 'setup-cabin', 'field-app', 'hybrid-index', 'satellite', 'fields', 'farm-map', 'recommendations',
  'irrigation', 'weather-advice', 'irrigation-ops', 'pest-escalation', 'field-intelligence',
  'spatial-indicators', 'devices', 'inventory', 'equipment',
  'tasks', 'activities', 'field-ranking', 'problem-fields', 'economics', 'phenology', 'scouting', 'advisory-report', 'analytics', 'alerts', 'reports', 'master-data', 'documents', 'governance', 'chatbot', 'settings',
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
  'dashboard', 'unified-cabin', 'command', 'map-center', 'tasks-cabin', 'rec-flow', 'hybrid-monitor', 'analyze-cabin', 'setup-cabin', 'field-app', 'satellite', 'fields', 'farm-map', 'tasks', 'activities', 'field-ranking', 'problem-fields', 'economics', 'phenology', 'scouting', 'advisory-report', 'alerts', 'chatbot', 'spatial-indicators',
  'irrigation', 'weather-advice', 'pest-escalation', 'field-intelligence',
  'inventory', 'equipment', 'devices', 'irrigation-ops',
];

// صفحات إداريّة (owner/manager فقط): البيانات المرجعيّة + الوثائق.
// لا تظهر لـagronomist/viewer حتى لو كان الخادم سيردّ 403 — منعٌ من المصدر في الواجهة.
const MANAGEMENT_ONLY_PAGES: PageId[] = ['master-data', 'documents', 'governance'];

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
  'economics', 'analytics', 'reports', 'advisory-report', 'field-ranking', 'problem-fields',
];
const VIEWER_PAGES: PageId[] = NON_MANAGEMENT_PAGES.filter(
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

/** صلاحيّة التعديل (إضافة/حذف/إقرار…). viewer قراءة فقط؛ غيره يعدّل في نطاقه. */
export function canMutate(role: string | undefined): boolean {
  return normalizeRole(role) !== 'viewer';
}

/** صلاحيّة الإدارة الحسّاسة (إدارة مستخدمين/إعدادات حرجة): owner/manager فقط. */
export function canManage(role: string | undefined): boolean {
  const r = normalizeRole(role);
  return r === 'owner' || r === 'manager';
}

/** صلاحيّة إنشاء مزرعة (farm:create) — owner فقط (يطابق RBAC الخلفيّة:
 *  FARM_CREATE مقصور على OWNER). تُستخدم لبوّابة الـonboarding كي لا يُحبَس
 *  غير المالك (manager/agronomist/worker/viewer) في شاشة إنشاء مزرعة لا
 *  يستطيع إكمالها (POST /api/v1/farms يردّ 403 لهم). */
export function canCreateFarm(role: string | undefined): boolean {
  return normalizeRole(role) === 'owner';
}

/** تسمية عربيّة موحّدة للدور. */
export const ROLE_LABEL_AR: Record<Role, string> = {
  owner: 'مالك',
  manager: 'مدير',
  agronomist: 'مهندس زراعيّ',
  worker: 'عامل',
  viewer: 'مُشاهِد',
};
