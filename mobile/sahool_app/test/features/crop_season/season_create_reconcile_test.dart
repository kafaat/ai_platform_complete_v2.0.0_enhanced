// R02 (إنشاء الموسم) + OD-2: خادم HTTP محلّيّ حقيقيّ يلتزم بالموسم ثمّ يُسقط الردّ.
// على مستوى الـCubit مع صندوق Hive على القرص يُعاد فتحه، وعلى مستوى الشاشة (حياة
// الشاشة: إغلاقها وإعادة فتحها فوق التخزين نفسه). المطلوب: موسم واحد، مفتاح واحد،
// الحمولة الأصليّة وحدها تُرسَل، والتعديل تحديثٌ مستقلّ بعد التأكيد.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/crop_season/data/crop_season_api.dart';
import 'package:sahool_app/features/crop_season/data/season_models.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_cubit.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_logic.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_screen.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../../core/fake_http.dart';
import '../offline_sync/operation_test_support.dart';

const _create = '/api/v1/fields/f1/seasons';

Map<String, dynamic> _season(int n, Map<String, dynamic> body) => {
  'season_id': 'ssn_$n',
  'field_id': 'f1',
  'crops': body['crops'],
  'sowing_date': body['sowing_date'],
  'status': 'active',
  'row_version': 1,
  'stages': const [],
};

SeasonFormInput _input(String crop) =>
    SeasonFormInput(crop: crop, sowingDate: DateTime(2026, 3, 5));

void main() {
  setUp(() => HttpOverrides.global = null); // flutter_test يردّ 400 لكلّ HttpClient

  group('cubit + Hive on disk', () {
    late Directory dir;
    late MemoryKeyStore keys;
    late LocalCommitServer server;
    late MemoryTokenStore tokens;
    late ApiClient client;

    setUp(() async {
      dir = Directory.systemTemp.createTempSync('season_reconcile_test');
      Hive.init(dir.path);
      keys = MemoryKeyStore();
      server = await LocalCommitServer.start(createPath: _create, make: _season);
      tokens = MemoryTokenStore(accessToken: jwtFor('alice', tenant: 't1'));
      client = realClient(server, tokens);
    });

    tearDown(() async {
      await server.close();
      await Hive.close();
      dir.deleteSync(recursive: true);
    });

    SeasonFormCubit cubitOver(OperationStore store) => SeasonFormCubit(
      CropSeasonApi(client),
      fieldId: 'f1',
      ledger: ledgerFor(tokens, store, client: client),
    );

    test('R02 season: commit + dropped response + edit + reopen → one season, '
        'one key, original recovered; the edit is a separate PATCH after the '
        'user confirms', () async {
      server.plan.add(const CommitThenDrop());
      var store = await HiveOperationStore.openEncrypted(keys: keys);
      var cubit = cubitOver(store);

      await cubit.submit(_input('wheat'));
      final u = cubit.state as SeasonFormUnconfirmed;
      expect(u.outcome.messageAr, kOperationUnknownAr);
      final key = cubit.operation!.operationId;
      expect(server.creates.single.key, key);
      expect(server.resources, hasLength(1));

      await cubit.submit(_input('maize')); // تعديل ثمّ حفظ
      expect(server.creates, hasLength(1), reason: 'المسودّة لا تُرسَل');
      expect(cubit.idempotencyKey.value, key, reason: 'لا تدوير');

      await cubit.close();
      await Hive.close();
      store = await HiveOperationStore.openEncrypted(keys: keys);
      cubit = cubitOver(store);
      await cubit.restore();
      final restored = cubit.state as SeasonFormUnconfirmed;
      expect(restored.outcome.record.operationId, key);
      expect(restored.outcome.record.payload['crops'], ['wheat']);
      expect(restored.outcome.draftChanges.single.after, ['maize']);

      await cubit.recover();
      final rec = cubit.state as SeasonFormRecovered;
      expect(rec.season.seasonId, 'ssn_1');
      expect(rec.pendingEdits.single.key, 'crops');
      expect(server.resources, hasLength(1), reason: 'موسم واحد');
      expect(server.creates.map((c) => c.key).toSet(), {key});
      expect(server.creates.every((c) => (c.body!['crops'] as List).first == 'wheat'), isTrue);
      expect(
        server.requests.where((r) => r.method == 'PATCH'),
        isEmpty,
        reason: 'لا تحديث قبل تأكيد المستخدم',
      );

      server.patchResponses['/api/v1/fields/f1/seasons/ssn_1'] = {
        ..._season(1, {'crops': ['maize'], 'sowing_date': '2026-03-05'}),
        'row_version': 2,
      };
      await cubit.applyPendingEdits();
      final saved = (cubit.state as SeasonFormSaved).season;
      expect(saved.crops, ['maize']);
      final patch = server.requests.singleWhere((r) => r.method == 'PATCH');
      expect(patch.body, {'crops': ['maize'], 'base_version': 1});
      expect(patch.key, isNot(key), reason: 'التحديث عمليّة مستقلّة بمفتاحها');
      expect(server.resources, hasLength(1));
      await cubit.close();
    });
  });

  testWidgets('R02 season screen: close after the unknown outcome keeps the '
      'edit; reopening shows the recover panel without a create button; '
      'recovery binds the real season', (t) async {
    final server = (await t.runAsync(
      () => LocalCommitServer.start(createPath: _create, make: _season),
    ))!;
    Season? popped;
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final client = realClient(server, tokens);
      final disk = <String, String>{};
      server.plan.add(const CommitThenDrop());
      t.view.physicalSize = const Size(1080, 3200);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);

      Widget app(OperationLedger ledger) => MaterialApp(
        theme: AppTheme.light,
        locale: const Locale('ar'),
        supportedLocales: const [Locale('ar')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () async {
                  popped = await Navigator.of(context).push<Season>(
                    MaterialPageRoute(
                      builder: (_) => SeasonFormScreen(
                        fieldId: 'f1',
                        api: CropSeasonApi(client),
                        today: DateTime(2026, 3, 5),
                        ledger: ledger,
                      ),
                    ),
                  );
                },
                child: const Text('افتح'),
              ),
            ),
          ),
        ),
      );

      await t.pumpWidget(app(ledgerFor(tokens, MemoryOperationStore(disk), client: client)));
      await t.tap(find.text('افتح'));
      await _settle(t);
      await t.enterText(find.byKey(const ValueKey('season_crop_text')), 'wheat');
      await t.tap(find.byKey(const ValueKey('season_sowing')));
      await t.pumpAndSettle();
      await t.tap(find.byType(TextButton).last); // تأكيد التاريخ
      await t.pumpAndSettle();
      await t.tap(find.byKey(const ValueKey('season_submit')));
      await _settle(t);

      expect(find.text(kOperationUnknownAr), findsOneWidget);
      expect(find.byKey(const ValueKey('season_submit')), findsNothing);
      expect(find.text(kRecoverActionAr), findsOneWidget);
      final key = server.creates.single.key;

      // تعديل ثمّ مغادرة الشاشة (زرّ الرجوع).
      await t.enterText(find.byKey(const ValueKey('season_crop_text')), 'maize');
      await t.pump();
      await t.binding.handlePopRoute(); // رجوع النظام
      await _settle(t);
      expect(server.creates, hasLength(1));

      // إعادة الفتح فوق «القرص» نفسه بمخزن جديد.
      final reopened = MemoryOperationStore(disk);
      expect(reopened.records.single.draft?['crops'], ['maize']);
      await t.pumpWidget(const SizedBox());
      await t.pumpWidget(app(ledgerFor(tokens, reopened, client: client)));
      await t.tap(find.text('افتح'));
      await _settle(t);
      expect(find.text(kOperationUnknownAr), findsOneWidget);
      expect(find.text('المحصول: wheat ← maize'), findsOneWidget);
      expect(find.byKey(const ValueKey('season_submit')), findsNothing);

      await t.tap(find.text(kRecoverActionAr));
      await _settle(t);
      expect(find.byKey(const ValueKey('pending-op-recovered')), findsOneWidget);
      await t.tap(find.byKey(const ValueKey('season_keep_recovered')));
      await _settle(t);
      expect(popped?.seasonId, 'ssn_1');
      expect(server.resources, hasLength(1));
      expect(server.creates.map((c) => c.key).toSet(), {key});
      expect(server.creates.every((c) => (c.body!['crops'] as List).first == 'wheat'), isTrue);
    } finally {
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });

  testWidgets('OD-2 season screen: a 409 shows the recover wording, no create '
      'button, and the retry keeps the key', (t) async {
    final server = (await t.runAsync(
      () => LocalCommitServer.start(createPath: _create, make: _season),
    ))!;
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final client = realClient(server, tokens);
      server.plan.add(
        const Status(409, {
          'detail': {'reason': 'payload_mismatch'},
        }),
      );
      t.view.physicalSize = const Size(1080, 3200);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      await t.pumpWidget(
        MaterialApp(
          theme: AppTheme.light,
          locale: const Locale('ar'),
          supportedLocales: const [Locale('ar')],
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          home: SeasonFormScreen(
            fieldId: 'f1',
            api: CropSeasonApi(client),
            today: DateTime(2026, 3, 5),
            ledger: ledgerFor(tokens, MemoryOperationStore(), client: client),
          ),
        ),
      );
      await _settle(t);
      await t.enterText(find.byKey(const ValueKey('season_crop_text')), 'wheat');
      await t.tap(find.byKey(const ValueKey('season_sowing')));
      await t.pumpAndSettle();
      await t.tap(find.byType(TextButton).last);
      await t.pumpAndSettle();
      await t.tap(find.byKey(const ValueKey('season_submit')));
      await _settle(t);

      expect(find.text(kOperationConflictAr), findsOneWidget);
      expect(find.text(kRecoverActionAr), findsOneWidget);
      expect(find.byKey(const ValueKey('season_submit')), findsNothing);
      expect(find.text('حفظ الموسم'), findsNothing);

      await t.enterText(find.byKey(const ValueKey('season_crop_text')), 'maize');
      await t.tap(find.text(kRecoverActionAr));
      await _settle(t);
      expect(server.creates, hasLength(2));
      expect(server.creates.map((c) => c.key).toSet(), hasLength(1));
      expect((server.creates.last.body!['crops'] as List).first, 'wheat');
    } finally {
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });
}

/// يترك الإدخال/الإخراج الحقيقيّ يتقدّم ثمّ يرسم (بلا pumpAndSettle أثناء التحميل).
Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 25; i++) {
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pump(const Duration(milliseconds: 50));
  }
}
