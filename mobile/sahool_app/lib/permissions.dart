// SAHOOL — lib/permissions.dart
// تطبيق الأدوار (RBAC) في تطبيق الموبايل، موازٍ لـfrontend/src/lib/permissions.ts.
// مصدر واحد للحقيقة: الدور يُقرأ من الجلسة (AuthService). fail-closed: الدور
// المجهول يُعامَل كـviewer (أقلّ صلاحيّة) لا كمالك.
import 'services/auth_service.dart';

enum AppRole { owner, manager, agronomist, worker, viewer }

// تطبيع الأسماء القديمة/المرادفة لأدوار النظام الخمسة المعتمدة (يطابق الواجهة).
const Map<String, AppRole> _roleAliases = {
  'owner': AppRole.owner,
  'admin': AppRole.owner,
  'manager': AppRole.manager,
  'agronomist': AppRole.agronomist,
  'expert': AppRole.agronomist,
  'worker': AppRole.worker,
  'farmer': AppRole.worker,
  'viewer': AppRole.viewer,
};

AppRole normalizeRole(String? role) =>
    _roleAliases[(role ?? '').toLowerCase()] ?? AppRole.viewer; // fail-closed

/// صلاحيّة التعديل (إضافة/تسجيل/تغيير حالة…). viewer قراءة فقط؛ غيره يعدّل في نطاقه.
bool canMutate(String? role) => normalizeRole(role) != AppRole.viewer;

/// الإدارة الحسّاسة (بيانات مرجعيّة/وثائق): owner/manager فقط — يطابق canManage في الواجهة.
bool canManage(String? role) {
  final r = normalizeRole(role);
  return r == AppRole.owner || r == AppRole.manager;
}

/// الدور الحاليّ من الجلسة (مصدر واحد للحقيقة).
String? currentRole() => AuthService.instance.userRole;
