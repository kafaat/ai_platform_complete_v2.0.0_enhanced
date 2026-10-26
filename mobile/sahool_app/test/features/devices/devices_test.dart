// أجهزة IoT: النمذجة، السجلّ (الاتّصال، آخر ظهور، الحقل، صحّة الأسطول)، حالات
// «لا قراءات» الصادقة، رسم كلّ مستشعر، غياب أوامر التشغيل، وورقة التسجيل.
import 'dart:async';

import 'package:dio/dio.dart' show RequestOptions;
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/routing/app_router.dart';
import 'package:sahool_app/features/devices/data/devices_api.dart';
import 'package:sahool_app/features/devices/data/devices_models.dart';
import 'package:sahool_app/features/devices/presentation/device_detail_screen.dart';
import 'package:sahool_app/features/devices/presentation/devices_screen.dart';

import '../operations_hub/ops_test_host.dart';

final now = DateTime.utc(2026, 10, 26, 9);

final devices = [
  {
    'device_id': 'dev_1',
    'name': 'حسّاس الرطوبة',
    'type': 'soil_moisture',
    'field_id': 'f1',
    'status': 'online',
    'online': true,
    'last_seen_at': now.subtract(const Duration(minutes: 5)).toIso8601String(),
    'firmware_version': '1.2.0',
  },
  {
    'device_id': 'dev_2',
    'name': 'عدّاد البئر',
    'type': 'water_meter',
    'field_id': null,
    'status': 'offline',
    'online': false,
    'last_seen_at': now.subtract(const Duration(hours: 3)).toIso8601String(),
    'firmware_version': null,
  },
  {
    'device_id': 'dev_3',
    'name': 'صمّام القناة',
    'type': 'actuator',
    'field_id': null,
    'status': 'unknown',
    'online': false,
    'last_seen_at': null,
    'firmware_version': null,
  },
];

const fleet = {
  'total_devices': 3,
  'online': 1,
  'silent': 2,
  'critical_silent': 1,
  'fleet_status_ar': '🔴 …',
  'silent_devices': [
    {
      'device_id': 'dev_2',
      'name': 'عدّاد البئر',
      'type': 'water_meter',
      'field_id': null,
      'silent': true,
      'criticality': 'critical',
      'detail_ar': 'صامت منذ 180 دقيقة (العتبة 60 د لنوع water_meter)',
      'criticality_note_ar': 'جهاز حرج صامت (الحقل غير نشط حاليّاً)',
      'threshold_minutes': 60,
    },
  ],
};

List<Map<String, Object?>> readings(
  int n, {
  String sensor = 'soil_moisture',
}) => [
  for (var i = 0; i < n; i++)
    {
      'sensor_type': sensor,
      'value': 20.0 + i,
      'unit': '%',
      // الخادم يُعيد الأحدث أوّلاً.
      'recorded_at': now.subtract(Duration(minutes: 10 * i)).toIso8601String(),
    },
];

FakeAdapter devAdapter({
  Object list = const [],
  FutureOr<FakeReply> Function(RequestOptions o)? fleetReply,
  Object telemetry = const [],
  FutureOr<FakeReply> Function(RequestOptions o)? onPost,
}) => routeAdapter({
  'GET /api/v1/devices': (_) => FakeReply(200, list),
  'GET /api/v1/devices/fleet-health':
      fleetReply ?? (_) => const FakeReply(200, fleet),
  'GET /api/v1/devices/dev_1/telemetry': (_) => FakeReply(200, telemetry),
  'GET /api/v1/devices/dev_3/telemetry': (_) => const FakeReply(200, []),
  if (onPost != null) 'POST /api/v1/devices': onPost,
});

Future<List<Map<String, dynamic>>> fieldsOk() async => [
  {'field_id': 'f1', 'name_ar': 'الحقل الشماليّ'},
  {'field_id': 'f2', 'name_ar': 'حقل الوادي'},
];

Future<List<Map<String, dynamic>>> fieldsFail() async =>
    throw const FormatException('fields down');

Future<void> pumpList(
  WidgetTester t,
  FakeAdapter a, {
  AppRole role = AppRole.owner,
  Future<List<Map<String, dynamic>>> Function() fields = fieldsOk,
}) async {
  useTallView(t);
  await t.pumpWidget(
    hostApp(
      DevicesScreen(
        api: DevicesApi(fakeClient(a)),
        role: role,
        fields: fields,
        clock: () => now,
      ),
    ),
  );
  await settle(t);
}

Future<void> pumpDetail(WidgetTester t, FakeAdapter a, String id) async {
  useTallView(t);
  await t.pumpWidget(
    hostApp(
      DeviceDetailScreen(
        deviceId: id,
        api: DevicesApi(fakeClient(a)),
        clock: () => now,
      ),
    ),
  );
  await settle(t);
}

void main() {
  group('models', () {
    test('series group per sensor, oldest first, skipping unusable points', () {
      final raw = [
        ...readings(3).map(TelemetryPoint.fromJson),
        TelemetryPoint.fromJson(const {
          'sensor_type': 'soil_moisture',
          'value': null,
          'recorded_at': null,
        }),
        TelemetryPoint.fromJson(readings(1, sensor: 'air_temp').first),
      ];
      final series = SensorSeries.group(raw);
      final soil = series.firstWhere((s) => s.sensorType == 'soil_moisture');
      expect(soil.points, hasLength(3));
      expect(soil.points.first.value, 22.0); // الأقدم
      expect(soil.latest!.value, 20.0); // الأحدث
      expect(soil.label, 'رطوبة التربة');
    });

    test('fleet health parses silent devices by criticality', () {
      final f = FleetHealth.fromJson(fleet);
      expect(f.silent, 2);
      expect(f.silentFor('dev_2')!.isCritical, isTrue);
      expect(f.silentFor('dev_1'), isNull);
    });
  });

  group('device list', () {
    testWidgets('connection, last seen and linked field per device', (t) async {
      await pumpList(t, devAdapter(list: devices));
      Finder inTile(String id, Finder f) =>
          find.descendant(of: find.byKey(ValueKey('device:$id')), matching: f);
      expect(inTile('dev_1', find.text('متّصل')), findsOneWidget);
      expect(
        inTile('dev_1', find.textContaining('آخر ظهور منذ 5 دقيقة')),
        findsOneWidget,
      );
      expect(
        inTile('dev_1', find.textContaining('الحقل: الحقل الشماليّ')),
        findsOneWidget,
      );
      expect(inTile('dev_2', find.text('غير متّصل')), findsOneWidget);
      expect(inTile('dev_2', find.text('صامت — حرج')), findsOneWidget);
      expect(inTile('dev_3', find.text('لم يتّصل قطّ')), findsOneWidget);
      expect(
        inTile('dev_3', find.textContaining('لم يُرسل أيّ قراءة بعد')),
        findsOneWidget,
      );
      expect(find.textContaining('1 جهاز حرج صامت'), findsOneWidget);
    });

    testWidgets('chevrons point forward in RTL (no chevron_left)', (t) async {
      await pumpList(t, devAdapter(list: devices));
      expect(find.byIcon(Icons.chevron_left), findsNothing);
      expect(find.byIcon(Icons.chevron_right_rounded), findsWidgets);
    });

    testWidgets('fleet health failing does not hide the device list', (
      t,
    ) async {
      await pumpList(
        t,
        devAdapter(list: devices, fleetReply: (_) => const FakeReply(503)),
        fields: fieldsFail,
      );
      await settle(t, frames: 30);
      expect(find.text('حسّاس الرطوبة'), findsOneWidget);
      expect(find.text('تعذّر حساب صحّة الأسطول'), findsOneWidget);
      // أسماء الحقول غير متاحة ⇒ «مرتبط بحقل» لا معرّف خامّ.
      expect(find.textContaining('الحقل: مرتبط بحقل'), findsOneWidget);
    });

    testWidgets('empty registry is an honest empty state', (t) async {
      await pumpList(t, devAdapter());
      expect(find.text('لا أجهزة مسجّلة بعد'), findsOneWidget);
    });

    testWidgets('403 on the list is an honest permission error', (t) async {
      await pumpList(
        t,
        routeAdapter({
          'GET /api/v1/devices': (_) => const FakeReply(403),
          'GET /api/v1/devices/fleet-health': (_) => const FakeReply(403),
        }),
      );
      expect(
        find.text('لا تملك صلاحيّة الوصول إلى هذا القسم.'),
        findsOneWidget,
      );
    });

    testWidgets('only owner/manager can register devices', (t) async {
      await pumpList(t, devAdapter(list: devices), role: AppRole.agronomist);
      expect(find.text('تسجيل جهاز'), findsNothing);
      expect(find.byTooltip('تحديث'), findsOneWidget);
    });

    testWidgets('tapping a device opens its readings', (t) async {
      await pumpList(t, devAdapter(list: devices, telemetry: readings(4)));
      await t.tap(find.text('حسّاس الرطوبة'));
      await t.pumpAndSettle();
      expect(find.byType(DeviceDetailScreen), findsOneWidget);
      expect(find.byType(LineChart), findsOneWidget);
    });
  });

  group('device readings', () {
    testWidgets('latest value with age and a chart per sensor', (t) async {
      await pumpDetail(
        t,
        devAdapter(
          list: devices,
          telemetry: [
            ...readings(5),
            ...readings(3, sensor: 'air_temp'),
          ],
        ),
        'dev_1',
      );
      expect(
        find.byKey(const ValueKey('series:soil_moisture')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('series:air_temp')), findsOneWidget);
      expect(find.byType(LineChart), findsNWidgets(2));
      expect(find.text('20'), findsWidgets); // آخر قيمة (fmtNumber)
      expect(find.textContaining('الآن'), findsWidgets);
    });

    testWidgets('no readings: an explicit "لا قراءات", no empty chart', (
      t,
    ) async {
      await pumpDetail(t, devAdapter(list: devices), 'dev_1');
      expect(find.text(kNoReadings), findsOneWidget);
      expect(find.byType(LineChart), findsNothing);
      expect(find.text('0'), findsNothing);
    });

    testWidgets('a single reading is shown but not drawn as a trend', (
      t,
    ) async {
      await pumpDetail(
        t,
        devAdapter(list: devices, telemetry: readings(1)),
        'dev_1',
      );
      expect(find.textContaining('قراءة واحدة فقط'), findsOneWidget);
      expect(find.byType(LineChart), findsNothing);
    });

    testWidgets('actuators are monitor-only: no command buttons', (t) async {
      await pumpDetail(t, devAdapter(list: devices), 'dev_3');
      expect(find.text(kActuatorMonitorOnly), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
      expect(find.textContaining('فتح الصمّام'), findsNothing);
    });

    testWidgets('telemetry 503 is the honest service message', (t) async {
      await pumpDetail(
        t,
        routeAdapter({
          'GET /api/v1/devices': (_) => FakeReply(200, devices),
          'GET /api/v1/devices/dev_1/telemetry': (_) => const FakeReply(503),
        }),
        'dev_1',
      );
      await settle(t, frames: 30);
      expect(
        find.text(
          'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
        ),
        findsOneWidget,
      );
    });

    test('deep link /devices/detail is owned by devices', () {
      expect(
        AppRouter.instance.match('/devices/detail?device_id=d')?.path,
        '/devices/detail',
      );
      expect(AppRouter.instance.ownerOf('/devices/detail'), 'devices');
    });
  });

  group('register sheet', () {
    Future<void> openSheet(
      WidgetTester t,
      FakeAdapter a, {
      Future<List<Map<String, dynamic>>> Function() fields = fieldsOk,
    }) async {
      await pumpList(t, a, fields: fields);
      await t.tap(find.text('تسجيل جهاز'));
      await t.pumpAndSettle();
    }

    testWidgets('validation inside the sheet; unlinked soil warning', (
      t,
    ) async {
      final a = devAdapter(
        list: devices,
        onPost: (_) => const FakeReply(201, {}),
      );
      await openSheet(t, a);
      expect(
        inBottomSheet(find.textContaining('لا تصل إلى توصيات الريّ')),
        findsOneWidget,
      );
      await t.tap(find.text('تسجيل الجهاز'));
      await t.pump();
      expect(inBottomSheet(find.text('الاسم مطلوب')), findsOneWidget);
      expect(find.byType(SnackBar), findsNothing);
      expect(a.requests.where((r) => r.method == 'POST'), isEmpty);
    });

    testWidgets('links the device to a chosen field with an idempotency key', (
      t,
    ) async {
      final a = devAdapter(
        list: devices,
        onPost: (_) => const FakeReply(201, {'device_id': 'dev_9'}),
      );
      await openSheet(t, a);
      await t.enterText(
        inBottomSheet(find.widgetWithText(TextFormField, 'الاسم')),
        'حسّاس',
      );
      await t.tap(inBottomSheet(find.text('بلا حقل')));
      await t.pumpAndSettle();
      await t.tap(find.text('حقل الوادي').last);
      await t.pumpAndSettle();
      expect(
        inBottomSheet(find.textContaining('لا تصل إلى توصيات الريّ')),
        findsNothing,
      );
      await t.tap(find.text('تسجيل الجهاز'));
      await settle(t);
      final post = a.requests.singleWhere((r) => r.method == 'POST');
      final body = requestBody(post);
      expect(body['field_id'], 'f2');
      expect(body['type'], 'soil_moisture');
      expect(post.headers[kIdempotencyHeader], isNotEmpty);
      await t.pumpAndSettle();
      expect(find.text('سُجّل الجهاز'), findsOneWidget);
    });

    testWidgets('fields failing to load still allows registering unlinked', (
      t,
    ) async {
      final a = devAdapter(
        list: devices,
        onPost: (_) => const FakeReply(201, {}),
      );
      await openSheet(t, a, fields: fieldsFail);
      expect(
        inBottomSheet(find.textContaining('تعذّر تحميل الحقول')),
        findsOneWidget,
      );
    });
  });
}
