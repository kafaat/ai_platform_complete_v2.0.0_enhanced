/// حارس ساكن (GAP-FIELD-FORMS-01 §8.6/§15.3): يمسح شجرة lib/ كاملة
/// ويتأكّد من خلوّها من توكنات الخدمة ومفاتيح التوقيع الممنوعة في العميل.
///
/// مسموح فقط ذكرها في تعليق توثيقيّ عن المنع؛ ممنوع أيّ String حرفيّ
/// يمكن أن يُرسل كترويسة أو قيمة سرّية.
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('lib/ خالية من FIELD_FORMS_SERVICE_TOKEN وX-Field-Forms-Token وHMAC',
      () {
    final libDir = Directory('lib');
    expect(libDir.existsSync(), isTrue,
        reason: 'يُشغَّل من جذر mobile/sahool_app');

    final violations = <String>[];
    for (final entity in libDir.listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final lines = entity.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
        // نتجاهل التعليقات التوثيقيّة عن المنع (// أو ///).
        final code = line.replaceAll(RegExp(r'//.*$'), '');
        for (final forbidden in [
          'FIELD_FORMS_SERVICE_TOKEN',
          'X-Field-Forms-Token',
          'x-field-forms-token',
          'hmac',
          'HMAC',
          'Hmac',
        ]) {
          if (code.contains(forbidden)) {
            violations.add('${entity.path}:${i + 1}: $forbidden');
          }
        }
      }
    }
    expect(violations, isEmpty,
        reason: 'توكن خدمة/توقيع داخل كود العميل: $violations');
  });
}
