// FarmBookApi فوق ApiClient الحقيقيّ: المسارات والاستعلامات كما في
// simple_farm_book.py، المفتاح في الجسم والترويسة، وأخطاء التصدير الثنائيّ.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/farm_book/data/farm_book_api.dart';

import '../../core/fake_http.dart';
import 'farm_book_fakes.dart';

void main() {
  late FakeFarmBookServer server;
  late FarmBookApi api;
  setUp(() {
    server = FakeFarmBookServer(entries: [entryJson(id: 'fbe_1')]);
    api = FarmBookApi(server.client);
  });

  test('createEntry forces client_operation_id = Idempotency-Key', () async {
    const key = IdempotencyKey('0190f7a2-0000-7000-8000-00000000abcd');
    final r = await api.createEntry({
      'entry_type': 'expense',
      'client_operation_id': 'something-else',
      'amount': '10',
    }, idempotencyKey: key);
    expect(r.entryId, 'fbe_new');
    expect(r.persisted, isTrue);
    final post = server.calls('POST', '/api/v1/farm-book/entries').single;
    expect(post.body['client_operation_id'], key.value);
    expect(post.headers['Idempotency-Key'], key.value);
  });

  test('listEntries sends from/to aliases and parses the server row', () async {
    final list = await api.listEntries(
      farmId: 'farm1',
      fieldId: 'f1',
      from: '2026-10-01',
      to: '2026-10-31',
    );
    expect(list.single.entryId, 'fbe_1');
    expect(list.single.amount, 1500);
    expect(server.calls('GET', '/api/v1/farm-book/entries').single.query, {
      'farm_id': 'farm1',
      'field_id': 'f1',
      'from': '2026-10-01',
      'to': '2026-10-31',
    });
  });

  test('a row without an amount is a format error, not a zero', () async {
    server.entries
      ..clear()
      ..add(entryJson(id: 'x')..remove('amount'));
    await expectLater(api.listEntries(), throwsA(isA<FormatException>()));
  });

  test('createParty posts PartyIn with the key header', () async {
    const key = IdempotencyKey('k-party-1');
    final p = await api.createParty({
      'party_id': 'party_1',
      'party_type': 'customer',
      'name': 'سالم',
    }, idempotencyKey: key);
    expect(p.partyId, 'party_1');
    expect(p.partyType, 'customer');
    expect(
      server
          .calls('POST', '/api/v1/farm-book/parties')
          .single
          .headers['Idempotency-Key'],
      key.value,
    );
  });

  test('monthly/balances parse the summary verbatim', () async {
    server.monthlySummary = summaryJson(expenses: 12.5, count: 1);
    final m = await api.monthly(month: '2026-10', farmId: 'farm1');
    expect(m.month, '2026-10');
    expect(m.summary.totalExpenses, 12.5);
    expect(m.summary.isOk, isTrue);
    final b = await api.balances(farmId: 'farm1', asOf: '2026-10-26');
    expect(b.asOf, '2026-10-26');
  });

  test(
    'export: a 503 JSON body in a bytes response keeps its detail',
    () async {
      server.intercept = (o) => o.path == '/api/v1/farm-book/export'
          ? const FakeReply(503, {'detail': 'reportlab_not_installed'})
          : null;
      try {
        await api.export(month: '2026-10', format: 'pdf', farmId: 'farm1');
        fail('expected ApiException');
      } on ApiException catch (e) {
        expect(e.kind, ApiErrorKind.unavailable);
        expect(e.detail, 'reportlab_not_installed');
      }
    },
  );

  test('export rejects an unknown format before any request', () async {
    expect(
      () => api.export(month: '2026-10', format: 'xlsx'),
      throwsArgumentError,
    );
    expect(server.seen, isEmpty);
  });

  test('Content-Disposition filename is sanitised', () {
    expect(
      FarmBookApi.filenameFromDisposition(
        'attachment; filename="farm_book_2026-10.csv"',
      ),
      'farm_book_2026-10.csv',
    );
    expect(
      FarmBookApi.filenameFromDisposition(
        'attachment; filename="../../etc/passwd"',
      ),
      isNull,
    );
    expect(FarmBookApi.filenameFromDisposition(null), isNull);
  });

  test('a network failure surfaces as ApiException(network)', () async {
    server.intercept = (_) =>
        const FakeReply.fail(DioExceptionType.connectionError);
    await expectLater(
      api.listParties(),
      throwsA(
        isA<ApiException>().having((e) => e.kind, 'kind', ApiErrorKind.network),
      ),
    );
  });
}
