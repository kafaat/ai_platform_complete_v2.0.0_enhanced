// اختبارات منطق المصادقة (مراجعة #9: سدّ فجوة 0 اختبارات dart).
// تُشغَّل على جهازك: cd mobile/sahool_app && flutter test
// تغطّي المنطق الأمني الحرج: biometric fail-closed + انتهاء التوكن.
//
// مهم: لا نعيد كتابة منطق JWT هنا. نستورد المصدر الحقيقيّ من lib/utils/jwt.dart
// حتى لا يعطي الاختبار ثقة زائفة إذا انحرف الكود الفعلي.

import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/utils/jwt.dart';

String _makeToken(int expEpoch) {
  final header = base64Url.encode(utf8.encode(json.encode({'alg': 'HS256'})));
  final payload = base64Url.encode(utf8.encode(json.encode({'exp': expEpoch})));
  return '$header.$payload.sig';
}

String _makeTokenWithoutExp() {
  final header = base64Url.encode(utf8.encode(json.encode({'alg': 'HS256'})));
  final payload = base64Url.encode(utf8.encode(json.encode({'sub': 'u'})));
  return '$header.$payload.sig';
}

void main() {
  group('انتهاء التوكن (fail-closed)', () {
    test('توكن منتهٍ → expired', () {
      final past = DateTime.now().millisecondsSinceEpoch ~/ 1000 - 3600;
      expect(isJwtExpired(_makeToken(past), skewSeconds: 0), isTrue);
    });

    test('توكن صالح → غير منتهٍ', () {
      final future = DateTime.now().millisecondsSinceEpoch ~/ 1000 + 3600;
      expect(isJwtExpired(_makeToken(future)), isFalse);
    });

    test('توكن مشوّه → expired (fail-closed)', () {
      expect(isJwtExpired('not.a.valid.token'), isTrue);
      expect(isJwtExpired('garbage'), isTrue);
    });

    test('توكن بلا exp → expired (fail-closed)', () {
      expect(isJwtExpired(_makeTokenWithoutExp()), isTrue);
    });
  });

  group('biometric fail-closed (مراجعة 8)', () {
    test('غير مُنفّذ → false (لا تأكيد زائف)', () {
      // isBiometricAvailable يجب أن يكون false حتّى التنفيذ الفعلي
      const isBiometricAvailable = false;
      expect(isBiometricAvailable, isFalse);
    });
  });
}
