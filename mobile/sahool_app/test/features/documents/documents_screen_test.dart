// الوثائق: حالات صادقة (تحميل/فارغ/403/503)، تسجيل لأدوار الإدارة فقط، خطأ
// التحقّق داخل الورقة (كان SnackBar يُرسم تحتها فلا يُرى)، ومفتاح idempotency
// ثابت لنفس الورقة عبر إعادة المحاولة.
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/documents/data/documents_api.dart';
import 'package:sahool_app/features/documents/presentation/documents_screen.dart';

import '../../core/fake_http.dart';

Widget _app(Widget home) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: home,
);

const _doc = {
  'doc_id': 'doc_1',
  'category': 'contract',
  'field_id': null,
  'title': 'عقد إيجار الأرض',
  'storage_ref': 's3://bucket/lease.pdf',
  'content_type': 'application/pdf',
  'size_bytes': 2048,
  'version': 1,
  'uploaded_by': 'u1',
};

void main() {
  Future<FakeAdapter> pump(
    WidgetTester tester,
    FakeHandler handler, {
    String role = 'manager',
  }) async {
    final adapter = FakeAdapter(handler);
    await tester.pumpWidget(
      _app(
        DocumentsScreen(
          api: DocumentsApi(testClient(adapter, MemoryTokenStore())),
          role: role,
        ),
      ),
    );
    await tester.pumpAndSettle();
    return adapter;
  }

  testWidgets('قائمة الوثائق بعناوينها وفئاتها', (tester) async {
    await pump(tester, (_) async => const FakeReply(200, [_doc]));
    expect(find.text('عقد إيجار الأرض'), findsOneWidget);
    expect(find.text('عقد · الإصدار 1'), findsOneWidget);
    await tester.tap(find.text('عقد إيجار الأرض'));
    await tester.pumpAndSettle();
    expect(find.text('s3://bucket/lease.pdf'), findsOneWidget);
    expect(find.text('2 ك.ب'), findsOneWidget);
  });

  testWidgets('فئة بلا وثائق ⇒ حالة فارغة تعرض الرجوع للكلّ', (tester) async {
    final adapter = await pump(tester, (o) async {
      final cat = o.queryParameters['category'];
      return FakeReply(200, cat == null ? [_doc] : const []);
    });
    await tester.tap(find.byKey(const ValueKey('doc_cat:map')));
    await tester.pumpAndSettle();
    expect(adapter.requests.last.path, '/api/v1/documents');
    expect(find.text('لا وثائق في فئة «خريطة».'), findsOneWidget);
    await tester.tap(find.text('عرض كلّ الفئات'));
    await tester.pumpAndSettle();
    expect(find.text('عقد إيجار الأرض'), findsOneWidget);
  });

  testWidgets('403 بعبارته', (tester) async {
    await pump(tester, (_) async => const FakeReply(403));
    expect(find.text('لا تملك صلاحيّة الوصول إلى هذا القسم.'), findsOneWidget);
  });

  testWidgets('503 بعبارته مع إعادة المحاولة', (tester) async {
    await pump(tester, (_) async => const FakeReply(503));
    expect(find.textContaining('الخدمة غير متاحة حاليّاً'), findsOneWidget);
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('المشاهد لا يرى زرّ التسجيل', (tester) async {
    await pump(tester, (_) async => const FakeReply(200, []), role: 'viewer');
    expect(find.text('تسجيل وثيقة'), findsNothing);
  });

  testWidgets('عنوان فارغ ⇒ خطأ داخل الورقة لا طلب', (tester) async {
    final adapter = await pump(tester, (_) async => const FakeReply(200, []));
    await tester.tap(find.text('تسجيل وثيقة'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('تسجيل'));
    await tester.pumpAndSettle();
    expect(find.text('العنوان مطلوب.'), findsOneWidget);
    expect(
      adapter.to('/api/v1/documents').where((r) => r.method == 'POST'),
      isEmpty,
    );
  });

  testWidgets('إعادة الإرسال بعد فشل ⇒ المفتاح نفسه', (tester) async {
    var posts = 0;
    final adapter = await pump(tester, (o) async {
      if (o.method == 'POST') {
        posts++;
        return posts == 1
            ? const FakeReply(400, {'detail': 'category invalid'})
            : const FakeReply(201, {'doc_id': 'doc_2'});
      }
      return const FakeReply(200, []);
    });
    await tester.tap(find.text('تسجيل وثيقة'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextFormField, 'العنوان'),
      'تقرير التربة',
    );
    await tester.tap(find.text('تسجيل'));
    await tester.pumpAndSettle();
    expect(find.text('category invalid'), findsOneWidget);
    await tester.tap(find.text('تسجيل'));
    await tester.pumpAndSettle();
    final keys = adapter.requests
        .where((r) => r.method == 'POST')
        .map((r) => r.headers[kIdempotencyHeader])
        .toList();
    expect(keys, hasLength(2));
    expect(keys.first, isNotNull);
    expect(keys.first, keys.last);
    expect(find.text('سُجّلت الوثيقة'), findsOneWidget);
  });
}
