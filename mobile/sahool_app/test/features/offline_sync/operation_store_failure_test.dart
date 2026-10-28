// R04 بالتوصيل الافتراضيّ (بلا حقن): التخزين المحلّيّ غير متاح (Hive لم يُهيَّأ في
// هذه العزلة) ⇒ لا يخرج أيّ طلب إنشاء إلى الخادم المحلّيّ الحقيقيّ. يستعمل واجهات
// موجودة في شجرة الأساس أيضاً، فيُشغَّل عليها كما هو (هناك يُرسَل الطلب بلا سجلّ).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/crop_season/data/crop_season_api.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_cubit.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_logic.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_screen.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/maps/draw/field_save_cubit.dart';
import 'package:sahool_app/services/auth_service.dart';

import '../../core/local_commit_server.dart';
import '../irrigation/irrigation_test_helpers.dart' show host;
import 'outbox_test_support.dart' show jwtFor;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    FlutterSecureStorage.setMockInitialValues({});
    await AuthService.instance.saveToken(jwtFor('alice', tenant: 't1'));
  });

  setUp(() => HttpOverrides.global = null); // flutter_test يردّ 400 لكلّ HttpClient

  test('R04 field: no local record ⇒ zero create requests', () async {
    final server = await LocalCommitServer.start(
      createPath: '/api/v1/fields',
      make: (n, b) => {'field_id': 'fld_$n'},
    );
    try {
      final client = realClient(server, const AuthServiceTokenStore());
      final cubit = FieldSaveCubit(
        createApi: FieldCreateApi(client),
        fieldsApi: FieldsApi(client),
        cache: ResponseCache(),
      );
      await cubit.save(
        const FieldCreateDraft(
          name: 'الحقل الشرقيّ',
          geometry: {'type': 'Polygon', 'coordinates': []},
        ),
      );
      expect(server.requests, isEmpty, reason: 'لا طلب شبكة إطلاقاً');
      expect(cubit.state, isA<FieldSaveFailed>());
      await cubit.close();
    } finally {
      await server.close();
    }
  });

  test('R04 season: no local record ⇒ zero create requests', () async {
    final server = await LocalCommitServer.start(
      createPath: '/api/v1/fields/f1/seasons',
      make: (n, b) => {'season_id': 'ssn_$n'},
    );
    try {
      final client = realClient(server, const AuthServiceTokenStore());
      final cubit = SeasonFormCubit(CropSeasonApi(client), fieldId: 'f1');
      await cubit.submit(
        SeasonFormInput(crop: 'wheat', sowingDate: DateTime(2026, 3, 5)),
      );
      expect(server.requests, isEmpty, reason: 'لا طلب شبكة إطلاقاً');
      expect(cubit.state, isA<SeasonFormEditing>());
      await cubit.close();
    } finally {
      await server.close();
    }
  });

  testWidgets('R04 schedule sheet: no local record ⇒ zero create requests and '
      'an honest "nothing was sent" message', (t) async {
    final server = (await t.runAsync(
      () => LocalCommitServer.start(
        createPath: '/api/v1/irrigation/schedules',
        make: (n, b) => {'schedule_id': 'sch_$n'},
      ),
    ))!;
    server.getResponses['/api/v1/irrigation/valves'] = const <Object>[];
    server.getResponses['/api/v1/irrigation/schedules'] = const <Object>[];
    Future<void> settle() async {
      for (var i = 0; i < 25; i++) {
        await t.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 20)),
        );
        await t.pump(const Duration(milliseconds: 50));
      }
    }

    try {
      final client = realClient(server, const AuthServiceTokenStore());
      await t.pumpWidget(
        host(IrrigationOpsScreen(api: IrrigationApi(client), role: 'owner')),
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
      expect(
        server.requests.where((r) => r.method == 'POST'),
        isEmpty,
        reason: 'لا طلب إنشاء إطلاقاً',
      );
      expect(find.textContaining('فلم يُرسَل شيء'), findsOneWidget);
    } finally {
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });
}
