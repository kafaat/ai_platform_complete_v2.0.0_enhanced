// SAHOOL — lib/core/offline/cache_cipher.dart
// تشفير مدخلة واحدة من كاش القراءة دون اتّصال (OfflineReadCache).
//
// AES-256-CBC بـHiveAesCipher (من hive، تبعيّة قائمة؛ IV عشوائيّ لكلّ مدخلة).
// النصّ قبل التشفير = sha256(مفتاح التخزين ‖ 0 ‖ الحمولة) ‖ الحمولة، فالبصمة
// نفسها مشفَّرة. عند الفكّ تُعاد البصمة وتُقارن، فيصير كلّ من:
//   • مفتاح نطاق آخر (مستأجِر آخر) ⇒ حشوة فاسدة أو بصمة لا تطابق،
//   • بايت معدَّل في المدخلة ⇒ كتلة مشوّهة فبصمة لا تطابق،
//   • مدخلة منقولة إلى مفتاح تخزين آخر ⇒ بصمة لا تطابق،
// رفضاً صريحاً (null)، لا نصّاً مشوّهاً يُعرض.
//
// لا توقيع ولا سرّ خدمة هنا: المفتاح عشوائيّ محلّيّ لكلّ نطاق، يولَد على الجهاز
// ويبقى في flutter_secure_storage، ولا يُرسَل إلى أيّ خادم.
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:hive/hive.dart';

const int _digestLength = 32;

/// 32 بايتاً من مولّد آمن — مفتاح جديد لنطاق (مستأجِر+مستخدم).
List<int> newMasterKey([Random? random]) {
  final r = random ?? Random.secure();
  return List<int>.generate(32, (_) => r.nextInt(256));
}

class CacheCipher {
  CacheCipher(List<int> key) : _aes = HiveAesCipher(key);

  final HiveAesCipher _aes;

  static List<int> _digest(String storageKey, List<int> payload) =>
      sha256.convert([...utf8.encode(storageKey), 0, ...payload]).bytes;

  /// يشفّر [plaintext] مربوطاً بـ[storageKey]؛ الناتج base64(IV ‖ CT).
  String seal(String storageKey, String plaintext) {
    final payload = utf8.encode(plaintext);
    final input = Uint8List.fromList([
      ..._digest(storageKey, payload),
      ...payload,
    ]);
    final out = Uint8List(_aes.maxEncryptedSize(input));
    final n = _aes.encrypt(input, 0, input.length, out, 0);
    return base64.encode(out.sublist(0, n));
  }

  /// يفكّ ما ختمه [seal] لـ[storageKey] نفسه. أيّ مفتاح آخر أو عبث أو صيغة
  /// تالفة ⇒ null (لا استثناء ولا نصّ مشوّه).
  String? open(String storageKey, String sealed) {
    try {
      final body = base64.decode(sealed);
      if (body.length < 16 + _digestLength + 16) return null;
      final out = Uint8List(body.length);
      final n = _aes.decrypt(body, 0, body.length, out, 0);
      if (n < _digestLength) return null;
      final tag = out.sublist(0, _digestLength);
      final payload = out.sublist(_digestLength, n);
      if (!_constantTimeEquals(tag, _digest(storageKey, payload))) return null;
      return utf8.decode(payload);
    } catch (_) {
      return null;
    }
  }

  static bool _constantTimeEquals(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a[i] ^ b[i];
    }
    return diff == 0;
  }
}
