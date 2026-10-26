// SAHOOL — lib/core/widgets/app_scaffold.dart
// هيكل الشاشة القياسيّ: AppBar بعنوان وإجراءات، جسم بحشوة الصفحة، سحب للتحديث
// اختياريّ، وزرّ عائم بوسم Hero فريد (كانت الأزرار العائمة بلا وسم في شاشات
// التبويبات المتزامنة تُطلق «multiple heroes share the same tag» عند كلّ انتقال).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/tokens.dart';

class AppScaffold extends StatelessWidget {
  const AppScaffold({
    super.key,
    required this.title,
    required this.body,
    this.actions,
    this.floatingActionButton,
    this.onRefresh,
    this.padded = false,
    this.bottom,
    this.showBack,
  });

  final String title;
  final Widget body;
  final List<Widget>? actions;
  final Widget? floatingActionButton;

  /// إن مُرّر: سحب للتحديث (يجب أن يكون الجسم قابلاً للتمرير).
  final Future<void> Function()? onRefresh;

  /// true ⇒ حشوة الصفحة القياسيّة حول الجسم.
  final bool padded;
  final PreferredSizeWidget? bottom;

  /// null ⇒ تلقائيّ (يظهر زرّ الرجوع إن أمكن الرجوع).
  final bool? showBack;

  @override
  Widget build(BuildContext context) {
    Widget content = padded
        ? Padding(
            padding: const EdgeInsetsDirectional.symmetric(
                horizontal: SahoolSpacing.page),
            child: body)
        : body;
    if (onRefresh != null) {
      content = RefreshIndicator(onRefresh: onRefresh!, child: content);
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        actions: actions,
        bottom: bottom,
        automaticallyImplyLeading: showBack ?? true,
      ),
      body: SafeArea(top: false, child: content),
      floatingActionButton: floatingActionButton,
    );
  }
}

/// زرّ عائم مُمتدّ بوسم Hero فريد مشتقّ من [heroKey] (اسم المسار عادةً).
class AppFab extends StatelessWidget {
  const AppFab({
    super.key,
    required this.heroKey,
    required this.label,
    required this.icon,
    required this.onPressed,
  });

  final String heroKey;
  final String label;
  final IconData icon;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => FloatingActionButton.extended(
        heroTag: 'fab:$heroKey',
        onPressed: onPressed,
        icon: Icon(icon),
        label: Text(label),
        tooltip: label,
      );
}
