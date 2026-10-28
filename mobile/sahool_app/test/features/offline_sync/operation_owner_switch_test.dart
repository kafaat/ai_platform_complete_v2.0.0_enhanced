// المالك يُعاد فحصه بعد كلّ await وقبل الإرسال مباشرة (مراجعة D1 must_fix #1): تبديل
// الجلسة إلى مالكٍ/مستأجرٍ آخر أثناء استعلام GET /api/v1/commands/{id} أو أثناء الكتابة
// المحلّيّة لا يُخرج حمولة alice برمز bob — كان يُنشئ مورد alice داخل مستأجر bob ثمّ
// يحذف السجلّ من دفتر alice. خادم HTTP محلّيّ حقيقيّ (dart:io) يبدّل التوكن والطلب
// «في الطريق» (قبل أيّ ردّ)، وApiClient حقيقيّ يرسل برمز اللحظة الحاضرة.
//
// لا يستعمل إلّا واجهات موجودة قبل الإصلاح، فيُشغَّل عليها كما هو ويحمرّ سلوكيّاً.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_screen.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';

import '../../core/fake_http.dart';
import '../irrigation/irrigation_test_helpers.dart' show host;
import 'operation_test_support.dart';

const _path = '/api/v1/irrigation/schedules';
const _kind = 'irrigation_schedule.create';
const _payload = {
  'name': 'ريّ الفجر',
  'start_time': '06:30',
  'duration_min': 30,
  'enabled': true,
};
const _alice = OutboxOwner(userId: 'alice', tenantId: 't1');

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
      send: (p, k) =>
          IrrigationApi(client).createSchedule(p, idempotencyKey: k),
    );

/// 503 على كلّ محاولات ApiClient (الأصل + 3 إعادات بالمفتاح نفسه) ⇒ نتيجة مجهولة.
void _unknownOutcome(LocalCommitServer s) {
  for (var i = 0; i < 4; i++) {
    s.plan.add(const Status(503, {'detail': 'الخدمة غير متاحة'}));
  }
}

bool _isLookup(ServedRequest r) =>
    r.method == 'GET' && r.path.startsWith('/api/v1/commands/');

/// يُبطئ الكتابة ويبدّل الجلسة أثناءها (تبديلٌ بين فحص المالك والإرسال).
class _SwitchOnWriteStore extends MemoryOperationStore {
  _SwitchOnWriteStore(this.onWrite);
  final void Function() onWrite;
  bool armed = false;

  @override
  Future<void> put(OperationRecord record) async {
    if (armed) {
      armed = false;
      onWrite();
    }
    await super.put(record);
  }
}

void main() {
  late LocalCommitServer server;
  late MemoryTokenStore tokens;
  late ApiClient client;
  final bobToken = jwtFor('bob', tenant: 't2');

  setUp(
    () => HttpOverrides.global = null,
  ); // flutter_test يردّ 400 لكلّ HttpClient

  group('ledger level', () {
    setUp(() async {
      server = await LocalCommitServer.start(
        createPath: _path,
        make: _schedule,
      );
      tokens = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
      client = realClient(server, tokens);
    });

    tearDown(() => server.close());

    test('recover: the session switches to bob@t2 while GET /commands is in '
        'flight ⇒ zero creates after the switch, nothing sent with bob\'s '
        'token, and alice\'s record stays on disk for her', () async {
      final store = MemoryOperationStore();
      final op = _op(ledgerFor(tokens, store, client: client), client);
      _unknownOutcome(server);
      final first = await op.submit(Map.of(_payload));
      expect(first, isA<CreateUnconfirmed>());
      final key = op.record!.operationId;
      final createsBefore = server.creates.length;

      // الطلب في الطريق: يصل GET /commands إلى الخادم ثمّ تتبدّل الجلسة قبل الردّ.
      server.onArrive = (r) async {
        if (_isLookup(r)) tokens.accessToken = bobToken;
      };
      final o = await op.recover();

      expect(
        server.requests.where(_isLookup),
        hasLength(1),
        reason: 'الاستعلام نفسه خرج برمز alice',
      );
      expect(
        server.creates.length,
        createsBefore,
        reason: 'لا إنشاء بعد التبديل',
      );
      expect(
        server.requests.where((r) => r.auth == 'Bearer $bobToken'),
        isEmpty,
        reason: 'لا طلب كتابة برمز bob',
      );
      expect(o, isA<CreateNotSaved>());
      expect((o as CreateNotSaved).messageAr, kOperationNoSessionAr);
      // السجلّ لمالكه، بحالته، على القرص.
      final onDisk = OperationRecord.decode(store.disk[key]!);
      expect(onDisk.owner, _alice);
      expect(onDisk.state, OperationState.outcomeUnknown);
      expect(onDisk.payload, _payload);
      expect(
        await ledgerFor(tokens, store).openFor(_kind),
        isNull,
        reason: 'bob لا يرى عمليّة alice',
      );

      // عودة alice: الاستعادة بنفس المفتاح ونفس الحمولة، مورد واحد.
      server.onArrive = null;
      tokens.accessToken = jwtFor('alice', tenant: 't1');
      final back = await op.recover();
      expect(back, isA<CreateConfirmed>());
      expect(server.resources, hasLength(1));
      expect(server.creates.map((c) => c.key).toSet(), {key});
      expect(server.creates.last.body, _payload);
    });

    test('submit: the session switches while the record is being written ⇒ '
        'the first create never leaves with the new owner\'s token', () async {
      late _SwitchOnWriteStore store;
      store = _SwitchOnWriteStore(() => tokens.accessToken = bobToken)
        ..armed = true;
      final op = _op(ledgerFor(tokens, store, client: client), client);
      final o = await op.submit(Map.of(_payload));
      expect(server.creates, isEmpty, reason: 'لا إنشاء برمز bob');
      expect(o, isA<CreateNotSaved>());
      expect((o as CreateNotSaved).messageAr, kOperationNoSessionAr);
      final onDisk = OperationRecord.decode(store.disk.values.single);
      expect(onDisk.owner, _alice, reason: 'السجلّ لمالكه');
    });

    test('a same-payload resubmit after an unknown outcome (submit → recover '
        'path) is also re-checked after the lookup', () async {
      final store = MemoryOperationStore();
      final op = _op(ledgerFor(tokens, store, client: client), client);
      _unknownOutcome(server);
      await op.submit(Map.of(_payload));
      final createsBefore = server.creates.length;
      server.onArrive = (r) async {
        if (_isLookup(r)) tokens.accessToken = bobToken;
      };
      final o = await op.submit(Map.of(_payload));
      expect(server.creates.length, createsBefore);
      expect(o, isA<CreateNotSaved>());
    });
  });

  testWidgets('schedule sheet: tap recover, the session switches to another '
      'tenant during the lookup ⇒ zero creates after the switch and the panel '
      'stays', (t) async {
    final s = (await t.runAsync(
      () => LocalCommitServer.start(createPath: _path, make: _schedule),
    ))!;
    s.getResponses['/api/v1/irrigation/valves'] = const <Object>[];
    s.getResponses[_path] = const <Object>[];
    Future<void> settle() async {
      for (var i = 0; i < 25; i++) {
        await t.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 20)),
        );
        await t.pump(const Duration(milliseconds: 50));
      }
    }

    try {
      final tk = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
      final c = realClient(s, tk);
      final disk = <String, String>{};
      _unknownOutcome(s);
      await t.pumpWidget(
        host(
          IrrigationOpsScreen(
            api: IrrigationApi(c),
            role: 'owner',
            ledger: ledgerFor(tk, MemoryOperationStore(disk), client: c),
          ),
        ),
      );
      await settle();
      await t.tap(find.text('الجداول'));
      await t.pumpAndSettle();
      await t.tap(find.byType(FloatingActionButton));
      await settle();
      final inputs = find.byType(TextField);
      await t.enterText(inputs.at(0), 'ريّ الفجر');
      await t.enterText(inputs.at(1), '06:30');
      await t.enterText(inputs.at(2), '30');
      await t.tap(find.text('إنشاء الجدول'));
      await settle();
      expect(find.text(kOperationUnknownAr), findsOneWidget);
      final createsBefore = s.creates.length;

      s.onArrive = (r) async {
        if (_isLookup(r)) tk.accessToken = bobToken;
      };
      await t.tap(find.text(kRecoverActionAr));
      await settle();

      expect(s.requests.where(_isLookup), hasLength(1));
      expect(s.creates.length, createsBefore, reason: 'لا إنشاء بعد التبديل');
      expect(
        s.requests.where(
          (r) => r.auth == 'Bearer $bobToken' && r.method == 'POST',
        ),
        isEmpty,
      );
      expect(find.text(kOperationNoSessionAr), findsOneWidget);
      expect(find.text('إنشاء الجدول'), findsNothing, reason: 'لا إعادة إنشاء');
      final rec = MemoryOperationStore(disk).records.single;
      expect(rec.owner, _alice);
      expect(rec.state, OperationState.outcomeUnknown);
    } finally {
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(s.close);
    }
  });
}
