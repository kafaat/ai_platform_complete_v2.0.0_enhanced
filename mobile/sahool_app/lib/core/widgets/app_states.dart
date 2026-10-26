// SAHOOL — lib/core/widgets/app_states.dart
// حالات العرض المتّسقة مع السمة: تحميل / خطأ / فارغ / غير مقيس. تحمل دلالات
// state_views نفسها (الرسالة من apiErrorMessage: 503 ⇒ الخدمة معطّلة، 401 ⇒
// انتهت الجلسة، 403 ⇒ لا صلاحيّة، 404 ⇒ غير موجود) وتضيف أيقونة تميّز نوع
// الفشل (انقطاع ≠ صلاحيّة ≠ خادم) كي لا يُقرأ كلّ خطأ «خطأ غير متوقّع».
// لا بيانات بديلة أبداً: الحالة تُعرَض كما هي.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import 'primary_button.dart';

class LoadingState extends StatelessWidget {
  const LoadingState({super.key, this.message});
  final String? message;

  @override
  Widget build(BuildContext context) => Center(
        child: Semantics(
          label: message ?? 'جارٍ التحميل',
          liveRegion: true,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const CircularProgressIndicator(),
              if (message != null) ...[
                const SizedBox(height: SahoolSpacing.md),
                Text(message!, style: context.textStyles.bodyMedium),
              ],
            ],
          ),
        ),
      );
}

class ErrorState extends StatelessWidget {
  /// [error] أيّ خطأ (ApiException/DioException/FormatException/…) — يُصنَّف هنا.
  const ErrorState({super.key, required this.error, this.onRetry, this.title});

  final Object error;
  final VoidCallback? onRetry;
  final String? title;

  static IconData iconFor(ApiException e) {
    switch (e.kind) {
      case ApiErrorKind.network:
      case ApiErrorKind.timeout:
        return Icons.wifi_off_rounded;
      case ApiErrorKind.unauthorized:
      case ApiErrorKind.forbidden:
        return Icons.lock_outline_rounded;
      case ApiErrorKind.notFound:
        return Icons.search_off_rounded;
      case ApiErrorKind.unavailable:
      case ApiErrorKind.server:
        return Icons.cloud_off_rounded;
      default:
        return Icons.error_outline_rounded;
    }
  }

  @override
  Widget build(BuildContext context) {
    final e = ApiException.from(error);
    final t = context.tokens;
    final retryable = onRetry != null &&
        e.kind != ApiErrorKind.forbidden &&
        e.kind != ApiErrorKind.notFound;
    return _StateFrame(
      icon: iconFor(e),
      iconColor: e.isConnectivity ? t.warning : t.danger,
      title: title,
      message: e.messageAr,
      action: retryable
          ? PrimaryButton(
              label: 'إعادة المحاولة',
              icon: Icons.refresh_rounded,
              onPressed: onRetry,
              expand: false,
            )
          : null,
    );
  }
}

class EmptyState extends StatelessWidget {
  const EmptyState({
    super.key,
    required this.message,
    this.title,
    this.icon = Icons.inbox_outlined,
    this.actionLabel,
    this.onAction,
  });

  final String message;
  final String? title;
  final IconData icon;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) => _StateFrame(
        icon: icon,
        iconColor: context.tokens.muted,
        title: title,
        message: message,
        action: (actionLabel != null && onAction != null)
            ? PrimaryButton(
                label: actionLabel!, onPressed: onAction, expand: false)
            : null,
      );
}

class _StateFrame extends StatelessWidget {
  const _StateFrame({
    required this.icon,
    required this.iconColor,
    required this.message,
    this.title,
    this.action,
  });

  final IconData icon;
  final Color iconColor;
  final String? title;
  final String message;
  final Widget? action;

  @override
  Widget build(BuildContext context) => Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(SahoolSpacing.xl),
          child: Semantics(
            liveRegion: true,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(icon, size: 48, color: iconColor),
                const SizedBox(height: SahoolSpacing.md),
                if (title != null) ...[
                  Text(title!,
                      textAlign: TextAlign.center,
                      style: context.textStyles.titleLarge),
                  const SizedBox(height: SahoolSpacing.sm),
                ],
                Text(message,
                    textAlign: TextAlign.center,
                    style: context.textStyles.bodyLarge
                        ?.copyWith(color: context.tokens.muted)),
                if (action != null) ...[
                  const SizedBox(height: SahoolSpacing.xl),
                  action!,
                ],
              ],
            ),
          ),
        ),
      );
}
