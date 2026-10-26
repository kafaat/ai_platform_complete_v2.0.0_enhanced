// البيانات المرجعيّة: الفئة تُغيَّر بشريحة وتُجلب بمعاملها، 409 يعرض تفصيل الخادم
// داخل الورقة، والإضافة لأدوار الإدارة فقط مع مفتاح idempotency.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/master_data/data/master_data_api.dart';
import 'package:sahool_app/features/master_data/presentation/master_data_screen.dart';

import '../../core/fake_http.dart';

Widget _app(Widget home) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: home,
);

void main() {
  Future<FakeAdapter> pump(
    WidgetTester tester,
    FakeHandler handler, {
    String role = 'owner',
  }) async {
    final adapter = FakeAdapter(handler);
    await tester.pumpWidget(
      _app(
        MasterDataScreen(
          api: MasterDataApi(testClient(adapter, MemoryTokenStore())),
          role: role,
        ),
      ),
    );
    await tester.pumpAndSettle();
    return adapter;
  }

  testWidgets('تبديل الفئة يجلبها بمعاملها', (tester) async {
    final adapter = await pump(tester, (o) async {
      final cat = o.queryParameters['category'];
      return FakeReply(200, [
        {
          'md_id': 'md_$cat',
          'category': cat,
          'code': 'c-$cat',
          'name_ar': cat == 'fertilizer' ? 'يوريا' : 'قمح',
          'name_en': null,
          'metadata': {},
        },
      ]);
    });
    expect(adapter.requests.first.path, '/api/v1/master-data');
    expect(find.text('قمح'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('md_cat:fertilizer')));
    await tester.pumpAndSettle();
    expect(find.text('يوريا'), findsOneWidget);
    expect(find.text('قمح'), findsNothing);
  });

  testWidgets('فئة فارغة ⇒ حالة فارغة صادقة', (tester) async {
    await pump(tester, (_) async => const FakeReply(200, []));
    expect(find.text('لا عناصر في «المحاصيل» بعد.'), findsOneWidget);
  });

  testWidgets('عامل لا يرى زرّ الإضافة', (tester) async {
    await pump(tester, (_) async => const FakeReply(200, []), role: 'worker');
    expect(find.text('إضافة عنصر'), findsNothing);
  });

  testWidgets('409 ⇒ تفصيل الخادم داخل الورقة، بمفتاح idempotency', (
    tester,
  ) async {
    final adapter = await pump(tester, (o) async {
      if (o.method == 'POST') {
        return const FakeReply(409, {
          'detail': 'الرمز موجود مسبقاً في هذه الفئة',
        });
      }
      return const FakeReply(200, []);
    });
    await tester.tap(find.text('إضافة عنصر'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'الرمز'),
      'wheat',
    );
    await tester.enterText(
      find.widgetWithText(TextFormField, 'الاسم العربيّ'),
      'قمح',
    );
    await tester.tap(find.text('إضافة'));
    await tester.pumpAndSettle();
    expect(find.text('الرمز موجود مسبقاً في هذه الفئة'), findsOneWidget);
    final post = adapter.requests.singleWhere((r) => r.method == 'POST');
    expect(post.headers[kIdempotencyHeader], isNotNull);
    expect((post.data! as Map)['category'], 'crop');
  });
}
