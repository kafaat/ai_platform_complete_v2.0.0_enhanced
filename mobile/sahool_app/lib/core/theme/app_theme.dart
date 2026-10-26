// SAHOOL — lib/core/theme/app_theme.dart
// سمتا Material 3 (فاتحة/داكنة) تُبنيان من ملفّ رموز واحد (tokens.dart). لا لون
// ولا مقاس مُثبَّت هنا خارج الرموز. المكوّنات تضمن هدف لمس ≥48dp وحقولاً
// وأزراراً مقروءة في ضوء الشمس.
import 'package:flutter/material.dart';

import 'sahool_tokens.dart';
import 'tokens.dart';

abstract final class AppTheme {
  /// السمة الفاتحة «الحقل» (الأوضح خارجيّاً).
  static ThemeData get light => build(SahoolColors.light);

  /// السمة الداكنة.
  static ThemeData get dark => build(SahoolColors.dark);

  static ThemeData build(SahoolColorSet c) {
    final scheme = ColorScheme(
      brightness: c.brightness,
      primary: c.primary,
      onPrimary: c.onPrimary,
      secondary: c.accent,
      onSecondary: c.onAccent,
      tertiary: c.info,
      onTertiary: c.brightness == Brightness.light
          ? Colors.white
          : c.background,
      error: c.danger,
      onError: c.onDanger,
      surface: c.surface,
      onSurface: c.ink,
      onSurfaceVariant: c.muted,
      surfaceContainerLowest: c.background,
      surfaceContainerLow: c.background,
      surfaceContainer: c.surface,
      surfaceContainerHigh: c.surfaceAlt,
      surfaceContainerHighest: c.surfaceAlt,
      outline: c.line,
      outlineVariant: c.line,
    );

    final text = _textTheme(c);
    const minTarget = Size(SahoolSizes.minTouchTarget, SahoolSizes.minTouchTarget);
    const buttonSize = Size(SahoolSizes.minTouchTarget, SahoolSizes.buttonHeight);
    final buttonShape =
        RoundedRectangleBorder(borderRadius: SahoolRadius.mdAll);
    const buttonText =
        TextStyle(fontSize: SahoolType.bodyLarge, fontWeight: SahoolType.semibold);
    OutlineInputBorder border(Color color, [double width = 1]) =>
        OutlineInputBorder(
          borderRadius: SahoolRadius.mdAll,
          borderSide: BorderSide(color: color, width: width),
        );

    return ThemeData(
      useMaterial3: true,
      brightness: c.brightness,
      colorScheme: scheme,
      fontFamily: SahoolType.fontFamily,
      textTheme: text,
      scaffoldBackgroundColor: c.background,
      canvasColor: c.background,
      dividerColor: c.line,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      visualDensity: VisualDensity.standard,
      extensions: [SahoolTokens(c)],
      appBarTheme: AppBarTheme(
        backgroundColor: c.surface,
        foregroundColor: c.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        centerTitle: false,
        titleTextStyle: text.titleLarge,
      ),
      cardTheme: CardThemeData(
        color: c.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: SahoolRadius.lgAll,
          side: BorderSide(color: c.line),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: buttonSize,
          shape: buttonShape,
          textStyle: buttonText,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: c.primary,
          foregroundColor: c.onPrimary,
          minimumSize: buttonSize,
          shape: buttonShape,
          textStyle: buttonText,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: c.primary,
          minimumSize: buttonSize,
          shape: buttonShape,
          side: BorderSide(color: c.line, width: 1.2),
          textStyle: buttonText,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: c.primary,
          minimumSize: minTarget,
          textStyle: buttonText,
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(minimumSize: minTarget),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: c.primary,
        foregroundColor: c.onPrimary,
        shape: RoundedRectangleBorder(borderRadius: SahoolRadius.lgAll),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: c.surfaceAlt,
        contentPadding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.lg, vertical: SahoolSpacing.md + 2),
        labelStyle: TextStyle(color: c.muted),
        hintStyle: TextStyle(color: c.muted),
        helperStyle: TextStyle(color: c.muted, fontSize: SahoolType.caption),
        border: border(c.line),
        enabledBorder: border(c.line),
        focusedBorder: border(c.primary, 2),
        errorBorder: border(c.danger),
        focusedErrorBorder: border(c.danger, 2),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: c.surfaceAlt,
        selectedColor: c.primary.withValues(alpha: 0.18),
        labelStyle: TextStyle(color: c.ink, fontSize: SahoolType.body),
        secondaryLabelStyle: TextStyle(color: c.ink),
        side: BorderSide(color: c.line),
        shape: const StadiumBorder(),
        padding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.sm, vertical: SahoolSpacing.xs),
      ),
      listTileTheme: ListTileThemeData(
        iconColor: c.muted,
        textColor: c.ink,
        minVerticalPadding: SahoolSpacing.md,
        minTileHeight: 56,
        contentPadding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.lg),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: c.surface,
        indicatorColor: c.primary.withValues(alpha: 0.18),
        surfaceTintColor: Colors.transparent,
        height: 68,
        labelTextStyle: WidgetStateProperty.resolveWith((states) => TextStyle(
              fontSize: SahoolType.caption,
              fontWeight: states.contains(WidgetState.selected)
                  ? SahoolType.bold
                  : SahoolType.semibold,
              color: states.contains(WidgetState.selected) ? c.ink : c.muted,
            )),
        iconTheme: WidgetStateProperty.resolveWith((states) => IconThemeData(
              color: states.contains(WidgetState.selected) ? c.primary : c.muted,
            )),
      ),
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        backgroundColor: c.surface,
        selectedItemColor: c.primary,
        unselectedItemColor: c.muted,
        type: BottomNavigationBarType.fixed,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
              top: Radius.circular(SahoolRadius.lg)),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: c.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: SahoolRadius.lgAll),
        titleTextStyle: text.titleLarge,
        contentTextStyle: text.bodyLarge,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: c.ink,
        contentTextStyle: TextStyle(
            color: c.background, fontSize: SahoolType.body),
        shape: RoundedRectangleBorder(borderRadius: SahoolRadius.mdAll),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(color: c.primary),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.selected) ? c.onPrimary : c.muted),
        trackColor: WidgetStateProperty.resolveWith((s) =>
            s.contains(WidgetState.selected) ? c.primary : c.surfaceAlt),
      ),
      tabBarTheme: TabBarThemeData(
        labelColor: c.primary,
        unselectedLabelColor: c.muted,
        indicatorColor: c.primary,
        dividerColor: c.line,
      ),
    );
  }

  static TextTheme _textTheme(SahoolColorSet c) {
    TextStyle s(double size, FontWeight weight, Color color) => TextStyle(
          fontFamily: SahoolType.fontFamily,
          fontSize: size,
          fontWeight: weight,
          height: SahoolType.lineHeight,
          color: color,
        );
    return TextTheme(
      headlineMedium: s(SahoolType.headline, SahoolType.bold, c.ink),
      headlineSmall: s(24, SahoolType.bold, c.ink),
      titleLarge: s(SahoolType.title, SahoolType.bold, c.ink),
      titleMedium: s(SahoolType.bodyLarge, SahoolType.semibold, c.ink),
      titleSmall: s(SahoolType.body, SahoolType.semibold, c.ink),
      bodyLarge: s(SahoolType.bodyLarge, SahoolType.regular, c.ink),
      bodyMedium: s(SahoolType.body, SahoolType.regular, c.ink),
      bodySmall: s(SahoolType.caption, SahoolType.regular, c.muted),
      labelLarge: s(SahoolType.body, SahoolType.semibold, c.ink),
      labelMedium: s(SahoolType.caption, SahoolType.semibold, c.muted),
      labelSmall: s(SahoolType.caption, SahoolType.regular, c.muted),
    );
  }
}
