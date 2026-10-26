// FarmBookCubit: كتابة دون اتّصال عبر صندوق الإرسال بالمفتاح نفسه، رفض صادق حين
// لا صندوق، جسم السداد والعكس كما يشترط الخادم، والأدوار.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/farm_book/data/farm_book_api.dart';
import 'package:sahool_app/features/farm_book/data/farm_book_models.dart';
import 'package:sahool_app/features/farm_book/presentation/farm_book_cubit.dart';
import 'package:sahool_app/features/farm_book/presentation/farm_book_state.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';
import 'farm_book_fakes.dart';

class RecordingOutbox implements OfflineOutbox {
  RecordingOutbox({this.accept = true});
  final bool accept;
  final List<OutboxOp> ops = [];
  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    ops.add(op);
    return accept
        ? const OutboxReceipt.queued()
        : const OutboxReceipt.notQueued('x');
  }

  @override
  Stream<int> get pendingCount => Stream.value(ops.length);
}

FarmBookCubit cubitFor(
  FakeFarmBookServer s, {
  AppRole role = AppRole.owner,
  OfflineOutbox? outbox,
}) => FarmBookCubit(
  api: FarmBookApi(s.client),
  access: FarmBookAccess.forRole(role),
  farmsApi: FarmsApi(s.client),
  fieldsApi: FieldsApi(s.client),
  outbox: outbox == null ? null : () => outbox,
  now: () => DateTime(2026, 10, 26, 9),
);

const _draft = FarmBookEntryDraft(
  entryType: 'income',
  paymentMethod: 'cash',
  category: 'harvest_sale',
  amount: '90000',
  occurredOn: '2026-10-20',
);

void main() {
  test(
    'offline: the entry is queued with the same key and full body',
    () async {
      final s = FakeFarmBookServer();
      s.intercept = (o) => o.method == 'POST'
          ? const FakeReply.fail(DioExceptionType.connectionError)
          : null;
      const key = IdempotencyKey('0190f7a2-0000-7000-8000-0000000000aa');
      final outbox = RecordingOutbox();
      final c = cubitFor(s, outbox: outbox);
      await c.load();
      final out = await c.submitEntry(_draft, key);
      expect(out, isA<WriteQueued>());
      final op = outbox.ops.single;
      expect(op.method, 'POST');
      expect(op.path, '/api/v1/farm-book/entries');
      expect(op.idempotencyKey, key.value);
      expect(op.body['client_operation_id'], key.value);
      expect(op.body['amount'], '90000');
      expect(op.body['farm_id'], 'farm1');
      await c.close();
    },
  );

  test(
    'offline without a durable queue: honest failure, nothing claimed',
    () async {
      final s = FakeFarmBookServer();
      final c = cubitFor(s); // OfflineOutbox.instance الافتراضيّ لا يحفظ
      await c.load();
      s.intercept = (o) => o.method == 'POST'
          ? const FakeReply.fail(DioExceptionType.connectionError)
          : null;
      final out = await c.submitEntry(_draft, IdempotencyKey.generate());
      expect(out, isA<WriteFailed>());
      expect((out as WriteFailed).messageAr, contains('غير متاح بعد'));
      await c.close();
    },
  );

  test('a server 4xx is never queued', () async {
    final s = FakeFarmBookServer()
      ..onCreateEntry = (_) =>
          const FakeReply(422, {'detail': 'credit_requires_party'});
    final outbox = RecordingOutbox();
    final c = cubitFor(s, outbox: outbox);
    await c.load();
    final out = await c.submitEntry(_draft, IdempotencyKey.generate());
    expect(
      (out as WriteFailed).messageAr,
      'البيع أو الشراء الآجل يحتاج تحديد المورد أو العميل.',
    );
    expect(outbox.ops, isEmpty);
    await c.close();
  });

  test(
    'payment body: cash, debt_payment, party and currency of the debt',
    () async {
      final s = FakeFarmBookServer();
      final c = cubitFor(s);
      await c.load();
      final debt = FarmBookEntry.fromJson(
        entryJson(
          id: 'fbe_c',
          method: 'credit',
          partyId: 'party_a',
          currency: 'SAR',
          amount: 400,
        ),
      );
      final body = c.entryBody(
        FarmBookEntryDraft(
          entryType: 'payment',
          paymentMethod: 'credit',
          category: 'seed',
          amount: '100',
          occurredOn: '2026-10-26',
          partyId: 'ignored',
          settles: debt,
        ),
      );
      expect(body['payment_method'], 'cash');
      expect(body['category'], 'debt_payment');
      expect(body['party_id'], 'party_a');
      expect(body['settles_entry_id'], 'fbe_c');
      expect(body['currency'], 'SAR');
      await c.close();
    },
  );

  test(
    'openCreditEntries excludes payments, reversals and reversed credits',
    () async {
      final s = FakeFarmBookServer(
        entries: [
          entryJson(id: 'c1', method: 'credit', partyId: 'p'),
          entryJson(id: 'c', method: 'credit', partyId: 'p'),
          entryJson(id: 'r2', method: 'credit', partyId: 'p', reverses: 'c'),
          entryJson(id: 'cash', method: 'cash'),
        ],
      );
      final c = cubitFor(s);
      await c.load();
      final open = await c.openCreditEntries();
      expect(open.map((e) => e.entryId), ['c1']);
      expect(
        s.calls('GET', '/api/v1/farm-book/entries').last.query,
        {'farm_id': 'farm1'},
        reason: 'all dates, not just this month',
      );
      await c.close();
    },
  );

  test('a reversal of an earlier-month entry is dated today', () async {
    final s = FakeFarmBookServer();
    final c = cubitFor(s);
    await c.load();
    final original = FarmBookEntry.fromJson(
      entryJson(id: 'old', on: '2026-08-14'),
    );
    final b = c.reversalBody(original);
    expect(b['occurred_on'], '2026-10-26');
    expect(b['reverses_entry_id'], 'old');
    expect(b['amount'], '1500.00');
    await c.close();
  });

  test(
    'worker: no analytics calls; fields filtered to the selected farm',
    () async {
      final s = FakeFarmBookServer();
      final c = cubitFor(s, role: AppRole.worker);
      await c.load();
      await Future<void>.delayed(Duration.zero);
      expect(c.state.report, isA<SectionNotAllowed<FarmBookMonthly>>());
      expect(s.calls('GET', '/api/v1/farm-book/monthly'), isEmpty);
      expect(c.state.fieldOptions.map((f) => f.id), ['f1']);
      await c.close();
    },
  );

  test('cannot move past the current month', () async {
    final s = FakeFarmBookServer();
    final c = cubitFor(s);
    await c.load();
    final before = s.seen.length;
    await c.setMonth(c.state.month.next);
    expect(c.state.month.key, '2026-10');
    expect(s.seen.length, before);
    await c.close();
  });

  test('a farms 503 is a failed section, not an empty list', () async {
    final s = FakeFarmBookServer()
      ..intercept = (o) => o.path == '/api/v1/farms'
          ? const FakeReply(503, {'detail': 'db'})
          : null;
    final c = cubitFor(s);
    await c.load();
    expect(c.state.farms, isA<SectionFailed<List<FarmBookOption>>>());
    await c.close();
  });
}
