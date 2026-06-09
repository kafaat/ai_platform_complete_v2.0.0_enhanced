// SAHOOL v9.1.0 — lib/main.dart (مُحسَّن)
// Fixes: F01(BlocProvider), F02(WS connect), F03(ErrorBoundary)
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'bloc/dashboard_bloc.dart';
import 'screens/dashboard_screen.dart';
import 'screens/advisor_screen.dart';
import 'services/api_service.dart';
import 'services/auth_service.dart';
import 'services/websocket_service.dart';

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
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.dark(
          primary: const Color(0xFF10B981),
          secondary: const Color(0xFF3B82F6),
          surface: const Color(0xFF1A1D29),
          background: const Color(0xFF0F1117),
          onPrimary: Colors.white,
          onSecondary: Colors.white,
          onSurface: Colors.white,
          onBackground: Colors.white,
        ),
        fontFamily: 'Cairo',
        textTheme: const TextTheme(
          bodyMedium: TextStyle(fontFamily: 'Cairo'),
          titleLarge: TextStyle(fontFamily: 'Cairo', fontWeight: FontWeight.bold),
        ),
      ),
      builder: (context, child) => Directionality(
        textDirection: TextDirection.rtl,
        child: child!,
      ),
      home: const AuthGate(),
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

  // H02: Build items once
  static const List<BottomNavigationBarItem> _navItems = [
    BottomNavigationBarItem(icon: Icon(Icons.dashboard), label: 'لوحة القيادة'),
    BottomNavigationBarItem(icon: Icon(Icons.smart_toy), label: 'المستشار'),
    BottomNavigationBarItem(icon: Icon(Icons.satellite_alt), label: 'الأقمار'),
    BottomNavigationBarItem(icon: Icon(Icons.terrain), label: 'الحقول'),
    BottomNavigationBarItem(icon: Icon(Icons.person), label: 'الحساب'),
  ];

  // H02: Static screens list
  static const List<Widget> _screens = [
    DashboardScreen(),
    AdvisorScreen(),
    SatelliteScreen(),
    FieldsScreen(),
    ProfileScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    // H01: Handle Android back button
    return PopScope(
      canPop: _selectedIndex == 0,
      onPopInvoked: (didPop) {
        if (!didPop && _selectedIndex != 0) {
          setState(() => _selectedIndex = 0);
        }
      },
      child: Scaffold(
        body: IndexedStack(index: _selectedIndex, children: _screens),
        bottomNavigationBar: BottomNavigationBar(
          currentIndex: _selectedIndex,
          onTap: (i) => setState(() => _selectedIndex = i),
          type: BottomNavigationBarType.fixed,
          backgroundColor: const Color(0xFF1A1D29),
          selectedItemColor: const Color(0xFF10B981),
          unselectedItemColor: Colors.grey,
          items: _navItems,
        ),
      ),
    );
  }
}

// Placeholder screens
class LoginScreen extends StatelessWidget {
  const LoginScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(child: Text('تسجيل الدخول',
        style: TextStyle(color: Colors.white))));
}
class SatelliteScreen extends StatelessWidget {
  const SatelliteScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(child: Text('صور الأقمار الصناعية',
        style: TextStyle(color: Colors.white))));
}
class FieldsScreen extends StatelessWidget {
  const FieldsScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(child: Text('إدارة الحقول',
        style: TextStyle(color: Colors.white))));
}
class ProfileScreen extends StatelessWidget {
  const ProfileScreen({super.key});
  @override
  Widget build(BuildContext context) => const Scaffold(
    body: Center(child: Text('الحساب الشخصي',
        style: TextStyle(color: Colors.white))));
}
