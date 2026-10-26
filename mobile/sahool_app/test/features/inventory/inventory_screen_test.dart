// شاشة المخزون: كلّ حالة (تحميل/محمَّل/فارغ/خطأ/فشل تحديث)، التمييزات، التصفية،
// الدور، والتحميل المتوازي.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/inventory/data/inventory_api.dart';
import 'package:sahool_app/features/inventory/presentation/inventory_screen.dart';

import '../operations_hub/ops_test_host.dart';

final now = DateTime(2026, 10, 26, 9);

const items = [
  {
    'item_id': 'inv_1',
    'category': 'pesticide',
    'name': 'مبيد فطريّ',
    'unit': 'لتر',
    'reorder_level': 5.0,
    'total_quantity': 2.0,
    'low_stock': true,
  },
  {
    'item_id': 'inv_2',
    'category': 'fertilizer',
    'name': 'يوريا',
    'unit': 'كجم',
    'reorder_level': null,
    'total_quantity': 120.0,
    'low_stock': false,
  },
];

const expiring = [
  {
    'batch_id': 'bat_1',
    'item_id': 'inv_1',
    'name': 'مبيد فطريّ',
    'quantity': 2.0,
    'unit': 'لتر',
    'expiry_date': '2026-10-30',
  },
  {
    'batch_id': 'bat_2',
    'item_id': 'inv_1',
    'name': 'مبيد فطريّ',
    'quantity': 1.0,
    'unit': 'لتر',
    'expiry_date': '2026-10-01',
  },
];

FakeAdapter okAdapter({Object itemsBody = items, Object expBody = expiring}) =>
    routeAdapter({
      'GET /api/v1/inventory/items': (_) => FakeReply(200, itemsBody),
      'GET /api/v1/inventory/expiring': (_) => FakeReply(200, expBody),
    });

Future<void> pumpScreen(
  WidgetTester t,
  FakeAdapter adapter, {
  AppRole role = AppRole.owner,
}) async {
  // شاشة طويلة: القائمة كسولة، والعناصر خارج العرض لا تُبنى.
  t.view.physicalSize = const Size(800, 2400);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
  await t.pumpWidget(
    hostApp(
      InventoryScreen(
        api: InventoryApi(fakeClient(adapter)),
        role: role,
        clock: () => now,
      ),
    ),
  );
}

Finder metric(String label, num value) => find.byWidgetPredicate(
  (w) => w is MetricTile && w.label == label && w.value == value,
);

void main() {
  testWidgets('loading state shows while the server answers', (t) async {
    final gate = Completer<FakeReply>();
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => gate.future,
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
    });
    await pumpScreen(t, adapter);
    await t.pump();
    expect(find.text('جارٍ تحميل المخزون…'), findsOneWidget);
    gate.complete(const FakeReply(200, []));
    await settle(t);
  });

  testWidgets('items and expiring batches load in parallel', (t) async {
    final gate = Completer<FakeReply>();
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => gate.future,
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
    });
    await pumpScreen(t, adapter);
    await settle(t);
    // القائمة لم تُجب بعد، وطلب الدفعات أُرسل فعلاً.
    expect(
      adapter.requests.map((r) => r.path),
      containsAll(['/api/v1/inventory/items', '/api/v1/inventory/expiring']),
    );
    gate.complete(const FakeReply(200, []));
    await settle(t);
  });

  testWidgets('loaded: stock levels, low-stock and expiry highlights', (
    t,
  ) async {
    await pumpScreen(t, okAdapter());
    await settle(t);
    expect(find.text('يوريا'), findsOneWidget);
    expect(find.textContaining('المتوفّر: 120 كجم'), findsOneWidget);
    expect(find.text('مخزون منخفض'), findsWidgets);
    expect(find.text('تنتهي خلال 4 يوم'), findsOneWidget);
    expect(find.text('منتهية الصلاحيّة'), findsOneWidget);
    // ملخّص: عنصران، واحد منخفض، دفعتان.
    expect(metric('مخزون منخفض', 1), findsOneWidget);
    expect(metric('دفعات قاربت الانتهاء', 2), findsOneWidget);
  });

  testWidgets('low-only filter and search narrow the list honestly', (t) async {
    await pumpScreen(t, okAdapter(expBody: const []));
    await settle(t);
    await t.tap(find.text('منخفض فقط'));
    await t.pump();
    expect(find.text('يوريا'), findsNothing);
    expect(find.text('مبيد فطريّ'), findsOneWidget);
    await t.enterText(find.byType(TextField), 'غير موجود');
    await t.pump();
    expect(find.text('لا عناصر تطابق التصفية.'), findsOneWidget);
    await t.tap(find.text('مسح التصفية'));
    await t.pump();
    expect(find.text('يوريا'), findsOneWidget);
  });

  testWidgets('empty: honest empty state with a CTA for managers', (t) async {
    await pumpScreen(t, okAdapter(itemsBody: const [], expBody: const []));
    await settle(t);
    expect(find.text('لا توجد عناصر مخزون بعد'), findsOneWidget);
    expect(find.text('أضف أوّل عنصر'), findsOneWidget);
  });

  testWidgets('503 shows the honest service message with retry', (t) async {
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) =>
          const FakeReply(503, {'detail': 'db down'}),
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
    });
    await pumpScreen(t, adapter);
    await settle(t, frames: 30);
    expect(
      find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
      findsOneWidget,
    );
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('403 says no permission and offers no pointless retry', (
    t,
  ) async {
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => const FakeReply(403),
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(403),
    });
    await pumpScreen(t, adapter);
    await settle(t);
    expect(find.text('لا تملك صلاحيّة الوصول إلى هذا القسم.'), findsOneWidget);
    expect(find.text('إعادة المحاولة'), findsNothing);
  });

  testWidgets('a failed refresh keeps the data and says how old it is', (
    t,
  ) async {
    var calls = 0;
    final adapter = routeAdapter({
      'GET /api/v1/inventory/items': (_) => calls++ == 0
          ? const FakeReply(200, items)
          : const FakeReply(500, {'detail': 'boom'}),
      'GET /api/v1/inventory/expiring': (_) => const FakeReply(200, []),
    });
    await pumpScreen(t, adapter);
    await settle(t);
    await t.tap(find.byTooltip('تحديث'));
    await settle(t);
    expect(find.text('يوريا'), findsOneWidget);
    expect(find.textContaining('تعذّر التحديث: boom'), findsOneWidget);
  });

  // inventory:manage للمالك/المدير فقط؛ كانت canMutate تُظهر الإضافة للعامل.
  for (final role in [AppRole.worker, AppRole.agronomist, AppRole.viewer]) {
    testWidgets('${role.name} cannot see the add action', (t) async {
      await pumpScreen(t, okAdapter(), role: role);
      await settle(t);
      expect(find.text('عنصر جديد'), findsNothing);
    });
  }

  testWidgets('owner and manager get the add action', (t) async {
    await pumpScreen(t, okAdapter(), role: AppRole.manager);
    await settle(t);
    expect(find.text('عنصر جديد'), findsOneWidget);
  });

  testWidgets('the refresh button has a tooltip (screen readers)', (t) async {
    await pumpScreen(t, okAdapter());
    await settle(t);
    expect(find.byTooltip('تحديث'), findsOneWidget);
  });

  testWidgets('long names do not overflow at 360dp and text scale 1.3', (
    t,
  ) async {
    t.view.physicalSize = const Size(360, 780);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    final long = [
      {
        ...items.first,
        'name': 'مبيد فطريّ جهازيّ واسع الطيف لمكافحة البياض الدقيقيّ ' * 3,
      },
    ];
    await t.pumpWidget(
      hostApp(
        InventoryScreen(
          api: InventoryApi(fakeClient(okAdapter(itemsBody: long))),
          role: AppRole.owner,
          clock: () => now,
        ),
        textScale: 1.3,
      ),
    );
    await settle(t);
    expect(t.takeException(), isNull);
  });
}
