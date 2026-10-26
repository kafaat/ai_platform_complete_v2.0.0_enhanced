import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/theme/app_theme.dart';

/// MaterialApp بالسمة الفاتحة والعربيّة (بلا المندوبين ينهار كلّ TextField).
Widget authTestApp(Widget home) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: home,
);
