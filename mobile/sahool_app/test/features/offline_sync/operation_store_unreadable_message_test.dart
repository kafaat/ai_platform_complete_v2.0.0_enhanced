// صندوق العمليّات المعلّقة موجود ومفتاحه مفقود (مراجعة D1 must_fix #2) على صندوق Hive
// حقيقيّ وبالتوصيل الإنتاجيّ للحذف (بلا حقن): الرسالة تسمّي العطل لا «أعد المحاولة»،
// ولا طلب شبكة. لا يستعمل إلّا واجهات موجودة قبل الإصلاح ونصوصاً حرفيّة، فيُبنى على
// تلك الشجرة ويحمرّ سلوكيّاً هناك (كانت الرسالة «تعذّر حفظ الطلب … أعد المحاولة»).
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

import '../../core/fake_http.dart';
import 'operation_test_support.dart';

const _schedules = '/api/v1/irrigation/schedules';

void main() {
  late Directory dir;
  late LocalCommitServer server;

  setUp(() async {
    dir = Directory.systemTemp.createTempSync('op_store_unreadable_msg');
    Hive.init(dir.path);
    // ملفّات الصندوق «المستعادة من نسخة احتياطيّة» بمفتاحٍ لم يُستعَد.
    final box = await HiveOutboxStore.openEncryptedBox(
      keys: MemoryKeyStore(),
      name: HiveOperationStore.boxName,
    );
    await box.put('op_from_before', '{"opaque":true}');
    await box.close();
    server = await LocalCommitServer.start(
      createPath: _schedules,
      make: (n, b) => {'schedule_id': 'sch_$n'},
    );
  });

  tearDown(() async {
    await server.close();
    await Hive.close();
    dir.deleteSync(recursive: true);
  });

  test('a box whose key is gone: zero sends on every submit, and the message '
      'names the condition and the delete action instead of "retry"', () async {
    final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
    final client = realClient(server, tokens);
    final keys = MemoryKeyStore();
    final op = CreateOperation(
      ledger: OperationLedger(
        openStore: () => HiveOperationStore.openEncrypted(keys: keys),
        currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
      ),
      kind: 'irrigation_schedule.create',
      method: 'POST',
      path: _schedules,
      send: (p, k) =>
          IrrigationApi(client).createSchedule(p, idempotencyKey: k),
    );
    for (var i = 0; i < 3; i++) {
      final o = await op.submit({
        'name': 'ريّ الفجر',
        'start_time': '06:30',
        'duration_min': 30,
        'enabled': true,
      });
      expect(o, isA<CreateNotSaved>());
      final msg = (o as CreateNotSaved).messageAr;
      expect(msg, contains('مشفّر بمفتاح لم يعد موجوداً'));
      expect(msg, contains('احذف'));
      expect(msg, isNot(contains('أعد المحاولة')));
    }
    expect(server.requests, isEmpty, reason: 'R04: لا طلب شبكة');
    expect(keys.value, isNull, reason: 'لا مفتاح جديد فوق صندوقٍ قائم');
  });
}
