// SAHOOL — features/alerts/presentation/alerts_badge.dart
// شارة التنبيهات غير المُقَرّة — ودجة عامّة تضمّنها ميزات أخرى (اللوحة، الغلاف):
//
//   import 'package:sahool_app/features/alerts/presentation/alerts_badge.dart';
//   AlertsBellButton()                       // زرّ جرس يفتح الصندوق
//   AlertsBadge(child: Icon(Icons.notifications_outlined))
//
// العدد من AlertsUnreadCounter (status=active على الخادم + القناة الحيّة).
// غير مقيس ⇒ لا رقم (لا «0» مُطمئِن كاذب).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import '../alerts_paths.dart';
import '../data/alerts_unread.dart';

class AlertsBadge extends StatefulWidget {
  const AlertsBadge({super.key, required this.child, this.counter});

  final Widget child;

  /// للاختبار؛ الافتراضيّ العدّاد المشترك.
  final AlertsUnreadCounter? counter;

  @override
  State<AlertsBadge> createState() => _AlertsBadgeState();
}

class _AlertsBadgeState extends State<AlertsBadge> {
  AlertsUnreadCounter get _counter =>
      widget.counter ?? AlertsUnreadCounter.instance;

  @override
  void initState() {
    super.initState();
    _counter.ensureStarted();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _counter,
    builder: (context, _) {
      final text = _counter.badgeText;
      final scheme = Theme.of(context).colorScheme;
      return Semantics(
        label: text == null ? 'التنبيهات' : 'التنبيهات: $text غير مُقَرّ',
        child: Badge(
          isLabelVisible: text != null,
          backgroundColor: scheme.error,
          textColor: scheme.onError,
          label: text == null ? null : Text(text),
          child: widget.child,
        ),
      );
    },
  );
}

/// زرّ جرس بشارة يفتح صندوق التنبيهات (هدف لمس 48dp).
class AlertsBellButton extends StatelessWidget {
  const AlertsBellButton({super.key, this.counter});
  final AlertsUnreadCounter? counter;

  @override
  Widget build(BuildContext context) => IconButton(
    tooltip: 'التنبيهات',
    constraints: const BoxConstraints(
      minWidth: SahoolSizes.minTouchTarget,
      minHeight: SahoolSizes.minTouchTarget,
    ),
    onPressed: () => context.openRoute<void>(AlertsPaths.inbox),
    icon: AlertsBadge(
      counter: counter,
      child: const Icon(Icons.notifications_outlined),
    ),
  );
}
