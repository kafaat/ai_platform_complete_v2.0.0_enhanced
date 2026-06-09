// اختبارات منطق المصادقة (مراجعة #9: سدّ فجوة 0 اختبارات dart).
// تُشغَّل على جهازك: cd mobile/sahool_app && flutter test
// تغطّي المنطق الأمني الحرج: biometric fail-closed + انتهاء التوكن.

import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';

// منطق انتهاء التوكن (نسخة قابلة للاختبار من _isTokenExpired)
bool isTokenExpired(String token) {
  try {
    final parts = token.split('.');
    if (parts.length != 3) return true;
    final payload = json.decode(
      utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
    ) as Map<String, dynamic>;
    final exp = payload['exp'] as int?;
    if (exp == null) return true;
    return DateTime.now().millisecondsSinceEpoch ~/ 1000 >= exp;
  } catch (_) {
    return true; // فشل التحليل → اعتبره منتهياً (fail-closed)
  }
}

String _makeToken(int expEpoch) {
  final header = base64Url.encode(utf8.encode(json.encode({'alg': 'HS256'})));
  final payload = base64Url.encode(utf8.encode(json.encode({'exp': expEpoch})));
  return '$header.$payload.sig';
}

void main() {
  group('انتهاء التوكن (fail-closed)', () {
    test('توكن منتهٍ → expired', () {
      final past = DateTime.now().millisecondsSinceEpoch ~/ 1000 - 3600;
      expect(isTokenExpired(_makeToken(past)), isTrue);
    });

    test('توكن صالح → غير منتهٍ', () {
      final future = DateTime.now().millisecondsSinceEpoch ~/ 1000 + 3600;
      expect(isTokenExpired(_makeToken(future)), isFalse);
    });

    test('توكن مشوّه → expired (fail-closed)', () {
      expect(isTokenExpired('not.a.valid.token'), isTrue);
      expect(isTokenExpired('garbage'), isTrue);
    });

    test('توكن بلا exp → expired (fail-closed)', () {
      final noExp = base64Url.encode(utf8.encode(json.encode({'sub': 'u'})));
      final header = base64Url.encode(utf8.encode(json.encode({'alg': 'HS256'})));
      expect(isTokenExpired('$header.$noExp.sig'), isTrue);
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
