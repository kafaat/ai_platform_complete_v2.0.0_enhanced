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
  'spatial-indicators', 'tasks', 'analytics', 'alerts', 'reports', 'chatbot', 'settings',
];

// worker (مزارع/عامل): الصفحات التشغيليّة فقط (وفق سياسة الإعدادات الموثّقة:
// لوحة + أقمار + حقول + مهام، مع التنبيهات/المستشار/المكانيّة لمتابعة حقله).
const WORKER_PAGES: PageId[] = [
  'dashboard', 'satellite', 'fields', 'tasks', 'alerts', 'chatbot', 'spatial-indicators',
];

const ROLE_PAGES: Record<Role, PageId[]> = {
  owner: ALL_PAGES,
  manager: ALL_PAGES,
  agronomist: ALL_PAGES,
  worker: WORKER_PAGES,
  viewer: ALL_PAGES, // يرى كلّ شيء لكن قراءةً فقط (انظر canMutate)
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
