// شاشة الاستكشاف: حالات التحميل/الخطأ/الفراغ/«القاعدة غير مفعّلة»، الترشيح،
// الخريطة، والأدوار.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/scouting/presentation/scouting_screen.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

void main() {
  Future<void> pump(WidgetTester t, Widget w) async {
    await t.pumpWidget(host(w));
    await t.pumpAndSettle();
  }

  testWidgets('loading then a pin list for the only field', (t) async {
    final gate = Completer<FakeReply>();
    final (api, adapter) = fakeApi((o) => gate.future);
    await t.pumpWidget(host(ScoutingScreen(deps: testDeps(api: api))));
    await t.pump();
    await t.pump();
    expect(find.text('جارٍ تحميل المشاهدات…'), findsOneWidget);
    gate.complete(
      FakeReply(200, {
        'pins': [pinJson('p1', note: 'منّ كثيف')],
        'total': 1,
      }),
    );
    await t.pumpAndSettle();
    expect(adapter.requests.single.path, '/api/v1/scouting/pins');
    expect(find.text('آفة حشريّة'), findsOneWidget);
    expect(find.text('شديدة'), findsOneWidget);
    expect(find.textContaining('منّ كثيف'), findsOneWidget);
  });

  testWidgets('empty list is an empty state with the primary action', (
    t,
  ) async {
    final (api, _) = fakeApi(
      (o) async => const FakeReply(200, {'pins': [], 'total': 0}),
    );
    await pump(t, ScoutingScreen(deps: testDeps(api: api)));
    expect(find.text('لا مشاهدات بعد'), findsOneWidget);
    expect(find.text('مشاهدة جديدة'), findsWidgets);
  });

  testWidgets('database-disabled note is shown, not a silent empty list', (
    t,
  ) async {
    final (api, _) = fakeApi(
      (o) async => const FakeReply(200, {
        'pins': [],
        'total': 0,
        'note_ar': 'القاعدة غير مفعّلة (DATABASE_URL) — لا دبابيس مُخزَّنة',
      }),
    );
    await pump(t, ScoutingScreen(deps: testDeps(api: api)));
    expect(find.textContaining('القاعدة غير مفعّلة'), findsOneWidget);
  });

  testWidgets('503 shows the typed message with retry', (t) async {
    final (api, _) = fakeApi((o) async => unavailable('x'));
    await pump(t, ScoutingScreen(deps: testDeps(api: api)));
    expect(
      find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
      findsOneWidget,
    );
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('fields load failure is an error state', (t) async {
    final (api, _) = fakeApi((o) async => const FakeReply(200, {}));
    await pump(
      t,
      ScoutingScreen(
        deps: testDeps(
          api: api,
          fieldsLoader: () async => throw const FormatException('bad'),
        ),
      ),
    );
    expect(find.text('bad'), findsOneWidget);
  });

  testWidgets('no fields ⇒ honest empty state, no pins request', (t) async {
    final (api, adapter) = fakeApi((o) async => const FakeReply(200, {}));
    await pump(
      t,
      ScoutingScreen(
        deps: testDeps(api: api, fields: const []),
      ),
    );
    expect(find.text('لا حقول بعد'), findsOneWidget);
    expect(adapter.requests, isEmpty);
  });

  testWidgets('several fields ⇒ choose one first', (t) async {
    final (api, adapter) = fakeApi(
      (o) async => const FakeReply(200, {'pins': [], 'total': 0}),
    );
    await pump(
      t,
      ScoutingScreen(
        deps: testDeps(api: api, fields: const [sanaaField, noCentreField]),
      ),
    );
    expect(find.text('اختر الحقل'), findsOneWidget);
    await t.tap(find.text('حقل بلا مركز'));
    await t.pumpAndSettle();
    expect(adapter.requests.single.path, '/api/v1/scouting/pins');
    expect(find.text('الاستكشاف — حقل بلا مركز'), findsOneWidget);
  });

  testWidgets('severity filter hides pins of other severities', (t) async {
    final (api, _) = fakeApi(
      (o) async => FakeReply(200, {
        'pins': [
          pinJson('p1', category: 'pest', severity: 'high'),
          pinJson('p2', category: 'weed', severity: 'low'),
        ],
      }),
    );
    await pump(t, ScoutingScreen(deps: testDeps(api: api)));
    expect(find.text('أعشاب ضارّة'), findsOneWidget);
    await t.tap(find.text('كلّ الشدّات'));
    await t.pumpAndSettle();
    await t.tap(find.text('شديدة').last);
    await t.pumpAndSettle();
    expect(find.text('أعشاب ضارّة'), findsNothing);
    expect(find.text('آفة حشريّة'), findsOneWidget);
  });

  testWidgets('date filter excludes old pins', (t) async {
    final old = DateTime.now()
        .subtract(const Duration(days: 40))
        .toUtc()
        .toIso8601String();
    final (api, _) = fakeApi(
      (o) async => FakeReply(200, {
        'pins': [
          pinJson('p1', category: 'pest'),
          pinJson('p2', category: 'disease', createdAt: old),
        ],
      }),
    );
    await pump(t, ScoutingScreen(deps: testDeps(api: api)));
    expect(find.text('مرض'), findsOneWidget);
    await t.tap(find.text('كلّ التواريخ'));
    await t.pumpAndSettle();
    await t.tap(find.text('آخر ٣٠ يوماً').last);
    await t.pumpAndSettle();
    expect(find.text('مرض'), findsNothing);
    expect(find.text('آفة حشريّة'), findsOneWidget);
  });

  testWidgets('map view draws one marker per pin', (t) async {
    final (api, _) = fakeApi(
      (o) async => FakeReply(200, {
        'pins': [pinJson('p1'), pinJson('p2', lat: 15.352, lng: 44.203)],
      }),
    );
    await pump(t, ScoutingScreen(deps: testDeps(api: api)));
    await t.tap(find.text('خريطة'));
    await t.pumpAndSettle();
    expect(find.byType(FlutterMap), findsOneWidget);
    expect(find.byType(MarkerLayer), findsOneWidget);
    final layer = t.widget<MarkerLayer>(find.byType(MarkerLayer));
    expect(layer.markers, hasLength(2));
  });

  testWidgets('viewer can read pins but gets no record actions', (t) async {
    final (api, _) = fakeApi(
      (o) async => FakeReply(200, {
        'pins': [pinJson('p1')],
      }),
    );
    await pump(
      t,
      ScoutingScreen(
        deps: testDeps(api: api, role: 'viewer'),
      ),
    );
    expect(find.text('آفة حشريّة'), findsOneWidget);
    expect(find.text('مشاهدة جديدة'), findsNothing);
    expect(find.byTooltip('كشف الآفات بالصورة'), findsNothing);
  });
}
