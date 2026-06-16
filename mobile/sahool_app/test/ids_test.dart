// اختبارات توليد المعرّفات — تستورد الكود الفعليّ (lib/utils/ids.dart) لا نسخة
// مُعاد كتابتها، كي تكشف انحراف المنطق الحقيقيّ. تُشغَّل: flutter test
//
// تغطّي: صحّة صيغة UUIDv7 (RFC 9562) لـgenerateRequestId، تفرّده تحت توليد
// مكثّف، وثبات صيغة generateOperationId (^op_<hex>_<6hex>$) لئلّا تنكسر الخلفيّة.

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/utils/ids.dart';

void main() {
  group('generateRequestId — UUIDv7 صالح', () {
    // 8-4-4-4-12 hex صغير، الإصدار 7، الـvariant ∈ {8,9,a,b}.
    final uuidV7 = RegExp(
      r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    );

    test('يطابق صيغة UUIDv7 القانونيّة', () {
      expect(uuidV7.hasMatch(generateRequestId()), isTrue);
    });

    test('1000 توليد كلّها صالحة وفريدة (لا تصادم تحت التزامن)', () {
      final ids = <String>{};
      for (var i = 0; i < 1000; i++) {
        final id = generateRequestId();
        expect(uuidV7.hasMatch(id), isTrue, reason: 'صيغة غير صالحة: $id');
        ids.add(id);
      }
      expect(ids.length, equals(1000), reason: 'يجب أن تكون كلّ المعرّفات فريدة');
    });
  });

  group('generateOperationId — صيغة websocket الثابتة', () {
    final opRegex = RegExp(r'^op_[0-9a-f]+_[0-9a-f]{6}$');

    test('يطابق ^op_<hex>_<6hex>$', () {
      expect(opRegex.hasMatch(generateOperationId()), isTrue);
    });

    test('100 توليد كلّها بالصيغة المتوقّعة', () {
      for (var i = 0; i < 100; i++) {
        expect(opRegex.hasMatch(generateOperationId()), isTrue);
      }
    });
  });
}
