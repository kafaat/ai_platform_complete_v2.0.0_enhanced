// SAHOOL — lib/theme/app_theme.dart
// سمة «تطبيق الحقل» على طراز FieldView (تربة/ذهب/أخضر دافئ على خلفيّة كريميّة).
// القيم منقولة من رموز التصميم في الويب: frontend/src/components/ds/tokens.ts
// (brown #2C1A0E · gold #E8A020 · green #3EB050 · cream #FBF7F0). الهدف لمسة
// خفيفة على ThemeData (ألوان/أسطح/أزرار) دون إعادة كتابة الشاشات؛ الشاشات التي
// تثبّت ألوانها صراحةً (kBg/kSurface في state_views) تبقى كما هي حتّى تُكسى لاحقاً.
import 'package:flutter/material.dart';

/// لوحة ألوان FieldView (مصدر واحد للحقيقة، يطابق tokens.ts في الويب).
abstract final class SahoolPalette {
  static const brown = Color(0xFF2C1A0E); // تربة عميقة — نصّ/عناوين
  static const gold = Color(0xFFE8A020); // ذهبيّ — إجراء/تمييز (CTA)
  static const green = Color(0xFF3EB050); // أخضر المحصول السليم — نجاح
  static const greenDark = Color(0xFF2E7D32);
  static const cream = Color(0xFFFBF7F0); // خلفيّة الصفحة (فاتح دافئ)
  static const card = Color(0xFFFFFFFF); // سطح البطاقة
  static const card2 = Color(0xFFF7F2EA); // سطح ثانويّ
  static const line = Color(0xFFE8DFD2); // خطّ فاصل شعريّ
  static const muted = Color(0xFF8A7B6B); // نصّ ثانويّ
  static const danger = Color(0xFFC0392B);
}

abstract final class AppTheme {
  /// السمة الفاتحة على طراز FieldView. تُطبَّق على عناصر Material غير المُثبَّتة
  /// اللون (الأزرار، AppBar، حقول الإدخال، شريط التنقّل) — تشمل واجهة الدخول/MFA.
  static ThemeData get light {
    const scheme = ColorScheme.light(
      primary: SahoolPalette.green,
      onPrimary: Colors.white,
      secondary: SahoolPalette.gold,
      onSecondary: SahoolPalette.brown,
      surface: SahoolPalette.card,
      onSurface: SahoolPalette.brown,
      error: SahoolPalette.danger,
      onError: Colors.white,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: SahoolPalette.cream,
      fontFamily: 'Cairo',
      textTheme: const TextTheme(
        bodyMedium: TextStyle(fontFamily: 'Cairo', color: SahoolPalette.brown),
        titleLarge: TextStyle(
            fontFamily: 'Cairo',
            fontWeight: FontWeight.bold,
            color: SahoolPalette.brown),
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: SahoolPalette.card,
        foregroundColor: SahoolPalette.brown,
        elevation: 0,
        surfaceTintColor: Colors.transparent,
      ),
      cardColor: SahoolPalette.card,
      dividerColor: SahoolPalette.line,
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: SahoolPalette.green,
          foregroundColor: Colors.white,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12)),
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: SahoolPalette.card,
        selectedItemColor: SahoolPalette.green,
        unselectedItemColor: SahoolPalette.muted,
        type: BottomNavigationBarType.fixed,
      ),
    );
  }
}
