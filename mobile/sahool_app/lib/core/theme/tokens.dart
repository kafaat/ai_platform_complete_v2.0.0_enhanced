// SAHOOL — lib/core/theme/tokens.dart
// ملفّ الرموز الوحيد لنظام التصميم. كلّ لون/مسافة/نصف قطر/حجم خطّ في التطبيق
// يأتي من هنا (مباشرةً، أو عبر Theme.of(context) و[SahoolTokens]).
//
// المصدر: رموز الويب frontend/src/components/ds/tokens.ts (سمة «الحقل» الفاتحة
// وT_DARK)، كما جُدولت في تدقيق واجهة الموبايل. فرقان مقصودان عن الويب، كلاهما
// للتباين (WCAG AA ≥ 4.5:1 للنصّ، مُختبَر في test/core/theme_tokens_test.dart):
//   • الأخضر #3EB050 مع نصّ أبيض تباينه ≈2.6 — لا يصلح خلفيّةً لزرّ. الزرّ الأساسيّ
//     في الفاتح يستعمل الأخضر الداكن #2E7D32، ويبقى #3EB050 لوناً للحالة/التمييز.
//   • النصّ الثانويّ الفاتح #8A7B6B على الكريميّ تباينه دون AA؛ نستعمل #5C4A38.
import 'package:flutter/material.dart';

/// مجموعة ألوان سمة واحدة (فاتحة أو داكنة).
@immutable
class SahoolColorSet {
  const SahoolColorSet({
    required this.brightness,
    required this.background,
    required this.surface,
    required this.surfaceAlt,
    required this.line,
    required this.ink,
    required this.muted,
    required this.faint,
    required this.primary,
    required this.onPrimary,
    required this.accent,
    required this.onAccent,
    required this.danger,
    required this.onDanger,
    required this.info,
    required this.success,
    required this.warning,
  });

  final Brightness brightness;

  /// خلفيّة الصفحة.
  final Color background;

  /// سطح البطاقة/الورقة.
  final Color surface;

  /// سطح ثانويّ (حقول الإدخال، الرقائق).
  final Color surfaceAlt;

  /// خطّ فاصل شعريّ وحدود البطاقات.
  final Color line;

  /// النصّ الأساسيّ.
  final Color ink;

  /// النصّ الثانويّ (AA على الخلفيّة والسطح).
  final Color muted;

  /// نصّ ثالثيّ/معطّل — للزخرفة فقط، لا لمعلومة يحتاجها المستخدم.
  final Color faint;

  /// الإجراء الأساسيّ (أزرار مملوءة، العنصر المحدّد).
  final Color primary;
  final Color onPrimary;

  /// الإجراء المميَّز (ذهبيّ — CTA ثانويّ، تمييز).
  final Color accent;
  final Color onAccent;

  final Color danger;
  final Color onDanger;
  final Color info;
  final Color success;
  final Color warning;
}

abstract final class SahoolColors {
  // ألوان العلامة (مشتركة بين السمتين).
  static const brandGreen = Color(0xFF3EB050);
  static const brandGreenDark = Color(0xFF2E7D32);
  static const brandGold = Color(0xFFE8A020);
  static const brandBrown = Color(0xFF2C1A0E);

  // قيم السمة الداكنة كثوابت مسمّاة (تُستعمل في ثوابت const القديمة kBg/kSurface).
  static const darkBackground = Color(0xFF0F1117);
  static const darkSurface = Color(0xFF1E293B);
  static const darkInfo = Color(0xFF2D9CDB);
  static const darkWarning = Color(0xFFF59E0B);

  /// السمة الفاتحة «الحقل» — الأوضح تحت الشمس.
  static const light = SahoolColorSet(
    brightness: Brightness.light,
    background: Color(0xFFFBF7F0),
    surface: Color(0xFFFFFFFF),
    surfaceAlt: Color(0xFFF7F2EA),
    line: Color(0xFFE8DFD2),
    ink: brandBrown,
    muted: Color(0xFF5C4A38),
    faint: Color(0xFFB8AB9A),
    primary: brandGreenDark,
    onPrimary: Color(0xFFFFFFFF),
    accent: brandGold,
    onAccent: brandBrown,
    danger: Color(0xFFC0392B),
    onDanger: Color(0xFFFFFFFF),
    info: Color(0xFF1F6FA3),
    success: brandGreenDark,
    warning: Color(0xFF8A5A00),
  );

  /// السمة الداكنة (T_DARK في الويب).
  static const dark = SahoolColorSet(
    brightness: Brightness.dark,
    background: darkBackground,
    surface: darkSurface,
    surfaceAlt: Color(0xFF0F172A),
    line: Color(0xFF334155),
    ink: Color(0xFFE2E8F0),
    muted: Color(0xFF94A3B8),
    faint: Color(0xFF64748B),
    primary: brandGreen,
    onPrimary: Color(0xFF0F1117),
    accent: brandGold,
    onAccent: brandBrown,
    danger: Color(0xFFF87171),
    onDanger: Color(0xFF0F1117),
    info: darkInfo,
    success: brandGreen,
    warning: darkWarning,
  );

  /// سلّم الحالة (STATUS_COLORS في الويب): ممتاز → حرج. لا تُستعمل وحدها:
  /// كلّ حالة تُعرَض مع نصّ/أيقونة (StatusChip) لا باللون فقط.
  static const statusExcellent = Color(0xFF16A34A);
  static const statusGood = Color(0xFF65A30D);
  static const statusFair = Color(0xFFCA8A04);
  static const statusPoor = Color(0xFFF97316);
  static const statusCritical = Color(0xFFDC2626);

  /// سلّم NDVI (ndvi1..6 في الويب)، من التربة العارية إلى الغطاء الكثيف.
  static const ndviRamp = <Color>[
    Color(0xFFC0392B),
    Color(0xFFE67E22),
    Color(0xFFF1C40F),
    Color(0xFFA3CB38),
    Color(0xFF3EB050),
    Color(0xFF16794A),
  ];
}

/// لون NDVI الموحّد (بديل الدوالّ الثلاث المتباينة في الشاشات). [ndvi] في
/// [-1, 1]؛ null ⇒ لون «غير مقيس» المحايد بدل اختلاق صحّة.
Color ndviColor(double? ndvi, {Color unknown = const Color(0xFF8A93A6)}) {
  if (ndvi == null || ndvi.isNaN) return unknown;
  const stops = [0.1, 0.2, 0.3, 0.45, 0.6];
  for (var i = 0; i < stops.length; i++) {
    if (ndvi < stops[i]) return SahoolColors.ndviRamp[i];
  }
  return SahoolColors.ndviRamp.last;
}

/// المسافات (SPACE في الويب). استعمل EdgeInsetsDirectional لا EdgeInsets.only
/// (left/right) كي يصحّ الاتّجاه في RTL.
abstract final class SahoolSpacing {
  static const double xxs = 2;
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;

  /// الحشوة الأفقيّة القياسيّة للصفحة.
  static const double page = lg;
}

/// أنصاف الأقطار (RADIUS في الويب).
abstract final class SahoolRadius {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double pill = 999;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
}

/// أحجام عامّة.
abstract final class SahoolSizes {
  /// أدنى هدف لمس (Material/WCAG): 48dp. المستخدم في الحقل قد يرتدي قفّازاً.
  static const double minTouchTarget = 48;

  /// ارتفاع الأزرار الأساسيّة — أكبر من الأدنى لسهولة الضغط في الخارج.
  static const double buttonHeight = 52;

  static const double iconSm = 18;
  static const double iconMd = 24;
  static const double iconLg = 32;
}

/// سلّم الخطّ العربيّ (12/14/16/20/28؛ أوزان 400/600/700). 12sp حدّ أدنى لأيّ
/// نصّ يحمل معلومة؛ متن 14–16 لقراءة خارجيّة. ارتفاع السطر 1.5 للعربيّة.
abstract final class SahoolType {
  /// null ⇒ خطّ النظام العربيّ (Noto Naskh/Sans Arabic على أندرويد، SF Arabic
  /// على iOS). لتضمين Cairo (رخصة OFL): ضع ملفّات .ttf تحت assets/fonts/،
  /// أعلِنها في pubspec.yaml، ثمّ عيّن 'Cairo' هنا. لم تُضمَّن الآن لأنّ الملفّات
  /// غير موجودة في المستودع، وإعلان خطّ غائب كان يوهم بخطّ لا يُعرَض.
  static const String? fontFamily = null;

  static const double caption = 12;
  static const double body = 14;
  static const double bodyLarge = 16;
  static const double title = 20;
  static const double headline = 28;
  static const double lineHeight = 1.5;

  static const FontWeight regular = FontWeight.w400;
  static const FontWeight semibold = FontWeight.w600;
  static const FontWeight bold = FontWeight.w700;
}

/// مُدد الحركة.
abstract final class SahoolMotion {
  static const Duration fast = Duration(milliseconds: 150);
  static const Duration normal = Duration(milliseconds: 250);
}
