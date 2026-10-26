// SAHOOL — features/weather/presentation/weather_cubit.dart
// طقس حقل واحد: كلّ قسم يُحمَّل مستقلّاً ويحمل حالته الصادقة (تحميل/جاهز/فشل/
// غير متاح)، فتعذّر منتجٍ واحد (مثل توصية الريّ بلا موسم) لا يُسقط الصفحة.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';

import '../data/weather_api.dart';
import '../data/weather_models.dart';

enum SectionStatus { loading, ready, failed, unavailable }

@immutable
class Section<T> {
  const Section.loading()
    : status = SectionStatus.loading,
      data = null,
      error = null,
      reasonAr = null;
  const Section.ready(T this.data)
    : status = SectionStatus.ready,
      error = null,
      reasonAr = null;
  const Section.failed(ApiException this.error)
    : status = SectionStatus.failed,
      data = null,
      reasonAr = null;
  const Section.unavailable(String this.reasonAr)
    : status = SectionStatus.unavailable,
      data = null,
      error = null;

  final SectionStatus status;
  final T? data;
  final ApiException? error;
  final String? reasonAr;

  bool get isLoading => status == SectionStatus.loading;
}

/// نصّ الخطأ: 422 من نقاط الحقل يحمل أحياناً {code, message_ar} لا نصّاً.
String weatherErrorText(ApiException e) {
  final d = e.detail;
  if (d is Map && d['message_ar'] != null) return d['message_ar'].toString();
  return e.messageAr;
}

const String kNoFieldWeather = 'لا بيانات طقس لهذا الحقل';
const String kNoCoordinatesReason =
    'لم يُحدَّد موقع الحقل (الإحداثيّات) بعد — حدّده من مساحة عمل الحقل ليظهر طقسه.';

@immutable
class WeatherState {
  const WeatherState({
    this.location = const Section.loading(),
    this.current = const Section.loading(),
    this.forecast = const Section.loading(),
    this.alerts = const Section.loading(),
    this.windows = const Section.loading(),
    this.irrigation = const Section.loading(),
    this.disease = const Section.loading(),
    this.thermal = const Section.loading(),
    this.cropStress = const Section.loading(),
    this.loadedAt,
  });

  final Section<FieldLocation> location;
  final Section<CurrentWeather> current;
  final Section<WeatherForecast> forecast;
  final Section<List<WeatherAlert>> alerts;
  final Section<OperationWindows> windows;
  final Section<IrrigationAdvice> irrigation;
  final Section<DiseaseRisk> disease;
  final Section<ThermalStress> thermal;
  final Section<CropStress> cropStress;
  final DateTime? loadedAt;

  /// الحقل معروف لكن بلا إحداثيّات ⇒ لا طقس صادقاً.
  bool get noCoordinates =>
      location.status == SectionStatus.ready && !location.data!.hasCoordinates;

  WeatherState copyWith({
    Section<FieldLocation>? location,
    Section<CurrentWeather>? current,
    Section<WeatherForecast>? forecast,
    Section<List<WeatherAlert>>? alerts,
    Section<OperationWindows>? windows,
    Section<IrrigationAdvice>? irrigation,
    Section<DiseaseRisk>? disease,
    Section<ThermalStress>? thermal,
    Section<CropStress>? cropStress,
    DateTime? loadedAt,
  }) => WeatherState(
    location: location ?? this.location,
    current: current ?? this.current,
    forecast: forecast ?? this.forecast,
    alerts: alerts ?? this.alerts,
    windows: windows ?? this.windows,
    irrigation: irrigation ?? this.irrigation,
    disease: disease ?? this.disease,
    thermal: thermal ?? this.thermal,
    cropStress: cropStress ?? this.cropStress,
    loadedAt: loadedAt ?? this.loadedAt,
  );
}

class WeatherCubit extends Cubit<WeatherState> {
  WeatherCubit(this._api, this.fieldId) : super(const WeatherState());

  final WeatherApi _api;
  final String fieldId;
  int _generation = 0;

  Future<void> load() async {
    final gen = ++_generation;
    emit(const WeatherState());
    bool live() => !isClosed && gen == _generation;

    Future<void> run<T>(
      Future<T> Function() call,
      WeatherState Function(Section<T>) put,
    ) async {
      Section<T> s;
      try {
        s = Section.ready(await call());
      } catch (e) {
        s = Section.failed(ApiException.from(e));
      }
      // حقل بلا إحداثيّات: الصفحة كلّها «لا بيانات طقس» — لا نعرض أخطاء 422 مكرّرة.
      if (live() && !state.noCoordinates) emit(put(s));
    }

    final fieldCalls = <Future<void>>[
      run(
        () => _api.operationWindows(fieldId),
        (s) => state.copyWith(windows: s),
      ),
      run(
        () => _api.irrigationAdvice(fieldId),
        (s) => state.copyWith(irrigation: s),
      ),
      run(() => _api.diseaseRisk(fieldId), (s) => state.copyWith(disease: s)),
      run(() => _api.thermalStress(fieldId), (s) => state.copyWith(thermal: s)),
      run(() => _api.cropStress(fieldId), (s) => state.copyWith(cropStress: s)),
    ];

    FieldLocation loc;
    try {
      loc = await _api.getFieldLocation(fieldId);
    } catch (e) {
      if (live()) {
        emit(state.copyWith(location: Section.failed(ApiException.from(e))));
      }
      await Future.wait(fieldCalls);
      return;
    }
    if (!live()) return;
    if (!loc.hasCoordinates) {
      emit(
        WeatherState(
          location: Section.ready(loc),
          current: const Section.unavailable(kNoCoordinatesReason),
          forecast: const Section.unavailable(kNoCoordinatesReason),
          alerts: const Section.unavailable(kNoCoordinatesReason),
          windows: const Section.unavailable(kNoCoordinatesReason),
          irrigation: const Section.unavailable(kNoCoordinatesReason),
          disease: const Section.unavailable(kNoCoordinatesReason),
          thermal: const Section.unavailable(kNoCoordinatesReason),
          cropStress: const Section.unavailable(kNoCoordinatesReason),
          loadedAt: DateTime.now(),
        ),
      );
      await Future.wait(fieldCalls);
      return;
    }
    emit(
      state.copyWith(location: Section.ready(loc), loadedAt: DateTime.now()),
    );
    final lat = loc.lat!, lon = loc.lon!;
    await Future.wait([
      ...fieldCalls,
      run(() => _api.current(lat, lon), (s) {
        // استجابة بلا أيّ قراءة ⇒ «غير متاح» لا بطاقة أصفار.
        final c = s.data;
        if (c != null && !c.hasAnyReading) {
          return state.copyWith(
            current: const Section.unavailable(
              'خدمة الطقس لم تُرجع قراءات حاليّة لموقع الحقل.',
            ),
          );
        }
        return state.copyWith(current: s);
      }),
      run(() => _api.forecast(lat, lon), (s) {
        final f = s.data;
        if (f != null && f.days.isEmpty) {
          return state.copyWith(
            forecast: const Section.unavailable(
              'خدمة الطقس لم تُرجع أيّام توقّع لموقع الحقل.',
            ),
          );
        }
        return state.copyWith(forecast: s);
      }),
      run(() => _api.weatherAlerts(lat, lon), (s) => state.copyWith(alerts: s)),
    ]);
  }
}
