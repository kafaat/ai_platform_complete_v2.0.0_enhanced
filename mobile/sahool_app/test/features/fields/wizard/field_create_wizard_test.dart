// معالج إنشاء الحقل من الطرف إلى الطرف على ApiClient حقيقيّ ومحوّل مزيّف:
// رجوع النظام يحفظ المُدخَل، ربطة العنق تُحجَب، والحفظ يرسل farm_id ومفتاح
// منع التكرار ثمّ يفتح مساحة عمل الحقل الجديد.
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

import '../../../core/fake_http.dart';
import '../../offline_sync/operation_test_support.dart';

// حقل قائم صغير يتمركز عنده الرسم (تكبير 15)، بعيد عن نقرات الاختبار.
const _existing = {
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
};

class _Harness {
  _Harness() {
    adapter = FakeAdapter((o) async {
      if (o.method == 'GET' && o.path == '/api/v1/farms') {
        return const FakeReply(200, [
          {'farm_id': 'farm_1', 'name': 'مزرعة الوادي'},
        ]);
      }
      if (o.method == 'GET' && o.path == '/api/v1/fields') {
        return const FakeReply(200, [_existing]);
      }
      if (o.method == 'POST' && o.path == '/api/v1/fields') {
        return const FakeReply(201, {
          'field_id': 'fld_new',
          'name_ar': 'الحقل الشرقيّ',
          'area_ha': 12.34,
        });
      }
      return const FakeReply(404, {'detail': 'غير موجود'});
    });
    client = testClient(adapter, tokens);
  }

  late final FakeAdapter adapter;
  late final ApiClient client;
  final tokens = MemoryTokenStore(
    accessToken: fakeJwt(const Duration(hours: 1)),
  );
  bool? result;
  Object? workspaceArg;

  Widget app() => MaterialApp(
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
            onPressed: () async {
              result = await Navigator.of(context).push<bool>(
                MaterialPageRoute(
                  builder: (_) => FieldCreateWizard(
                    farmsApi: FarmsApi(client),
                    fieldsApi: FieldsApi(client),
                    createApi: FieldCreateApi(client),
                    showBasemap: false,
                    canCreate: true,
                    ledger: ledgerFor(tokens, MemoryOperationStore()),
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
}

Future<void> _open(WidgetTester t, _Harness h) async {
  t.view.physicalSize = const Size(1080, 2700);
  t.view.devicePixelRatio = 3;
  addTearDown(t.view.reset);
  await t.pumpWidget(h.app());
  await t.tap(find.text('افتح'));
  await t.pumpAndSettle();
}

String _stepTitle(WidgetTester t) =>
    t.widget<Text>(find.byKey(const ValueKey('wizard-step-title'))).data!;

Future<void> _next(WidgetTester t) async {
  await t.tap(find.byKey(const ValueKey('wizard-next')));
  await t.pumpAndSettle();
}

Future<void> _tapMap(WidgetTester t, Offset d) async {
  expect(t.getSize(find.byType(FlutterMap)).height, greaterThan(250));
  await t.tapAt(t.getCenter(find.byType(FlutterMap)) + d);
  await t.pump(const Duration(milliseconds: 400));
}

void main() {
  testWidgets('system back steps back and keeps every input', (t) async {
    final h = _Harness();
    await _open(t, h);
    expect(_stepTitle(t), contains('الخطوة 1 من 4'));
    await t.enterText(find.byType(TextFormField).first, 'الحقل الشرقيّ');
    await t.pump();
    await _next(t);
    expect(_stepTitle(t), contains('الخطوة 2 من 4'));
    await _tapMap(t, const Offset(-100, -70));

    // رجوع النظام (زرّ أندرويد): خطوة إلى الوراء، لا إغلاق المعالج.
    await t.binding.handlePopRoute();
    await t.pumpAndSettle();
    expect(_stepTitle(t), contains('الخطوة 1 من 4'));
    expect(find.text('الحقل الشرقيّ'), findsOneWidget);

    // في الخطوة الأولى مع مدخلات: تأكيد قبل الإسقاط؛ «متابعة» يُبقي كلّ شيء.
    await t.binding.handlePopRoute();
    await t.pumpAndSettle();
    expect(find.text('الخروج من إضافة الحقل؟'), findsOneWidget);
    await t.tap(find.text('متابعة الإدخال'));
    await t.pumpAndSettle();
    expect(find.text('الحقل الشرقيّ'), findsOneWidget);
    expect(h.result, isNull);

    // الرأس المرسوم ما زال موجوداً.
    await _next(t);
    expect(find.byKey(const ValueKey('draw-vertex-0')), findsOneWidget);
  });

  testWidgets('a bow-tie cannot pass the boundary step', (t) async {
    final h = _Harness();
    await _open(t, h);
    await t.enterText(find.byType(TextFormField).first, 'ربطة');
    await t.pump();
    await _next(t);
    await _tapMap(t, const Offset(-100, -70));
    await _tapMap(t, const Offset(100, 70));
    await _tapMap(t, const Offset(100, -70));
    await _tapMap(t, const Offset(-100, 70));
    await t.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('issue-self_intersection')),
      findsOneWidget,
    );
    final next = t.widget<FilledButton>(
      find.descendant(
        of: find.byKey(const ValueKey('wizard-next')),
        matching: find.byType(FilledButton),
      ),
    );
    expect(next.onPressed, isNull);
  });

  testWidgets('save sends farm_id + Idempotency-Key and opens the workspace', (
    t,
  ) async {
    final h = _Harness();
    await _open(t, h);
    await t.enterText(find.byType(TextFormField).first, 'الحقل الشرقيّ');
    await t.pump();
    await _next(t);
    await _tapMap(t, const Offset(-110, -60));
    await _tapMap(t, const Offset(-10, -60));
    await _tapMap(t, const Offset(-60, 70));
    await t.pumpAndSettle();
    final areaText = t
        .widget<Text>(find.byKey(const ValueKey('boundary-area')))
        .data!;
    expect(areaText, contains('كما سيحفظها الخادم'));
    expect(find.byKey(const ValueKey('issue-overlap')), findsNothing);
    await _next(t); // المحصول
    await _next(t); // المراجعة
    expect(_stepTitle(t), contains('الخطوة 4 من 4'));
    expect(find.text('مزرعة الوادي'), findsOneWidget);

    await t.tap(find.byKey(const ValueKey('save-field')));
    await t.pumpAndSettle();

    final post = h.adapter
        .to('/api/v1/fields')
        .where((r) => r.method == 'POST');
    expect(post, hasLength(1));
    final body = post.single.data as Map;
    expect(body['farm_id'], 'farm_1');
    expect(body['name'], 'الحقل الشرقيّ');
    expect((body['geometry'] as Map)['type'], 'Polygon');
    expect(post.single.headers['Idempotency-Key'], isNotNull);
    expect(h.result, isTrue, reason: 'قائمة الحقول التي فتحت المعالج تُحدَّث');
    expect(h.workspaceArg, 'fld_new');
    expect(find.text('مساحة العمل'), findsOneWidget);
  });
}
