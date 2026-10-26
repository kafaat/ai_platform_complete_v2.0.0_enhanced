// SAHOOL — features/weather/data/weather_api.dart
// نقاط ميزة الطقس. يملكه وكيل ميزة الطقس.
//
// العقود (services/sahool-platform/api):
//   GET /api/v1/fields/{id}                        routers/fields.py:1032 (FieldDetail:
//       name_ar, crop, lat, lon — موقع الحقل؛ null ⇒ لا طقس صادقاً)
//   GET /api/v1/weather/current?lat&lon            routers/weather.py:2085
//       ⇒ current_view (weather-service): temperature_c, humidity_pct,
//         wind_speed_10m_kmh/wind_speed_ms, precipitation_mm, weather_code, time,
//         quality_status, missing_fields
//   GET /api/v1/weather/forecast?lat&lon&days      routers/weather.py:2091
//       ⇒ forecast_view: {days: [{date, temp_max_c, temp_min_c, precipitation_mm,
//         et0_mm, wind_max_ms, wind_max_kmh, weather_code, rh_mean_pct, …}],
//         quality_status, days_missing_fields}
//   GET /api/v1/weather/alerts?lat&lon             routers/weather.py:2654
//       ⇒ {alerts: [{type, severity, title_ar, detail_ar, window}]}
//   GET /api/v1/fields/{id}/weather/operation-windows  field_workspace_weather.py:283
//   GET /api/v1/fields/{id}/weather/irrigation-advice  :334
//   GET /api/v1/fields/{id}/weather/disease-risk       :405
//   GET /api/v1/fields/{id}/weather/thermal-stress     :181
//   GET /api/v1/fields/{id}/weather/crop-stress        :216
// نقاط الحقل تستنتج lat/lon من الحقل على الخادم (422 إن غابت الإحداثيّات).
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/in_flight.dart';
import 'package:sahool_app/core/network/response_shape.dart';

import 'weather_models.dart';

class WeatherApi {
  WeatherApi([ApiClient? client]) : _client = client ?? ApiClient.instance;
  static final WeatherApi instance = WeatherApi();
  final ApiClient _client;
  final InFlight<FieldLocation> _locations = InFlight();

  static String _f(String fieldId) => Uri.encodeComponent(fieldId);

  /// موقع الحقل واسمه (يدمج الطلبات المتزامنة لنفس الحقل — شرائط متعدّدة).
  Future<FieldLocation> getFieldLocation(String fieldId) => _locations.run(
    fieldId,
    () async => FieldLocation.fromJson(
      asJsonMap(await _client.get('/api/v1/fields/${_f(fieldId)}')),
    ),
  );

  Future<CurrentWeather> current(double lat, double lon) async =>
      CurrentWeather.fromJson(
        asJsonMap(
          await _client.get(
            '/api/v1/weather/current',
            query: {'lat': lat, 'lon': lon},
          ),
        ),
      );

  Future<WeatherForecast> forecast(
    double lat,
    double lon, {
    int days = 7,
  }) async => WeatherForecast.fromJson(
    asJsonMap(
      await _client.get(
        '/api/v1/weather/forecast',
        query: {'lat': lat, 'lon': lon, 'days': days},
      ),
    ),
  );

  Future<List<WeatherAlert>> weatherAlerts(double lat, double lon) async {
    final r = asJsonMap(
      await _client.get(
        '/api/v1/weather/alerts',
        query: {'lat': lat, 'lon': lon},
      ),
    );
    return asWrappedJsonList(r, const [
      'alerts',
    ]).map(WeatherAlert.fromJson).toList();
  }

  Future<OperationWindows> operationWindows(
    String fieldId, {
    int horizonHours = 48,
  }) async => OperationWindows.fromJson(
    asJsonMap(
      await _client.get(
        '/api/v1/fields/${_f(fieldId)}/weather/operation-windows',
        query: {'horizon_hours': horizonHours},
      ),
    ),
  );

  Future<IrrigationAdvice> irrigationAdvice(String fieldId) async =>
      IrrigationAdvice.fromJson(
        asJsonMap(
          await _client.get(
            '/api/v1/fields/${_f(fieldId)}/weather/irrigation-advice',
          ),
        ),
      );

  Future<DiseaseRisk> diseaseRisk(String fieldId) async => DiseaseRisk.fromJson(
    asJsonMap(
      await _client.get('/api/v1/fields/${_f(fieldId)}/weather/disease-risk'),
    ),
  );

  Future<ThermalStress> thermalStress(String fieldId, {int days = 3}) async =>
      ThermalStress.fromJson(
        asJsonMap(
          await _client.get(
            '/api/v1/fields/${_f(fieldId)}/weather/thermal-stress',
            query: {'days': days},
          ),
        ),
      );

  Future<CropStress> cropStress(String fieldId) async => CropStress.fromJson(
    asJsonMap(
      await _client.get('/api/v1/fields/${_f(fieldId)}/weather/crop-stress'),
    ),
  );
}
