// SAHOOL — lib/core/routing/shell_scope.dart
// يسمح لشاشة داخل تبويب بطلب الانتقال إلى تبويب آخر (مثل «أنشئ أوّل حقل» في
// الرئيسية ⇒ تبويب الحقول) دون أن تعرف الغلاف.
import 'package:flutter/widgets.dart';

class ShellScope extends InheritedWidget {
  const ShellScope({
    super.key,
    required this.currentId,
    required this.select,
    required super.child,
  });

  /// معرّف التبويب الحاليّ (انظر shell_destinations.dart).
  final String currentId;

  /// ينتقل إلى التبويب [id] إن كان ظاهراً لهذا الدور؛ يُعيد false إن لم يكن.
  final bool Function(String id) select;

  static ShellScope? maybeOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<ShellScope>();

  @override
  bool updateShouldNotify(ShellScope old) => old.currentId != currentId;
}
