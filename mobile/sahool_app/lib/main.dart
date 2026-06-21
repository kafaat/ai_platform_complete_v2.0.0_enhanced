// SAHOOL v9.1.0 — lib/main.dart (مُحسَّن)
// Fixes: F01(BlocProvider), F02(WS connect), F03(ErrorBoundary)
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'bloc/dashboard_bloc.dart';
import 'screens/dashboard_screen.dart';
import 'screens/advisor_screen.dart';
import 'screens/login_screen.dart';
import 'screens/fields_screen.dart';
import 'screens/satellite_screen.dart';
import 'screens/more_screen.dart';
import 'screens/onboarding_screen.dart';
import 'screens/field_workspace_screen.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/websocket_service.dart';
import 'theme/app_theme.dart';

// ملاحظة بيئة التشغيل المحليّة (dart-define): مرّر عنوان الـAPI/الـWS عند التشغيل
// دون تثبيتهما في الشيفرة (انظر String.fromEnvironment في api/websocket service؛
// يُلحَق المسار /ws/notifications بقيمة WS_URL داخليّاً):
//   flutter run \
//     --dart-define=API_URL=http://10.0.2.2:8000 \
//     --dart-define=WS_URL=ws://10.0.2.2:8000
// الافتراضيّ للإنتاج: API_URL=https://api.sahool.ye و WS_URL=wss://api.sahool.ye.

void main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // F07: Initialize Hive for chat history
  await Hive.initFlutter();
  await Hive.openBox('chat_history');
  await Hive.openBox('settings');

  // F03: Global error boundary
  FlutterError.onError = (details) {
    FlutterError.dumpErrorToConsole(details);
    // Log to remote in production
  };

  ErrorWidget.builder = (FlutterErrorDetails details) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F1117),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Text('🌿', style: TextStyle(fontSize: 48)),
              const SizedBox(height: 16),
              const Text('حدث خطأ غير متوقع',
                  style: TextStyle(color: Colors.white, fontSize: 18,
                      fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text(details.exception.toString(),
                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                  textAlign: TextAlign.center),
              const SizedBox(height: 24),
              ElevatedButton(
                onPressed: () => runApp(const SAHOOLApp()),
                style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF10B981)),
                child: const Text('إعادة التشغيل'),
              ),
            ],
          ),
        ),
      ),
    );
  };

  runApp(const SAHOOLApp());
}

class SAHOOLApp extends StatelessWidget {
  const SAHOOLApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'SAHOOL — المنصة الزراعية الذكية',
      debugShowCheckedModeBanner: false,
      locale: const Locale('ar', 'YE'),
      supportedLocales: const [Locale('ar', 'YE'), Locale('en', 'US')],
      // سمة «تطبيق الحقل» على طراز FieldView (كريميّ/أخضر/ذهبيّ) — lib/theme.
      theme: AppTheme.light,
      builder: (context, child) => Directionality(
        textDirection: TextDirection.rtl,
        child: child!,
      ),
      home: const AuthGate(),
      // مسار مساحة عمل الحقل (Field-Centric): بطاقة الحقل تنادي
      // pushNamed('field_workspace', arguments: fieldId).
      onGenerateRoute: (settings) {
        if (settings.name == FieldWorkspaceScreen.routeName) {
          final fid = settings.arguments is String ? settings.arguments as String : null;
          return MaterialPageRoute(
            settings: settings,
            builder: (_) => FieldWorkspaceScreen(fieldId: fid),
          );
        }
        return null;
      },
    );
  }
}

// F02: AuthGate connects WebSocket after login
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});
  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  bool _isReady = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    await AuthService.instance.loadSaved();
    if (AuthService.instance.token != null) {
      // F02: Connect WebSocket when authenticated
      await WebSocketService.instance.connect();
    }
    if (mounted) setState(() => _isReady = true);
  }

  @override
  void dispose() {
    WebSocketService.instance.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_isReady) {
      return const Scaffold(
        backgroundColor: Color(0xFF0F1117),
        body: Center(child: CircularProgressIndicator(color: Color(0xFF10B981))),
      );
    }

    if (AuthService.instance.token == null) {
      return const LoginScreen();
    }

    // F01: DashboardBloc properly provided
    return MultiBlocProvider(
      providers: [
        BlocProvider<DashboardBloc>(
          create: (_) => DashboardBloc(ApiService.instance)..add(LoadDashboard()),
        ),
      ],
      child: const MainNavigation(),
    );
  }
}

class MainNavigation extends StatefulWidget {
  const MainNavigation({super.key});
  @override
  State<MainNavigation> createState() => _MainNavigationState();
}

class _MainNavigationState extends State<MainNavigation> {
  int _selectedIndex = 0;

  // فهرس تبويب «بيانات» (الحقول) — وجهة زرّ «إنشاء أوّل حقل» (من الترحيب/اللوحة).
  // في تنظيم FieldView: نظرة عامّة(0)/صحّة الحقل(1)/بيانات(2)/تحليل(3)/إعدادات(4).
  static const int _fieldsTabIndex = 2;

  // بوّابة الترحيب: نتحقّق مرّة من وجود حقول للمستخدم المُصادَق عليه. حتّى تكتمل
  // المحاولة نُبقي العرض على اللوحة العاديّة (لا نحجب الواجهة بمؤشّر تحميل ثانٍ).
  // فشل الجلب (شبكة/خادم) لا يفرض الترحيب — نتركه false fail-open ليرى المستخدم
  // اللوحة بحالة الخطأ الخاصّة بها بدل بوّابة ترحيب مضلِّلة.
  bool _checkedFields = false;
  bool _hasZeroFields = false;

  @override
  void initState() {
    super.initState();
    _checkFields();
  }

  Future<void> _checkFields() async {
    try {
      final data = await ApiService.instance.getDashboard();
      final zero = _isZeroFields(data);
      if (mounted) {
        setState(() {
          _hasZeroFields = zero;
          _checkedFields = true;
        });
      }
    } catch (_) {
      // fail-open: لا نفرض الترحيب عند تعذّر الجلب.
      if (mounted) setState(() => _checkedFields = true);
    }
  }

  // كشف «صفر حقول» دفاعيّاً: نقبل عدّاد صريح (fields_count) أو قائمة حقول بأيّ من
  // المفاتيح المحتملة (نفس منطق fields_screen). أيّ غموض يُعدّ «ليس صفراً» (fail-open).
  bool _isZeroFields(Map<String, dynamic> data) {
    final count = data['fields_count'];
    if (count is num) return count == 0;
    final raw = data['fields'] ?? data['fields_summary'] ?? data['field_list'];
    if (raw is List) return raw.isEmpty;
    return false;
  }

  void _goToFields() {
    setState(() {
      _hasZeroFields = false; // اخرج من بوّابة الترحيب
      _selectedIndex = _fieldsTabIndex;
    });
  }

  // تنظيم المعلومات على طراز FieldView (5 وجهات، تسميات عربيّة):
  //   نظرة عامّة → DashboardScreen | صحّة الحقل → SatelliteScreen (مؤشّرات/NDVI)
  //   بيانات → FieldsScreen (حقول المستخدم وبياناتها) | تحليل → AdvisorScreen
  //   إعدادات → MoreScreen (الوحدات الثانويّة + الحساب/الإعدادات).
  // العمليّات (OperationsHubScreen) تبقى موجودة وتُفتَح من «المزيد» (لم تُحذَف).
  static const List<BottomNavigationBarItem> _navItems = [
    BottomNavigationBarItem(icon: Icon(Icons.dashboard_outlined), label: 'نظرة عامّة'),
    BottomNavigationBarItem(icon: Icon(Icons.eco_outlined), label: 'صحّة الحقل'),
    BottomNavigationBarItem(icon: Icon(Icons.layers_outlined), label: 'بيانات'),
    BottomNavigationBarItem(icon: Icon(Icons.insights_outlined), label: 'تحليل'),
    BottomNavigationBarItem(icon: Icon(Icons.settings_outlined), label: 'إعدادات'),
  ];

  @override
  Widget build(BuildContext context) {
    // بوّابة الترحيب: مستخدم مُصادَق عليه بلا حقول ⇒ شاشة ترحيب بزرّ رئيسيّ.
    if (_checkedFields && _hasZeroFields) {
      return OnboardingScreen(onStart: _goToFields);
    }

    // قائمة الشاشات تُبنى هنا (لا const) لتمرير الـcallback إلى اللوحة.
    // ترتيب FieldView: نظرة عامّة/صحّة الحقل/بيانات/تحليل/إعدادات.
    final screens = <Widget>[
      DashboardScreen(onCreateField: _goToFields), // نظرة عامّة
      const SatelliteScreen(),                     // صحّة الحقل (مؤشّرات/NDVI)
      const FieldsScreen(),                        // بيانات (الحقول)
      const AdvisorScreen(),                       // تحليل (المستشار)
      const MoreScreen(),                          // إعدادات (+ الوحدات الثانويّة)
    ];

    // H01: Handle Android back button
    return PopScope(
      canPop: _selectedIndex == 0,
      onPopInvoked: (didPop) {
        if (!didPop && _selectedIndex != 0) {
          setState(() => _selectedIndex = 0);
        }
      },
      child: Scaffold(
        body: IndexedStack(index: _selectedIndex, children: screens),
        // الألوان من bottomNavigationBarTheme (سمة FieldView) — لا تثبيت هنا.
        bottomNavigationBar: BottomNavigationBar(
          currentIndex: _selectedIndex,
          onTap: (i) => setState(() => _selectedIndex = i),
          type: BottomNavigationBarType.fixed,
          items: _navItems,
        ),
      ),
    );
  }
}

// الشاشات في ملفّاتها المستقلّة (screens/*.dart). شريط التنقّل أُعيد تنظيمه على
// طراز FieldView لخمس وجهات (نظرة عامّة/صحّة الحقل/بيانات/تحليل/إعدادات) بإعادة
// استعمال الشاشات القائمة (لوحة→نظرة، أقمار→صحّة، حقول→بيانات، مستشار→تحليل،
// المزيد→إعدادات). العمليّات والوحدات الثانويّة تبقى مُتاحة من «المزيد» (لم تُحذَف).
// بوّابة الترحيب (OnboardingScreen) تُعرَض للمستخدم المُصادَق عليه بلا حقول بعد.
