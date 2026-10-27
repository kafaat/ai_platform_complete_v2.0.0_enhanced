// R01 (إنشاء الحقل): خادم HTTP محلّيّ حقيقيّ يلتزم بالحقل ثمّ يُسقط الردّ، ثمّ يعدّل
// المستخدم النموذج، ثمّ يُعاد فتح التخزين (Hive على القرص) والـCubit. المطلوب: مورد
// واحد، لا مفتاح جديد تلقائيّاً، استعادة الأصل ثمّ عرض التعديل.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/maps/draw/field_save_cubit.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../../../core/fake_http.dart';
import '../../offline_sync/operation_test_support.dart';

const _geometry = {
  'type': 'Polygon',
  'coordinates': [
    [
      [44.2, 15.35],
      [44.21, 15.35],
      [44.21, 15.36],
      [44.2, 15.35],
    ],
  ],
};

FieldCreateDraft _draft(String name) => FieldCreateDraft(
  name: name,
  geometry: _geometry,
  farmId: 'farm_1',
  irrigationType: 'drip',
  boundarySource: 'manual',
);

void main() {
  late Directory dir;
  late MemoryKeyStore keys;
  late LocalCommitServer server;
  late MemoryTokenStore tokens;
  late ApiClient client;

  setUp(() async {
    dir = Directory.systemTemp.createTempSync('field_reconcile_test');
    Hive.init(dir.path);
    keys = MemoryKeyStore();
    server = await LocalCommitServer.start(
      createPath: '/api/v1/fields',
      make: (n, body) => {
        'field_id': 'fld_$n',
        'name_ar': body['name'],
        'area_ha': 12.5,
      },
    );
    tokens = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
    client = realClient(server, tokens);
  });

  tearDown(() async {
    await server.close();
    await Hive.close();
    dir.deleteSync(recursive: true);
  });

  FieldSaveCubit cubitOver(OperationStore store) => FieldSaveCubit(
    createApi: FieldCreateApi(client),
    fieldsApi: FieldsApi(client),
    cache: ResponseCache(),
    ledger: ledgerFor(tokens, store, client: client),
  );

  test('R01: commit, dropped response, edited draft, storage reopened → one '
      'field, one key, original recovered, edit shown not sent', () async {
    server.plan.add(const CommitThenDrop());
    var store = await HiveOperationStore.openEncrypted(keys: keys);
    var cubit = cubitOver(store);

    await cubit.save(_draft('الحقل الشرقيّ'));
    expect(server.resources, hasLength(1), reason: 'الخادم التزم');
    final u = cubit.state as FieldSaveUnconfirmed;
    expect(u.outcome.messageAr, kOperationUnknownAr);
    expect(u.outcome.messageAr, contains('لم نتأكد من نتيجة الحفظ'));
    final key = cubit.createKey!.value;
    expect(server.creates.single.key, key);

    // المستخدم يعدّل الاسم ويضغط حفظ: لا طلب، المسودّة تُحفظ وتُعرض فروقها.
    await cubit.save(_draft('الحقل الغربيّ'));
    expect(server.creates, hasLength(1), reason: 'لا إنشاء بالمسودّة');
    final edited = cubit.state as FieldSaveUnconfirmed;
    expect(edited.outcome.draftChanges.single.key, 'name');
    expect(edited.outcome.draftChanges.single.after, 'الحقل الغربيّ');
    expect(cubit.createKey!.value, key, reason: 'لا تدوير للمفتاح');

    // إغلاق الشاشة والتطبيق ثمّ الفتح من جديد فوق الملفّات نفسها.
    await cubit.close();
    await Hive.close();
    store = await HiveOperationStore.openEncrypted(keys: keys);
    cubit = cubitOver(store);
    await cubit.restore();
    final restored = cubit.state as FieldSaveUnconfirmed;
    expect(restored.outcome.record.operationId, key);
    expect(restored.outcome.record.payload['name'], 'الحقل الشرقيّ');
    expect(restored.outcome.draftChanges.single.after, 'الحقل الغربيّ');

    // الاستعادة: نفس المفتاح ونفس الحمولة الأصليّة ⇒ الحقل المُلتزَم نفسه.
    await cubit.recover(draft: _draft('الحقل الغربيّ'));
    final done = cubit.state as FieldSaveDone;
    expect(done.fieldId, 'fld_1');
    expect(done.pendingEdits.single.key, 'name');
    expect(done.pendingEdits.single.before, 'الحقل الشرقيّ');
    expect(done.pendingEdits.single.after, 'الحقل الغربيّ');

    expect(server.resources, hasLength(1), reason: 'مورد واحد');
    expect(server.creates.map((c) => c.key).toSet(), {key});
    expect(
      server.creates.every((c) => c.body!['name'] == 'الحقل الشرقيّ'),
      isTrue,
      reason: 'لم تُرسَل المسودّة ضمن إعادة الإنشاء',
    );
    expect(store.records, isEmpty);
    await cubit.close();
  });

  test('OD-2: after a 409 no request carries a different key for the field '
      'create', () async {
    server.plan.add(
      const Status(409, {'detail': 'الأمر قيد المعالجة — أعد المحاولة لاحقاً'}),
    );
    final store = MemoryOperationStore();
    final cubit = cubitOver(store);
    await cubit.save(_draft('الحقل الشرقيّ'));
    final u = cubit.state as FieldSaveUnconfirmed;
    expect(u.outcome.messageAr, kOperationInProgressAr);
    await cubit.save(_draft('الحقل الغربيّ')); // تعديل ثمّ حفظ
    await cubit.recover(draft: _draft('الحقل الغربيّ'));
    expect(cubit.state, isA<FieldSaveDone>());
    expect(server.creates, hasLength(2));
    expect(server.creates.map((c) => c.key).toSet(), hasLength(1));
    expect(server.creates.last.body!['name'], 'الحقل الشرقيّ');
    await cubit.close();
  });
}
