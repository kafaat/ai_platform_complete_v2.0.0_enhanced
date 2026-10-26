// مسارات الاستكشاف ومداخل القائمة («التقاط مشاهدة» إجراء سريع ظاهر)، وبوّابة
// اختيار الحقل للروابط العميقة.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_route.dart';
import 'package:sahool_app/features/scouting/presentation/scouting_widgets.dart';
import 'package:sahool_app/features/scouting/scouting_routes.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

void main() {
  AppRoute route(String path) =>
      scoutingFeature.routes.firstWhere((r) => r.path == path);

  test('three routes: pins, capture (quick action), pest-detect', () {
    expect(scoutingFeature.routes.map((r) => r.path), [
      '/scouting',
      '/scouting/capture',
      '/scouting/pest-detect',
    ]);
  });

  test(
    'capture is discoverable right after tasks in operations, editors only',
    () {
      final capture = route(ScoutingRoutes.capture);
      expect(capture.titleAr, 'التقاط مشاهدة');
      expect(capture.menu?.section, MenuSection.operations);
      // مباشرةً بعد «المهام» (10) وقبل الريّ (30). app_router_test يثبّت
      // أنّ المهام ثاني عنصر في العمليّات.
      expect(capture.menu!.order, inExclusiveRange(10, 30));
      expect(capture.allows(AppRole.worker), isTrue);
      expect(capture.allows(AppRole.viewer), isFalse);
    },
  );

  test('pins list is in crop health and readable by viewers', () {
    final pins = route(ScoutingRoutes.pins);
    expect(pins.menu?.section, MenuSection.cropHealth);
    expect(pins.allows(AppRole.viewer), isTrue);
    expect(route(ScoutingRoutes.pestDetect).allows(AppRole.viewer), isFalse);
  });

  testWidgets('field gate opens the flow directly for a known field_id', (
    t,
  ) async {
    final (api, _) = fakeApi((o) async => const FakeReply(200, {}));
    await t.pumpWidget(
      host(
        ScoutingFieldGate(
          title: 'التقاط مشاهدة',
          deps: testDeps(api: api, fields: const [sanaaField, noCentreField]),
          initialFieldId: 'f2',
          builder: (_, f) => Text('flow:${f.id}'),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('flow:f2'), findsOneWidget);
  });

  testWidgets('field gate says so when the linked field is not the user\'s', (
    t,
  ) async {
    final (api, _) = fakeApi((o) async => const FakeReply(200, {}));
    await t.pumpWidget(
      host(
        ScoutingFieldGate(
          title: 'التقاط مشاهدة',
          deps: testDeps(api: api),
          initialFieldId: 'nope',
          builder: (_, f) => Text('flow:${f.id}'),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.textContaining('غير موجود ضمن حقولك'), findsOneWidget);
    await t.tap(find.text('حقل القمح'));
    await t.pumpAndSettle();
    expect(find.text('flow:f1'), findsOneWidget);
  });
}
