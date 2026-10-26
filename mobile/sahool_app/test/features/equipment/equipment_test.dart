// المعدّات: النمذجة من شكل الخادم، حالات الشاشة، حالة «تعمل» الحقيقيّة، التصفية،
// الدور، التفاصيل (القادمة/المتأخّرة/السجلّ)، وورقتا الكتابة (تحقّق داخليّ،
// أرقام عربيّة، مفتاح منع تكرار ثابت، حفظ دون اتّصال صادق).
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/equipment/data/equipment_api.dart';
import 'package:sahool_app/features/equipment/data/equipment_models.dart';
import 'package:sahool_app/features/equipment/presentation/equipment_detail_screen.dart';
import 'package:sahool_app/features/equipment/presentation/equipment_screen.dart';

import '../operations_hub/ops_test_host.dart';

final now = DateTime(2026, 10, 26, 9);

const fleet = [
  {
    'equipment_id': 'eqp_1',
    'name': 'جرّار ماسي',
    'type': 'tractor',
    'status': 'operational',
    'operating_hours': 1250.5,
    'purchase_date': '2019-04-01',
  },
  {
    'equipment_id': 'eqp_2',
    'name': 'مضخّة البئر',
    'type': 'pump',
    'status': 'broken',
    'operating_hours': 0.0,
    'purchase_date': null,
  },
];

const records = [
  {
    'maintenance_id': 'mnt_late',
    'kind': 'scheduled',
    'status': 'planned',
    'scheduled_date': '2026-10-20',
    'performed_date': null,
    'cost_usd': null,
    'notes': null,
  },
  {
    'maintenance_id': 'mnt_soon',
    'kind': 'inspection',
    'status': 'planned',
    'scheduled_date': '2026-11-05',
    'performed_date': null,
    'cost_usd': null,
    'notes': null,
  },
  {
    'maintenance_id': 'mnt_done',
    'kind': 'repair',
    'status': 'done',
    'scheduled_date': null,
    'performed_date': '2026-09-01',
    'cost_usd': 45.5,
    'notes': 'تبديل فلتر الزيت',
  },
];

FakeAdapter fleetAdapter({
  Object list = fleet,
  Object maint = records,
  FutureOr<FakeReply> Function(RequestOptions o)? onPost,
}) => routeAdapter({
  'GET /api/v1/equipment': (_) => FakeReply(200, list),
  'GET /api/v1/equipment/eqp_1/maintenance': (_) => FakeReply(200, maint),
  'POST /api/v1/equipment': (_) =>
      const FakeReply(201, {'equipment_id': 'eqp_9'}),
  if (onPost != null) 'POST /api/v1/equipment/eqp_1/maintenance': onPost,
});

Future<void> pumpList(
  WidgetTester t,
  FakeAdapter a, {
  AppRole role = AppRole.owner,
}) async {
  useTallView(t);
  await t.pumpWidget(
    hostApp(
      EquipmentScreen(
        api: EquipmentApi(fakeClient(a)),
        role: role,
        clock: () => now,
      ),
    ),
  );
  await settle(t);
}

Future<void> pumpDetail(
  WidgetTester t,
  FakeAdapter a, {
  AppRole role = AppRole.owner,
  FakeOutbox? outbox,
}) async {
  useTallView(t);
  await t.pumpWidget(
    hostApp(
      EquipmentDetailScreen(
        equipmentId: 'eqp_1',
        api: EquipmentApi(fakeClient(a)),
        role: role,
        outbox: outbox,
        clock: () => now,
      ),
    ),
  );
  await settle(t);
}

Future<void> openLogSheet(WidgetTester t) async {
  await t.tap(find.text('تسجيل صيانة'));
  await t.pumpAndSettle();
}

void main() {
  group('models', () {
    test('status labels follow the database CHECK, not "active"', () {
      final e = Equipment.fromJson(fleet.first);
      expect(e.statusLabel, 'تعمل');
      expect(equipmentStatusTone(e.status), StatusTone.success);
      expect(equipmentStatusTone('active'), StatusTone.neutral);
      expect(e.purchaseDate, DateTime(2019, 4, 1));
    });

    test('maintenance overdue is planned and dated before today', () {
      final late = MaintenanceRecord.fromJson(records[0]);
      final done = MaintenanceRecord.fromJson(records[2]);
      expect(late.isOverdue(now), isTrue);
      expect(done.isOverdue(now), isFalse);
      expect(done.costUsd, 45.5);
    });
  });

  group('fleet screen', () {
    testWidgets('loaded: status chips, hours and counts', (t) async {
      await pumpList(t, fleetAdapter());
      expect(find.text('جرّار ماسي'), findsOneWidget);
      // كانت الشاشة القديمة تقارن بـ'active' فتُظهر المعدّة العاملة بلا حالة.
      expect(
        find.descendant(
          of: find.byKey(const ValueKey('equipment:eqp_1')),
          matching: find.text('تعمل'),
        ),
        findsOneWidget,
      );
      expect(find.textContaining('1,250.5 ساعة'), findsOneWidget);
      expect(
        find.byWidgetPredicate(
          (w) => w is MetricTile && w.label == 'معطّلة' && w.value == 1,
        ),
        findsOneWidget,
      );
    });

    testWidgets('status filter narrows the fleet', (t) async {
      await pumpList(t, fleetAdapter());
      await t.tap(find.widgetWithText(ChoiceChip, 'معطّلة'));
      await t.pump();
      expect(find.text('جرّار ماسي'), findsNothing);
      expect(find.text('مضخّة البئر'), findsOneWidget);
      await t.tap(find.widgetWithText(ChoiceChip, 'خارج الخدمة'));
      await t.pump();
      expect(find.text('لا معدّات بهذه الحالة.'), findsOneWidget);
    });

    testWidgets('empty fleet is an honest empty state', (t) async {
      await pumpList(t, fleetAdapter(list: const []));
      expect(find.text('لا توجد معدّات مسجّلة بعد'), findsOneWidget);
      expect(find.text('سجّل أوّل معدّة'), findsOneWidget);
    });

    testWidgets('503 shows the service message', (t) async {
      final a = routeAdapter({
        'GET /api/v1/equipment': (_) => const FakeReply(503),
      });
      await pumpList(t, a);
      await settle(t, frames: 30);
      expect(
        find.text(
          'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
        ),
        findsOneWidget,
      );
    });

    testWidgets('workers and viewers cannot add equipment', (t) async {
      await pumpList(t, fleetAdapter(), role: AppRole.worker);
      expect(find.text('معدّة جديدة'), findsNothing);
      expect(find.byTooltip('تحديث'), findsOneWidget);
    });

    testWidgets(
      'add sheet validates inside the sheet and sends Arabic digits',
      (t) async {
        final a = fleetAdapter();
        await pumpList(t, a);
        await t.tap(find.text('معدّة جديدة'));
        await t.pumpAndSettle();
        expect(inBottomSheet(find.text('جرّار')), findsOneWidget);
        await t.tap(find.text('حفظ المعدّة'));
        await t.pump();
        expect(inBottomSheet(find.text('الاسم مطلوب')), findsOneWidget);
        expect(find.byType(SnackBar), findsNothing);
        await t.enterText(
          inBottomSheet(find.widgetWithText(TextFormField, 'الاسم')),
          'جرّار 2',
        );
        await t.enterText(
          inBottomSheet(
            find.widgetWithText(TextFormField, 'ساعات التشغيل الحاليّة'),
          ),
          '١٢٠٫٥',
        );
        await t.tap(find.text('حفظ المعدّة'));
        await settle(t);
        final post = a.requests.singleWhere(
          (r) => r.method == 'POST' && r.path == '/api/v1/equipment',
        );
        expect(requestBody(post)['operating_hours'], 120.5);
        expect(requestBody(post)['type'], 'tractor');
        expect(post.headers[kIdempotencyHeader], isNotEmpty);
      },
    );
  });

  group('detail screen', () {
    testWidgets('upcoming sorted with overdue flagged; history apart', (
      t,
    ) async {
      await pumpDetail(t, fleetAdapter());
      expect(find.text('1 متأخّرة'), findsOneWidget);
      final late = t.getTopLeft(
        find.byKey(const ValueKey('maintenance:mnt_late')),
      );
      final soon = t.getTopLeft(
        find.byKey(const ValueKey('maintenance:mnt_soon')),
      );
      expect(late.dy, lessThan(soon.dy));
      expect(find.textContaining('45.5 دولار'), findsOneWidget);
      expect(find.textContaining('تبديل فلتر الزيت'), findsOneWidget);
      expect(find.textContaining('تاريخ الشراء: 1 أبريل 2019'), findsOneWidget);
    });

    testWidgets('no records: honest empty lines', (t) async {
      await pumpDetail(t, fleetAdapter(maint: const []));
      expect(find.text('لا صيانة مخطّطة لهذه المعدّة.'), findsOneWidget);
      expect(find.text('لا سجلّات صيانة منفّذة بعد.'), findsOneWidget);
    });

    testWidgets('a viewer cannot log maintenance', (t) async {
      await pumpDetail(t, fleetAdapter(), role: AppRole.viewer);
      expect(find.text('تسجيل صيانة'), findsNothing);
    });

    testWidgets('planned without a date is rejected inside the sheet', (
      t,
    ) async {
      final a = fleetAdapter(onPost: (_) => const FakeReply(201, {}));
      await pumpDetail(t, a);
      await openLogSheet(t);
      await t.tap(inBottomSheet(find.text('مُنجَزة')));
      await t.pumpAndSettle();
      await t.tap(find.text('مخطّطة').last);
      await t.pumpAndSettle();
      await t.tap(find.text('حفظ السجلّ'));
      await t.pump();
      expect(
        inBottomSheet(find.text('حدّد موعد الصيانة المخطّطة')),
        findsOneWidget,
      );
      expect(find.byType(SnackBar), findsNothing);
      expect(a.requests.where((r) => r.method == 'POST'), isEmpty);
    });

    testWidgets('done today with an Arabic cost; retry keeps the key', (
      t,
    ) async {
      var n = 0;
      final a = fleetAdapter(
        onPost: (_) => n++ == 0
            ? const FakeReply(500, {'detail': 'تعذّر الحفظ'})
            : const FakeReply(201, {'maintenance_id': 'mnt_9'}),
      );
      await pumpDetail(t, a);
      await openLogSheet(t);
      await t.enterText(
        inBottomSheet(find.widgetWithText(TextFormField, 'التكلفة (اختياري)')),
        '٣٠',
      );
      await t.tap(find.text('حفظ السجلّ'));
      await settle(t);
      expect(inBottomSheet(find.text('تعذّر الحفظ')), findsOneWidget);
      await t.tap(find.text('حفظ السجلّ'));
      await settle(t);
      final posts = a.requests.where((r) => r.method == 'POST').toList();
      expect(posts, hasLength(2));
      expect(
        posts[1].headers[kIdempotencyHeader],
        posts[0].headers[kIdempotencyHeader],
      );
      final body = requestBody(posts[1]);
      expect(body['cost_usd'], 30);
      expect(body['status'], 'done');
      expect(body['performed_date'], '2026-10-26');
      await t.pumpAndSettle();
      expect(find.byType(BottomSheet), findsNothing);
    });

    testWidgets('offline: queued in the outbox with the same key', (t) async {
      final outbox = FakeOutbox();
      final a = fleetAdapter(
        onPost: (_) => const FakeReply.fail(DioExceptionType.connectionError),
      );
      await pumpDetail(t, a, outbox: outbox);
      await openLogSheet(t);
      await t.tap(find.text('حفظ السجلّ'));
      await settle(t);
      final op = outbox.ops.single;
      expect(op.path, '/api/v1/equipment/eqp_1/maintenance');
      expect(
        op.idempotencyKey,
        a.requests
            .firstWhere((r) => r.method == 'POST')
            .headers[kIdempotencyHeader],
      );
      await t.pumpAndSettle();
      expect(find.textContaining('حُفظت العمليّة على الجهاز'), findsOneWidget);
    });

    testWidgets('unknown equipment is an honest not-found', (t) async {
      useTallView(t);
      await t.pumpWidget(
        hostApp(
          EquipmentDetailScreen(
            equipmentId: 'eqp_missing',
            api: EquipmentApi(
              fakeClient(
                routeAdapter({
                  'GET /api/v1/equipment': (_) => const FakeReply(200, fleet),
                  'GET /api/v1/equipment/eqp_missing/maintenance': (_) =>
                      const FakeReply(200, []),
                }),
              ),
            ),
            role: AppRole.owner,
            clock: () => now,
          ),
        ),
      );
      await settle(t);
      expect(find.text('العنصر غير موجود.'), findsOneWidget);
    });
  });

  test('deep link /equipment/detail is owned by equipment', () {
    expect(
      AppRouter.instance.match('/equipment/detail?equipment_id=e')?.path,
      '/equipment/detail',
    );
    expect(AppRouter.instance.ownerOf('/equipment/detail'), 'equipment');
  });
}
