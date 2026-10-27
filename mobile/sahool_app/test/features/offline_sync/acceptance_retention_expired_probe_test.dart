// Acceptance probe (D1 x D4 contract seam): the server's D4 contract answers a
// replay older than its retention window with
//   409 {detail: {code: idempotency_conflict, reason: retention_expired, ...}}
// (services/sahool-platform/api/idempotency.py). The command was executed, so the
// mobile ledger must not treat this 409 as a proven refusal (saved_locally), which
// would make the operation dismissible and re-creatable under a new key.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../../core/fake_http.dart';
import 'operation_test_support.dart';

const _path = '/api/v1/irrigation/schedules';
const _payload = {
  'name': 'ريّ الفجر',
  'start_time': '06:30',
  'duration_min': 30,
  'enabled': true,
};

void main() {
  test('a server 409 retention_expired after a committed, dropped create is '
      'not read as "never executed"', () async {
    final server = await LocalCommitServer.start(
      createPath: _path,
      make: (n, body) => {'schedule_id': 'sch_$n', 'name': body['name']},
    );
    addTearDown(server.close);
    final tokens = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
    final ApiClient client = realClient(server, tokens);
    server.plan
      ..add(const CommitThenDrop())
      ..add(
        const Status(409, {
          'detail': {
            'code': 'idempotency_conflict',
            'reason': 'retention_expired',
            'message_ar': 'انقضت مدّة الاحتفاظ بنتيجة هذه العملية على الخادم.',
          },
        }),
      );
    final op = CreateOperation(
      ledger: ledgerFor(tokens, MemoryOperationStore(), client: client),
      kind: 'irrigation_schedule.create',
      method: 'POST',
      path: _path,
      send: (p, k) => IrrigationApi(client).createSchedule(p, idempotencyKey: k),
    );

    expect(await op.submit(Map.of(_payload)), isA<CreateUnconfirmed>());
    expect(server.resources, hasLength(1), reason: 'the server committed');

    final outcome = await op.recover();
    expect(outcome, isNot(isA<CreateRejected>()),
        reason: 'retention_expired is not a refusal before execution');
    expect(op.record!.mayHaveExecuted, isTrue,
        reason: 'saved_locally would allow a payload change / dismiss and a '
            'second create under a new key');
    expect(await op.dismiss(), op.record?.state == OperationState.needsReconciliation,
        reason: 'only needs_reconciliation may be closed by the user');
  });
}
