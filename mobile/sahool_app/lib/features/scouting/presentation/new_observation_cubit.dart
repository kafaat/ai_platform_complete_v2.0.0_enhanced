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
//
// مصدر الموقع (v257): يُرسل location_source (gps | field_centroid) وaccuracy_m لقراءة
// GPS فقط، فيميّز المشرف من جهاز آخر الموقع المقيس من مركز الحقل. اختيار المستخدم
// اليدويّ (مركز الحقل) يُلغي أيّ طلب GPS معلّق: ردٌّ متأخّر لا يكتب فوقه.
//
// الصورة (v260): بعد حفظ الدبّوس تُرفع بايتات الصورة إلى scout-ingest
// (POST /api/v1/scouting-media/fields/{f}/pins/{p}/photo + X-Content-SHA256) بمفتاح ثانٍ
// ثابت؛ مصدرها الوحيد على الخادم scout_photo_evidence، وإيصالها مستقلّ عن إيصال الدبّوس
// (دبّوس محفوظ ليس صورة محفوظة). دون اتّصال تُودَع عمليّة observation_photo_upload بعد
// عمليّة الدبّوس لنفس الحقل (الصندوق يحفظ الترتيب) وتحمل البصمة لا البايتات. بعد
// الالتزام تُجمَّد الصورة (لا التقاط ولا حذف)، وحالة الرفع تُعرض للمفتّش.
import 'dart:async';

import 'package:crypto/crypto.dart' as crypto;
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

/// حالة رفع صورة المشاهدة كما تُعرض للمفتّش.
enum PhotoUpload { none, uploading, uploaded, queued, failed }

/// حدّ الخادم (MAX_PHOTO_BYTES في shared/security/scout_photo.py).
const int kMaxPinPhotoBytes = 8 * 1024 * 1024;

/// قيمة location_source على السلك لوضع الموقع؛ null ⇒ لا موقع.
String? locationSourceWire(LocationMode mode) => switch (mode) {
  LocationMode.gps => 'gps',
  LocationMode.fieldCentre => 'field_centroid',
  _ => null,
};

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
    this.photoUpload = PhotoUpload.none,
    this.photoUploadMessage,
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

  /// مسار الصورة على الجهاز؛ تُرفع بعد حفظ الدبّوس (حالة الرفع في [photoUpload]).
  final String? photoPath;
  final String? photoError;
  final Map<ObservationField, String> errors;
  final bool submitting;
  final SubmitOutcome outcome;
  final String? outcomeMessage;

  /// مشاكل المحصول من تصنيف الخادم (فارغة إن لم يُعرف المحصول).
  final List<TaxonomyIssue> issues;

  final PhotoUpload photoUpload;
  final String? photoUploadMessage;

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
    PhotoUpload? photoUpload,
    String? photoUploadMessage,
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
    photoUpload: photoUpload ?? this.photoUpload,
    photoUploadMessage: photoUploadMessage ?? this.photoUploadMessage,
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
    IdempotencyKey? photoIdempotencyKey,
    IssueCategory? initialCategory,
    String? initialNote,
  }) : _api = api,
       _location = location,
       _photos = photos,
       _store = photoStore,
       _outbox = outbox,
       _connectivity = connectivity ?? ConnectivityStatus.instance,
       key = idempotencyKey ?? IdempotencyKey.generate(),
       photoKey = photoIdempotencyKey ?? IdempotencyKey.generate(),
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

  /// ثابت لنيّة «صورة هذه المشاهدة» (عمليّة صندوق ثانية بمفتاح مستقلّ).
  final IdempotencyKey photoKey;

  /// جيل طلب الموقع: يزيد مع كلّ طلب GPS ومع كلّ اختيار يدويّ، فردٌّ لجيل سابق يُهمَل.
  int _locationGen = 0;

  /// صحيحة بعد إرسال/إيداع ناجح: الصورة صارت مرتبطة بمشاهدة محفوظة.
  bool _committed = false;

  /// صحيحة بعد أن أكّد الصندوق إيداع عمليّة الصورة (لا إيداع ثانٍ).
  bool _photoQueued = false;

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
    final gen = ++_locationGen;
    emit(
      state.copyWith(
        locationMode: LocationMode.locating,
        clearGpsFailure: true,
      ),
    );
    final r = await _location.current();
    // أُغلق النموذج، أو اختار المستخدم موقعاً يدويّاً أثناء الانتظار ⇒ الردّ متأخّر.
    if (isClosed || gen != _locationGen) return;
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
    _locationGen++; // يُلغي طلب GPS معلّقاً: الاختيار اليدويّ هو الأخير
    final errors = Map.of(state.errors)..remove(ObservationField.location);
    emit(
      state.copyWith(
        locationMode: LocationMode.fieldCentre,
        lat: field.centerLat,
        lng: field.centerLng,
        clearAccuracy: true,
        clearGpsFailure: true,
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

  Future<void> capturePhoto({bool fromCamera = true, CapturedPhoto? existing}) async {
    // الدليل يُجمَّد أثناء الحفظ وبعده: بصمة عمليّة الصورة المودَعة تخصّ هذا الملفّ.
    if (state.submitting || _committed) return;
    try {
      final photo = existing ?? await _photos.capture(fromCamera: fromCamera);
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
    if (state.submitting || _committed) return;
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

  /// جسم PinCreateRequest (api/api_models.py). لا photo_uri ولا صورة: الصورة تُرفع
  /// ببايتاتها إلى scout-ingest بعد حفظ الدبّوس (انظر [_sendPhoto]).
  Map<String, dynamic> buildBody() {
    final note = state.note.trim();
    final source = locationSourceWire(state.locationMode);
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
      if (source != null) 'location_source': source,
      if (source == 'gps' && state.accuracyM != null)
        'accuracy_m': state.accuracyM,
    };
  }

  static bool isTransient(ApiException e) =>
      e.isConnectivity ||
      e.kind == ApiErrorKind.unavailable ||
      const {502, 503, 504}.contains(e.statusCode);

  Future<void> submit() async {
    if (state.submitting) return; // منع الإرسال المزدوج
    if (_committed) {
      // الدبّوس ملتزَم ولم تصل صورته: يُعاد رفع الصورة وحدها، ولا يُعاد إنشاء الدبّوس.
      if (_photoQueued ||
          state.photoPath == null ||
          state.photoUpload != PhotoUpload.failed) {
        return;
      }
      emit(state.copyWith(submitting: true));
      final photo = await _sendPhoto(online: true);
      if (isClosed) return;
      emit(
        state.copyWith(
          submitting: false,
          outcome: photo == PhotoUpload.failed
              ? SubmitOutcome.failed
              : state.outcome,
          outcomeMessage: 'الدبّوس محفوظ سابقاً.${_photoSuffix(photo)}',
        ),
      );
      return;
    }
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
      if (r['persisted'] != true) {
        // الخادم تحقّق ولم يُدِم (القاعدة غير متاحة) — نعيد المحاولة لاحقاً.
        await _enqueue(body, why: 'not_persisted');
        return;
      }
      _committed = true;
      final photo = await _sendPhoto(online: true);
      if (isClosed) return;
      emit(
        state.copyWith(
          submitting: false,
          outcome: SubmitOutcome.sent,
          outcomeMessage: 'حُفظت المشاهدة على الخادم.${_photoSuffix(photo)}',
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
      final photo = await _sendPhoto(online: false);
      if (isClosed) return;
      emit(
        state.copyWith(
          submitting: false,
          outcome: SubmitOutcome.queued,
          outcomeMessage:
              '${why == 'not_persisted' ? 'محفوظ للإرسال — تحقّق الخادم منها لكنه لم يحفظها بعد، وستُعاد تلقائيّاً.' : 'محفوظ للإرسال — ستُرسل المشاهدة عند عودة الاتّصال.'}'
              '${_photoSuffix(photo)}',
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

  static String _photoSuffix(PhotoUpload p) => switch (p) {
    PhotoUpload.uploaded => ' رُفعت الصورة ويراها المشرف.',
    PhotoUpload.queued =>
      ' الصورة بانتظار الرفع وستُرسل تلقائيّاً (تابعها في حالة المزامنة).',
    PhotoUpload.failed => ' لم تُرفع الصورة — بقيت على هذا الجهاز فقط.',
    PhotoUpload.none || PhotoUpload.uploading => '',
  };

  /// يرفع صورة دبّوسٍ ملتزَم إلى scout-ingest (v260، scout_photo_evidence): مباشرةً إن
  /// كان الدبّوس قد وصل والجهاز متّصل، وإلّا (أو عند فشل عابر، أو إيصال لا يطابق
  /// البايتات) تُودَع عمليّة [kObservationPhotoKind] بمفتاح [photoKey] الثابت بعد عمليّة
  /// الدبّوس لنفس الحقل. العمليّة تحمل البصمة لا البايتات. فشلٌ غير عابر
  /// (حجم/نوع/تعارض/الميزة معطّلة) يُعرض كما قاله الخادم ولا يُودَع ليتكرّر.
  Future<PhotoUpload> _sendPhoto({required bool online}) async {
    final path = state.photoPath;
    if (path == null) return PhotoUpload.none;
    if (_photoQueued) return state.photoUpload;
    final Uint8List bytes;
    final String digest;
    try {
      scoutingPhotoType(path);
      bytes = await _store.read(path);
      if (bytes.isEmpty || bytes.length > kMaxPinPhotoBytes) {
        return _photoState(
          PhotoUpload.failed,
          'الصورة أكبر من 8 ميغابايت (أو فارغة) — لم تُرفع.',
        );
      }
      digest = crypto.sha256.convert(bytes).toString();
    } on FormatException {
      return _photoState(
        PhotoUpload.failed,
        'نوع الصورة غير مدعوم (JPG أو PNG أو WebP فقط) — لم تُرفع.',
      );
    } catch (_) {
      return _photoState(PhotoUpload.failed, 'تعذّر قراءة الصورة من الجهاز.');
    }
    if (online && _connectivity.isOnline) {
      _photoState(PhotoUpload.uploading, 'جارٍ رفع الصورة…');
      try {
        await _api.uploadPinPhoto(
          fieldId: field.id,
          pinId: pinId,
          bytes: bytes,
          filename: path,
          idempotencyKey: photoKey,
        );
        return _photoState(
          PhotoUpload.uploaded,
          'رُفعت الصورة إلى المخزن المشترك — دليل غير معتمد تشخيصيّاً.',
        );
      } on FormatException {
        // 2xx لا يطابق هذه البايتات: ليس إيصالاً ⇒ إعادة لاحقة بالمفتاح نفسه.
      } catch (e) {
        final err = ApiException.from(e);
        if (!isTransient(err)) {
          // 403 = no live grant for this field (owner phase 6, v263): never queued as if offline;
          // the photo stays on the device until the owner grants the field.
          return _photoState(
            PhotoUpload.failed,
            err.statusCode == 403
                ? 'حُفظ الدبوس، لكن رفع الصورة رُفض لغياب تفويض هذا الحقل. الصورة على الجهاز؛ اطلب منح الصلاحية ثم أعد المحاولة.'
                : err.messageAr,
          );
        }
      }
    }
    OutboxReceipt receipt;
    try {
      receipt = await _box.enqueue(
        OutboxOp(
          kind: kObservationPhotoKind,
          method: 'POST',
          path: scoutingPhotoPath(field.id, pinId),
          body: {'field_id': field.id, 'pin_id': pinId, 'sha256': digest},
          idempotencyKey: photoKey.value,
          fieldId: field.id,
          labelAr:
              'صورة مشاهدة ${state.category?.labelAr ?? ''} — ${field.nameAr}',
        ),
      );
    } catch (_) {
      receipt = const OutboxReceipt.notQueued('enqueue_failed');
    }
    if (receipt.queued) _photoQueued = true;
    return receipt.queued
        ? _photoState(PhotoUpload.queued, 'الصورة بانتظار الرفع.')
        : _photoState(
            PhotoUpload.failed,
            'تعذّر حفظ الصورة للإرسال لاحقاً — بقيت على هذا الجهاز فقط.',
          );
  }

  PhotoUpload _photoState(PhotoUpload p, String message) {
    if (!isClosed) {
      emit(state.copyWith(photoUpload: p, photoUploadMessage: message));
    }
    return p;
  }

  @override
  Future<void> close() async {
    // نموذج أُغلق بلا حفظ ⇒ صورته يتيمة؛ تُحذف كي لا تتراكم على الجهاز.
    final p = state.photoPath;
    if (!_committed && p != null) unawaited(_store.discard(p));
    return super.close();
  }
}
