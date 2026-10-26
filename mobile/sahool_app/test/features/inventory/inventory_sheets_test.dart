// أوراق الكتابة في المخزون: التحقّق داخل الورقة (لا SnackBar تحتها)، الأرقام
// العربيّة، مفتاح منع التكرار الثابت عبر المحاولات، والحفظ دون اتّصال الصادق.
import 'dart:async';
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/presentation/inventory_item_screen.dart';
import 'package:sahool_app/features/inventory/presentation/inventory_screen.dart';

import 'inventory_test_host.dart';

final now = DateTime(2026, 10, 26, 9);

const item = {
  'item_id': 'inv_1',
  'category': 'fertilizer',
  'name': 'يوريا',
  'unit': 'كجم',
  'reorder_level': 10.0,
  'total_quantity': 4.0,
  'low_stock': true,
};

void tall(WidgetTester t) {
  t.view.physicalSize = const Size(800, 2000);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
}

Map<String, dynamic> bodyOf(RecordedRequest r) => r.data is String
    ? jsonDecode(r.data! as String) as Map<String, dynamic>
    : Map<String, dynamic>.from(r.data! as Map);

Finder inSheet(Finder f) =>
    find.descendant(of: find.byType(BottomSheet), matching: f);

Future<void> openStockIn(
  WidgetTester t,
  FakeAdapter adapter, {
  FakeOutbox? outbox,
}) async {
  tall(t);
  await t.pumpWidget(
    hostApp(
      InventoryItemScreen(
        itemId: 'inv_1',
        api: InventoryApi(fakeClient(adapter)),
        role: AppRole.owner,
        outbox: outbox,
        clock: () => now,
      ),
    ),
  );
  await settle(t);
  await t.tap(find.text('إدخال مخزون (دفعة جديدة)'));
  await t.pumpAndSettle();
}

FakeAdapter itemAdapter(
  FutureOr<FakeReply> Function(RequestOptions o) onPost,
) => routeAdapter({
  'GET /api/v1/inventory/items': (_) => const FakeReply(200, [item]),
  'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
  'POST /api/v1/inventory/items/inv_1/batches': onPost,
});

void main() {
  testWidgets('add-item validation shows inside the sheet, not in a SnackBar', (
    t,
  ) async {
    tall(t);
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => const FakeReply(200, [item]),
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
    });
    await t.pumpWidget(
      hostApp(
        InventoryScreen(
          api: InventoryApi(fakeClient(adapter)),
          role: AppRole.owner,
          clock: () => now,
        ),
      ),
    );
    await settle(t);
    await t.tap(find.text('عنصر جديد'));
    await t.pumpAndSettle();
    // القائمة المنسدلة تبدأ بقيمتها (initialValue، لا value المهجور).
    expect(inSheet(find.text('سماد')), findsOneWidget);
    await t.tap(find.text('حفظ العنصر'));
    await t.pump();
    expect(inSheet(find.text('الاسم مطلوب')), findsOneWidget);
    expect(
      inSheet(find.text('راجع الحقول المعلَّمة باللون الأحمر.')),
      findsOneWidget,
    );
    expect(find.byType(SnackBar), findsNothing);
    expect(
      adapter.to('/api/v1/inventory/items').where((r) => r.method == 'POST'),
      isEmpty,
    );
  });

  testWidgets('a server rejection is shown inside the sheet', (t) async {
    tall(t);
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => const FakeReply(200, [item]),
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
      'POST /api/v1/inventory/items': (_) => const FakeReply(422, {
        'detail': [
          {'msg': 'الاسم طويل جدّاً'},
        ],
      }),
    });
    await t.pumpWidget(
      hostApp(
        InventoryScreen(
          api: InventoryApi(fakeClient(adapter)),
          role: AppRole.owner,
          clock: () => now,
        ),
      ),
    );
    await settle(t);
    await t.tap(find.text('عنصر جديد'));
    await t.pumpAndSettle();
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'الاسم')),
      'س',
    );
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'حدّ إعادة الطلب')),
      '٥',
    );
    await t.tap(find.text('حفظ العنصر'));
    await settle(t);
    expect(inSheet(find.text('الاسم طويل جدّاً')), findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
    final post = adapter.requests.firstWhere((r) => r.method == 'POST');
    expect(bodyOf(post)['reorder_level'], 5);
    expect(post.headers[kIdempotencyHeader], isNotEmpty);
  });

  testWidgets('stock-in accepts Arabic-Indic digits (٢٫٥ ⇒ 2.5)', (t) async {
    final adapter = itemAdapter(
      (_) => const FakeReply(201, {'batch_id': 'bat_1'}),
    );
    await openStockIn(t, adapter);
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'الكمّيّة المستلمة')),
      '٢٫٥',
    );
    await t.tap(find.text('حفظ الدفعة'));
    await settle(t);
    final post = adapter.requests.singleWhere((r) => r.method == 'POST');
    final body = bodyOf(post);
    expect(body['quantity'], 2.5);
    expect(body['unit'], 'كجم');
    expect(body['received_at'], '2026-10-26');
    await t.pumpAndSettle();
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.text('أُضيفت الدفعة'), findsOneWidget);
  });

  testWidgets('stock-in rejects zero and empty quantities inline', (t) async {
    final adapter = itemAdapter((_) => const FakeReply(201, {}));
    await openStockIn(t, adapter);
    await t.tap(find.text('حفظ الدفعة'));
    await t.pump();
    expect(inSheet(find.text('الكمّيّة مطلوبة')), findsOneWidget);
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'الكمّيّة المستلمة')),
      '0',
    );
    await t.tap(find.text('حفظ الدفعة'));
    await t.pump();
    expect(
      inSheet(find.text('الكمّيّة يجب أن تكون أكبر من صفر')),
      findsOneWidget,
    );
    expect(adapter.requests.where((r) => r.method == 'POST'), isEmpty);
  });

  testWidgets('a retry after a failure reuses the same Idempotency-Key', (
    t,
  ) async {
    var n = 0;
    final adapter = itemAdapter(
      (_) => n++ == 0
          ? const FakeReply(500, {'detail': 'خطأ مؤقّت'})
          : const FakeReply(201, {'batch_id': 'bat_1'}),
    );
    await openStockIn(t, adapter);
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'الكمّيّة المستلمة')),
      '3',
    );
    await t.tap(find.text('حفظ الدفعة'));
    await settle(t);
    expect(inSheet(find.text('خطأ مؤقّت')), findsOneWidget);
    await t.tap(find.text('حفظ الدفعة'));
    await settle(t);
    final posts = adapter.requests.where((r) => r.method == 'POST').toList();
    expect(posts, hasLength(2));
    expect(posts[0].headers[kIdempotencyHeader], isNotEmpty);
    expect(
      posts[1].headers[kIdempotencyHeader],
      posts[0].headers[kIdempotencyHeader],
    );
  });

  testWidgets('offline with a working outbox: queued with the same key', (
    t,
  ) async {
    final outbox = FakeOutbox();
    final adapter = itemAdapter(
      (_) => const FakeReply.fail(DioExceptionType.connectionError),
    );
    await openStockIn(t, adapter, outbox: outbox);
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'الكمّيّة المستلمة')),
      '7',
    );
    await t.tap(find.text('حفظ الدفعة'));
    await settle(t);
    final op = outbox.ops.single;
    expect(op.path, '/api/v1/inventory/items/inv_1/batches');
    expect(op.body['quantity'], 7);
    final sent = adapter.requests.firstWhere((r) => r.method == 'POST');
    expect(op.idempotencyKey, sent.headers[kIdempotencyHeader]);
    await t.pumpAndSettle();
    expect(find.byType(BottomSheet), findsNothing);
    expect(find.textContaining('حُفظت العمليّة على الجهاز'), findsOneWidget);
  });

  testWidgets('offline without an outbox says so and keeps the sheet open', (
    t,
  ) async {
    final adapter = itemAdapter(
      (_) => const FakeReply.fail(DioExceptionType.connectionError),
    );
    await openStockIn(t, adapter, outbox: FakeOutbox(accept: false));
    await t.enterText(
      inSheet(find.widgetWithText(TextFormField, 'الكمّيّة المستلمة')),
      '7',
    );
    await t.tap(find.text('حفظ الدفعة'));
    await settle(t);
    expect(
      inSheet(find.textContaining('الحفظ دون اتّصال غير متاح')),
      findsOneWidget,
    );
  });
}
