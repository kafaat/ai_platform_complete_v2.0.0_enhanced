// سجلّ العمليّات المعلّقة على خادم HTTP محلّيّ حقيقيّ وصندوق Hive على القرص:
// R03 (قتل التطبيق بعد الإرسال وقبل حفظ الردّ ⇒ المفتاح والحمولة والمالك من القرص)،
// R04 (فشل الكتابة المحلّيّة ⇒ صفر طلبات)، R13 (انقضاء الاحتفاظ ⇒ مصالحة لا إنشاء)،
// وOD-2 (409 لا يقود إلى مفتاح جديد؛ payload_mismatch / in_progress / بلا سبب).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';

import '../../core/fake_http.dart';
import 'operation_test_support.dart';

const _path = '/api/v1/irrigation/schedules';
const _kind = 'irrigation_schedule.create';
const _payload = {
  'name': 'ريّ الفجر',
  'start_time': '06:30',
  'duration_min': 30,
  'enabled': true,
};

Map<String, dynamic> _schedule(int n, Map<String, dynamic> body) => {
  'schedule_id': 'sch_$n',
  'name': body['name'],
  'message_ar': 'أُنشئ جدول الريّ',
};

CreateOperation _op(OperationLedger ledger, ApiClient client) =>
    CreateOperation(
      ledger: ledger,
      kind: _kind,
      method: 'POST',
      path: _path,
      send: (p, k) => IrrigationApi(client).createSchedule(p, idempotencyKey: k),
    );

void main() {
  late LocalCommitServer server;
  late MemoryTokenStore tokens;
  late ApiClient client;

  setUp(() async {
    server = await LocalCommitServer.start(createPath: _path, make: _schedule);
    tokens = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
    client = realClient(server, tokens);
  });

  tearDown(() => server.close());

  test('R04: a failed local write sends zero requests', () async {
    final store = MemoryOperationStore()..failWrites = true;
    final op = _op(ledgerFor(tokens, store, client: client), client);
    final o = await op.submit(Map.of(_payload));
    expect(o, isA<CreateNotSaved>());
    expect((o as CreateNotSaved).messageAr, kOperationNotSavedAr);
    expect(server.requests, isEmpty, reason: 'لا طلب شبكة إطلاقاً');
    expect(op.record, isNull);
  });

  test('R04: an unopenable store (no Hive) also sends nothing', () async {
    final ledger = OperationLedger(
      openStore: () async => throw const FileSystemException('locked'),
      currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
    );
    final o = await _op(ledger, client).submit(Map.of(_payload));
    expect(o, isA<CreateNotSaved>());
    expect(server.requests, isEmpty);
  });

  test('the record is on disk before the request leaves', () async {
    final store = MemoryOperationStore();
    server.plan.add(const CommitThenHang());
    final op = _op(ledgerFor(tokens, store, client: client), client);
    final pending = op.submit(Map.of(_payload));
    await server.createArrived(1);
    final onDisk = OperationRecord.decode(store.disk.values.single);
    expect(onDisk.state, OperationState.pending);
    expect(onDisk.operationId, server.creates.single.key);
    expect(onDisk.payload, _payload);
    expect(onDisk.owner, const OutboxOwner(userId: 'alice', tenantId: 't1'));
    await server.close();
    expect(await pending, isA<CreateUnconfirmed>());
  });

  group('R03: real Hive box on disk', () {
    late Directory dir;
    late MemoryKeyStore keys;

    setUp(() {
      dir = Directory.systemTemp.createTempSync('op_ledger_test');
      Hive.init(dir.path);
      keys = MemoryKeyStore();
    });

    tearDown(() async {
      await Hive.close();
      dir.deleteSync(recursive: true);
    });

    test('killed after send, before the response is saved: key, payload and '
        'owner come back from disk; recovery replays the same key and finds '
        'the one committed schedule', () async {
      server.plan.add(const CommitThenHang());
      final store1 = await HiveOperationStore.openEncrypted(keys: keys);
      final op1 = _op(ledgerFor(tokens, store1, client: client), client);
      // لا ننتظر: «يُقتل» التطبيق والطلب معلّق بعد التزام الخادم.
      final orphan = op1.submit(Map.of(_payload));
      await server.createArrived(1);
      final sentKey = server.creates.single.key;
      await Hive.close(); // القتل: لا كتابة بعد هذه النقطة تصل إلى القرص

      // «إعادة التشغيل»: صندوق جديد فوق الملفّات نفسها.
      final store2 = await HiveOperationStore.openEncrypted(keys: keys);
      final r = store2.records.single;
      expect(r.operationId, sentKey);
      expect(r.payload, _payload);
      expect(r.digest, payloadDigest(_payload));
      expect(r.owner, const OutboxOwner(userId: 'alice', tenantId: 't1'));
      expect(r.state, OperationState.pending);

      // مالك آخر على الجهاز نفسه لا يرى عمليّة alice.
      final bobTokens = MemoryTokenStore(accessToken: jwtFor('bob'));
      expect(
        await ledgerFor(bobTokens, store2).openFor(_kind),
        isNull,
        reason: 'الاستعادة لنفس المالك فقط',
      );
      // نفس المستخدم في مستأجر آخر ليس المالك نفسه.
      final otherTenant = MemoryTokenStore(
        accessToken: jwtFor('alice', tenant: 't2'),
      );
      expect(await ledgerFor(otherTenant, store2).openFor(_kind), isNull);

      final op2 = _op(ledgerFor(tokens, store2, client: client), client);
      final restored = await op2.restore();
      expect(restored, isA<CreateUnconfirmed>());
      expect((restored as CreateUnconfirmed).messageAr, kOperationUnknownAr);
      expect(op2.record!.state, OperationState.outcomeUnknown);

      final done = await op2.recover();
      expect(done, isA<CreateConfirmed>());
      expect((done as CreateConfirmed).result['schedule_id'], 'sch_1');
      expect(server.resources, hasLength(1), reason: 'مورد واحد');
      expect(server.creates.map((c) => c.key).toSet(), {sentKey});
      expect(server.creates.every((c) => c.body!['name'] == 'ريّ الفجر'), true);
      expect(store2.records, isEmpty, reason: 'المؤكَّدة تُزال من السجلّ');
      await server.close();
      await orphan;
    });
  });

  test('R13: past the retention window, not_found becomes '
      'needs_reconciliation — no replay, no new key', () async {
    var now = DateTime.utc(2026, 10, 27, 8);
    final store = MemoryOperationStore();
    final ledger = ledgerFor(
      tokens,
      store,
      client: client,
      clock: () => now,
    );
    server.plan.add(const Status(503, {'detail': 'down'}));
    server.plan.add(const Status(503, {'detail': 'down'}));
    server.plan.add(const Status(503, {'detail': 'down'}));
    server.plan.add(const Status(503, {'detail': 'down'}));
    final op = _op(ledger, client);
    expect(await op.submit(Map.of(_payload)), isA<CreateUnconfirmed>());
    final key = op.record!.operationId;
    final postsBefore = server.creates.length;

    now = now.add(kServerIdempotencyRetention + const Duration(minutes: 1));
    final o = await op.recover();
    expect(o, isA<CreateUnconfirmed>());
    final u = o as CreateUnconfirmed;
    expect(u.state, OperationState.needsReconciliation);
    expect(u.messageAr, kOperationReconcileAr);
    expect(u.canDismiss, isTrue);
    expect(server.creates, hasLength(postsBefore), reason: 'لا إعادة آليّة');
    expect(
      server.requests.where((r) => r.method == 'GET').single.path,
      '/api/v1/commands/$key',
    );
    // تعديل المستخدم بعدها لا يُرسَل أيضاً.
    final edited = await op.submit({..._payload, 'name': 'ريّ الضحى'});
    expect(edited, isA<CreateUnconfirmed>());
    expect(server.creates, hasLength(postsBefore));
    // الإغلاق قرار بشريّ صريح بعد المراجعة.
    expect(await op.dismiss(), isTrue);
    expect(store.records, isEmpty);
  });

  test('within retention, a found command is replayed with the same key and '
      'payload and returns the stored result', () async {
    final store = MemoryOperationStore();
    server.plan.add(const CommitThenDrop());
    final op = _op(ledgerFor(tokens, store, client: client), client);
    expect(await op.submit(Map.of(_payload)), isA<CreateUnconfirmed>());
    final o = await op.recover();
    expect(o, isA<CreateConfirmed>());
    expect(server.resources, hasLength(1));
    expect(server.creates, hasLength(2));
    expect(server.creates[1].key, server.creates[0].key);
    expect(server.creates[1].body, server.creates[0].body);
  });

  group('OD-2: a 409 never leads to a new key', () {
    Future<(CreateOperation, CreateUnconfirmed)> conflict(Object body) async {
      server.plan.add(Status(409, body));
      final op = _op(
        ledgerFor(tokens, MemoryOperationStore(), client: client),
        client,
      );
      final o = await op.submit(Map.of(_payload));
      expect(o, isA<CreateUnconfirmed>());
      return (op, o as CreateUnconfirmed);
    }

    test('payload_mismatch (D4 reason code) ⇒ needs_attention + recover '
        'wording; an edit and a recover keep the key', () async {
      final (op, u) = await conflict({
        'detail': {'reason': 'payload_mismatch', 'message_ar': 'x'},
      });
      expect(u.state, OperationState.needsAttention);
      expect(u.messageAr, kOperationConflictAr);
      expect(u.actionLabelAr, kRecoverActionAr);
      expect(u.canDismiss, isFalse, reason: 'لا مسار «أنشئ من جديد»');
      final key = server.creates.single.key;

      expect(
        await op.submit({..._payload, 'name': 'ريّ الضحى'}),
        isA<CreateUnconfirmed>(),
      );
      expect(server.creates, hasLength(1), reason: 'المسودّة لا تُرسَل');
      final r = await op.recover();
      expect(r, isA<CreateConfirmed>());
      expect(server.creates.map((c) => c.key).toSet(), {key});
      expect(server.creates.last.body, _payload, reason: 'الحمولة الأصليّة');
      expect(
        (r as CreateConfirmed).pendingEdits.single.key,
        'name',
        reason: 'التعديل يُعرض بعد الاستعادة ولا يُرسَل',
      );
    });

    test('the current server text for a reused key maps to payload_mismatch '
        '(its «use a new key» advice is not followed)', () async {
      final (_, u) = await conflict({
        'detail': 'Idempotency-Key أُعيد استعماله بحمولةٍ مختلفة — استعمل مفتاحاً جديداً',
      });
      expect(u.state, OperationState.needsAttention);
      expect(u.record.conflictReason, ConflictReason.payloadMismatch);
      expect(u.messageAr, kOperationConflictAr);
    });

    test('in_progress ⇒ still unknown, "check again later"', () async {
      final (op, u) = await conflict({
        'detail': {'reason': 'in_progress'},
      });
      expect(u.state, OperationState.outcomeUnknown);
      expect(u.inProgress, isTrue);
      expect(u.messageAr, kOperationInProgressAr);
      expect(u.actionLabelAr, kCheckAgainActionAr);
      final key = server.creates.single.key;
      await op.recover();
      expect(server.creates.map((c) => c.key).toSet(), {key});
    });

    test('the current in-progress text is recognised without a reason code', () async {
      final (_, u) = await conflict({
        'detail': 'الأمر قيد المعالجة — أعد المحاولة لاحقاً',
      });
      expect(u.inProgress, isTrue);
    });

    test('a 409 without any reason ⇒ the recover message; recovery checks the '
        'command first and only then reads the conflict as a business refusal',
        () async {
      final (op, u) = await conflict({'detail': 'يتعارض جدول الريّ مع جدول قائم'});
      expect(u.state, OperationState.needsAttention);
      expect(u.messageAr, kOperationConflictAr);
      final key = server.creates.single.key;
      // الاستعادة: GET commands ⇒ 404 (لم يُلتزَم شيء) ثمّ إعادة الأصل ⇒ 409 أعمال.
      server.plan.add(
        const Status(409, {'detail': 'يتعارض جدول الريّ مع جدول قائم'}),
      );
      final r = await op.recover();
      expect(r, isA<CreateRejected>());
      expect(op.record!.state, OperationState.savedLocally);
      // التصحيح يُرسَل بالمفتاح نفسه (لم يُنفَّذ له شيء)، لا بمفتاح جديد.
      final fixed = await op.submit({..._payload, 'start_time': '07:30'});
      expect(fixed, isA<CreateConfirmed>());
      expect(server.creates.map((c) => c.key).toSet(), {key});
      expect(server.resources, hasLength(1));
    });
  });

  test('a business 409 with a code is a proven refusal; the corrected payload '
      'keeps the operation key', () async {
    server.plan.add(
      const Status(409, {
        'detail': {'code': 'duplicate_field_name', 'message_ar': 'مكرّر'},
      }),
    );
    final op = _op(
      ledgerFor(tokens, MemoryOperationStore(), client: client),
      client,
    );
    expect(await op.submit(Map.of(_payload)), isA<CreateRejected>());
    expect(await op.submit({..._payload, 'name': 'آخر'}), isA<CreateConfirmed>());
    expect(server.creates[1].key, server.creates[0].key);
    expect(server.creates[1].body!['name'], 'آخر');
  });

  test('digest is canonical: key order does not matter', () {
    expect(
      payloadDigest({'a': 1, 'b': {'y': 2, 'x': 1}}),
      payloadDigest({'b': {'x': 1, 'y': 2}, 'a': 1}),
    );
    expect(payloadDigest({'a': 1}), isNot(payloadDigest({'a': 2})));
  });
}
