// SAHOOL — lib/core/routing/app_route.dart
// تعريف المسار ووحدة الميزة. كلّ ميزة تُعلن مساراتها في ملفّ واحد تملكه
// (features/<x>/<x>_routes.dart) كقائمة [AppRoute] داخل [FeatureModule]؛ الموجِّه
// (app_router.dart) يجمعها فقط. إضافة شاشة = سطر في ملفّ مسارات الميزة، لا تعديل
// في ملفّ مشترك.
import 'package:flutter/widgets.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/session/session_scope.dart';

/// وسائط مسار: معاملات الاستعلام من الرابط العميق (`/fields/workspace?field_id=f1`)
/// + الوسيط البرمجيّ (`pushNamed(..., arguments: x)`).
@immutable
class RouteArgs {
  const RouteArgs({this.query = const {}, this.extra});
  static const empty = RouteArgs();

  final Map<String, String> query;
  final Object? extra;

  /// قيمة من الاستعلام، أو من [extra] إن كان Map بنفس المفتاح.
  String? operator [](String key) {
    final q = query[key];
    if (q != null) return q;
    final e = extra;
    if (e is Map && e[key] != null) return e[key].toString();
    return null;
  }
}

typedef RoutePageBuilder = Widget Function(BuildContext context, RouteArgs args);

/// أقسام قائمة «المزيد» (ومراكز التجميع مثل مركز العمليّات). الترتيب = ترتيب
/// العرض. قسم جديد يتطلّب تعديل هذا الملفّ (core) — نادر عمداً.
enum MenuSection {
  farm('المزرعة والحقول'),
  cropHealth('صحّة المحصول'),
  operations('العمليّات'),
  records('السجلّات والبيانات المرجعيّة'),
  account('الحساب والأمان');

  const MenuSection(this.labelAr);
  final String labelAr;
}

/// ظهور مسار في قائمة «المزيد».
@immutable
class MenuEntry {
  const MenuEntry(this.section, {this.order = 100});
  final MenuSection section;

  /// الأصغر أوّلاً داخل القسم.
  final int order;
}

@immutable
class AppRoute {
  const AppRoute({
    required this.path,
    required this.titleAr,
    required this.builder,
    this.icon,
    this.allowedRoles,
    this.public = false,
    this.menu,
    this.aliases = const [],
    this.fullscreenDialog = false,
  });

  /// المسار القانونيّ — اسم الانتقال والرابط العميق معاً. يبدأ بـ«/» ويُكتب
  /// بأحرف صغيرة وشرطات (`/master-data`).
  final String path;
  final String titleAr;
  final IconData? icon;
  final RoutePageBuilder builder;

  /// الأدوار المسموح لها بفتح الشاشة؛ null ⇒ أيّ دور مسجَّل الدخول. هذا تحسين
  /// تجربة لا أمان: الخادم يفرض RBAC على كلّ نقطة مهما عرضت الواجهة.
  final Set<AppRole>? allowedRoles;

  /// true ⇒ تُفتح بلا جلسة (الدخول).
  final bool public;

  /// null ⇒ لا تظهر في «المزيد».
  final MenuEntry? menu;

  /// أسماء قديمة تبقى تعمل (مثل 'field_workspace').
  final List<String> aliases;
  final bool fullscreenDialog;

  bool allows(AppRole role) => allowedRoles == null || allowedRoles!.contains(role);
}

/// ما تُصدِّره كلّ ميزة من ملفّ مساراتها.
@immutable
class FeatureModule {
  const FeatureModule({
    required this.id,
    required this.routes,
    this.onSessionEnd,
  });

  /// معرّف الميزة = اسم مجلّدها تحت lib/features/.
  final String id;
  final List<AppRoute> routes;

  /// تنظيف حالة المستخدم عند الخروج (يُسجَّل في SessionScope باسم [id]).
  final SessionCleanup? onSessionEnd;
}

/// أدوار شائعة لتعريفات المسارات.
abstract final class RouteRoles {
  /// owner/manager — الإدارة الحسّاسة (يطابق canManage).
  static const management = {AppRole.owner, AppRole.manager};

  /// كلّ من يعدّل (يطابق canMutate): الكلّ عدا viewer.
  static const editors = {
    AppRole.owner,
    AppRole.manager,
    AppRole.agronomist,
    AppRole.worker,
  };
}
