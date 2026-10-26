// SAHOOL — features/auth/presentation/widgets/otp_code_field.dart
// حقل رمز المصادقة الثنائيّة (TOTP، 6 أرقام). لوحة المفاتيح العربيّة تكتب ٠-٩
// افتراضيّاً، وكان FilteringTextInputFormatter.digitsOnly يحذفها فيبقى الحقل
// فارغاً. هنا تُحوَّل إلى 0-9 أثناء الكتابة ويُحذف ما عداها.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

/// طول رمز TOTP المعتمد خادميّاً.
const int kOtpLength = 6;

/// الرمز بأرقام غربيّة فقط، أو null إن لم يكن 6 أرقام.
String? normalizeOtp(String raw) {
  final digits = normalizeDigits(raw).replaceAll(RegExp(r'[^0-9]'), '');
  return digits.length == kOtpLength ? digits : null;
}

class OtpCodeField extends StatelessWidget {
  const OtpCodeField({
    super.key,
    required this.controller,
    this.onSubmitted,
    this.autofocus = false,
    this.enabled = true,
    this.label = 'رمز التحقّق (6 أرقام)',
  });

  final TextEditingController controller;
  final VoidCallback? onSubmitted;
  final bool autofocus;
  final bool enabled;
  final String label;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      autofocus: autofocus,
      enabled: enabled,
      keyboardType: TextInputType.number,
      textInputAction: TextInputAction.done,
      autofillHints: const [AutofillHints.oneTimeCode],
      maxLength: kOtpLength,
      textAlign: TextAlign.center,
      textDirection: TextDirection.ltr,
      inputFormatters: const [LocalizedDigitsFormatter(digitsOnly: true)],
      style: context.textStyles.headlineSmall?.copyWith(
        letterSpacing: SahoolSpacing.sm,
        fontWeight: SahoolType.bold,
      ),
      onSubmitted: onSubmitted == null ? null : (_) => onSubmitted!(),
      decoration: InputDecoration(
        labelText: label,
        counterText: '',
        hintText: '••••••',
        prefixIcon: Icon(Icons.shield_outlined, color: context.tokens.muted),
      ),
    );
  }
}
