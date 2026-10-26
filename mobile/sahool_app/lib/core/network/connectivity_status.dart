// SAHOOL — lib/core/network/connectivity_status.dart
// حالة الاتّصال للتطبيق كلّه (لافتة «غير متّصل»، استئناف WebSocket). مصدرها
// connectivity_plus: يقيس وجود واجهة شبكة لا وصولاً فعليّاً إلى الخادم، لذا
// تقول اللافتة «لا اتّصال بالشبكة» لا «الخادم معطّل».
import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

class ConnectivityStatus extends ValueNotifier<bool> {
  /// [changes] و[initial] قابلان للحقن في الاختبارات.
  ConnectivityStatus({
    Stream<List<ConnectivityResult>>? changes,
    Future<List<ConnectivityResult>> Function()? initial,
  })  : _changes = changes,
        _initial = initial,
        super(true);

  static final ConnectivityStatus instance = ConnectivityStatus();

  final Stream<List<ConnectivityResult>>? _changes;
  final Future<List<ConnectivityResult>> Function()? _initial;
  StreamSubscription<List<ConnectivityResult>>? _sub;

  bool get isOnline => value;

  static bool _online(List<ConnectivityResult> r) =>
      r.any((x) => x != ConnectivityResult.none);

  /// يبدأ الاستماع (مرّة واحدة). أيّ تعذّر في الإضافة ⇒ نفترض الاتّصال (لا
  /// لافتة كاذبة)، والطلبات نفسها تكشف الانقطاع.
  Future<void> start() async {
    if (_sub != null) return;
    try {
      final changes = _changes ?? Connectivity().onConnectivityChanged;
      _sub = changes.listen((r) => value = _online(r), onError: (_) {});
      final first = await (_initial ?? Connectivity().checkConnectivity)();
      value = _online(first);
    } catch (_) {
      value = true;
    }
  }

  @override
  void dispose() {
    _sub?.cancel();
    _sub = null;
    super.dispose();
  }
}
