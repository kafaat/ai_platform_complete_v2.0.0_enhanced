// اختبارات منطق انتهاء JWT — تستورد الكود الفعليّ (lib/utils/jwt.dart) لا نسخة
// مُعاد كتابتها، كي تكشف انحراف المنطق الحقيقيّ. تُشغَّل: flutter test
//
// خلفيّة: كان AuthService._isTokenExpired يعيد «غير منتهٍ» لتوكن بلا exp
// (fail-open) بينما ApiService والاختبار التوثيقيّ يتوقّعان fail-closed. هذا
// الاختبار يثبّت السلوك الصحيح (fail-closed) على المصدر الموحّد.

import 'dart:convert';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/utils/jwt.dart';

String _makeToken(Map<String, dynamic> payload) {
  final header = base64Url.encode(utf8.encode(json.encode({'alg': 'HS256'})));
  final body = base64Url.encode(utf8.encode(json.encode(payload)));
  return '$header.$body.sig';
}

int _nowSec() => DateTime.now().millisecondsSinceEpoch ~/ 1000;

void main() {
  group('isJwtExpired — الحالات الصحيحة', () {
    test('توكن منتهٍ → expired', () {
      expect(isJwtExpired(_makeToken({'exp': _nowSec() - 3600})), isTrue);
    });

    test('توكن صالح (مستقبليّ) → غير منتهٍ', () {
      expect(isJwtExpired(_makeToken({'exp': _nowSec() + 3600})), isFalse);
    });
  });

  group('isJwtExpired — fail-closed (الثغرات المخفيّة)', () {
    test('توكن بلا exp → expired (كان fail-open في AuthService)', () {
      expect(isJwtExpired(_makeToken({'sub': 'u'})), isTrue);
    });

    test('exp بنوع غير صحيح (نصّ) → expired', () {
      expect(isJwtExpired(_makeToken({'exp': 'soon'})), isTrue);
    });

    test('بنية مشوّهة (ليست 3 أجزاء) → expired', () {
      expect(isJwtExpired('a.b'), isTrue);
      expect(isJwtExpired('garbage'), isTrue);
      expect(isJwtExpired(''), isTrue);
    });

    test('payload غير قابل لفكّ base64/JSON → expired', () {
      expect(isJwtExpired('a.!!!.c'), isTrue);
    });

    test('payload ليس كائن JSON (مصفوفة) → expired', () {
      final body = base64Url.encode(utf8.encode(json.encode([1, 2, 3])));
      final header = base64Url.encode(utf8.encode(json.encode({'alg': 'x'})));
      expect(isJwtExpired('$header.$body.sig'), isTrue);
    });
  });

  group('isJwtExpired — هامش الأمان (skew)', () {
    test('الافتراضيّ 60s: توكن ينتهي خلال 30s → يُعدّ منتهياً', () {
      expect(isJwtExpired(_makeToken({'exp': _nowSec() + 30})), isTrue);
    });

    test('skew=0: نفس التوكن → غير منتهٍ', () {
      expect(
        isJwtExpired(_makeToken({'exp': _nowSec() + 30}), skewSeconds: 0),
        isFalse,
      );
    });
  });
}
