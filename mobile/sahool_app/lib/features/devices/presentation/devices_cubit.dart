// SAHOOL — features/devices/presentation/devices_cubit.dart
// حالتا شاشتَي الأجهزة: السجلّ (الأجهزة + صحّة الأسطول + أسماء الحقول) وقراءات
// جهاز واحد مجمّعة بالمستشعر. صحّة الأسطول وأسماء الحقول إضافيّتان: فشلهما لا
// يُسقط القائمة بل يُعلَن مكانهما («غير متاح»)، وفشل القائمة نفسها خطأ صادق.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/devices/data/devices_api.dart';
import 'package:sahool_app/features/devices/data/devices_models.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

/// يحمّل حقول المستخدم ({field_id, name_ar, …}). الافتراضيّ FieldsApi.
typedef FieldsLoader = Future<List<Map<String, dynamic>>> Function();

FieldsLoader defaultFieldsLoader() => FieldsApi.instance.listFields;

/// field_id ⇒ الاسم العربيّ.
Map<String, String> fieldNamesOf(List<Map<String, dynamic>> fields) => {
  for (final f in fields)
    if (f['field_id'] != null)
      f['field_id'].toString(): (f['name_ar'] ?? f['name'] ?? f['field_id'])
          .toString(),
};

// ── السجلّ ──────────────────────────────────────────────────────────

sealed class DevicesState {
  const DevicesState();
}

class DevicesLoading extends DevicesState {
  const DevicesLoading();
}

class DevicesFailed extends DevicesState {
  const DevicesFailed(this.error);
  final ApiException error;
}

class DevicesLoaded extends DevicesState {
  const DevicesLoaded({
    required this.devices,
    required this.fetchedAt,
    this.fleet,
    this.fleetError,
    this.fieldNames,
    this.refreshError,
  });

  final List<Device> devices;
  final DateTime fetchedAt;

  /// null ⇒ تعذّر حساب صحّة الأسطول ([fleetError]).
  final FleetHealth? fleet;
  final ApiException? fleetError;

  /// null ⇒ تعذّر تحميل أسماء الحقول (يُعرض «مرتبط بحقل» فقط).
  final Map<String, String>? fieldNames;
  final ApiException? refreshError;

  int get onlineCount => devices.where((d) => d.online).length;
}

class DevicesCubit extends Cubit<DevicesState> {
  DevicesCubit(this._api, {FieldsLoader? fields, DateTime Function()? clock})
    : _fields = fields ?? defaultFieldsLoader(),
      _clock = clock ?? DateTime.now,
      super(const DevicesLoading());

  final DevicesApi _api;
  final FieldsLoader _fields;
  final DateTime Function() _clock;

  Future<void> load() async {
    if (state is! DevicesLoaded) emit(const DevicesLoading());
    ApiException? fleetError;
    final fleetF = _api.fleetHealth().then<FleetHealth?>(
      (f) => f,
      onError: (Object e) {
        fleetError = ApiException.from(e);
        return null;
      },
    );
    final fieldsF = Future.sync(
      _fields,
    ).then<Map<String, String>?>(fieldNamesOf, onError: (Object _) => null);
    try {
      final devices = await _api.listDevicesTyped();
      final fleet = await fleetF;
      final names = await fieldsF;
      if (isClosed) return;
      emit(
        DevicesLoaded(
          devices: devices,
          fetchedAt: _clock(),
          fleet: fleet,
          fleetError: fleetError,
          fieldNames: names,
        ),
      );
    } catch (e) {
      // لا نترك المستقبلين الإضافيّين بلا انتظار (أخطاؤهما مُلتقَطة أعلاه).
      await Future.wait([fleetF, fieldsF]);
      if (isClosed) return;
      final err = ApiException.from(e);
      final prev = state;
      emit(
        prev is DevicesLoaded
            ? DevicesLoaded(
                devices: prev.devices,
                fetchedAt: prev.fetchedAt,
                fleet: prev.fleet,
                fleetError: prev.fleetError,
                fieldNames: prev.fieldNames,
                refreshError: err,
              )
            : DevicesFailed(err),
      );
    }
  }
}

// ── قراءات جهاز ─────────────────────────────────────────────────────

/// عدد القراءات المطلوبة لكلّ عرض (الخادم ≤1000).
const int kTelemetryWindow = 500;

sealed class TelemetryState {
  const TelemetryState();
}

class TelemetryLoading extends TelemetryState {
  const TelemetryLoading();
}

class TelemetryFailed extends TelemetryState {
  const TelemetryFailed(this.error);
  final ApiException error;
}

class TelemetryLoaded extends TelemetryState {
  const TelemetryLoaded({
    required this.device,
    required this.series,
    required this.rawCount,
    required this.fetchedAt,
    this.refreshError,
  });

  final Device device;
  final List<SensorSeries> series;

  /// عدد القراءات كما أعادها الخادم (قد يفوق المرسوم إن نقصت قيمة/وقت).
  final int rawCount;
  final DateTime fetchedAt;
  final ApiException? refreshError;

  bool get isEmpty => series.isEmpty;
}

class TelemetryCubit extends Cubit<TelemetryState> {
  TelemetryCubit(this._api, this.deviceId, {DateTime Function()? clock})
    : _clock = clock ?? DateTime.now,
      super(const TelemetryLoading());

  final DevicesApi _api;
  final String deviceId;
  final DateTime Function() _clock;

  Future<void> load() async {
    if (state is! TelemetryLoaded) emit(const TelemetryLoading());
    try {
      // السجلّ يُعاد مع كلّ تحديث: «آخر ظهور» و«متّصل» يتغيّران مع القراءات،
      // ولا نقطة لقراءة جهاز واحد (والرابط العميق يصل بلا جهاز).
      final results = await Future.wait<Object>([
        _api.telemetry(deviceId, limit: kTelemetryWindow),
        _api.listDevicesTyped(),
      ]);
      if (isClosed) return;
      Device? device;
      for (final d in results[1] as List<Device>) {
        if (d.id == deviceId) device = d;
      }
      if (device == null) {
        emit(
          const TelemetryFailed(
            ApiException(
              kind: ApiErrorKind.notFound,
              statusCode: 404,
              messageAr: 'العنصر غير موجود.',
            ),
          ),
        );
        return;
      }
      final raw = results[0] as List<TelemetryPoint>;
      emit(
        TelemetryLoaded(
          device: device,
          series: SensorSeries.group(raw),
          rawCount: raw.length,
          fetchedAt: _clock(),
        ),
      );
    } catch (e) {
      if (isClosed) return;
      final err = ApiException.from(e);
      final prev = state;
      emit(
        prev is TelemetryLoaded
            ? TelemetryLoaded(
                device: prev.device,
                series: prev.series,
                rawCount: prev.rawCount,
                fetchedAt: prev.fetchedAt,
                refreshError: err,
              )
            : TelemetryFailed(err),
      );
    }
  }
}
