// SAHOOL — lib/core/theme/sahool_tokens.dart
// امتداد سمة يحمل رموز SAHOOL التي لا مكان لها في ColorScheme (نصّ ثانويّ،
// خطّ فاصل، ألوان الحالة). يُقرأ من أيّ ودجة: `context.tokens.muted`.
import 'package:flutter/material.dart';

import 'tokens.dart';

@immutable
class SahoolTokens extends ThemeExtension<SahoolTokens> {
  const SahoolTokens(this.colors);

  final SahoolColorSet colors;

  Color get background => colors.background;
  Color get surface => colors.surface;
  Color get surfaceAlt => colors.surfaceAlt;
  Color get line => colors.line;
  Color get ink => colors.ink;
  Color get muted => colors.muted;
  Color get faint => colors.faint;
  Color get success => colors.success;
  Color get warning => colors.warning;
  Color get danger => colors.danger;
  Color get info => colors.info;
  Color get accent => colors.accent;

  @override
  SahoolTokens copyWith({SahoolColorSet? colors}) =>
      SahoolTokens(colors ?? this.colors);

  // لا تدرّج بين مجموعتين (تبديل السمة فوريّ)؛ يكفي اختيار الأقرب.
  @override
  SahoolTokens lerp(ThemeExtension<SahoolTokens>? other, double t) =>
      (other is SahoolTokens && t >= 0.5) ? other : this;
}

extension SahoolThemeContext on BuildContext {
  /// رموز SAHOOL للسمة الحاليّة. تسقط إلى الداكنة إن لم تُركَّب السمة (اختبارات
  /// تضخّ MaterialApp عارياً).
  SahoolTokens get tokens =>
      Theme.of(this).extension<SahoolTokens>() ??
      const SahoolTokens(SahoolColors.dark);

  ColorScheme get colors => Theme.of(this).colorScheme;
  TextTheme get textStyles => Theme.of(this).textTheme;
}
