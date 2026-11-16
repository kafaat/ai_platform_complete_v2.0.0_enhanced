// SAHOOL — lib/core/offline/cache_cipher.dart
// تشفير مدخلة واحدة من كاش القراءة دون اتّصال (OfflineReadCache).
//
// AES-256-GCM — تشفير مُصادَق (AEAD) من pointycastle، لا بناءٌ يدويّ:
//   • nonce عشوائيّ ١٢ بايتاً لكلّ مدخلة (Random.secure)،
//   • البيانات المُصادَقة الإضافيّة (AAD) = مفتاح التخزين، فالمدخلة مربوطة بموضعها،
//   • وسم ١٢٨ بتّاً يُتحقَّق منه قبل إعادة أيّ نصّ.
// فيصير كلّ من:
//   • مفتاح نطاق آخر (مستأجِر آخر) ⇒ وسم لا يطابق،
//   • بايت معدَّل في المدخلة (ولو عمداً، بلا المفتاح) ⇒ وسم لا يطابق،
//   • مدخلة منقولة إلى مفتاح تخزين آخر ⇒ AAD مختلفة فوسم لا يطابق،
// رفضاً صريحاً (null)، لا نصّاً مشوّهاً يُعرض.
//
// نموذج التهديد: يحمي من قراءة مستأجِر آخر ومن العبث بالمخزن دون المفتاح. لا يحمي
// ممّن يملك المفتاح نفسه (من يقرأ flutter_secure_storage على جهاز مخترَق).
//
// لا توقيع ولا سرّ خدمة هنا: المفتاح عشوائيّ محلّيّ لكلّ نطاق، يولَد على الجهاز
// ويبقى في flutter_secure_storage، ولا يُرسَل إلى أيّ خادم.
import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:pointycastle/export.dart';

const int _nonceLength = 12;
const int _tagBits = 128;

/// 32 بايتاً من مولّد آمن — مفتاح جديد لنطاق (مستأجِر+مستخدم).
List<int> newMasterKey([Random? random]) {
  final r = random ?? Random.secure();
  return List<int>.generate(32, (_) => r.nextInt(256));
}

class CacheCipher {
  CacheCipher(List<int> key, {Random? random})
      : _key = KeyParameter(Uint8List.fromList(key)),
        _random = random ?? Random.secure() {
    if (key.length != 32) {
      throw ArgumentError.value(key.length, 'key', 'AES-256 needs 32 bytes');
    }
  }

  final KeyParameter _key;
  final Random _random;

  GCMBlockCipher _gcm(bool forEncryption, Uint8List nonce, String storageKey) =>
      GCMBlockCipher(AESEngine())
        ..init(
          forEncryption,
          AEADParameters(
            _key,
            _tagBits,
            nonce,
            Uint8List.fromList(utf8.encode(storageKey)),
          ),
        );

  /// يشفّر [plaintext] مربوطاً بـ[storageKey]؛ الناتج base64(nonce ‖ CT ‖ tag).
  String seal(String storageKey, String plaintext) {
    final nonce = Uint8List.fromList(
      List<int>.generate(_nonceLength, (_) => _random.nextInt(256)),
    );
    final sealed = _gcm(true, nonce, storageKey)
        .process(Uint8List.fromList(utf8.encode(plaintext)));
    return base64.encode([...nonce, ...sealed]);
  }

  /// يفكّ ما ختمه [seal] لـ[storageKey] نفسه. أيّ مفتاح آخر أو عبث أو صيغة
  /// تالفة ⇒ null (لا استثناء ولا نصّ مشوّه).
  String? open(String storageKey, String sealed) {
    try {
      final body = base64.decode(sealed);
      if (body.length < _nonceLength + _tagBits ~/ 8) return null;
      final nonce = Uint8List.sublistView(body, 0, _nonceLength);
      final payload = _gcm(false, Uint8List.fromList(nonce), storageKey)
          .process(Uint8List.sublistView(body, _nonceLength));
      return utf8.decode(payload);
    } catch (_) {
      // InvalidCipherTextException (وسم لا يطابق) أو صيغة تالفة.
      return null;
    }
  }
}
