// خريطة الرسم: النقر يضيف رؤوساً، المقابض ≥48dp (كانت 18px)، السحب يحرّك الرأس
// خطوة تراجع واحدة، المنتصف يُدرج، والضغط المطوّل يحذف.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/maps/draw/draw_controller.dart';
import 'package:sahool_app/features/maps/draw/draw_map.dart';

Widget host(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: Scaffold(body: SizedBox(width: 400, height: 600, child: child)),
);

Future<void> tapMap(WidgetTester t, Offset delta) async {
  final centre = t.getCenter(find.byType(FlutterMap));
  await t.tapAt(centre + delta);
  // التكبير بالنقر المزدوج مفعَّل ⇒ تُؤكَّد النقرة المفردة بعد مهلته.
  await t.pump(const Duration(milliseconds: 400));
}

void main() {
  late DrawController c;
  setUp(() => c = DrawController());
  tearDown(() => c.dispose());

  Future<void> pumpMap(WidgetTester t) async {
    await t.pumpWidget(
      host(
        DrawMap(
          controller: c,
          initialCenter: const LatLng(15.35, 44.2),
          initialZoom: 16,
          showBasemap: false,
        ),
      ),
    );
    await t.pump();
  }

  Future<void> drawTriangle(WidgetTester t) async {
    await tapMap(t, const Offset(-100, -100));
    await tapMap(t, const Offset(100, -100));
    await tapMap(t, const Offset(0, 100));
  }

  testWidgets('taps add vertices and handles are at least 48dp', (t) async {
    await pumpMap(t);
    await drawTriangle(t);
    expect(c.vertices, hasLength(3));
    for (var i = 0; i < 3; i++) {
      final s = t.getSize(find.byKey(ValueKey('draw-vertex-$i')));
      expect(s.width, greaterThanOrEqualTo(48));
      expect(s.height, greaterThanOrEqualTo(48));
    }
    expect(find.byKey(const ValueKey('draw-mid-0')), findsOneWidget);
  });

  testWidgets('dragging a vertex moves it as one undo step', (t) async {
    await pumpMap(t);
    await drawTriangle(t);
    final before = c.vertices[2];
    await t.drag(
      find.byKey(const ValueKey('draw-vertex-2')),
      const Offset(60, 0),
    );
    await t.pump();
    expect(c.vertices, hasLength(3), reason: 'السحب لا يضيف رأساً');
    expect(c.vertices[2].longitude, greaterThan(before.longitude));
    c.undo();
    expect(c.vertices[2], before);
  });

  testWidgets('tapping a midpoint inserts; long-press deletes', (t) async {
    await pumpMap(t);
    await drawTriangle(t);
    await t.tap(find.byKey(const ValueKey('draw-mid-0')));
    await t.pump(const Duration(milliseconds: 400));
    expect(c.vertices, hasLength(4));
    await t.longPress(find.byKey(const ValueKey('draw-vertex-1')));
    await t.pump(const Duration(milliseconds: 400));
    expect(c.vertices, hasLength(3));
  });

  testWidgets('pivot shows centre and radius handles; radius drag resizes', (
    t,
  ) async {
    c.setMode(DrawMode.circle);
    await pumpMap(t);
    await tapMap(t, Offset.zero);
    c.setRadius(100);
    await t.pump();
    expect(find.byKey(const ValueKey('draw-center')), findsOneWidget);
    await t.drag(
      find.byKey(const ValueKey('draw-radius')),
      const Offset(40, 0),
    );
    await t.pump();
    expect(c.radiusM, greaterThan(100));
    expect(c.ring, hasLength(96));
  });
}
