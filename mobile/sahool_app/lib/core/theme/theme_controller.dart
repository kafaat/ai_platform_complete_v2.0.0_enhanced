// SAHOOL — lib/core/theme/theme_controller.dart
// وضع السمة (فاتح/داكن/النظام) قابلاً للتبديل والحفظ في صندوق Hive 'settings'.
//
// الافتراضيّ اليوم داكن، عن قصد ومؤقّتاً: معظم الشاشات المنقولة ما زالت تثبّت
// خلفيّات داكنة ونصّاً أبيض (kBg/kSurface في state_views)، فتحت سمة فاتحة تصير
// حقول الإدخال نصّاً أبيض على تعبئة فاتحة لا يُقرأ. حين تنتقل الشاشات إلى
// Theme.of(context)/context.tokens (موجة 2) يُبدَّل [defaultMode] إلى light — وهو
// المطلوب للقراءة تحت الشمس. التبديل اليدويّ متاح من الآن (شاشة الحساب).
import 'package:flutter/material.dart';
import 'package:hive_flutter/hive_flutter.dart';

class ThemeController extends ValueNotifier<ThemeMode> {
  ThemeController([super.value = defaultMode]);

  static const ThemeMode defaultMode = ThemeMode.dark;
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
