// SAHOOL — features/maps/io/gps/gps_walk_cubit.dart
// مشي حدود الحقل بتيّار GPS مستمرّ (بدل قراءة واحدة لكلّ ضغطة تتجاهل الدقّة).
//
// كلّ قراءة تمرّ بـ[GpsFixFilter]: تُرفض الدقّة الأسوأ من الحدّ (افتراضاً 10 م)،
// والدقّة المجهولة، والموقع الوهميّ (mock)، والقفزة غير الممكنة مشياً/قيادةً،
// وتُتجاهل القراءة الملاصقة لسابقتها (الوقوف في مكان). الإيقاف المؤقّت يُلغي
// الاشتراك (لا قراءات ولا استهلاك بطّاريّة)، والاستئناف يُعيده. عند الإنهاء يُبسَّط
// المسار بـDouglas–Peucker. لا إحداثيّة تُختلَق: كلّ رأس قراءةٌ حقيقيّة مقبولة.
import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';

import '../geo/douglas_peucker.dart';
import '../geo/io_geometry.dart';
import '../geo/io_measure.dart';
import 'location_source.dart';

enum FixVerdict {
  accepted,
  poorAccuracy,
  unknownAccuracy,
  mocked,
  jump,
  tooClose,
}

extension FixVerdictAr on FixVerdict {
  String get messageAr => switch (this) {
    FixVerdict.accepted => 'قراءة مقبولة',
    FixVerdict.poorAccuracy => 'رُفضت: الدقّة أضعف من الحدّ',
    FixVerdict.unknownAccuracy => 'رُفضت: دقّة القراءة غير معروفة',
    FixVerdict.mocked => 'رُفضت: موقع وهميّ من تطبيق آخر',
    FixVerdict.jump => 'رُفضت: قفزة غير واقعيّة عن النقطة السابقة',
    FixVerdict.tooClose => 'تُجوهلت: ملاصقة للنقطة السابقة',
  };
}

/// مرشّح القراءات (نقيّ، قابل للاختبار).
class GpsFixFilter {
  const GpsFixFilter({
    this.maxAccuracyM = 10,
    this.minSpacingM = 2,
    this.maxSpeedMps = 12,
  });

  final double maxAccuracyM;

  /// قراءة أقرب من هذا للنقطة المقبولة السابقة لا تُضاف (ضجيج الوقوف).
  final double minSpacingM;

  /// سرعة ضمنيّة أعلى من هذا بين قراءتين ⇒ قفزة (≈43 كم/س؛ يكفي للسيّارة على
  /// طريق الحقل ويرفض قفزات الـGPS المعروفة بمئات الأمتار).
  final double maxSpeedMps;

  FixVerdict evaluate(Position fix, {LatLng? last, DateTime? lastAt}) {
    if (fix.isMocked) return FixVerdict.mocked;
    final acc = fix.accuracy;
    if (!acc.isFinite || acc <= 0) return FixVerdict.unknownAccuracy;
    if (acc > maxAccuracyM) return FixVerdict.poorAccuracy;
    if (last != null) {
      final here = LatLng(fix.latitude, fix.longitude);
      final d = haversineM(last, here);
      if (d < minSpacingM) return FixVerdict.tooClose;
      if (lastAt != null) {
        final secs = fix.timestamp.difference(lastAt).inMilliseconds / 1000;
        // القفزة تُقاس بعد طرح هامش الدقّة (قراءتان دقيقتان لا تقفزان).
        if (secs > 0 && (d - acc) / secs > maxSpeedMps) return FixVerdict.jump;
      }
    }
    return FixVerdict.accepted;
  }
}

enum GpsWalkPhase {
  idle,
  starting,
  recording,
  paused,
  finished,
  serviceDisabled,
  permissionDenied,
  permissionDeniedForever,
  failed,
}

class GpsWalkState {
  const GpsWalkState({
    this.phase = GpsWalkPhase.idle,
    this.track = const [],
    this.lastFix,
    this.lastAccuracyM,
    this.lastVerdict,
    this.rejected = 0,
    this.ignored = 0,
    this.maxAccuracyM = 10,
    this.toleranceM = 3,
    this.errorMessage,
  });

  final GpsWalkPhase phase;

  /// القراءات المقبولة بالترتيب (حلقة مفتوحة).
  final List<LatLng> track;

  /// آخر موقع ورد (مقبولاً أو لا) — لمؤشّر «أنت هنا».
  final LatLng? lastFix;
  final double? lastAccuracyM;
  final FixVerdict? lastVerdict;

  /// قراءات مرفوضة (دقّة/وهميّة/قفزة) — تُعرَض كي يعرف المزارع لماذا لا تزيد النقاط.
  final int rejected;

  /// قراءات متجاهَلة لأنّها ملاصقة للسابقة (وقوف).
  final int ignored;
  final double maxAccuracyM;

  /// تسامح التبسيط بالأمتار.
  final double toleranceM;
  final String? errorMessage;

  bool get isActive =>
      phase == GpsWalkPhase.recording || phase == GpsWalkPhase.paused;

  double get distanceM => pathLengthM(track);

  /// مساحة الحلقة المغلقة ضمنيّاً؛ null قبل ثلاث نقاط (لا رقم مختلَق).
  double? get areaHa =>
      track.length >= 3 ? polygonAreaHa(IoPolygon([track])) : null;

  List<LatLng> get simplified => simplifyRing(openRing(track), toleranceM);

  GpsWalkState copyWith({
    GpsWalkPhase? phase,
    List<LatLng>? track,
    LatLng? lastFix,
    double? lastAccuracyM,
    FixVerdict? lastVerdict,
    int? rejected,
    int? ignored,
    double? maxAccuracyM,
    double? toleranceM,
    String? errorMessage,
    bool clearError = false,
  }) => GpsWalkState(
    phase: phase ?? this.phase,
    track: track ?? this.track,
    lastFix: lastFix ?? this.lastFix,
    lastAccuracyM: lastAccuracyM ?? this.lastAccuracyM,
    lastVerdict: lastVerdict ?? this.lastVerdict,
    rejected: rejected ?? this.rejected,
    ignored: ignored ?? this.ignored,
    maxAccuracyM: maxAccuracyM ?? this.maxAccuracyM,
    toleranceM: toleranceM ?? this.toleranceM,
    errorMessage: clearError ? null : (errorMessage ?? this.errorMessage),
  );
}

class GpsWalkCubit extends Cubit<GpsWalkState> {
  GpsWalkCubit({LocationSource? source, double maxAccuracyM = 10})
    : _source = source ?? const GeolocatorLocationSource(),
      super(GpsWalkState(maxAccuracyM: maxAccuracyM));

  final LocationSource _source;
  StreamSubscription<Position>? _sub;
  DateTime? _lastAcceptedAt;

  GpsFixFilter get _filter => GpsFixFilter(maxAccuracyM: state.maxAccuracyM);

  /// يبدأ التسجيل بعد التحقّق من الخدمة والإذن.
  Future<void> start() async {
    if (state.isActive || state.phase == GpsWalkPhase.starting) return;
    emit(state.copyWith(phase: GpsWalkPhase.starting, clearError: true));
    try {
      if (!await _source.serviceEnabled()) {
        if (!isClosed) {
          emit(state.copyWith(phase: GpsWalkPhase.serviceDisabled));
        }
        return;
      }
      var perm = await _source.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await _source.requestPermission();
      }
      if (isClosed) return;
      if (perm == LocationPermission.deniedForever) {
        emit(state.copyWith(phase: GpsWalkPhase.permissionDeniedForever));
        return;
      }
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.unableToDetermine) {
        emit(state.copyWith(phase: GpsWalkPhase.permissionDenied));
        return;
      }
      _listen();
      emit(state.copyWith(phase: GpsWalkPhase.recording));
    } catch (e) {
      if (!isClosed) {
        emit(
          state.copyWith(
            phase: GpsWalkPhase.failed,
            errorMessage: 'تعذّر بدء الموقع: $e',
          ),
        );
      }
    }
  }

  void _listen() {
    _sub?.cancel();
    _sub = _source.positions().listen(_onFix, onError: _onStreamError);
  }

  void _onFix(Position fix) {
    if (state.phase != GpsWalkPhase.recording) return;
    final here = LatLng(fix.latitude, fix.longitude);
    final verdict = _filter.evaluate(
      fix,
      last: state.track.isEmpty ? null : state.track.last,
      lastAt: _lastAcceptedAt,
    );
    switch (verdict) {
      case FixVerdict.accepted:
        _lastAcceptedAt = fix.timestamp;
        emit(
          state.copyWith(
            track: [...state.track, here],
            lastFix: here,
            lastAccuracyM: fix.accuracy,
            lastVerdict: verdict,
          ),
        );
      case FixVerdict.tooClose:
        emit(
          state.copyWith(
            lastFix: here,
            lastAccuracyM: fix.accuracy,
            lastVerdict: verdict,
            ignored: state.ignored + 1,
          ),
        );
      default:
        emit(
          state.copyWith(
            lastFix: here,
            lastAccuracyM: fix.accuracy.isFinite ? fix.accuracy : null,
            lastVerdict: verdict,
            rejected: state.rejected + 1,
          ),
        );
    }
  }

  void _onStreamError(Object e) {
    _sub?.cancel();
    _sub = null;
    if (isClosed) return;
    if (e is LocationServiceDisabledException) {
      emit(state.copyWith(phase: GpsWalkPhase.serviceDisabled));
    } else if (e is PermissionDeniedException) {
      emit(state.copyWith(phase: GpsWalkPhase.permissionDenied));
    } else {
      emit(
        state.copyWith(
          phase: GpsWalkPhase.failed,
          errorMessage: 'انقطع تيّار الموقع: $e',
        ),
      );
    }
  }

  /// إيقاف مؤقّت: يُلغى الاشتراك فلا تُسجَّل قراءات أثناء التوقّف.
  void pause() {
    if (state.phase != GpsWalkPhase.recording) return;
    _sub?.cancel();
    _sub = null;
    emit(state.copyWith(phase: GpsWalkPhase.paused));
  }

  void resume() {
    if (state.phase != GpsWalkPhase.paused) return;
    // القفزة تُقاس من آخر نقطة مقبولة، لا من زمن التوقّف (المزارع قد يمشي أثناءه).
    _lastAcceptedAt = null;
    _listen();
    emit(state.copyWith(phase: GpsWalkPhase.recording));
  }

  void undoLast() {
    if (state.track.isEmpty) return;
    _lastAcceptedAt = null;
    emit(state.copyWith(track: state.track.sublist(0, state.track.length - 1)));
  }

  void setMaxAccuracy(double meters) =>
      emit(state.copyWith(maxAccuracyM: meters));

  void setTolerance(double meters) => emit(state.copyWith(toleranceM: meters));

  /// متابعة المشي بعد «إنهاء» (لم يُغلَق الحدّ بعد).
  void continueWalking() {
    if (state.phase != GpsWalkPhase.finished) return;
    emit(state.copyWith(phase: GpsWalkPhase.paused));
    resume();
  }

  Future<void> openSettings() => _source.openSettings(
    locationService: state.phase == GpsWalkPhase.serviceDisabled,
  );

  /// ينهي التسجيل (يبقي المسار للمراجعة والحفظ).
  void finish() {
    _sub?.cancel();
    _sub = null;
    emit(state.copyWith(phase: GpsWalkPhase.finished));
  }

  /// يمسح كلّ شيء ويعود للبداية.
  void reset() {
    _sub?.cancel();
    _sub = null;
    _lastAcceptedAt = null;
    emit(
      GpsWalkState(
        maxAccuracyM: state.maxAccuracyM,
        toleranceM: state.toleranceM,
      ),
    );
  }

  @override
  Future<void> close() async {
    await _sub?.cancel();
    return super.close();
  }
}
