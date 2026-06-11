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
const ALL_PAGES: PageId[] = [
  'dashboard', 'hybrid-index', 'satellite', 'fields', 'recommendations',
  'irrigation', 'irrigation-ops', 'pest-escalation', 'field-intelligence',
  'spatial-indicators', 'devices', 'inventory', 'equipment',
  'tasks', 'analytics', 'alerts', 'reports', 'master-data', 'documents', 'chatbot', 'settings',
];

// worker (مزارع/عامل): الصفحات التشغيليّة فقط (وفق سياسة الإعدادات الموثّقة:
// لوحة + أقمار + حقول + مهام، مع التنبيهات/المستشار/المكانيّة + أدوات حقله).
const WORKER_PAGES: PageId[] = [
  'dashboard', 'satellite', 'fields', 'tasks', 'alerts', 'chatbot', 'spatial-indicators',
  'irrigation', 'pest-escalation', 'field-intelligence',
  'inventory', 'equipment', 'devices', 'irrigation-ops',
];

// صفحات إداريّة (owner/manager فقط): البيانات المرجعيّة + الوثائق.
// لا تظهر لـagronomist/viewer حتى لو كان الخادم سيردّ 403 — منعٌ من المصدر في الواجهة.
const MANAGEMENT_ONLY_PAGES: PageId[] = ['master-data', 'documents'];

// كلّ ما عدا الصفحات الإداريّة (لـagronomist والمُشاهِد). يحافظ على وصولهما الكامل
// للصفحات التشغيليّة/التحليليّة، مع استبعاد الإداريّة فقط.
const NON_MANAGEMENT_PAGES: PageId[] = ALL_PAGES.filter(
  (p) => !MANAGEMENT_ONLY_PAGES.includes(p),
);

const ROLE_PAGES: Record<Role, PageId[]> = {
  owner: ALL_PAGES,
  manager: ALL_PAGES,
  agronomist: NON_MANAGEMENT_PAGES, // وصول كامل عدا الصفحات الإداريّة
  worker: WORKER_PAGES,
  viewer: NON_MANAGEMENT_PAGES, // يرى كلّ شيء (عدا الإداريّة) قراءةً فقط (انظر canMutate)
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

/** تسمية عربيّة موحّدة للدور. */
export const ROLE_LABEL_AR: Record<Role, string> = {
  owner: 'مالك',
  manager: 'مدير',
  agronomist: 'مهندس زراعيّ',
  worker: 'عامل',
  viewer: 'مُشاهِد',
};
