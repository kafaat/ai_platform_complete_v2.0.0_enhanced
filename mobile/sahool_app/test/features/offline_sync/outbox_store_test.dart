// الصندوق الدائم الحقيقيّ (Hive على القرص): مشفّر بـAES بمفتاح في التخزين الآمن،
// لا نصّ صريح في الملفّ، يبقى بعد إعادة الفتح، ولا يُفتح بمفتاح جديد إن ضاع مفتاحه.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

import 'outbox_test_support.dart';

class _BrokenKeys implements OutboxKeyStore {
  @override
  Future<String?> read() async => throw Exception('keystore locked');
  @override
  Future<void> write(String base64Key) async => throw Exception('locked');
}

OutboxRecord _record(int seq, {String marker = 'plain'}) => OutboxRecord(
  id: 'r$seq',
  seq: seq,
  owner: const OutboxOwner(userId: 'alice', tenantId: 't1'),
  op: op('/api/v1/tasks/$seq', body: {'notes': marker}),
  createdAt: DateTime.utc(2026, 10, 26),
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('outbox_store_test');
    Hive.init(dir.path);
    FlutterSecureStorage.setMockInitialValues({});
  });

  tearDown(() async {
    await Hive.close();
    dir.deleteSync(recursive: true);
  });

  File boxFile() => File('${dir.path}/${HiveOutboxStore.boxName}.hive');

  test('box is opened with an AES key kept in secure storage; no plaintext '
      'on disk', () async {
    final store = await HiveOutboxStore.openEncrypted();
    const marker = 'SECRET_FIELD_NOTE_42';
    await store.put(_record(1, marker: marker));
    await store.close();

    final stored = await const FlutterSecureStorage().read(
      key: SecureOutboxKeyStore.storageKey,
    );
    expect(stored, isNotNull);
    final key = base64Decode(stored!);
    expect(key, hasLength(32));

    final raw = boxFile().readAsBytesSync();
    expect(raw, isNotEmpty);
    expect(latin1.decode(raw).contains(marker), isFalse);
    expect(utf8.decode(raw, allowMalformed: true).contains('alice'), isFalse);

    // نفس المفتاح يفكّ السجلّ.
    final box = await Hive.openBox<String>(
      HiveOutboxStore.boxName,
      encryptionCipher: HiveAesCipher(key),
    );
    expect(OutboxRecord.decode(box.get('r1')!).op.body['notes'], marker);
  });

  test(
    'records survive reopening in FIFO order with an increasing seq',
    () async {
      var store = await HiveOutboxStore.openEncrypted();
      for (final s in [1, 2, 3]) {
        await store.put(_record(s));
      }
      await store.close();
      store = await HiveOutboxStore.openEncrypted();
      expect(store.records.map((r) => r.id), ['r1', 'r2', 'r3']);
      expect(store.nextSeq(), greaterThan(3));
    },
  );

  test(
    'lost key with an existing box ⇒ explicit failure, box untouched',
    () async {
      final store = await HiveOutboxStore.openEncrypted();
      await store.put(_record(1));
      await store.close();
      final size = boxFile().lengthSync();

      FlutterSecureStorage.setMockInitialValues({}); // المفتاح ضاع
      await expectLater(
        HiveOutboxStore.openEncrypted(),
        throwsA(
          isA<OutboxStoreException>().having(
            (e) => e.failure,
            'failure',
            OutboxStoreFailure.keyMissingForExistingBox,
          ),
        ),
      );
      expect(boxFile().lengthSync(), size, reason: 'never truncated silently');
    },
  );

  test(
    'secure storage failure ⇒ keyStorage failure, no unencrypted box',
    () async {
      await expectLater(
        HiveOutboxStore.openEncrypted(keys: _BrokenKeys()),
        throwsA(
          isA<OutboxStoreException>().having(
            (e) => e.failure,
            'failure',
            OutboxStoreFailure.keyStorage,
          ),
        ),
      );
      expect(boxFile().existsSync(), isFalse);
    },
  );

  test('queued ops survive an app restart (new outbox, same box)', () async {
    final h = Harness();
    final first = DurableOfflineOutbox(
      openStore: HiveOutboxStore.openEncrypted,
      currentOwner: () => OutboxOwner.fromAccessToken(h.tokens.accessToken),
      connectivity: h.connectivity, // offline: لا إرسال في هذا الاختبار
    );
    final o = op('/api/v1/tasks/5', fieldId: 'f1', label: 'إنهاء الريّ');
    expect((await first.enqueue(o)).queued, isTrue);
    await Hive.close();

    final second = DurableOfflineOutbox(
      openStore: HiveOutboxStore.openEncrypted,
      currentOwner: () => OutboxOwner.fromAccessToken(h.tokens.accessToken),
    );
    await second.ensureOpen();
    final pending = second.snapshot().pending.single;
    expect(pending.op.idempotencyKey, o.idempotencyKey);
    expect(pending.op.labelAr, 'إنهاء الريّ');
    expect(pending.op.fieldId, 'f1');
    expect(await second.pendingCount.first, 1);
  });
}
