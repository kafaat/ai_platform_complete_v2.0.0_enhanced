// صندوق العمليّات المعلّقة موجود ومفتاحه مفقود (مراجعة D1 must_fix #2): بعد استعادة
// نسخة احتياطيّة للجهاز تعود ملفّات Hive ولا يعود مفتاح Keystore، فيرمي
// HiveOutboxStore.openEncryptedBox «keyMissingForExistingBox» عند كلّ فتح. كان كلّ
// إنشاء حقل/موسم/جدول يردّ «أعد المحاولة» إلى الأبد بلا أيّ مخرج. المطلوب: R04 يبقى
// (صفر طلبات)، والرسالة تسمّي العطل، وحذف الصندوق قرارٌ صريح بعد تأكيد ثمّ يعود
// الحفظ ممكناً — على صندوق Hive حقيقيّ على القرص وخادم HTTP محلّيّ حقيقيّ.
// هذا الملفّ: السجلّ والـCubits؛ حياة الشاشة في operation_store_unreadable_screens_test.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/crop_season/data/crop_season_api.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_cubit.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_logic.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/maps/draw/field_save_cubit.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

import '../../core/fake_http.dart';
import 'operation_test_support.dart';

const _schedules = '/api/v1/irrigation/schedules';
const _seasons = '/api/v1/fields/f1/seasons';

/// صندوقٌ قائم على القرص بمفتاحٍ ضاع (مخزن مفاتيح آخر لا يُعاد).
Future<void> _restoredBackupBox() async {
  final lostKeys = MemoryKeyStore();
  final box = await HiveOutboxStore.openEncryptedBox(
    keys: lostKeys,
    name: HiveOperationStore.boxName,
  );
  await box.put('op_from_before', '{"opaque":true}');
  await box.close();
}

/// التوصيل الإنتاجيّ نفسه (صندوق Hive مشفّر) بمخزن مفاتيح فارغ — بلا حقن حذف.
OperationLedger _ledger(
  MemoryTokenStore tokens,
  ApiClient client,
  MemoryKeyStore keys,
) => OperationLedger(
  openStore: () => HiveOperationStore.openEncrypted(keys: keys),
  currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
  lookup: (id) => CommandStatusApi(client).exists(id),
);

Map<String, dynamic> _schedule(int n, Map<String, dynamic> body) => {
  'schedule_id': 'sch_$n',
  'name': body['name'],
  'message_ar': 'أُنشئ جدول الريّ',
};

void main() {
  late Directory dir;

  setUp(
    () => HttpOverrides.global = null,
  ); // flutter_test يردّ 400 لكلّ HttpClient

  group('ledger + cubits on a real Hive box', () {
    late MemoryKeyStore keys;
    late LocalCommitServer server;
    late MemoryTokenStore tokens;
    late ApiClient client;

    setUp(() async {
      dir = Directory.systemTemp.createTempSync('op_store_unreadable');
      Hive.init(dir.path);
      await _restoredBackupBox();
      keys = MemoryKeyStore();
      tokens = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
    });

    tearDown(() async {
      await server.close();
      await Hive.close();
      dir.deleteSync(recursive: true);
    });

    test('every submit is refused with zero sends and a message naming the '
        'condition (not "retry"); the user-confirmed delete opens a fresh box '
        'and the next submit sends exactly once', () async {
      server = await LocalCommitServer.start(
        createPath: _schedules,
        make: _schedule,
      );
      client = realClient(server, tokens);
      final ledger = _ledger(tokens, client, keys);
      final op = CreateOperation(
        ledger: ledger,
        kind: 'irrigation_schedule.create',
        method: 'POST',
        path: _schedules,
        send: (p, k) =>
            IrrigationApi(client).createSchedule(p, idempotencyKey: k),
      );
      const payload = {
        'name': 'ريّ الفجر',
        'start_time': '06:30',
        'duration_min': 30,
        'enabled': true,
      };

      final restored = await op.restore();
      expect(restored, isA<CreateNotSaved>(), reason: 'يُسمّى العطل عند الفتح');
      for (var i = 0; i < 3; i++) {
        final o = await op.submit(Map.of(payload));
        expect(o, isA<CreateNotSaved>());
        expect((o as CreateNotSaved).storeUnreadable, isTrue);
        expect(o.messageAr, kOperationStoreUnreadableAr);
        expect(o.messageAr, isNot(kOperationNotSavedAr));
      }
      expect(server.requests, isEmpty, reason: 'R04: لا طلب شبكة إطلاقاً');
      expect(ledger.storeUnreadable, isTrue);
      expect(
        await Hive.boxExists(HiveOperationStore.boxName),
        isTrue,
        reason: 'لا حذف صامت',
      );

      expect(await ledger.resetUnreadableStore(), isTrue);
      expect(ledger.storeUnreadable, isFalse);
      expect(keys.value, isNotNull, reason: 'مفتاح جديد لصندوق جديد');

      final o = await op.submit(Map.of(payload));
      expect(o, isA<CreateConfirmed>());
      expect(server.creates, hasLength(1));
      expect(server.resources, hasLength(1));

      // إعادة فتح التخزين: الصندوق الجديد يُقرأ بمفتاحه.
      await Hive.close();
      final reopened = await HiveOperationStore.openEncrypted(keys: keys);
      expect(reopened.records, isEmpty, reason: 'أُكّد الإنشاء فأُزيل سجلّه');
    });

    test('field cubit: refused with the condition named, reset after confirm, '
        'then one create', () async {
      server = await LocalCommitServer.start(
        createPath: '/api/v1/fields',
        make: (n, b) => {'field_id': 'fld_$n', 'name_ar': b['name']},
      );
      client = realClient(server, tokens);
      final cubit = FieldSaveCubit(
        createApi: FieldCreateApi(client),
        fieldsApi: FieldsApi(client),
        cache: ResponseCache(),
        ledger: _ledger(tokens, client, keys),
      );
      const draft = FieldCreateDraft(
        name: 'الحقل الشرقيّ',
        geometry: {'type': 'Polygon', 'coordinates': []},
      );
      await cubit.restore();
      expect((cubit.state as FieldSaveFailed).storeUnreadable, isTrue);
      await cubit.save(draft);
      final failed = cubit.state as FieldSaveFailed;
      expect(failed.storeUnreadable, isTrue);
      expect(failed.view.messageAr, kOperationStoreUnreadableAr);
      expect(server.requests, isEmpty);

      await cubit.resetUnreadableStore();
      expect(cubit.state, isA<FieldSaveIdle>());
      await cubit.save(draft);
      expect(cubit.state, isA<FieldSaveDone>());
      expect(server.creates, hasLength(1));
      await cubit.close();
    });

    test('season cubit: refused with the condition named, reset after confirm, '
        'then one create', () async {
      server = await LocalCommitServer.start(
        createPath: _seasons,
        make: (n, b) => {
          'season_id': 'ssn_$n',
          'field_id': 'f1',
          'crops': b['crops'],
          'sowing_date': b['sowing_date'],
          'status': 'active',
          'stages': const [],
        },
      );
      client = realClient(server, tokens);
      final cubit = SeasonFormCubit(
        CropSeasonApi(client),
        fieldId: 'f1',
        ledger: _ledger(tokens, client, keys),
      );
      final input = SeasonFormInput(
        crop: 'wheat',
        sowingDate: DateTime(2026, 3, 5),
      );
      await cubit.submit(input);
      final s = cubit.state as SeasonFormEditing;
      expect(s.storeUnreadable, isTrue);
      expect(s.submitError, kOperationStoreUnreadableAr);
      expect(server.requests, isEmpty);

      await cubit.resetUnreadableStore();
      await cubit.submit(input);
      expect(cubit.state, isA<SeasonFormSaved>());
      expect(server.creates, hasLength(1));
      await cubit.close();
    });

    test('reset is refused for any other failure (no silent delete)', () async {
      server = await LocalCommitServer.start(
        createPath: _schedules,
        make: _schedule,
      );
      var deletes = 0;
      final ledger = OperationLedger(
        openStore: () async =>
            throw const OutboxStoreException(OutboxStoreFailure.keyStorage),
        currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
        deleteUnreadableBox: () async => deletes++,
      );
      expect(await ledger.openFor('irrigation_schedule.create'), isNull);
      expect(ledger.storeUnreadable, isFalse);
      expect(await ledger.resetUnreadableStore(), isFalse);
      expect(deletes, 0);
    });
  });
}
