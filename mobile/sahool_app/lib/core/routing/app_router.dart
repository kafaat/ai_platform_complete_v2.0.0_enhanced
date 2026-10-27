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
//   • جلسة: مسار غير عامّ لا يُبنى بلا جلسة مصادَقة (رابط عميق قبل الدخول ⇒
//     صفحة «سجّل الدخول»)؛ الدور وحده لا يكفي لأنّ غياب الجلسة يُطبَّع إلى viewer.
//     يُحكم بعد حسم الجلسة (استعادة القرص + تجديد جارٍ) لا قبله، وفشل الشبكة
//     أثناء التجديد «غير معروف» لا رفض: رمز التحديث يبقى فتبقى الجلسة قابلة
//     للاستئناف حتّى يرفضها الخادم صراحةً.
//   • «المزيد»: [menuFor] يبني القائمة من MenuEntry في ملفّات المسارات.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/features/activities/activities_routes.dart';
import 'package:sahool_app/features/advisor/advisor_routes.dart';
import 'package:sahool_app/features/alerts/alerts_routes.dart';
import 'package:sahool_app/features/auth/auth_routes.dart';
import 'package:sahool_app/features/crop_season/crop_season_routes.dart';
import 'package:sahool_app/features/dashboard/dashboard_routes.dart';
import 'package:sahool_app/features/devices/devices_routes.dart';
import 'package:sahool_app/features/documents/documents_routes.dart';
import 'package:sahool_app/features/equipment/equipment_routes.dart';
import 'package:sahool_app/features/farm_book/farm_book_routes.dart';
import 'package:sahool_app/features/farms/farms_routes.dart';
import 'package:sahool_app/features/field_forms/field_forms_routes.dart';
import 'package:sahool_app/features/fields/fields_routes.dart';
import 'package:sahool_app/features/inventory/inventory_routes.dart';
import 'package:sahool_app/features/irrigation/irrigation_routes.dart';
import 'package:sahool_app/features/lab_sampling/lab_sampling_routes.dart';
import 'package:sahool_app/features/maps/maps_routes.dart';
import 'package:sahool_app/features/master_data/master_data_routes.dart';
import 'package:sahool_app/features/more/more_routes.dart';
import 'package:sahool_app/features/offline_sync/offline_sync_routes.dart';
import 'package:sahool_app/features/operations_hub/operations_hub_routes.dart';
import 'package:sahool_app/features/profile/profile_routes.dart';
import 'package:sahool_app/features/realtime/realtime_routes.dart';
import 'package:sahool_app/features/satellite/satellite_routes.dart';
import 'package:sahool_app/features/scouting/scouting_routes.dart';
import 'package:sahool_app/features/tasks/tasks_routes.dart';
import 'package:sahool_app/features/weather/weather_routes.dart';
import 'package:sahool_app/services/auth_service.dart';

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
  offlineSyncFeature,
  scoutingFeature,
  alertsFeature,
  weatherFeature,
  activitiesFeature,
  mapsFeature,
  cropSeasonFeature,
  labSamplingFeature,
  farmBookFeature,
];

class AppRouter {
  AppRouter({
    required List<FeatureModule> features,
    AppRole Function()? role,
    bool Function()? isAuthenticated,
    Future<void>? Function()? sessionPending,
  }) : features = List.unmodifiable(features),
       // حسم الجلسة: استعادتها من القرص ثمّ أيّ تجديد جارٍ لها. مسار خاصّ يُفتح
       // قبل الحسم ينتظره ولا يحكم على جلسة لم تُقرأ. الحاقن لـisAuthenticated
       // (الاختبارات) يملك الحكم كاملاً فلا انتظار افتراضيّ له.
       _sessionPending =
           sessionPending ??
           (isAuthenticated == null ? _defaultSessionPending : _settled),
       _role = role ?? (() => normalizeRole(currentRole())),
       // الجلسة القابلة للاستئناف لا صلاحية رمز الوصول: الرمز (60 دقيقة) يُجدَّد
       // عند أوّل نداء REST لا بمؤقّت، فبعد خمول ساعة يكون منتهياً والجلسة حيّة
       // برمز التحديث. البوّابة هنا تمنع رابطاً عميقاً بلا جلسة؛ رفض التحديث يمرّ
       // عبر ApiClient.onSessionExpired ⇒ AuthGate ⇒ شاشة الدخول.
       _isAuthenticated =
           isAuthenticated ?? (() => AuthService.instance.canResumeSession) {
    for (final f in features) {
      for (final r in f.routes) {
        for (final name in [r.path, ...r.aliases]) {
          final key = _normalize(name);
          final existing = _table[key];
          if (existing != null) {
            throw StateError(
              'Route "$key" is declared twice (feature "${f.id}" and '
              '"${_owner[key]}"). Each path belongs to one feature.',
            );
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
  final bool Function() _isAuthenticated;
  final Future<void>? Function() _sessionPending;
  final Map<String, AppRoute> _table = {};

  static Future<void>? _settled() => null;

  static Future<void>? _defaultSessionPending() =>
      AuthService.instance.pendingRestore ?? ApiClient.instance.pendingRefresh;
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
  Widget buildPage(
    BuildContext context,
    String path, {
    RouteArgs args = RouteArgs.empty,
  }) {
    final route = match(path);
    if (route == null) return RouteNotFoundPage(name: path);
    if (!route.allows(role)) return AccessDeniedPage(title: route.titleAr);
    return route.builder(context, args);
  }

  Route<dynamic>? onGenerateRoute(RouteSettings settings) {
    final name = settings.name;
    final route = match(name);
    if (route == null) return null; // ⇒ onUnknownRoute
    final query = name == null
        ? const <String, String>{}
        : Uri.parse(name).queryParameters;
    final args = RouteArgs(query: query, extra: settings.arguments);
    // غير العامّ يتطلّب جلسة أوّلاً (رابط عميق قبل الدخول)، ثمّ الدور.
    WidgetBuilder decide() {
      final signedIn = route.public || _isAuthenticated();
      final allowed = route.public || route.allows(role);
      return (context) => !signedIn
          ? SignInRequiredPage(title: route.titleAr)
          : allowed
          ? route.builder(context, args)
          : AccessDeniedPage(title: route.titleAr);
    }

    final pending = route.public ? null : _sessionPending();
    return MaterialPageRoute<dynamic>(
      settings: settings,
      fullscreenDialog: route.fullscreenDialog,
      builder: pending == null
          ? decide()
          : (context) => SessionPendingPage(
              title: route.titleAr,
              pending: pending,
              resolve: decide,
            ),
    );
  }

  Route<dynamic> onUnknownRoute(RouteSettings settings) =>
      MaterialPageRoute<dynamic>(
        settings: settings,
        builder: (_) => RouteNotFoundPage(name: settings.name ?? ''),
      );

  /// مداخل «المزيد» المسموحة للدور، مجمّعة بالقسم ومرتّبة.
  Map<MenuSection, List<AppRoute>> menuFor(
    AppRole role, {
    Set<MenuSection>? sections,
  }) {
    final out = <MenuSection, List<AppRoute>>{};
    for (final section in MenuSection.values) {
      if (sections != null && !sections.contains(section)) continue;
      final items =
          routes
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
