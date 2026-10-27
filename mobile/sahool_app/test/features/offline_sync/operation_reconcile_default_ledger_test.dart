// تكذيب على مستوى التطبيق بالتوصيل الافتراضيّ (بلا أيّ حقن لسجلّ العمليّات): الجلسة
// من AuthService، والتخزين صندوق Hive المشفّر الحقيقيّ على القرص، والشبكة خادم HTTP
// محلّيّ حقيقيّ يلتزم ثمّ يُسقط الردّ. يستعمل واجهات موجودة في شجرة الأساس أيضاً،
// فيُشغَّل عليها كما هو: هناك يُنشئ تعديلُ النموذج بعد النتيجة المجهولة سجلّاً ثانياً
// بمفتاح جديد. (ورقة الريّ: schedule_create_reconcile_test بسجلّ محقون، وR04 بلا حقن
// في operation_store_failure_test.)
import 'dart:io';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/crop_season/data/crop_season_api.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_cubit.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_logic.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/maps/draw/field_save_cubit.dart';
import 'package:sahool_app/services/auth_service.dart';

import '../../core/local_commit_server.dart';
import 'outbox_test_support.dart' show jwtFor;

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

FieldCreateDraft _field(String name) => FieldCreateDraft(
  name: name,
  geometry: _geometry,
  farmId: 'farm_1',
  irrigationType: 'drip',
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory dir;

  setUpAll(() async {
    dir = Directory.systemTemp.createTempSync('default_ledger_test');
    Hive.init(dir.path);
    FlutterSecureStorage.setMockInitialValues({});
    await AuthService.instance.saveToken(jwtFor('alice', tenant: 't1'));
  });

  tearDownAll(() async {
    await Hive.close();
    dir.deleteSync(recursive: true);
  });

  setUp(() => HttpOverrides.global = null); // flutter_test يردّ 400 لكلّ HttpClient

  test('field: commit + dropped response, then an edited save → still one '
      'field and one key (no re-create with a new key)', () async {
    final server = await LocalCommitServer.start(
      createPath: '/api/v1/fields',
      make: (n, b) => {'field_id': 'fld_$n', 'name_ar': b['name']},
    );
    try {
      final client = realClient(server, const AuthServiceTokenStore());
      server.plan.add(const CommitThenDrop());
      final cubit = FieldSaveCubit(
        createApi: FieldCreateApi(client),
        fieldsApi: FieldsApi(client),
        cache: ResponseCache(),
      );
      await cubit.save(_field('الحقل الشرقيّ'));
      expect(server.resources, hasLength(1));
      await cubit.save(_field('الحقل الغربيّ'));
      expect(server.resources, hasLength(1), reason: 'مورد واحد');
      expect(server.creates.map((c) => c.key).toSet(), hasLength(1));
      expect(
        server.creates.where((c) => c.body!['name'] == 'الحقل الغربيّ'),
        isEmpty,
        reason: 'المسودّة المعدّلة لا تُرسَل إنشاءً',
      );
      await cubit.close();
    } finally {
      await server.close();
    }
  });

  test('season: commit + dropped response, then an edited submit → still one '
      'season and one key', () async {
    final server = await LocalCommitServer.start(
      createPath: '/api/v1/fields/f1/seasons',
      make: (n, b) => {
        'season_id': 'ssn_$n',
        'field_id': 'f1',
        'crops': b['crops'],
        'status': 'active',
      },
    );
    try {
      final client = realClient(server, const AuthServiceTokenStore());
      server.plan.add(const CommitThenDrop());
      final cubit = SeasonFormCubit(CropSeasonApi(client), fieldId: 'f1');
      await cubit.submit(
        SeasonFormInput(crop: 'wheat', sowingDate: DateTime(2026, 3, 5)),
      );
      expect(server.resources, hasLength(1));
      await cubit.submit(
        SeasonFormInput(crop: 'maize', sowingDate: DateTime(2026, 3, 5)),
      );
      expect(server.resources, hasLength(1), reason: 'موسم واحد');
      expect(server.creates.map((c) => c.key).toSet(), hasLength(1));
      await cubit.close();
    } finally {
      await server.close();
    }
  });
}
