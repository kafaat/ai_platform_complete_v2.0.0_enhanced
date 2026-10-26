import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/utils/formatters.dart';

void main() {
  group('parseLocalizedNum', () {
    test('accepts Arabic-Indic and Persian digits with the Arabic decimal mark',
        () {
      expect(parseLocalizedNum('٢٫٥'), 2.5);
      expect(parseLocalizedNum('۱۲'), 12);
      expect(parseLocalizedNum('1,250.5'), 1250.5);
      expect(parseLocalizedNum('١٬٢٥٠'), 1250);
      expect(parseLocalizedNum(' 7 '), 7);
    });

    test('empty or invalid input is null, never zero', () {
      expect(parseLocalizedNum(''), isNull);
      expect(parseLocalizedNum(null), isNull);
      expect(parseLocalizedNum('abc'), isNull);
      expect(parseLocalizedInt('٣٫٥'), isNull);
      expect(parseLocalizedInt('٤٢'), 42);
    });
  });

  test('LocalizedDigitsFormatter converts while typing; digitsOnly strips the rest',
      () {
    const f = LocalizedDigitsFormatter();
    expect(
        f.formatEditUpdate(TextEditingValue.empty,
                const TextEditingValue(text: '١٢٫٥'))
            .text,
        '12.5');
    const mfa = LocalizedDigitsFormatter(digitsOnly: true);
    expect(
        mfa.formatEditUpdate(TextEditingValue.empty,
                const TextEditingValue(text: '١٢٣ ٤٥٦'))
            .text,
        '123456');
  });

  group('display formatting', () {
    test('units use the canonical Arabic abbreviations', () {
      expect(fmtArea(1.5), '1.5 هـ');
      expect(fmtMm(12), '12 مم');
      expect(fmtTempC(31.4), '31 °م');
      expect(fmtYieldKgHa(4200), '4,200 كجم/هـ');
      expect(fmtPct(0.42, fraction: true), '42٪');
      expect(fmtYer(12000), '12,000 ر.ي');
    });

    test('missing values say "not measured" instead of null or zero', () {
      expect(fmtArea(null), kNotMeasured);
      expect(fmtPct(null), kNotMeasured);
      expect(fmtNumber(double.nan), kNotMeasured);
    });

    test('dates are local, Arabic month names, western digits', () {
      expect(fmtDate(DateTime(2026, 3, 5)), '5 مارس 2026');
      expect(fmtIsoDate('not-a-date'), 'not-a-date');
      expect(fmtDate(null), '—');
      final now = DateTime(2026, 1, 1, 12);
      expect(fmtAge(now.subtract(const Duration(minutes: 5)), now: now),
          'منذ 5 دقيقة');
    });
  });
}
