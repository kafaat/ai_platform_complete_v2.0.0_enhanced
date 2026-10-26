// SAHOOL — lib/core/widgets/primary_button.dart
// أزرار الإجراء: ارتفاع 52dp (هدف لمس كبير للعمل الخارجيّ)، حالة «جارٍ» تمنع
// الضغط المزدوج (ومعه الكتابة المكرّرة)، وتسمية دلاليّة لقارئ الشاشة.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/tokens.dart';

enum ButtonTone { primary, accent, danger }

class PrimaryButton extends StatelessWidget {
  const PrimaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.loading = false,
    this.expand = true,
    this.tone = ButtonTone.primary,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;

  /// true ⇒ مؤشّر تقدّم ويُعطَّل الزرّ (لا إرسال ثانٍ أثناء الأوّل).
  final bool loading;

  /// true ⇒ يملأ العرض المتاح.
  final bool expand;
  final ButtonTone tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (bg, fg) = switch (tone) {
      ButtonTone.primary => (scheme.primary, scheme.onPrimary),
      ButtonTone.accent => (scheme.secondary, scheme.onSecondary),
      ButtonTone.danger => (scheme.error, scheme.onError),
    };
    final child = loading
        ? SizedBox(
            width: 22,
            height: 22,
            child: CircularProgressIndicator(strokeWidth: 2.4, color: fg),
          )
        : Text(label);
    final style = FilledButton.styleFrom(backgroundColor: bg, foregroundColor: fg);
    final button = icon != null && !loading
        ? FilledButton.icon(
            onPressed: onPressed, style: style, icon: Icon(icon), label: child)
        : FilledButton(
            onPressed: loading ? null : onPressed, style: style, child: child);
    return Semantics(
      button: true,
      label: loading ? '$label — جارٍ التنفيذ' : null,
      child: expand ? SizedBox(width: double.infinity, child: button) : button,
    );
  }
}

class SecondaryButton extends StatelessWidget {
  const SecondaryButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.icon,
    this.expand = true,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final button = icon != null
        ? OutlinedButton.icon(
            onPressed: onPressed, icon: Icon(icon), label: Text(label))
        : OutlinedButton(onPressed: onPressed, child: Text(label));
    return expand ? SizedBox(width: double.infinity, child: button) : button;
  }
}

/// زرّ أيقونة بتلميح إلزاميّ (قارئ الشاشة + الضغط المطوّل) وهدف 48dp.
class AppIconButton extends StatelessWidget {
  const AppIconButton({
    super.key,
    required this.icon,
    required this.tooltip,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) => IconButton(
        icon: Icon(icon),
        tooltip: tooltip,
        onPressed: onPressed,
        constraints: const BoxConstraints(
          minWidth: SahoolSizes.minTouchTarget,
          minHeight: SahoolSizes.minTouchTarget,
        ),
      );
}
