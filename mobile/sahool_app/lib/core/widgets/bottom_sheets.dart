// SAHOOL — lib/core/widgets/bottom_sheets.dart
// ورقة سفليّة قياسيّة: مقبض سحب، عنوان، محتوى قابل للتمرير يرتفع فوق لوحة
// المفاتيح، وزرّ إجراء ثابت. رسائل التحقّق تُعرَض داخلها ([errorText]) لأنّ
// SnackBar من داخل الورقة يُرسَم تحتها فلا يُرى.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import 'primary_button.dart';

Future<T?> showAppBottomSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  bool isDismissible = true,
}) =>
    showModalBottomSheet<T>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      isDismissible: isDismissible,
      builder: builder,
    );

class AppSheet extends StatelessWidget {
  const AppSheet({
    super.key,
    required this.title,
    required this.children,
    this.submitLabel,
    this.onSubmit,
    this.submitting = false,
    this.errorText,
  });

  final String title;
  final List<Widget> children;
  final String? submitLabel;
  final VoidCallback? onSubmit;
  final bool submitting;

  /// خطأ الإرسال/التحقّق — يُعرَض داخل الورقة فوق الزرّ.
  final String? errorText;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Padding(
      padding: EdgeInsetsDirectional.only(
        start: SahoolSpacing.lg,
        end: SahoolSpacing.lg,
        bottom: MediaQuery.viewInsetsOf(context).bottom + SahoolSpacing.lg,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Semantics(
              header: true,
              child: Text(title, style: context.textStyles.titleLarge),
            ),
            ...children,
            if (errorText != null) ...[
              const SizedBox(height: SahoolSpacing.md),
              Semantics(
                liveRegion: true,
                child: Text(errorText!,
                    style: context.textStyles.bodyMedium
                        ?.copyWith(color: t.danger)),
              ),
            ],
            if (onSubmit != null) ...[
              const SizedBox(height: SahoolSpacing.lg),
              PrimaryButton(
                label: submitLabel ?? 'حفظ',
                onPressed: onSubmit,
                loading: submitting,
              ),
            ],
          ],
        ),
      ),
    );
  }
}
