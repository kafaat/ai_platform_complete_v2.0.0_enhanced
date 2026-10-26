// SAHOOL — features/scouting/presentation/new_observation_cubit.dart
// تدفّق «مشاهدة جديدة»: موقع GPS (أو مركز الحقل صراحةً) + فئة + شدّة + ملاحظة +
// صورة محلّيّة، ثمّ الإرسال إلى POST /api/v1/fields/{id}/pins.
//
// الإرسال دون اتّصال: إن كان الجهاز بلا شبكة، أو فشل الطلب فشلاً عابراً
// (شبكة/مهلة/502/503/504)، أو تحقّق الخادم ولم يُدِم (persisted=false)، تُودَع
// العمليّة في OfflineOutbox بمفتاح ثابت. «محفوظ للإرسال» يُعرض فقط إن قال الإيصال
// queued=true؛ وإلّا خطأ صادق بأنّ المشاهدة لم تُحفظ.
//
// مفتاح Idempotency-Key واحد لكلّ نيّة (يُولَّد عند فتح النموذج) وهو نفسه pin_id،
// والخادم idempotent على pin_id (ON CONFLICT DO NOTHING) — الإعادة لا تكرّر.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../data/device_sources.dart';
import '../data/scouting_api.dart';
import '../data/scouting_models.dart';

/// حدود اليمن كما يتحقّق منها الخادم (_YEMEN_BBOX في api/scouting_pins.py).
/// تحقّق مسبق كي لا تُودَع عمليّة سيرفضها الخادم 422 إلى الأبد.
const double kYemenMinLat = 12.0;
const double kYemenMaxLat = 19.5;
const double kYemenMinLng = 41.0;
const double kYemenMaxLng = 54.6;

bool insideYemen(double lat, double lng) =>
    lat >= kYemenMinLat &&
    lat <= kYemenMaxLat &&
    lng >= kYemenMinLng &&
    lng <= kYemenMaxLng;

enum LocationMode { none, locating, gps, fieldCentre, failed }

enum SubmitOutcome { none, sent, queued, failed }

/// مفاتيح أخطاء التحقّق.
enum ObservationField { location, category, severity }

@immutable
class NewObservationState {
  const NewObservationState({
    this.locationMode = LocationMode.none,
    this.lat,
    this.lng,
    this.accuracyM,
    this.gpsFailure,
    this.category,
    this.issueCode,
    this.severity,
    this.note = '',
    this.photoPath,
    this.photoError,
    this.errors = const {},
    this.submitting = false,
    this.outcome = SubmitOutcome.none,
    this.outcomeMessage,
    this.issues = const [],
  });

  final LocationMode locationMode;
  final double? lat;
  final double? lng;
  final double? accuracyM;
  final GpsFailure? gpsFailure;
  final IssueCategory? category;
  final String? issueCode;
  final PinSeverity? severity;
  final String note;

  /// مسار الصورة على الجهاز (لا تُرسل — لا تخزين صور في الخادم).
  final String? photoPath;
  final String? photoError;
  final Map<ObservationField, String> errors;
  final bool submitting;
  final SubmitOutcome outcome;
  final String? outcomeMessage;

  /// مشاكل المحصول من تصنيف الخادم (فارغة إن لم يُعرف المحصول).
  final List<TaxonomyIssue> issues;

  bool get hasLocation => lat != null && lng != null;

  List<TaxonomyIssue> get issuesForCategory => category == null
      ? const []
      : issues.where((i) => i.categoryWire == category!.wire).toList();

  NewObservationState copyWith({
    LocationMode? locationMode,
    double? lat,
    double? lng,
    double? accuracyM,
    bool clearAccuracy = false,
    GpsFailure? gpsFailure,
    bool clearGpsFailure = false,
    IssueCategory? category,
    String? issueCode,
    bool clearIssueCode = false,
    PinSeverity? severity,
    String? note,
    String? photoPath,
    bool clearPhoto = false,
    String? photoError,
    bool clearPhotoError = false,
    Map<ObservationField, String>? errors,
    bool? submitting,
    SubmitOutcome? outcome,
    String? outcomeMessage,
    bool clearOutcomeMessage = false,
    List<TaxonomyIssue>? issues,
  }) => NewObservationState(
    locationMode: locationMode ?? this.locationMode,
    lat: lat ?? this.lat,
    lng: lng ?? this.lng,
    accuracyM: clearAccuracy ? null : (accuracyM ?? this.accuracyM),
    gpsFailure: clearGpsFailure ? null : (gpsFailure ?? this.gpsFailure),
    category: category ?? this.category,
    issueCode: clearIssueCode ? null : (issueCode ?? this.issueCode),
    severity: severity ?? this.severity,
    note: note ?? this.note,
    photoPath: clearPhoto ? null : (photoPath ?? this.photoPath),
    photoError: clearPhotoError ? null : (photoError ?? this.photoError),
    errors: errors ?? this.errors,
    submitting: submitting ?? this.submitting,
    outcome: outcome ?? this.outcome,
    outcomeMessage: clearOutcomeMessage
        ? null
        : (outcomeMessage ?? this.outcomeMessage),
    issues: issues ?? this.issues,
  );
}

class NewObservationCubit extends Cubit<NewObservationState> {
  NewObservationCubit({
    required this.field,
    required ScoutingApi api,
    required LocationSource location,
    required PhotoCapturer photos,
    required LocalPhotoStore photoStore,
    OfflineOutbox? outbox,
    ConnectivityStatus? connectivity,
    IdempotencyKey? idempotencyKey,
    IssueCategory? initialCategory,
    String? initialNote,
  }) : _api = api,
       _location = location,
       _photos = photos,
       _store = photoStore,
       _outbox = outbox,
       _connectivity = connectivity ?? ConnectivityStatus.instance,
       key = idempotencyKey ?? IdempotencyKey.generate(),
       super(
         NewObservationState(
           category: initialCategory,
           note: initialNote ?? '',
         ),
       );

  final ScoutingField field;
  final ScoutingApi _api;
  final LocationSource _location;
  final PhotoCapturer _photos;
  final LocalPhotoStore _store;
  final OfflineOutbox? _outbox;
  final ConnectivityStatus _connectivity;

  /// ثابت لنيّة «هذه المشاهدة» — وهو pin_id أيضاً.
  final IdempotencyKey key;
  String get pinId => key.value;

  /// صحيحة بعد إرسال/إيداع ناجح: الصورة صارت مرتبطة بمشاهدة محفوظة.
  bool _committed = false;

  OfflineOutbox get _box => _outbox ?? OfflineOutbox.instance;

  /// تبدأ الشاشة: موقع + تصنيف المحصول (إن عُرف) بالتوازي.
  Future<void> start() async {
    await Future.wait([locate(), _loadTaxonomy()]);
  }

  Future<void> _loadTaxonomy() async {
    final crop = field.crop;
    if (crop == null) return;
    try {
      final issues = await _api.cropIssues(crop);
      if (!isClosed) emit(state.copyWith(issues: issues));
    } catch (_) {
      // التصنيف اختياريّ: الفئة كافية للإرسال؛ لا نعرض قائمة مخترَعة.
    }
  }

  Future<void> locate() async {
    if (state.locationMode == LocationMode.locating) return;
    final previous = state.locationMode;
    emit(
      state.copyWith(
        locationMode: LocationMode.locating,
        clearGpsFailure: true,
      ),
    );
    final r = await _location.current();
    if (isClosed) return;
    switch (r) {
      case GpsFix(:final lat, :final lng, :final accuracyM):
        final errors = Map.of(state.errors)..remove(ObservationField.location);
        emit(
          NewObservationState(
            locationMode: LocationMode.gps,
            lat: lat,
            lng: lng,
            accuracyM: accuracyM,
            category: state.category,
            issueCode: state.issueCode,
            severity: state.severity,
            note: state.note,
            photoPath: state.photoPath,
            errors: errors,
            issues: state.issues,
          ),
        );
      case GpsFailure():
        // لا نمحو موقعاً سابقاً صالحاً؛ نعلن الفشل فقط.
        emit(
          state.copyWith(
            locationMode: state.hasLocation ? previous : LocationMode.failed,
            gpsFailure: r,
          ),
        );
    }
  }

  /// بديل يدويّ صريح: مركز الحقل المسجَّل (ليس قياساً لموقع المشاهدة).
  void useFieldCentre() {
    if (!field.hasCenter) return;
    final errors = Map.of(state.errors)..remove(ObservationField.location);
    emit(
      state.copyWith(
        locationMode: LocationMode.fieldCentre,
        lat: field.centerLat,
        lng: field.centerLng,
        clearAccuracy: true,
        errors: errors,
      ),
    );
  }

  Future<void> openLocationSettings() async {
    final f = state.gpsFailure;
    if (f != null) await _location.openSettings(f.reason);
  }

  void selectCategory(IssueCategory c) {
    final errors = Map.of(state.errors)..remove(ObservationField.category);
    emit(
      state.copyWith(
        category: c,
        clearIssueCode: c != state.category,
        errors: errors,
      ),
    );
  }

  void selectIssue(String? code) => code == null
      ? emit(state.copyWith(clearIssueCode: true))
      : emit(state.copyWith(issueCode: code));

  void selectSeverity(PinSeverity s) {
    final errors = Map.of(state.errors)..remove(ObservationField.severity);
    emit(state.copyWith(severity: s, errors: errors));
  }

  void setNote(String v) => emit(state.copyWith(note: v));

  Future<void> capturePhoto({bool fromCamera = true}) async {
    try {
      final photo = await _photos.capture(fromCamera: fromCamera);
      if (photo == null || isClosed) return;
      final old = state.photoPath;
      final saved = await _store.keep(pinId, photo);
      if (old != null && old != saved) await _store.discard(old);
      if (!isClosed) {
        emit(state.copyWith(photoPath: saved, clearPhotoError: true));
      }
    } on PhotoCaptureException catch (e) {
      if (!isClosed) emit(state.copyWith(photoError: e.messageAr));
    } catch (_) {
      if (!isClosed) {
        emit(state.copyWith(photoError: 'تعذّر حفظ الصورة على الجهاز.'));
      }
    }
  }

  Future<void> removePhoto() async {
    final p = state.photoPath;
    if (p == null) return;
    await _store.discard(p);
    if (!isClosed) emit(state.copyWith(clearPhoto: true));
  }

  Map<ObservationField, String> validate() {
    final errors = <ObservationField, String>{};
    if (!state.hasLocation) {
      errors[ObservationField.location] =
          'حدّد الموقع (GPS أو مركز الحقل) قبل الحفظ.';
    } else if (!insideYemen(state.lat!, state.lng!)) {
      errors[ObservationField.location] =
          'الموقع خارج حدود اليمن — لن يقبله الخادم.';
    }
    if (state.category == null) {
      errors[ObservationField.category] = 'اختر نوع المشكلة.';
    }
    if (state.severity == null) {
      errors[ObservationField.severity] = 'اختر الشدّة.';
    }
    return errors;
  }

  /// جسم PinCreateRequest (api/api_models.py:374). photo_uri لا يُرسل: الصورة
  /// ملفّ محلّيّ لا يملك الخادم وصولاً إليه.
  Map<String, dynamic> buildBody() {
    final note = state.note.trim();
    return {
      'pin_id': pinId,
      'field_id': field.id,
      'lat': state.lat,
      'lng': state.lng,
      'issue_category': state.category!.wire,
      'severity': state.severity!.wire,
      'status': 'new',
      'persistence': 'seasonal',
      if (field.crop != null) 'crop': field.crop,
      if (state.issueCode != null) 'issue_code': state.issueCode,
      if (note.isNotEmpty) 'note_ar': note,
    };
  }

  static bool isTransient(ApiException e) =>
      e.isConnectivity ||
      e.kind == ApiErrorKind.unavailable ||
      const {502, 503, 504}.contains(e.statusCode);

  Future<void> submit() async {
    if (state.submitting || _committed) return; // منع الإرسال المزدوج
    final errors = validate();
    if (errors.isNotEmpty) {
      emit(
        state.copyWith(
          errors: errors,
          outcome: SubmitOutcome.none,
          clearOutcomeMessage: true,
        ),
      );
      return;
    }
    emit(
      state.copyWith(
        errors: const {},
        submitting: true,
        outcome: SubmitOutcome.none,
        clearOutcomeMessage: true,
      ),
    );
    final body = buildBody();

    if (!_connectivity.isOnline) {
      await _enqueue(body, why: 'offline');
      return;
    }
    try {
      final r = await _api.createPin(field.id, body, idempotencyKey: key);
      if (isClosed) return;
      if (r['persisted'] == false) {
        // الخادم تحقّق ولم يُدِم (القاعدة غير متاحة) — نعيد المحاولة لاحقاً.
        await _enqueue(body, why: 'not_persisted');
        return;
      }
      _committed = true;
      emit(
        state.copyWith(
          submitting: false,
          outcome: SubmitOutcome.sent,
          outcomeMessage: 'حُفظت المشاهدة على الخادم.',
        ),
      );
    } catch (e) {
      final err = ApiException.from(e);
      if (isTransient(err)) {
        await _enqueue(body, why: err.kind.name);
        return;
      }
      if (!isClosed) {
        emit(
          state.copyWith(
            submitting: false,
            outcome: SubmitOutcome.failed,
            outcomeMessage: err.messageAr,
          ),
        );
      }
    }
  }

  Future<void> _enqueue(
    Map<String, dynamic> body, {
    required String why,
  }) async {
    OutboxReceipt receipt;
    try {
      receipt = await _box.enqueue(
        OutboxOp(
          kind: 'observation_create',
          method: 'POST',
          path: scoutingPinCreatePath(field.id),
          body: body,
          idempotencyKey: key.value,
          fieldId: field.id,
          labelAr: 'مشاهدة ${state.category?.labelAr ?? ''} — ${field.nameAr}',
        ),
      );
    } catch (_) {
      receipt = const OutboxReceipt.notQueued('enqueue_failed');
    }
    if (isClosed) return;
    if (receipt.queued) {
      _committed = true;
      emit(
        state.copyWith(
          submitting: false,
          outcome: SubmitOutcome.queued,
          outcomeMessage: why == 'not_persisted'
              ? 'محفوظ للإرسال — تحقّق الخادم منها لكنه لم يحفظها بعد، وستُعاد تلقائيّاً.'
              : 'محفوظ للإرسال — ستُرسل المشاهدة عند عودة الاتّصال.',
        ),
      );
    } else {
      emit(
        state.copyWith(
          submitting: false,
          outcome: SubmitOutcome.failed,
          outcomeMessage: why == 'offline'
              ? 'لا اتّصال، وتعذّر حفظ المشاهدة للإرسال لاحقاً على هذا الجهاز — لم تُحفظ. أعد المحاولة عند توفّر الشبكة.'
              : 'تعذّر الإرسال، وتعذّر حفظ المشاهدة للإرسال لاحقاً — لم تُحفظ. أعد المحاولة.',
        ),
      );
    }
  }

  @override
  Future<void> close() async {
    // نموذج أُغلق بلا حفظ ⇒ صورته يتيمة؛ تُحذف كي لا تتراكم على الجهاز.
    final p = state.photoPath;
    if (!_committed && p != null) unawaited(_store.discard(p));
    return super.close();
  }
}
