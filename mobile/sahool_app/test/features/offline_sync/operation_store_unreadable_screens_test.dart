// صندوق العمليّات المعلّقة موجود ومفتاحه مفقود (مراجعة D1 must_fix #2): بعد استعادة
// نسخة احتياطيّة للجهاز تعود ملفّات Hive ولا يعود مفتاح Keystore، فيرمي
// HiveOutboxStore.openEncryptedBox «keyMissingForExistingBox» عند كلّ فتح. كان كلّ
// إنشاء حقل/موسم/جدول يردّ «أعد المحاولة» إلى الأبد بلا أيّ مخرج. المطلوب: R04 يبقى
// (صفر طلبات)، والرسالة تسمّي العطل، وحذف الصندوق قرارٌ صريح بعد تأكيد ثمّ يعود
// الحفظ ممكناً — على صندوق Hive حقيقيّ على القرص وخادم HTTP محلّيّ حقيقيّ.
//
// هذا الملفّ: حياة الشاشة (ورقة الجدول، شاشة الموسم، معالج الحقل). فتح Hive نفسه داخل
// منطقة testWidgets الزمنيّة المزيّفة لا يتقدّم، فالصندوق هنا ملفٌّ حقيقيّ على القرص
// يحاكي «موجود بلا مفتاح» (فتحه يرمي keyMissingForExistingBox كما يرمي
// HiveOutboxStore)، وحذفه يحذف الملفّ؛ والسجلّات فوق «قرص» في الذاكرة يُعاد فتحه.
// صندوق Hive الحقيقيّ مغطّى في operation_store_unreadable_test.dart.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/crop_season/data/crop_season_api.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_screen.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/presentation/field_create_wizard.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_screen.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';

import '../../core/fake_http.dart';
import '../irrigation/irrigation_test_helpers.dart' show host;
import 'operation_test_support.dart';

const _schedules = '/api/v1/irrigation/schedules';
const _seasons = '/api/v1/fields/f1/seasons';

/// نصوص حرفيّة (لا ثوابت جديدة) كي يُبنى الاختبار على شجرة ما قبل الإصلاح ويحمرّ
/// سلوكيّاً هناك.
const _resetLabel = 'حذف سجلّ العمليّات غير المقروء';
const _conditionText = 'مشفّر بمفتاح لم يعد موجوداً';

/// ملفّ الصندوق «المستعاد من نسخة احتياطيّة» (مفتاحه لم يُستعَد).
File _boxFile(Directory dir) =>
    File('${dir.path}/${HiveOperationStore.boxName}.hive');

/// سجلّ عمليّات فوق ملفّ صندوقٍ لا يُقرأ ما دام موجوداً؛ حذفه قرار المستخدم.
OperationLedger _ledger(
  MemoryTokenStore tokens,
  ApiClient client,
  Directory dir,
  Map<String, String> disk,
) => OperationLedger(
  openStore: () async {
    if (_boxFile(dir).existsSync()) {
      throw const OutboxStoreException(
        OutboxStoreFailure.keyMissingForExistingBox,
      );
    }
    return MemoryOperationStore(disk);
  },
  currentOwner: () => OutboxOwner.fromAccessToken(tokens.accessToken),
  lookup: (id) => CommandStatusApi(client).exists(id),
  deleteUnreadableBox: () async => _boxFile(dir).deleteSync(),
);

Map<String, dynamic> _schedule(int n, Map<String, dynamic> body) => {
  'schedule_id': 'sch_$n',
  'name': body['name'],
  'message_ar': 'أُنشئ جدول الريّ',
};

Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 25; i++) {
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pump(const Duration(milliseconds: 50));
  }
}

void main() {
  late Directory dir;

  setUp(
    () => HttpOverrides.global = null,
  ); // flutter_test يردّ 400 لكلّ HttpClient

  group('screens over an unreadable box file', () {
    setUp(() {
      dir = Directory.systemTemp.createTempSync('op_store_screen');
      _boxFile(dir).writeAsBytesSync(List.filled(64, 7)); // مشفّر بمفتاحٍ ضاع
    });

    tearDown(() => dir.deleteSync(recursive: true));

    testWidgets('schedule sheet: names the condition, sends nothing, and after '
        'the confirmed delete the create goes out once', (t) async {
      final server = (await t.runAsync(() async {
        return LocalCommitServer.start(createPath: _schedules, make: _schedule);
      }))!;
      server.getResponses['/api/v1/irrigation/valves'] = const <Object>[];
      server.getResponses[_schedules] = const <Object>[];
      try {
        final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
        final client = realClient(server, tokens);
        final disk = <String, String>{};
        await t.pumpWidget(
          host(
            IrrigationOpsScreen(
              api: IrrigationApi(client),
              role: 'owner',
              ledger: _ledger(tokens, client, dir, disk),
            ),
          ),
        );
        await _settle(t);
        await t.tap(find.text('الجداول'));
        await t.pumpAndSettle();
        await t.tap(find.byType(FloatingActionButton));
        await _settle(t);
        final inputs = find.byType(TextField);
        await t.enterText(inputs.at(0), 'ريّ الفجر');
        await t.enterText(inputs.at(1), '06:30');
        await t.enterText(inputs.at(2), '30');
        for (var i = 0; i < 2; i++) {
          await t.tap(find.text('إنشاء الجدول'));
          await _settle(t);
        }
        expect(server.creates, isEmpty, reason: 'R04: صفر طلبات');
        expect(find.textContaining(_conditionText), findsOneWidget);
        expect(find.textContaining('أعد المحاولة'), findsNothing);

        await t.ensureVisible(find.text(_resetLabel));
        await t.tap(find.text(_resetLabel));
        await t.pumpAndSettle();
        await t.tap(find.text('حذف')); // التأكيد
        await _settle(t);
        expect(find.textContaining(_conditionText), findsNothing);

        await t.tap(find.text('إنشاء الجدول'));
        await _settle(t);
        expect(server.creates, hasLength(1));
        expect(find.text('أُنشئ جدول الريّ.'), findsOneWidget);
        expect(_boxFile(dir).existsSync(), isFalse);
        // إعادة فتح التخزين: لا عمليّة معلّقة (أُكّد الإنشاء فأُزيل سجلّه).
        expect(MemoryOperationStore(disk).records, isEmpty);
      } finally {
        await t.pumpWidget(const SizedBox());
        await t.pump(const Duration(seconds: 31));
        await t.runAsync(server.close);
      }
    });

    testWidgets('season screen: the condition is named on open; cancelling the '
        'confirm deletes nothing; confirming lets the season be saved once', (
      t,
    ) async {
      final server = (await t.runAsync(() async {
        return LocalCommitServer.start(
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
      }))!;
      try {
        final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
        final client = realClient(server, tokens);
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
              ledger: _ledger(tokens, client, dir, <String, String>{}),
            ),
          ),
        );
        await _settle(t);
        expect(find.textContaining(_conditionText), findsOneWidget);

        await t.tap(find.text(_resetLabel));
        await t.pumpAndSettle();
        await t.tap(find.text('إلغاء'));
        await _settle(t);
        expect(find.textContaining(_conditionText), findsOneWidget);
        expect(_boxFile(dir).existsSync(), isTrue);

        await t.tap(find.text(_resetLabel));
        await t.pumpAndSettle();
        await t.tap(find.text('حذف'));
        await _settle(t);
        expect(find.textContaining(_conditionText), findsNothing);

        await t.enterText(
          find.byKey(const ValueKey('season_crop_text')),
          'wheat',
        );
        await t.tap(find.byKey(const ValueKey('season_sowing')));
        await t.pumpAndSettle();
        await t.tap(find.byType(TextButton).last); // تأكيد التاريخ
        await t.pumpAndSettle();
        await t.tap(find.byKey(const ValueKey('season_submit')));
        await _settle(t);
        expect(server.creates, hasLength(1));
      } finally {
        await t.pumpWidget(const SizedBox());
        await t.pump(const Duration(seconds: 31));
        await t.runAsync(server.close);
      }
    });

    testWidgets('field wizard: the condition is named on open, before any '
        'input, with the delete action', (t) async {
      final server = (await t.runAsync(() async {
        return LocalCommitServer.start(
          createPath: '/api/v1/fields',
          make: (n, b) => {'field_id': 'fld_$n'},
        );
      }))!;
      server.getResponses['/api/v1/farms'] = const <Object>[];
      server.getResponses['/api/v1/fields'] = const <Object>[];
      try {
        final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
        final client = realClient(server, tokens);
        await t.pumpWidget(
          MaterialApp(
            theme: AppTheme.light,
            locale: const Locale('ar'),
            supportedLocales: const [Locale('ar')],
            localizationsDelegates: GlobalMaterialLocalizations.delegates,
            home: FieldCreateWizard(
              farmsApi: FarmsApi(client),
              fieldsApi: FieldsApi(client),
              createApi: FieldCreateApi(client),
              showBasemap: false,
              canCreate: true,
              ledger: _ledger(tokens, client, dir, <String, String>{}),
            ),
          ),
        );
        await _settle(t);
        expect(find.textContaining(_conditionText), findsOneWidget);
        await t.tap(find.text(_resetLabel));
        await t.pumpAndSettle();
        await t.tap(find.text('حذف'));
        await _settle(t);
        expect(find.textContaining(_conditionText), findsNothing);
        expect(
          _boxFile(dir).existsSync(),
          isFalse,
          reason: 'حُذف الصندوق غير المقروء بعد التأكيد',
        );
        expect(server.creates, isEmpty);
      } finally {
        await t.pumpWidget(const SizedBox());
        await t.pump(const Duration(seconds: 31));
        await t.runAsync(server.close);
      }
    });
  });
}
