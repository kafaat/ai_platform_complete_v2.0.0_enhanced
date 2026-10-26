// تفاصيل عنصر المخزون: المستوى، الدفعات الخاصّة به، حدود الخادم المُعلَنة،
// تنبيه سلامة المبيد الصادق، الدور، والرابط العميق.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/presentation/inventory_item_screen.dart';

import 'inventory_test_host.dart';

final now = DateTime(2026, 10, 26, 9);

FakeAdapter adapterFor(String category) => routeAdapter({
  'GET /api/v1/inventory/items': (_) => FakeReply(200, [
    {
      'item_id': 'inv_1',
      'category': category,
      'name': 'العنصر',
      'unit': 'لتر',
      'reorder_level': null,
      'total_quantity': 12.5,
      'low_stock': false,
    },
  ]),
  'GET /api/v1/inventory/expiring': (o) {
    expect(o.queryParameters['days'], kAllBatchesWindowDays);
    return const FakeReply(200, [
      {
        'batch_id': 'bat_mine',
        'item_id': 'inv_1',
        'name': 'العنصر',
        'quantity': 2.0,
        'unit': 'لتر',
        'expiry_date': '2027-01-01',
      },
      {
        'batch_id': 'bat_other',
        'item_id': 'inv_2',
        'name': 'غيره',
        'quantity': 9.0,
        'unit': 'كجم',
        'expiry_date': '2026-11-01',
      },
    ]);
  },
});

Future<void> pumpItem(
  WidgetTester t,
  FakeAdapter a, {
  AppRole role = AppRole.owner,
  String id = 'inv_1',
}) async {
  t.view.physicalSize = const Size(800, 2000);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
  await t.pumpWidget(
    hostApp(
      InventoryItemScreen(
        itemId: id,
        api: InventoryApi(fakeClient(a)),
        role: role,
        clock: () => now,
      ),
    ),
  );
  await settle(t);
}

void main() {
  testWidgets('shows the level and only this item\'s batches', (t) async {
    await pumpItem(t, adapterFor('fertilizer'));
    expect(find.text('12.5'), findsOneWidget);
    expect(find.textContaining('غير محدّد'), findsOneWidget);
    expect(find.byKey(const ValueKey('batch:bat_mine')), findsOneWidget);
    expect(find.byKey(const ValueKey('batch:bat_other')), findsNothing);
  });

  testWidgets('stock-out is disabled with the backend reason', (t) async {
    await pumpItem(t, adapterFor('fertilizer'));
    final out = t.widget<OutlinedButton>(
      find.ancestor(
        of: find.text('صرف من المخزون'),
        matching: find.byWidgetPredicate((w) => w is OutlinedButton),
      ),
    );
    expect(out.onPressed, isNull);
    expect(find.text(kStockOutUnavailable), findsOneWidget);
  });

  testWidgets('pesticides get an honest safety note; fertilizers do not', (
    t,
  ) async {
    await pumpItem(t, adapterFor('pesticide'));
    expect(find.text(kSafetyDataUnavailable), findsOneWidget);
  });

  testWidgets('fertilizers carry no pesticide safety note', (t) async {
    await pumpItem(t, adapterFor('fertilizer'));
    expect(find.text(kSafetyDataUnavailable), findsNothing);
  });

  testWidgets('a worker sees the item but no stock actions', (t) async {
    await pumpItem(t, adapterFor('seed'), role: AppRole.worker);
    expect(find.text('12.5'), findsOneWidget);
    expect(find.text('إدخال مخزون (دفعة جديدة)'), findsNothing);
  });

  testWidgets('an unknown item id is an honest not-found', (t) async {
    await pumpItem(t, adapterFor('seed'), id: 'inv_missing');
    expect(find.text('العنصر غير موجود.'), findsOneWidget);
  });

  test('deep link /inventory/item resolves to the item screen', () {
    final route = AppRouter.instance.match('/inventory/item?item_id=inv_1');
    expect(route?.path, '/inventory/item');
    expect(AppRouter.instance.ownerOf('/inventory/item'), 'inventory');
  });
}
