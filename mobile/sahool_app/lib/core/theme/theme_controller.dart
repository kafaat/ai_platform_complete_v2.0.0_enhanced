// SAHOOL — lib/core/theme/theme_controller.dart
// وضع السمة (فاتح/داكن/النظام) قابلاً للتبديل والحفظ في صندوق Hive 'settings'.
//
// الافتراضيّ فاتح: أقرأ تحت الشمس. كانت داكنة مؤقّتاً حين ثبّتت الشاشات المنقولة
// خلفيّات داكنة ونصّاً أبيض؛ بعد موجة 2 تقرأ الشاشات Theme.of(context)/
// context.tokens. المستخدم يغيّرها من شاشة الحساب، ويُحفَظ اختياره.
import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';

class ThemeController extends ValueNotifier<ThemeMode> {
  ThemeController([super.value = defaultMode]);

  static const ThemeMode defaultMode = ThemeMode.light;
  static const String _boxName = 'settings';
  static const String _key = 'theme_mode';

  static final ThemeController instance = ThemeController();

  /// يقرأ الوضع المحفوظ إن كان الصندوق مفتوحاً؛ أيّ تعذّر ⇒ الافتراضيّ.
  void load() {
    try {
      if (!Hive.isBoxOpen(_boxName)) return;
      final saved = Hive.box<dynamic>(_boxName).get(_key);
      value = ThemeMode.values.firstWhere((m) => m.name == saved,
          orElse: () => defaultMode);
    } catch (_) {
      value = defaultMode;
    }
  }

  Future<void> setMode(ThemeMode mode) async {
    value = mode;
    try {
      if (Hive.isBoxOpen(_boxName)) {
        await Hive.box<dynamic>(_boxName).put(_key, mode.name);
      }
    } catch (_) {
      // الحفظ تحسين لا شرط: الوضع مطبَّق في الجلسة الحاليّة.
    }
  }
}
