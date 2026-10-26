// تحقّق المبلغ (أرقام عربيّة-هنديّة و«٫»)، تنسيق المبالغ، وترجمة رموز الخادم.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/farm_book/presentation/farm_book_text.dart';

void main() {
  group('amount input', () {
    test(
      'Arabic-Indic, Persian digits, ٫ and thousands separators normalise',
      () {
        expect(normalizeAmount('١٢٣٤٫٥'), '1234.5');
        expect(normalizeAmount('۲۵۰'), '250');
        expect(normalizeAmount('١٬٢٠٠٫٧٥'), '1200.75');
        expect(normalizeAmount(' 12,000 '), '12000');
      },
    );

    test('invalid amounts are rejected, never sent as 0', () {
      for (final bad in ['', '٠', '0.00', '-5', '1.234', 'abc', '1..2', '١٫']) {
        expect(normalizeAmount(bad), isNull, reason: bad);
        expect(validateAmount(bad), isNotNull, reason: bad);
      }
      expect(validateAmount('12345678901234567'), 'المبلغ أكبر من المسموح');
      expect(validateAmount('١٫٢٣٤'), 'المبلغ يقبل منزلتين عشريّتين كحدّ أقصى');
      expect(validateAmount('٠'), 'المبلغ يجب أن يكون أكبر من صفر');
      expect(validateAmount('٩٩٫٩٩'), isNull);
    });
  });

  test('money formatting uses the shared formatter and Arabic units', () {
    expect(fmtMoney(12500.5, 'YER'), '12,500.5 ر.ي');
    expect(fmtMoney(1000, 'usd'), '1,000 دولار');
    expect(fmtMoney(null, 'YER'), 'غير مقيس');
    expect(fmtMoney(-120, 'YER'), '\u200E-120 ر.ي');
  });

  test('server detail codes map to Arabic; status contracts are kept', () {
    expect(
      farmBookErrorMessage(
        const ApiException(
          kind: ApiErrorKind.conflict,
          statusCode: 409,
          messageAr: 'تعارض: السجلّ موجود مسبقاً.',
          detail: 'entry_already_reversed',
        ),
      ),
      'هذا القيد عُكس من قبل؛ لا يُعكس مرّتين.',
    );
    const db = ApiException(
      kind: ApiErrorKind.unavailable,
      statusCode: 503,
      messageAr: 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
      detail: 'حفظ القيد المالي المبسط غير متاح',
    );
    expect(farmBookErrorMessage(db), db.messageAr);
  });

  test('category labels fall back to the raw code, never blank', () {
    expect(categoryLabel('seed'), 'بذور');
    expect(categoryLabel('debt_payment'), 'سداد دين');
    expect(categoryLabel('custom_x'), 'custom_x');
  });
}
