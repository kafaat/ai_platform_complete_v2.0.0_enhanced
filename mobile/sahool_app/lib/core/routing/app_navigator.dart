// SAHOOL — lib/core/routing/app_navigator.dart
// مفتاح الملّاح العامّ وأدوات الانتقال. المفتاح يسمح لطبقات بلا BuildContext
// (انتهاء الجلسة من ApiClient) بإعادة المستخدم إلى الجذر.
import 'package:flutter/widgets.dart';

final GlobalKey<NavigatorState> appNavigatorKey =
    GlobalKey<NavigatorState>(debugLabel: 'sahool-root');

extension AppNavigation on BuildContext {
  /// يفتح مساراً بمساره القانونيّ (أو رابط عميق بمعاملات استعلام).
  Future<T?> openRoute<T extends Object?>(String path, {Object? arguments}) =>
      Navigator.of(this).pushNamed<T>(path, arguments: arguments);

  /// يعيد إلى أوّل شاشة (غلاف التطبيق/الدخول) مُغلقاً كلّ المكدّس.
  void popToRoot() => Navigator.of(this).popUntil((r) => r.isFirst);
}

/// نفس [AppNavigation.popToRoot] بلا سياق.
void popToRootGlobally() =>
    appNavigatorKey.currentState?.popUntil((r) => r.isFirst);
