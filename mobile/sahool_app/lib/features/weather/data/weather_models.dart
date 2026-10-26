// SAHOOL — features/weather/data/weather_models.dart
// نماذج الطقس بأسماء مفاتيح الخادم حرفيّاً. كلّ قيمة غائبة تبقى null وتُعرَض
// «غير مقيس» — الصفر قراءة فيزيائيّة (0 مم = لا مطر) لا يُخلط بالغياب.
import 'package:flutter/foundation.dart';

double? _num(Object? v) {
  if (v is num) return v.isNaN ? null : v.toDouble();
  if (v is String) return double.tryParse(v);
  return null;
}

int? _int(Object? v) => _num(v)?.round();

String? _str(Object? v) {
  if (v == null) return null;
  final s = v.toString();
  return s.isEmpty ? null : s;
}

DateTime? _date(Object? v) {
  final s = _str(v);
  return s == null ? null : DateTime.tryParse(s);
}

List<String> _strList(Object? v) =>
    v is List ? v.map((e) => e.toString()).toList() : const [];

/// موقع الحقل من GET /api/v1/fields/{id}.
@immutable
class FieldLocation {
  const FieldLocation({
    required this.fieldId,
    this.nameAr,
    this.lat,
    this.lon,
    this.crop,
  });
  final String fieldId;
  final String? nameAr;
  final double? lat;
  final double? lon;
  final String? crop;

  bool get hasCoordinates => lat != null && lon != null;

  factory FieldLocation.fromJson(Map<String, dynamic> j) => FieldLocation(
    fieldId: _str(j['field_id']) ?? '',
    nameAr: _str(j['name_ar']),
    lat: _num(j['lat']),
    lon: _num(j['lon']),
    crop: _str(j['crop']),
  );
}

/// الطقس الآن (current_view).
@immutable
class CurrentWeather {
  const CurrentWeather({
    this.temperatureC,
    this.humidityPct,
    this.windKmh,
    this.precipitationMm,
    this.weatherCode,
    this.time,
    this.qualityStatus,
    this.missingFields = const [],
  });

  final double? temperatureC;
  final double? humidityPct;
  final double? windKmh;
  final double? precipitationMm;
  final int? weatherCode;
  final DateTime? time;
  final String? qualityStatus;
  final List<String> missingFields;

  bool get hasAnyReading =>
      temperatureC != null ||
      humidityPct != null ||
      windKmh != null ||
      precipitationMm != null;

  bool get degraded =>
      missingFields.isNotEmpty ||
      (qualityStatus != null &&
          qualityStatus != 'validated' &&
          qualityStatus != 'ok');

  factory CurrentWeather.fromJson(Map<String, dynamic> j) {
    final kmh = _num(j['wind_speed_10m_kmh']);
    final ms = _num(j['wind_speed_ms']);
    return CurrentWeather(
      temperatureC: _num(j['temperature_c']),
      humidityPct: _num(j['humidity_pct']),
      windKmh: kmh ?? (ms == null ? null : ms * 3.6),
      precipitationMm: _num(j['precipitation_mm']),
      weatherCode: _int(j['weather_code']),
      time: _date(j['time'] ?? j['timestamp']),
      qualityStatus: _str(j['quality_status']),
      missingFields: _strList(j['missing_fields']),
    );
  }
}

/// يوم توقّع (normalize_daily).
@immutable
class ForecastDay {
  const ForecastDay({
    this.date,
    this.tempMaxC,
    this.tempMinC,
    this.precipitationMm,
    this.windMaxKmh,
    this.et0Mm,
    this.weatherCode,
    this.rhMeanPct,
  });

  final DateTime? date;
  final double? tempMaxC;
  final double? tempMinC;
  final double? precipitationMm;
  final double? windMaxKmh;
  final double? et0Mm;
  final int? weatherCode;
  final double? rhMeanPct;

  factory ForecastDay.fromJson(Map<String, dynamic> j) {
    final kmh = _num(j['wind_max_kmh']);
    final ms = _num(j['wind_max_ms']);
    return ForecastDay(
      date: _date(j['date']),
      tempMaxC: _num(j['temp_max_c']),
      tempMinC: _num(j['temp_min_c']),
      precipitationMm: _num(j['precipitation_mm']),
      windMaxKmh: kmh ?? (ms == null ? null : ms * 3.6),
      et0Mm: _num(j['et0_mm']),
      weatherCode: _int(j['weather_code']),
      rhMeanPct: _num(j['rh_mean_pct']),
    );
  }
}

@immutable
class WeatherForecast {
  const WeatherForecast({required this.days, this.qualityStatus});
  final List<ForecastDay> days;
  final String? qualityStatus;

  factory WeatherForecast.fromJson(Map<String, dynamic> j) {
    final days = j['days'];
    if (days != null && days is! List) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: days ليست قائمة.',
      );
    }
    return WeatherForecast(
      days: (days as List? ?? const [])
          .whereType<Map>()
          .map((e) => ForecastDay.fromJson(e.cast<String, dynamic>()))
          .toList(),
      qualityStatus: _str(j['quality_status']),
    );
  }
}

/// نافذة عمليّة (field_workspace_weather._window_from_operation).
@immutable
class OperationWindow {
  const OperationWindow({
    required this.operation,
    required this.suitability,
    this.startAt,
    this.startOffsetHours,
    this.score,
    this.limitingFactors = const [],
    this.adviceAr,
    this.recommended = false,
  });

  final String operation;

  /// optimal | acceptable | poor | unsafe | unknown
  final String suitability;
  final DateTime? startAt;
  final int? startOffsetHours;
  final double? score;
  final List<String> limitingFactors;
  final String? adviceAr;
  final bool recommended;

  factory OperationWindow.fromJson(Map<String, dynamic> j) => OperationWindow(
    operation: _str(j['operation']) ?? '',
    suitability: _str(j['suitability']) ?? 'unknown',
    startAt: _date(j['start_at']),
    startOffsetHours: _int(j['start_offset_hours']),
    score: _num(j['score']),
    limitingFactors: _strList(j['limiting_factors']),
    adviceAr: _str(j['advice_ar']),
    recommended: j['recommended'] == true,
  );
}

@immutable
class OperationWindows {
  const OperationWindows({
    required this.windows,
    this.degraded = false,
    this.warningAr,
  });
  final List<OperationWindow> windows;
  final bool degraded;
  final String? warningAr;

  factory OperationWindows.fromJson(Map<String, dynamic> j) {
    final w = j['windows'];
    if (w is! List) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: نوافذ العمليّات ليست قائمة.',
      );
    }
    return OperationWindows(
      windows: w
          .whereType<Map>()
          .map((e) => OperationWindow.fromJson(e.cast<String, dynamic>()))
          .toList(),
      degraded: j['degraded'] == true,
      warningAr: _str(j['warning_ar']),
    );
  }

  OperationWindow? of(String operation) {
    for (final w in windows) {
      if (w.operation == operation) return w;
    }
    return null;
  }
}

/// توصية الريّ (weather_advice.irrigation_advice).
@immutable
class IrrigationAdvice {
  const IrrigationAdvice({
    this.recommendedMm,
    this.urgency,
    this.timingAr,
    this.rationaleAr,
    this.et0,
    this.soilMoisturePct,
    this.forecastHold = false,
  });
  final double? recommendedMm;

  /// none | low | moderate | high
  final String? urgency;
  final String? timingAr;
  final String? rationaleAr;
  final double? et0;
  final double? soilMoisturePct;
  final bool forecastHold;

  factory IrrigationAdvice.fromJson(Map<String, dynamic> j) => IrrigationAdvice(
    recommendedMm: _num(j['recommended_mm']),
    urgency: _str(j['urgency']),
    timingAr: _str(j['timing_ar']),
    rationaleAr: _str(j['rationale_ar']),
    et0: _num(j['et0']),
    soilMoisturePct: _num(j['soil_moisture_pct']),
    forecastHold: j['forecast_hold'] == true,
  );
}

/// خطر الأمراض الفطريّة (weather_advice.disease_risk).
@immutable
class DiseaseRisk {
  const DiseaseRisk({
    this.riskLevel,
    this.diseasesAr = const [],
    this.adviceAr,
    this.temperatureC,
    this.humidityPct,
    this.rainMm3d,
  });
  final String? riskLevel;
  final List<String> diseasesAr;
  final String? adviceAr;
  final double? temperatureC;
  final double? humidityPct;
  final double? rainMm3d;

  factory DiseaseRisk.fromJson(Map<String, dynamic> j) => DiseaseRisk(
    riskLevel: _str(j['risk_level']),
    diseasesAr: _strList(j['diseases_ar']),
    adviceAr: _str(j['advice_ar']),
    temperatureC: _num(j['temperature_c']),
    humidityPct: _num(j['humidity_pct']),
    rainMm3d: _num(j['rain_mm_3d']),
  );
}

/// الإجهاد الحراريّ المركّب (weather-service thermal_stress.py).
@immutable
class ThermalStress {
  const ThermalStress({
    this.status,
    this.risk,
    this.dayMaxC,
    this.nightMinC,
    this.heatStressDays,
    this.coldStressNights,
    this.frostNights,
    this.horizonDays,
    this.limitingFactors = const [],
  });

  /// ok | insufficient_context
  final String? status;

  /// none | low | moderate | high
  final String? risk;
  final double? dayMaxC;
  final double? nightMinC;
  final int? heatStressDays;
  final int? coldStressNights;
  final int? frostNights;
  final int? horizonDays;
  final List<String> limitingFactors;

  bool get insufficientContext => status == 'insufficient_context';

  factory ThermalStress.fromJson(Map<String, dynamic> j) => ThermalStress(
    status: _str(j['status']),
    risk: _str(j['risk']),
    dayMaxC: _num(j['day_max_c']),
    nightMinC: _num(j['night_min_c']),
    heatStressDays: _int(j['heat_stress_days']),
    coldStressNights: _int(j['cold_stress_nights']),
    frostNights: _int(j['frost_nights']),
    horizonDays: _int(j['horizon_days']),
    limitingFactors: _strList(j['limiting_factors']),
  );
}

/// منتج واحد من عائلة إجهاد المحصول (الرقود/التلقيح/البرودة).
@immutable
class CropStressProduct {
  const CropStressProduct({required this.key, this.status, this.risk});
  final String key;
  final String? status;
  final String? risk;
}

@immutable
class CropStress {
  const CropStress({
    required this.products,
    this.failed = const [],
    this.partial = false,
  });
  final List<CropStressProduct> products;

  /// منتجات تعذّر جلبها (best-effort على الخادم).
  final List<String> failed;
  final bool partial;

  factory CropStress.fromJson(Map<String, dynamic> j) {
    final p = j['products'];
    final products = <CropStressProduct>[];
    if (p is Map) {
      p.forEach((k, v) {
        final m = v is Map
            ? v.cast<String, dynamic>()
            : const <String, dynamic>{};
        products.add(
          CropStressProduct(
            key: k.toString(),
            status: _str(m['status']),
            risk: _str(m['risk'] ?? m['risk_level']),
          ),
        );
      });
    }
    final e = j['errors'];
    return CropStress(
      products: products,
      failed: e is Map ? e.keys.map((k) => k.toString()).toList() : const [],
      partial: j['partial'] == true,
    );
  }
}

/// تنبيه طقس مشتقّ (weather_alerts.derive_weather_alerts).
@immutable
class WeatherAlert {
  const WeatherAlert({
    required this.type,
    this.severity,
    this.titleAr,
    this.detailAr,
  });
  final String type;
  final String? severity;
  final String? titleAr;
  final String? detailAr;

  factory WeatherAlert.fromJson(Map<String, dynamic> j) => WeatherAlert(
    type: _str(j['type']) ?? '',
    severity: _str(j['severity']),
    titleAr: _str(j['title_ar']),
    detailAr: _str(j['detail_ar']),
  );
}
