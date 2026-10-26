// SAHOOL — features/devices/data/devices_models.dart
// نماذج أجهزة IoT كما يُعيدها الخادم (services/sahool-platform/api/routers/
// devices.py، fleet_health.py، device_registry.py). «متّصل» يحسبه الخادم من
// last_seen_at (نافذة 15 دقيقة)؛ «صامت» في صحّة الأسطول يحسبه بعتبة لكلّ نوع.
// لا أوامر تحكّم هنا: المشغّلات تُعرَض ولا تُشغَّل من التطبيق.

const Map<String, String> kDeviceTypes = {
  'soil_moisture': 'رطوبة التربة',
  'weather_station': 'محطّة طقس',
  'water_meter': 'عدّاد ماء',
  'camera': 'كاميرا',
  'actuator': 'مُشغِّل (صمّام/مضخّة)',
  'other': 'أخرى',
};

/// أسماء القياسات المعروفة (telemetry_fields في device_registry.py).
const Map<String, String> kSensorLabels = {
  'soil_moisture': 'رطوبة التربة',
  'air_temp': 'حرارة الهواء',
  'air_humidity': 'رطوبة الهواء',
  'rainfall': 'الهطول',
  'wind_speed': 'سرعة الرياح',
  'water_flow': 'تدفّق الماء',
  'water_volume': 'حجم الماء',
};

String sensorLabel(String sensorType) =>
    kSensorLabels[sensorType] ?? sensorType;

double? _toDouble(Object? v) {
  if (v is num) return v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

DateTime? _instant(Object? v) =>
    v is String && v.isNotEmpty ? DateTime.tryParse(v) : null;

class Device {
  const Device({
    required this.id,
    required this.name,
    required this.type,
    required this.fieldId,
    required this.status,
    required this.online,
    required this.lastSeenAt,
    required this.firmwareVersion,
  });

  factory Device.fromJson(Map<String, dynamic> m) {
    final id = m['device_id'];
    if (id == null) {
      throw const FormatException('جهاز بلا device_id في استجابة الخادم.');
    }
    final field = m['field_id'];
    return Device(
      id: id.toString(),
      name: (m['name'] ?? '').toString(),
      type: (m['type'] ?? 'other').toString(),
      fieldId: field == null || '$field'.isEmpty ? null : field.toString(),
      status: (m['status'] ?? 'unknown').toString(),
      online: m['online'] == true,
      lastSeenAt: _instant(m['last_seen_at']),
      firmwareVersion: m['firmware_version']?.toString(),
    );
  }

  final String id;
  final String name;
  final String type;
  final String? fieldId;
  final String status;

  /// ظهر خلال آخر 15 دقيقة (محسوب خادميّاً).
  final bool online;

  /// null ⇒ لم يُرسل الجهاز أيّ قراءة قطّ.
  final DateTime? lastSeenAt;
  final String? firmwareVersion;

  String get typeLabel => kDeviceTypes[type] ?? type;
  bool get neverSeen => lastSeenAt == null;
  bool get isActuator => type == 'actuator';
}

class TelemetryPoint {
  const TelemetryPoint({
    required this.sensorType,
    required this.value,
    required this.unit,
    required this.recordedAt,
  });

  factory TelemetryPoint.fromJson(Map<String, dynamic> m) => TelemetryPoint(
    sensorType: (m['sensor_type'] ?? '').toString(),
    value: _toDouble(m['value']),
    unit: (m['unit'] as String?)?.trim().isEmpty ?? true
        ? null
        : (m['unit'] as String).trim(),
    recordedAt: _instant(m['recorded_at']),
  );

  final String sensorType;
  final double? value;
  final String? unit;
  final DateTime? recordedAt;
}

/// سلسلة قراءات مستشعر واحد، تصاعديّاً بالزمن (للرسم).
class SensorSeries {
  const SensorSeries({required this.sensorType, required this.points});

  final String sensorType;

  /// قراءات بقيمة ووقت، الأقدم أوّلاً.
  final List<TelemetryPoint> points;

  TelemetryPoint? get latest => points.isEmpty ? null : points.last;
  String? get unit => latest?.unit;
  String get label => sensorLabel(sensorType);

  /// يجمّع القراءات حسب المستشعر؛ قراءة بلا قيمة أو وقت لا تُرسَم.
  static List<SensorSeries> group(List<TelemetryPoint> raw) {
    final by = <String, List<TelemetryPoint>>{};
    for (final p in raw) {
      if (p.value == null || p.recordedAt == null) continue;
      by.putIfAbsent(p.sensorType, () => []).add(p);
    }
    final out = [
      for (final e in by.entries)
        SensorSeries(
          sensorType: e.key,
          points: e.value
            ..sort((a, b) => a.recordedAt!.compareTo(b.recordedAt!)),
        ),
    ]..sort((a, b) => b.latest!.recordedAt!.compareTo(a.latest!.recordedAt!));
    return out;
  }
}

class SilentDevice {
  const SilentDevice({
    required this.deviceId,
    required this.name,
    required this.criticality,
    required this.detailAr,
    required this.criticalityNoteAr,
  });

  factory SilentDevice.fromJson(Map<String, dynamic> m) => SilentDevice(
    deviceId: (m['device_id'] ?? '').toString(),
    name: (m['name'] ?? '').toString(),
    criticality: (m['criticality'] ?? '').toString(),
    detailAr: (m['detail_ar'] ?? '').toString(),
    criticalityNoteAr: (m['criticality_note_ar'] ?? '').toString(),
  );

  final String deviceId;
  final String name;

  /// critical | important | optional
  final String criticality;
  final String detailAr;
  final String criticalityNoteAr;

  bool get isCritical => criticality == 'critical';
}

class FleetHealth {
  const FleetHealth({
    required this.totalDevices,
    required this.silent,
    required this.criticalSilent,
    required this.silentDevices,
  });

  factory FleetHealth.fromJson(Map<String, dynamic> m) {
    final list = m['silent_devices'];
    return FleetHealth(
      totalDevices: (m['total_devices'] as num?)?.toInt(),
      silent: (m['silent'] as num?)?.toInt(),
      criticalSilent: (m['critical_silent'] as num?)?.toInt(),
      silentDevices: list is List
          ? [
              for (final e in list)
                if (e is Map) SilentDevice.fromJson(e.cast<String, dynamic>()),
            ]
          : const [],
    );
  }

  final int? totalDevices;
  final int? silent;
  final int? criticalSilent;

  /// مرتّبة بالخطورة (الحرجة أوّلاً) كما يُعيدها الخادم.
  final List<SilentDevice> silentDevices;

  SilentDevice? silentFor(String deviceId) {
    for (final s in silentDevices) {
      if (s.deviceId == deviceId) return s;
    }
    return null;
  }
}
