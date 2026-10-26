// SAHOOL — lib/core/routing/app_shell.dart
// غلاف التطبيق بعد الدخول: شريط تنقّل سفليّ (NavigationBar، M3) بوجهات حسب
// الدور، وتبويبات تُبنى من مسارات الميزات.
//
//   • كسول: لا يُبنى التبويب إلّا عند أوّل زيارة ثمّ يبقى حيّاً — كانت التبويبات
//     الخمسة تُبنى عند الإقلاع فتُطلق أربعة طلبات لوحة متوازية على شبكة ضعيفة.
//   • HeroMode معطّل للتبويبات غير الظاهرة — كانت أزرار عائمة بلا وسم في تبويبين
//     تُطلق «multiple heroes share the same tag» عند كلّ انتقال.
//   • الرجوع (أندرويد) يعود إلى التبويب الافتتاحيّ قبل الخروج.
//   • عند العودة إلى المقدّمة أو عودة الشبكة يُستأنف WebSocket.
//   • بوّابة الترحيب: مستخدم بلا حقول يرى شاشة الترحيب (fail-open: تعذّر الجلب
//     لا يفرضها).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/routing/shell_destinations.dart';
import 'package:sahool_app/core/routing/shell_scope.dart';
import 'package:sahool_app/features/auth/presentation/onboarding_screen.dart';
import 'package:sahool_app/features/dashboard/data/dashboard_api.dart';
import 'package:sahool_app/services/websocket_service.dart';

class AppShell extends StatefulWidget {
  const AppShell({
    super.key,
    this.router,
    this.role,
    this.zeroFieldsCheck,
    this.connectivity,
    this.onResume,
  });

  /// للاختبارات؛ الافتراضيّ AppRouter.instance.
  final AppRouter? router;

  /// للاختبارات؛ الافتراضيّ دور الجلسة.
  final AppRole? role;

  /// يُرجع true إن كان المستخدم بلا حقول. الافتراضيّ يقرأ لوحة المعلومات.
  /// null-returning ⇒ لا بوّابة.
  final Future<bool> Function()? zeroFieldsCheck;
  final ConnectivityStatus? connectivity;

  /// يُستدعى عند العودة إلى المقدّمة/عودة الشبكة (افتراضيّاً: استئناف WS).
  final Future<void> Function()? onResume;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> with WidgetsBindingObserver {
  late final AppRouter _router = widget.router ?? AppRouter.instance;
  late final AppRole _role = widget.role ?? normalizeRole(currentRole());
  late final List<ShellDestination> _destinations = destinationsFor(_role);
  late final int _initialIndex = _indexOf(initialDestinationFor(_role)) ?? 0;
  late int _index = _initialIndex;
  final Set<int> _visited = {};

  /// ودجة كلّ تبويب تُنشأ مرّة وتُعاد كما هي، فلا يُعاد استدعاء بانيها عند
  /// تبديل التبويب (ولا يُعاد طلب بياناته).
  final Map<int, Widget> _pages = {};
  bool _zeroFields = false;
  ConnectivityStatus get _connectivity =>
      widget.connectivity ?? ConnectivityStatus.instance;

  int? _indexOf(String id) {
    final i = _destinations.indexWhere((d) => d.id == id);
    return i < 0 ? null : i;
  }

  @override
  void initState() {
    super.initState();
    _visited.add(_index);
    WidgetsBinding.instance.addObserver(this);
    _connectivity.addListener(_onConnectivity);
    unawaited(_checkZeroFields());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _connectivity.removeListener(_onConnectivity);
    super.dispose();
  }

  Future<void> _resume() =>
      (widget.onResume ?? WebSocketService.instance.ensureConnected)();

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_resume());
  }

  void _onConnectivity() {
    if (_connectivity.isOnline) unawaited(_resume());
  }

  Future<void> _checkZeroFields() async {
    try {
      final check = widget.zeroFieldsCheck ?? _defaultZeroFieldsCheck;
      final zero = await check();
      if (mounted && zero) setState(() => _zeroFields = true);
    } catch (_) {
      // fail-open: لا نفرض الترحيب عند تعذّر الجلب.
    }
  }

  static Future<bool> _defaultZeroFieldsCheck() async {
    final data = await DashboardApi.instance.getDashboard();
    final count = data['fields_count'];
    if (count is num) return count == 0;
    final raw = data['fields'] ?? data['fields_summary'] ?? data['field_list'];
    if (raw is List) return raw.isEmpty;
    return false; // غموض ⇒ ليس صفراً
  }

  bool _select(String id) {
    final i = _indexOf(id);
    if (i == null) return false;
    setState(() {
      _zeroFields = false;
      _index = i;
      _visited.add(i);
    });
    return true;
  }

  @override
  Widget build(BuildContext context) {
    if (_zeroFields) {
      return OnboardingScreen(onStart: () {
        setState(() => _zeroFields = false);
        if (!_select('fields')) context.openRoute<void>('/fields');
      });
    }

    final current = _destinations[_index];
    return ShellScope(
      currentId: current.id,
      select: _select,
      child: PopScope(
        canPop: _index == _initialIndex,
        onPopInvokedWithResult: (didPop, _) {
          if (!didPop && _index != _initialIndex) {
            setState(() => _index = _initialIndex);
          }
        },
        child: Scaffold(
          body: IndexedStack(
            index: _index,
            children: [
              for (var i = 0; i < _destinations.length; i++)
                HeroMode(
                  enabled: i == _index,
                  child: _visited.contains(i)
                      ? _pages.putIfAbsent(
                          i,
                          () => KeyedSubtree(
                            key: ValueKey('tab:${_destinations[i].id}'),
                            child: Builder(
                              builder: (ctx) => _router.buildPage(
                                  ctx, _destinations[i].routePath),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
            ],
          ),
          bottomNavigationBar: NavigationBar(
            selectedIndex: _index,
            onDestinationSelected: (i) => _select(_destinations[i].id),
            destinations: [
              for (final d in _destinations)
                NavigationDestination(
                  icon: Icon(d.icon),
                  selectedIcon: Icon(d.selectedIcon),
                  label: d.labelAr,
                  tooltip: d.labelAr,
                ),
            ],
          ),
        ),
      ),
    );
  }
}
