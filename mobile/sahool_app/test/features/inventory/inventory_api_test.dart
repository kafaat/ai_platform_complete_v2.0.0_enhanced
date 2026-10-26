// InventoryApi فوق ApiClient الحقيقيّ: المسارات والاستعلام والمفتاح ونمذجة الردّ.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/data/inventory_models.dart';

import '../operations_hub/ops_test_host.dart';

void main() {
  test(
    'listItems parses the server shape (total, low_stock, null reorder)',
    () async {
      final adapter = routeAdapter({
        'GET /api/v1/inventory/items': (_) => const FakeReply(200, [
          {
            'item_id': 'inv_1',
            'category': 'pesticide',
            'name': 'مبيد',
            'unit': 'لتر',
            'reorder_level': 5.0,
            'total_quantity': 2.0,
            'low_stock': true,
          },
          {
            'item_id': 'inv_2',
            'category': 'seed',
            'name': 'بذور',
            'unit': 'كجم',
            'reorder_level': null,
            'total_quantity': 0.0,
            'low_stock': false,
          },
        ]),
      });
      final items = await InventoryApi(fakeClient(adapter)).listItems();
      expect(items, hasLength(2));
      expect(items.first.lowStock, isTrue);
      expect(items.first.totalQuantity, 2.0);
      expect(items.last.reorderLevel, isNull);
      expect(items.last.categoryLabel, 'بذور');
    },
  );

  test('listExpiring sends days and parses calendar dates', () async {
    final adapter = routeAdapter({
      'GET /api/v1/inventory/expiring': (o) {
        expect(o.queryParameters['days'], 3650);
        return const FakeReply(200, [
          {
            'batch_id': 'bat_1',
            'item_id': 'inv_1',
            'name': 'مبيد',
            'quantity': 3.5,
            'unit': 'لتر',
            'expiry_date': '2026-11-02',
          },
        ]);
      },
    });
    final b = (await InventoryApi(
      fakeClient(adapter),
    ).listExpiring(days: 3650)).single;
    expect(b.expiryDate, DateTime(2026, 11, 2));
    expect(b.daysLeft(DateTime(2026, 10, 26, 23, 59)), 7);
    expect(b.isExpired(DateTime(2026, 11, 3)), isTrue);
  });

  test('a row without item_id is a shape error, not a silent row', () async {
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => const FakeReply(200, [
        {'name': 'x'},
      ]),
    });
    expect(
      InventoryApi(fakeClient(adapter)).listItems(),
      throwsA(isA<FormatException>()),
    );
  });

  test('writes carry the caller\'s Idempotency-Key', () async {
    final adapter = routeAdapter({
      'POST /api/v1/inventory/items/inv_1/batches': (_) =>
          const FakeReply(201, {'batch_id': 'bat_9'}),
    });
    await InventoryApi(fakeClient(adapter)).addInventoryBatch('inv_1', {
      'quantity': 1,
    }, idempotencyKey: const IdempotencyKey('k-1'));
    expect(adapter.requests.single.headers[kIdempotencyHeader], 'k-1');
  });

  test('isoCalendarDate pads and never shifts by time zone', () {
    expect(isoCalendarDate(DateTime(2026, 3, 5, 23, 30)), '2026-03-05');
  });
}
