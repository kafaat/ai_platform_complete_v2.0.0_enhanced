/// هويّة جهاز ثابتة لمسار النماذج الميدانيّة.
///
/// تُولَّد مرّة واحدة وتُحفظ في التخزين الآمن. تدخل في تنزيل تعريفات النماذج
/// وفي ترويسة X-Device-Id عند الإرسال، بحيث يستطيع الخادم ربط إثبات المزامنة
/// بالجهاز نفسه. تدوير الهويّة صريح؛ نافذة قبول الهويّة السابقة يملكها الخادم.
library;

import 'dart:math';

import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class DeviceIdService {
  static final DeviceIdService instance = DeviceIdService._internal();
  DeviceIdService._internal();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const _key = 'field_forms_device_id';

  String? _cached;

  String _generate() {
    final random = Random.secure();
    final suffix = List<int>.generate(24, (_) => random.nextInt(256))
        .map((value) => value.toRadixString(16).padLeft(2, '0'))
        .join();
    return 'dev-$suffix';
  }

  Future<String> deviceId() async {
    final cached = _cached;
    if (cached != null) return cached;

    try {
      final saved = await _storage.read(key: _key);
      if (saved != null && saved.isNotEmpty) {
        _cached = saved;
        return saved;
      }
      final generated = _generate();
      await _storage.write(key: _key, value: generated);
      _cached = generated;
      return generated;
    } catch (error) {
      debugPrint(
        'DeviceIdService: secure storage unavailable ($error); using session id',
      );
      final generated = _cached ?? _generate();
      _cached = generated;
      return generated;
    }
  }

  Future<String> rotate() async {
    final generated = _generate();
    try {
      await _storage.write(key: _key, value: generated);
    } catch (error) {
      debugPrint('DeviceIdService.rotate: persist failed ($error)');
    }
    _cached = generated;
    return generated;
  }
}
