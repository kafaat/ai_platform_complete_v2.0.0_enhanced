// معالج إنشاء الحقل على خادم HTTP محلّيّ حقيقيّ: R01 على مستوى الشاشة (إغلاق المعالج
// بعد نتيجة مجهولة ثمّ إعادة فتحه فوق التخزين نفسه) وOD-2 (409 يعرض صياغة الاستعادة
// بلا زرّ حفظ، والاستعادة تُبقي المفتاح).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/farms/data/farms_api.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/fields/presentation/field_create_wizard.dart';
import 'package:sahool_app/features/maps/draw/field_create_api.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../../../core/fake_http.dart';
import '../../offline_sync/operation_test_support.dart';

class _App {
  _App(this.client, this.ledger);
  final ApiClient client;
  final OperationLedger ledger;
  Object? workspaceArg;

  Widget build() => MaterialApp(
    theme: AppTheme.light,
    locale: const Locale('ar'),
    supportedLocales: const [Locale('ar')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    onGenerateRoute: (s) => s.name == 'field_workspace'
        ? MaterialPageRoute<void>(
            settings: s,
            builder: (_) {
              workspaceArg = s.arguments;
              return const Scaffold(body: Text('مساحة العمل'));
            },
          )
        : null,
    home: Builder(
      builder: (context) => Scaffold(
        body: Center(
          child: FilledButton(
            onPressed: () => Navigator.of(context).push<bool>(
              MaterialPageRoute(
                builder: (_) => FieldCreateWizard(
                  farmsApi: FarmsApi(client),
                  fieldsApi: FieldsApi(client),
                  createApi: FieldCreateApi(client),
                  showBasemap: false,
                  canCreate: true,
                  ledger: ledger,
                ),
              ),
            ),
            child: const Text('افتح'),
          ),
        ),
      ),
    ),
  );
}

Future<LocalCommitServer> _server(WidgetTester t) async {
  final s = (await t.runAsync(
    () => LocalCommitServer.start(
      createPath: '/api/v1/fields',
      make: (n, body) => {
        'field_id': 'fld_$n',
        'name_ar': body['name'],
        'area_ha': 12.34,
      },
    ),
  ))!;
  s.getResponses['/api/v1/farms'] = [
    {'farm_id': 'farm_1', 'name': 'مزرعة الوادي'},
  ];
  // حقل قائم صغير يتمركز عنده الرسم (كما في field_create_wizard_test).
  s.getResponses['/api/v1/fields'] = [
    {
      'field_id': 'fld_old',
      'name_ar': 'الحقل القديم',
      'area_ha': 0.3,
      'geometry': {
        'type': 'Polygon',
        'coordinates': [
          [
            [44.2, 15.35],
            [44.2003, 15.35],
            [44.2003, 15.3503],
            [44.2, 15.35],
          ],
        ],
      },
    },
  ];
  return s;
}

Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 25; i++) {
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pump(const Duration(milliseconds: 50));
  }
}

Future<void> _open(WidgetTester t, _App app) async {
  await t.pumpWidget(app.build());
  await t.tap(find.text('افتح'));
  await _settle(t);
}

Future<void> _next(WidgetTester t) async {
  await t.tap(find.byKey(const ValueKey('wizard-next')));
  await t.pumpAndSettle();
}

Future<void> _tapMap(WidgetTester t, Offset d) async {
  await t.tapAt(t.getCenter(find.byType(FlutterMap)) + d);
  await t.pump(const Duration(milliseconds: 400));
}

/// يملأ المعالج حتى خطوة المراجعة ثمّ يضغط «حفظ الحقل».
Future<void> _fillAndSave(WidgetTester t, String name) async {
  await t.enterText(find.byType(TextFormField).first, name);
  await t.pump();
  await _next(t);
  await _tapMap(t, const Offset(-110, -60));
  await _tapMap(t, const Offset(-10, -60));
  await _tapMap(t, const Offset(-60, 70));
  await t.pumpAndSettle();
  await _next(t); // المحصول
  await _next(t); // المراجعة
  await t.tap(find.byKey(const ValueKey('save-field')));
  await _settle(t);
}

void main() {
  setUp(() => HttpOverrides.global = null); // flutter_test يردّ 400 لكلّ HttpClient

  void bigView(WidgetTester t) {
    t.view.physicalSize = const Size(1080, 2700);
    t.view.devicePixelRatio = 3;
    addTearDown(t.view.reset);
  }

  testWidgets('R01 wizard: dropped response → recover panel and no save '
      'button; the wizard is closed and reopened over the same storage; '
      'recovery opens the one committed field', (t) async {
    bigView(t);
    final server = await _server(t);
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final client = realClient(server, tokens);
      final disk = <String, String>{};
      server.plan.add(const CommitThenDrop());
      await _open(t, _App(client, ledgerFor(tokens, MemoryOperationStore(disk), client: client)));
      await _fillAndSave(t, 'الحقل الشرقيّ');

      expect(server.resources, hasLength(1));
      expect(find.text(kOperationUnknownAr), findsOneWidget);
      expect(find.byKey(const ValueKey('save-field')), findsNothing);
      final key = server.creates.single.key;

      // إغلاق المعالج والتطبيق ثمّ الفتح من جديد فوق «القرص» نفسه.
      await t.pumpWidget(const SizedBox());
      await _settle(t);
      final app2 = _App(client, ledgerFor(tokens, MemoryOperationStore(disk), client: client));
      await _open(t, app2);
      expect(find.text(kOperationUnknownAr), findsOneWidget);
      expect(find.text(kRecoverActionAr), findsOneWidget);

      await t.tap(find.text(kRecoverActionAr));
      await _settle(t);
      await t.pumpAndSettle();
      expect(app2.workspaceArg, 'fld_1');
      expect(server.resources, hasLength(1), reason: 'حقل واحد');
      expect(server.creates.map((c) => c.key).toSet(), {key});
    } finally {
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });

  testWidgets('OD-2 wizard: a 409 shows the recover wording and no save '
      'button; recovery keeps the key', (t) async {
    bigView(t);
    final server = await _server(t);
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final client = realClient(server, tokens);
      server.plan.add(const Status(409, {'detail': 'تعارض'}));
      final app = _App(client, ledgerFor(tokens, MemoryOperationStore(), client: client));
      await _open(t, app);
      await _fillAndSave(t, 'الحقل الشرقيّ');

      expect(find.text(kOperationConflictAr), findsOneWidget);
      expect(find.text(kRecoverActionAr), findsOneWidget);
      expect(find.byKey(const ValueKey('save-field')), findsNothing);
      expect(find.text('حفظ الحقل'), findsNothing);

      await t.tap(find.text(kRecoverActionAr));
      await _settle(t);
      await t.pumpAndSettle();
      expect(app.workspaceArg, 'fld_1');
      expect(server.creates, hasLength(2));
      expect(server.creates.map((c) => c.key).toSet(), hasLength(1));
    } finally {
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });
}
