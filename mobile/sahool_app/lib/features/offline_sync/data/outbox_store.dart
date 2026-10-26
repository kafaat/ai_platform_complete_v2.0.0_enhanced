// SAHOOL — features/offline_sync/data/outbox_store.dart
// التخزين الدائم لصندوق الإرسال: صندوق Hive مشفّر (HiveAesCipher) بمفتاح 256 بت
// يُحفَظ في flutter_secure_storage (Keystore/Keychain)، لا في الصندوق ولا في
// SharedPreferences. السجلّ JSON نصّيّ، فلا محوّلات Hive ولا أنواع مولَّدة.
//
// مفتاح مفقود وصندوق موجود ⇒ لا نفتحه بمفتاح جديد: Hive يعامل الإطارات غير
// القابلة لفكّ التشفير كتلفٍ فيقصّ الملفّ (ضياع صامت). نُبلغ بالعطل بدلاً من ذلك
// ونترك الحذف قراراً صريحاً للمستخدم.
import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive/hive.dart';

import 'outbox_record.dart';

/// سبب تعذّر فتح الصندوق — يُعرَض في صفحة حالة المزامنة.
enum OutboxStoreFailure {
  /// تعذّرت قراءة/كتابة مفتاح التشفير من التخزين الآمن.
  keyStorage,

  /// الصندوق موجود ومفتاحه مفقود — بياناته غير قابلة للقراءة.
  keyMissingForExistingBox,

  /// فشل فتح Hive نفسه (لم يُهيَّأ، قرص ممتلئ، …).
  openFailed,
}

class OutboxStoreException implements Exception {
  const OutboxStoreException(this.failure, [this.cause]);
  final OutboxStoreFailure failure;
  final Object? cause;

  String get messageAr => switch (failure) {
    OutboxStoreFailure.keyStorage =>
      'تعذّر الوصول إلى مفتاح التشفير في التخزين الآمن للجهاز؛ لا يمكن حفظ العمليّات دون اتّصال الآن.',
    OutboxStoreFailure.keyMissingForExistingBox =>
      'صندوق المزامنة على هذا الجهاز مشفّر بمفتاح لم يعد موجوداً، فلا يمكن قراءة ما فيه.',
    OutboxStoreFailure.openFailed => 'تعذّر فتح صندوق المزامنة على هذا الجهاز.',
  };

  @override
  String toString() => 'OutboxStoreException(${failure.name}): $cause';
}

/// تخزين السجلّات. التنفيذ الإنتاجيّ [HiveOutboxStore]؛ الاختبارات تحقن غيره.
abstract class OutboxStore {
  /// كلّ السجلّات (لكلّ المالكين)، مرتّبة بـseq.
  List<OutboxRecord> get records;
  OutboxRecord? byId(String id);

  /// رقم الترتيب التالي (يزيد دائماً).
  int nextSeq();
  Future<void> put(OutboxRecord record);
  Future<void> remove(String id);
}

/// مصدر مفتاح التشفير.
abstract class OutboxKeyStore {
  Future<String?> read();
  Future<void> write(String base64Key);
}

class SecureOutboxKeyStore implements OutboxKeyStore {
  const SecureOutboxKeyStore([this._storage = _defaultStorage]);

  // نفس خيارات AuthService (EncryptedSharedPreferences على Android).
  static const _defaultStorage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const storageKey = 'sahool_offline_outbox_key_v1';

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read() => _storage.read(key: storageKey);

  @override
  Future<void> write(String base64Key) =>
      _storage.write(key: storageKey, value: base64Key);
}

class HiveOutboxStore implements OutboxStore {
  HiveOutboxStore._(this._box) {
    for (final key in _box.keys) {
      final raw = _box.get(key);
      if (raw == null) continue;
      try {
        final r = OutboxRecord.decode(raw);
        _records[r.id] = r;
        if (r.seq > _seq) _seq = r.seq;
      } catch (_) {
        // سجلّ لا يُفكّ (إصدار أحدث؟) يبقى في الصندوق كما هو ولا يُحذف.
      }
    }
  }

  static const boxName = 'sahool_offline_outbox_v1';

  final Box<String> _box;
  final Map<String, OutboxRecord> _records = {};
  int _seq = 0;

  /// يفتح الصندوق المشفّر. يرمي [OutboxStoreException] عند التعذّر.
  /// يفترض أنّ Hive مُهيَّأ (main.dart: `Hive.initFlutter()`).
  static Future<HiveOutboxStore> openEncrypted({
    OutboxKeyStore keys = const SecureOutboxKeyStore(),
    String name = boxName,
  }) async {
    final List<int> key;
    try {
      key = await _loadKey(keys, name);
    } on OutboxStoreException {
      rethrow;
    } catch (e) {
      throw OutboxStoreException(OutboxStoreFailure.keyStorage, e);
    }
    try {
      final box = await Hive.openBox<String>(
        name,
        encryptionCipher: HiveAesCipher(key),
      );
      return HiveOutboxStore._(box);
    } catch (e) {
      throw OutboxStoreException(OutboxStoreFailure.openFailed, e);
    }
  }

  static Future<List<int>> _loadKey(OutboxKeyStore keys, String name) async {
    final stored = await keys.read();
    if (stored != null && stored.isNotEmpty) {
      final bytes = base64Decode(stored);
      if (bytes.length == 32) return bytes;
    }
    // لا مفتاح صالح: صندوق قائم ⇒ لا نفتحه بمفتاح جديد (Hive سيقصّه).
    bool exists;
    try {
      exists = await Hive.boxExists(name);
    } catch (e) {
      throw OutboxStoreException(OutboxStoreFailure.openFailed, e);
    }
    if (exists) {
      throw const OutboxStoreException(
        OutboxStoreFailure.keyMissingForExistingBox,
      );
    }
    final fresh = Hive.generateSecureKey();
    await keys.write(base64Encode(fresh));
    // اقرأه من جديد: لا نفتح صندوقاً بمفتاحٍ لم يُثبَت حفظه.
    final check = await keys.read();
    if (check == null || base64Decode(check).length != 32) {
      throw const OutboxStoreException(OutboxStoreFailure.keyStorage);
    }
    return base64Decode(check);
  }

  /// يحذف صندوقاً لا يُقرأ (مفتاحه مفقود). قرار صريح من المستخدم فقط.
  static Future<void> deleteUnreadable({String name = boxName}) =>
      Hive.deleteBoxFromDisk(name);

  @override
  List<OutboxRecord> get records =>
      _records.values.toList()..sort((a, b) => a.seq.compareTo(b.seq));

  @override
  OutboxRecord? byId(String id) => _records[id];

  @override
  int nextSeq() => ++_seq;

  @override
  Future<void> put(OutboxRecord record) async {
    await _box.put(record.id, record.encode());
    _records[record.id] = record;
    if (record.seq > _seq) _seq = record.seq;
  }

  @override
  Future<void> remove(String id) async {
    await _box.delete(id);
    _records.remove(id);
  }

  Future<void> close() => _box.close();
}
