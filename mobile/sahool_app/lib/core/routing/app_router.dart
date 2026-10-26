// SAHOOL — lib/core/routing/app_router.dart
// الموجِّه الوحيد. يجمع وحدات الميزات (كلّ features/<x>/<x>_routes.dart) ولا
// يعرّف أيّ مسار بنفسه. هذا هو الملفّ الوحيد الذي يستورد كلّ ملفّات المسارات؛
// كلّ الميزات الحاليّة مُسجَّلة فيه، فلا تعدّله ميزة موجودة أبداً — فقط ميزة
// جديدة كلّيّاً تضيف سطراً إلى [allFeatures].
//
// ما يضمنه:
//   • مسار فريد: تكرار مسار/اسم بديل بين ميزتين يرمي StateError عند الإقلاع
//     (ويحرسه test/core/app_router_test.dart).
//   • روابط عميقة: '/fields/workspace?field_id=f1' ⇒ RouteArgs.query.
//   • أدوار: مسار بـallowedRoles لا يُفتح لغير أهله (صفحة «لا صلاحيّة» صادقة).
//   • «المزيد»: [menuFor] يبني القائمة من MenuEntry في ملفّات المسارات.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/features/advisor/advisor_routes.dart';
import 'package:sahool_app/features/auth/auth_routes.dart';
import 'package:sahool_app/features/dashboard/dashboard_routes.dart';
import 'package:sahool_app/features/devices/devices_routes.dart';
import 'package:sahool_app/features/documents/documents_routes.dart';
import 'package:sahool_app/features/equipment/equipment_routes.dart';
import 'package:sahool_app/features/farms/farms_routes.dart';
import 'package:sahool_app/features/field_forms/field_forms_routes.dart';
import 'package:sahool_app/features/fields/fields_routes.dart';
import 'package:sahool_app/features/inventory/inventory_routes.dart';
import 'package:sahool_app/features/irrigation/irrigation_routes.dart';
import 'package:sahool_app/features/master_data/master_data_routes.dart';
import 'package:sahool_app/features/more/more_routes.dart';
import 'package:sahool_app/features/operations_hub/operations_hub_routes.dart';
import 'package:sahool_app/features/profile/profile_routes.dart';
import 'package:sahool_app/features/realtime/realtime_routes.dart';
import 'package:sahool_app/features/satellite/satellite_routes.dart';
import 'package:sahool_app/features/tasks/tasks_routes.dart';

import 'app_route.dart';
import 'route_pages.dart';

/// كلّ ميزات التطبيق. الترتيب لا يؤثّر في السلوك.
final List<FeatureModule> allFeatures = [
  authFeature,
  dashboardFeature,
  farmsFeature,
  fieldsFeature,
  satelliteFeature,
  irrigationFeature,
  tasksFeature,
  inventoryFeature,
  equipmentFeature,
  devicesFeature,
  documentsFeature,
  advisorFeature,
  masterDataFeature,
  profileFeature,
  operationsHubFeature,
  moreFeature,
  fieldFormsFeature,
  realtimeFeature,
];

class AppRouter {
  AppRouter({
    required List<FeatureModule> features,
    AppRole Function()? role,
  })  : features = List.unmodifiable(features),
        _role = role ?? (() => normalizeRole(currentRole())) {
    for (final f in features) {
      for (final r in f.routes) {
        for (final name in [r.path, ...r.aliases]) {
          final key = _normalize(name);
          final existing = _table[key];
          if (existing != null) {
            throw StateError(
                'Route "$key" is declared twice (feature "${f.id}" and '
                '"${_owner[key]}"). Each path belongs to one feature.');
          }
          _table[key] = r;
          _owner[key] = f.id;
        }
      }
    }
  }

  static final AppRouter instance = AppRouter(features: allFeatures);

  final List<FeatureModule> features;
  final AppRole Function() _role;
  final Map<String, AppRoute> _table = {};
  final Map<String, String> _owner = {};

  AppRole get role => _role();

  Iterable<AppRoute> get routes => features.expand((f) => f.routes);

  static String _normalize(String name) {
    final path = Uri.parse(name).path;
    if (path.length > 1 && path.endsWith('/')) {
      return path.substring(0, path.length - 1);
    }
    return path;
  }

  /// المسار المطابق لاسم/رابط (يتجاهل الاستعلام)، أو null.
  AppRoute? match(String? name) =>
      name == null ? null : _table[_normalize(name)];

  /// معرّف الميزة المالكة لمسار (للتشخيص والاختبارات).
  String? ownerOf(String name) => _owner[_normalize(name)];

  /// بناء صفحة مسار مباشرةً (لتبويبات الغلاف). يحترم الأدوار.
  Widget buildPage(BuildContext context, String path,
      {RouteArgs args = RouteArgs.empty}) {
    final route = match(path);
    if (route == null) return RouteNotFoundPage(name: path);
    if (!route.allows(role)) return AccessDeniedPage(title: route.titleAr);
    return route.builder(context, args);
  }

  Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    final name = settings.name;
    final route = match(name);
    if (route == null) return null; // ⇒ onUnknownRoute
    final query = name == null ? const <String, String>{} : Uri.parse(name).queryParameters;
    final args = RouteArgs(query: query, extra: settings.arguments);
    final allowed = route.public || route.allows(role);
    return MaterialPageRoute<dynamic>(
      settings: settings,
      fullscreenDialog: route.fullscreenDialog,
      builder: (context) => allowed
          ? route.builder(context, args)
          : AccessDeniedPage(title: route.titleAr),
    );
  }

  Route<dynamic> onUnknownRoute(RouteSettings settings) =>
      MaterialPageRoute<dynamic>(
        settings: settings,
        builder: (_) => RouteNotFoundPage(name: settings.name ?? ''),
      );

  /// مداخل «المزيد» المسموحة للدور، مجمّعة بالقسم ومرتّبة.
  Map<MenuSection, List<AppRoute>> menuFor(AppRole role,
      {Set<MenuSection>? sections}) {
    final out = <MenuSection, List<AppRoute>>{};
    for (final section in MenuSection.values) {
      if (sections != null && !sections.contains(section)) continue;
      final items = routes
          .where((r) => r.menu?.section == section && r.allows(role))
          .toList()
        ..sort((a, b) => a.menu!.order.compareTo(b.menu!.order));
      if (items.isNotEmpty) out[section] = items;
    }
    return out;
  }

  /// يسجّل دوالّ تنظيف الميزات في [scope] (مرّة عند الإقلاع).
  void registerSessionCleanups(SessionScope scope) {
    for (final f in features) {
      final cleanup = f.onSessionEnd;
      if (cleanup != null) scope.register(f.id, cleanup);
    }
  }
}
