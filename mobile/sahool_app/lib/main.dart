// SAHOOL — lib/main.dart
// جذر التطبيق: تهيئة، MaterialApp (سمة، لغة عربيّة RTL، موجِّه)، وAuthGate.
// لا مسارات ولا شاشات تُعرَّف هنا: المسارات في features/<x>/<x>_routes.dart
// يجمعها core/routing/app_router.dart، والغلاف في core/routing/app_shell.dart.
//
// مسار مُثبَّت: scripts/ci/mobile_contract_gate.py وtests_v9 تقرأ هذا الملفّ
// (رسالة ErrorWidget الآمنة بحارس kDebugMode، فحص isAuthenticated في AuthGate،
// تهيئة/إتلاف FieldFormsCoordinator).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/app_shell.dart';
import 'package:sahool_app/core/session/auth_state.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/core/theme/theme_controller.dart';
import 'package:sahool_app/core/widgets/app_error_widget.dart';
import 'package:sahool_app/core/widgets/app_states.dart';
import 'package:sahool_app/core/widgets/offline_banner.dart';
import 'package:sahool_app/features/advisor/data/chat_history_store.dart';
import 'package:sahool_app/features/auth/presentation/login_screen.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_coordinator.dart';
import 'package:sahool_app/services/auth_service.dart';
import 'package:sahool_app/services/push_service.dart';
import 'package:sahool_app/services/websocket_service.dart';

// ملاحظة بيئة التشغيل المحليّة (dart-define): مرّر عنوان الـAPI/الـWS عند التشغيل
// دون تثبيتهما في الشيفرة (انظر lib/config/app_config.dart؛ يُلحَق المسار
// /ws/notifications بقيمة WS_URL داخليّاً):
//   flutter run \
//     --dart-define=SAHOOL_ENV=dev \
//     --dart-define=API_URL=<emulator-http-gateway> \
//     --dart-define=WS_URL=<emulator-ws-gateway>
// 10.0.2.2 = مضيف المُحاكي (Android emulator)، وبلا منفذ ⇒ بوّابة nginx على :80
// (المرجع القانونيّ في docker-compose.v9.yml). لا تستعمل :8000 — منفذ المنصّة الداخليّ
// غير مكشوف للمضيف في v9. لجهاز حقيقيّ: عنوان مضيفك على الشبكة. الافتراضيّ
// للإنتاج: https://api.sahool.ye وWS_URL=wss://api.sahool.ye.

/// رسالة الخطأ الآمنة للإنتاج (لا تفاصيل استثناء خارج وضع التطوير).
const String kSafeErrorMessage =
    'حدث خطأ غير متوقع. يرجى المحاولة مجدداً. تم تسجيل الخطأ لفريق الدعم.';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Hive.initFlutter();
  await Hive.openBox('settings');
  // سجلّ المستشار القديم بنصّ صريح مشترك بين المستخدمين: لا يقرؤه شيء ⇒ يُحذَف.
  unawaited(purgeLegacyAdvisorChat());
  ThemeController.instance.load();

  // تنظيفات الميزات عند الخروج (FeatureModule.onSessionEnd).
  AppRouter.instance.registerSessionCleanups(SessionScope.instance);
  // AuthGate تستعيد الجلسة بعد أوّل بناء؛ رابط عميق يُولَّد قبلها ينتظرها.
  AuthService.instance.expectRestore();
  unawaited(ConnectivityStatus.instance.start());

  FlutterError.onError = (details) {
    FlutterError.dumpErrorToConsole(details);
  };

  // فشل بناء ودجة ⇒ بطاقة خطأ مضغوطة في مكانها (لا شاشة كاملة). التفاصيل في
  // وضع التطوير فقط (kDebugMode)؛ الإنتاج يعرض رسالة آمنة.
  ErrorWidget.builder = (FlutterErrorDetails details) => AppErrorWidget(
        details: details,
        message: kSafeErrorMessage,
      );

  runApp(const SAHOOLApp());
}

class SAHOOLApp extends StatelessWidget {
  const SAHOOLApp({super.key, this.home, this.router});

  /// للاختبارات: شاشة جذر بديلة عن AuthGate.
  final Widget? home;
  final AppRouter? router;

  @override
  Widget build(BuildContext context) {
    final r = router ?? AppRouter.instance;
    return ValueListenableBuilder<ThemeMode>(
      valueListenable: ThemeController.instance,
      builder: (context, mode, _) => MaterialApp(
        title: 'SAHOOL — المنصة الزراعية الذكية',
        debugShowCheckedModeBanner: false,
        navigatorKey: appNavigatorKey,
        // العربيّة أوّلاً. المندوبات (delegates) لازمة: بدونها كان كلّ TextField
        // وDatePicker وزرّ رجوع يرمي «No MaterialLocalizations found»، وهي التي
        // تجعل الاتّجاه RTL (لا حاجة لـDirectionality يدويّ).
        locale: const Locale('ar', 'YE'),
        supportedLocales: const [Locale('ar', 'YE'), Locale('en', 'US')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        theme: AppTheme.light,
        darkTheme: AppTheme.dark,
        themeMode: mode,
        builder: (context, child) =>
            OfflineBannerHost(child: child ?? const SizedBox.shrink()),
        home: home ?? const AuthGate(),
        onGenerateRoute: r.onGenerateRoute,
        onUnknownRoute: r.onUnknownRoute,
      ),
    );
  }
}

/// بوّابة الجلسة: تحميل الجلسة المحفوظة (وتجديدها إن انتهى رمز الوصول وبقي رمز
/// التحديث)، ثمّ الدخول أو الغلاف. تستمع إلى AuthState (دخول/خروج) وإلى
/// ApiClient.onSessionExpired (رفض الخادم لرمز التحديث) فتعود إلى الدخول من أيّ
/// شاشة بدل أن تبقى الشاشات تفشل بـ401.
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});
  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool _isReady = false;
  StreamSubscription<void>? _expiredSub;

  @override
  void initState() {
    super.initState();
    AuthState.instance.addListener(_onAuthChanged);
    _expiredSub = ApiClient.instance.onSessionExpired.listen((_) {
      AuthState.instance.expired();
    });
    _init();
  }

  Future<void> _init() async {
    await AuthService.instance.loadSaved();
    // رمز وصول منتهٍ + رمز تحديث محفوظ ⇒ جدّد قبل القرار (لا دخول كلّ ساعة).
    if (!AuthService.instance.isAuthenticated &&
        AuthService.instance.refreshToken != null) {
      await ApiClient.instance.validAccessToken();
    }
    // فشل الشبكة أثناء التجديد «غير معروف» لا رفض للهويّة: رمز التحديث باقٍ
    // فالجلسة قابلة للاستئناف (الغلاف يعمل دون اتّصال ويجدّد عند أوّل نداء). رفض
    // الخادم الصريح يمسح الجلسة فيعيدها onSessionExpired إلى الدخول.
    if (AuthService.instance.canResumeSession) await _startSession();
    if (mounted) setState(() => _isReady = true);
  }

  Future<void> _startSession() async {
    // الـWS نقل لحظيّ اختياريّ: لا يحجب الغلاف (REST يعمل). مصافحة بطيئة/معلّقة
    // كانت تُبقي شاشة التحميل بلا مهلة؛ إعادة المحاولة يتولّاها الخدمة نفسها.
    unawaited(WebSocketService.instance.connect().catchError((Object _) {}));
    // الدفع (FCM) غير حاجب ودفاعيّ بالكامل (يبقى no-op بلا google-services).
    unawaited(PushService.instance.init().catchError((Object _) {}));
    unawaited(
      FieldFormsCoordinator.instance.init().catchError((Object _) {}),
    );
  }

  void _onAuthChanged() {
    switch (AuthState.instance.last) {
      case AuthChange.signedIn:
        unawaited(_startSession());
      case AuthChange.expired:
        unawaited(WebSocketService.instance.dispose());
        popToRootGlobally();
        _showExpiredNotice();
      case AuthChange.signedOut:
      case null:
        break;
    }
    if (mounted) setState(() {});
  }

  void _showExpiredNotice() {
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(const SnackBar(
      content: Text('انتهت الجلسة — يُرجى تسجيل الدخول من جديد.'),
    ));
  }

  @override
  void dispose() {
    AuthState.instance.removeListener(_onAuthChanged);
    _expiredSub?.cancel();
    WebSocketService.instance.dispose();
    unawaited(FieldFormsCoordinator.instance.dispose());
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_isReady) {
      return const Scaffold(body: LoadingState());
    }

    if (!AuthService.instance.isAuthenticated) {
      // رمز وصول منتهٍ ورمز تحديث باقٍ (تجديد فشل على الشبكة) ⇒ الحكم «غير
      // معروف» لا رفض: الغلاف يبقى ويُجدَّد عند أوّل نداء. الدخول فقط بلا جلسة
      // قابلة للاستئناف (لا رموز، أو رفض الخادم الصريح الذي يمسحها).
      if (!AuthService.instance.canResumeSession) return const LoginScreen();
    }

    // الغلاف يُعاد إنشاؤه لكلّ مستخدم (المفتاح) فتُحسَب وجهات الدور من جديد.
    return AppShell(key: ValueKey(AuthService.instance.userId ?? '_'));
  }
}
