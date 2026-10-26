// SAHOOL — features/devices/data/devices_api.dart
// نقاط أجهزة IoT والقياسات (device:view / device:manage / observation:record).
// يملكه وكيل الأجهزة.
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'devices_models.dart';

class DevicesApi {
  DevicesApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final DevicesApi instance = DevicesApi();
  final ApiClient _client;

  Future<List<Map<String, dynamic>>> listDevices() async =>
      asJsonList(await _client.get('/api/v1/devices'));

  Future<Map<String, dynamic>> registerDevice(
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/devices',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  Future<List<Map<String, dynamic>>> getDeviceTelemetry(
    String deviceId, {
    int limit = 20,
  }) async => asJsonList(
    await _client.get(
      '/api/v1/devices/$deviceId/telemetry',
      query: {'limit': limit},
    ),
  );

  Future<Map<String, dynamic>> recordTelemetry(
    String deviceId,
    Map<String, dynamic> payload, {
    IdempotencyKey? idempotencyKey,
  }) async => asJsonMap(
    await _client.post(
      '/api/v1/devices/$deviceId/telemetry',
      data: payload,
      idempotencyKey: idempotencyKey,
    ),
  );

  // ── نسخ مُنمَّطة وقراءات إضافيّة (append-only) ─────────────────────────

  Future<List<Device>> listDevicesTyped() async =>
      (await listDevices()).map(Device.fromJson).toList();

  /// أحدث [limit] قراءة (الخادم يقيّده بـ1..1000)، الأحدث أوّلاً.
  Future<List<TelemetryPoint>> telemetry(
    String deviceId, {
    int limit = 500,
  }) async => (await getDeviceTelemetry(
    deviceId,
    limit: limit,
  )).map(TelemetryPoint.fromJson).toList();

  /// صحّة الأسطول: الأجهزة الصامتة مرتّبة بالخطورة (مراقبة فقط، لا تحكّم).
  Future<FleetHealth> fleetHealth() async => FleetHealth.fromJson(
    asJsonMap(await _client.get('/api/v1/devices/fleet-health')),
  );
}
