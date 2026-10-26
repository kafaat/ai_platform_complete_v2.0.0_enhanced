// تباين الرموز (WCAG): النصّ الأساسيّ والثانويّ على الخلفيّة والسطح، ونصّ الأزرار
// على ألوانها، ≥ 4.5:1 في السمتين — شرط القراءة تحت الشمس.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/state_views.dart';

double contrast(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final hi = la > lb ? la : lb;
  final lo = la > lb ? lb : la;
  return (hi + 0.05) / (lo + 0.05);
}

void main() {
  for (final entry in {
    'light': SahoolColors.light,
    'dark': SahoolColors.dark,
  }.entries) {
    final c = entry.value;
    test('${entry.key}: text and action pairs meet AA (4.5:1)', () {
      final pairs = <String, (Color, Color)>{
        'ink/background': (c.ink, c.background),
        'ink/surface': (c.ink, c.surface),
        'muted/background': (c.muted, c.background),
        'muted/surface': (c.muted, c.surface),
        'muted/surfaceAlt': (c.muted, c.surfaceAlt),
        'onPrimary/primary': (c.onPrimary, c.primary),
        'onAccent/accent': (c.onAccent, c.accent),
        'onDanger/danger': (c.onDanger, c.danger),
        'danger/surface': (c.danger, c.surface),
        'warning/surface': (c.warning, c.surface),
        'info/surface': (c.info, c.surface),
        'success/surface': (c.success, c.surface),
      };
      for (final p in pairs.entries) {
        expect(contrast(p.value.$1, p.value.$2), greaterThanOrEqualTo(4.5),
            reason: '${entry.key} ${p.key}');
      }
    });
  }

  test('themes carry the token extension and Material 3', () {
    for (final theme in [AppTheme.light, AppTheme.dark]) {
      expect(theme.useMaterial3, isTrue);
      expect(theme.extension<SahoolTokens>(), isNotNull);
      expect(theme.materialTapTargetSize, MaterialTapTargetSize.padded);
    }
    expect(AppTheme.light.colorScheme.primary, SahoolColors.light.primary);
    expect(AppTheme.dark.scaffoldBackgroundColor, SahoolColors.dark.background);
  });

  test('legacy screen constants are aliases of the dark tokens', () {
    expect(kBg, SahoolColors.dark.background);
    expect(kSurface, SahoolColors.dark.surface);
    expect(kPrimary, SahoolColors.dark.primary);
  });

  test('ndviColor follows the ramp and never invents health for null', () {
    expect(ndviColor(null), isNot(isIn(SahoolColors.ndviRamp)));
    expect(ndviColor(0.0), SahoolColors.ndviRamp.first);
    expect(ndviColor(0.9), SahoolColors.ndviRamp.last);
    expect(ndviColor(0.5), SahoolColors.ndviRamp[4]);
  });
}
