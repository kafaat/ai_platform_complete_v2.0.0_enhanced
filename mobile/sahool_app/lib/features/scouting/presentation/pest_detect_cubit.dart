// SAHOOL — features/scouting/presentation/pest_detect_cubit.dart
// كشف الآفات بالصورة لحقل محدّد. نُقل من المستشار لأنّ نداءه كان بلا field_id
// فيرفضه الخادم 422 دائماً. هنا الحقل شرط مسبق للشاشة، ويُرسل field_id دائماً.
//
// ميزة متّصلة فقط: بلا شبكة تُعلن حالة «يتطلّب اتّصالاً» ولا يُرسل شيء. النتيجة
// كما ردّها الخادم (الأسماء والثقة)، والفشل (مثل 503 «النموذج غير مُجهَّز»)
// يُعرض كما هو — لا كشف مُلفَّق.
import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';

import '../data/device_sources.dart';
import '../data/scouting_api.dart';
import '../data/scouting_models.dart';

sealed class PestDetectState {
  const PestDetectState();
}

class PestDetectIdle extends PestDetectState {
  const PestDetectIdle({this.message});

  /// رسالة كاميرا (إذن مرفوض…) إن وُجدت.
  final String? message;
}

class PestDetectOffline extends PestDetectState {
  const PestDetectOffline();
}

class PestDetectSending extends PestDetectState {
  const PestDetectSending(this.photoPath);
  final String photoPath;
}

class PestDetectDone extends PestDetectState {
  const PestDetectDone(this.photoPath, this.result);
  final String photoPath;
  final PestDetectResult result;
}

class PestDetectFailed extends PestDetectState {
  const PestDetectFailed(this.photoPath, this.error);
  final String photoPath;
  final ApiException error;

  /// نصّ الخادم الخام (detail) — مثل «نموذج كشف الآفات غير مُجهَّز» على 503،
  /// لأنّ صياغة 503 العامّة تتحدّث عن قاعدة البيانات.
  String? get serverDetail {
    final d = error.detail;
    if (d is String && d.isNotEmpty && d != error.messageAr) return d;
    return null;
  }
}

class PestDetectCubit extends Cubit<PestDetectState> {
  PestDetectCubit({
    required this.field,
    required ScoutingApi api,
    required PhotoCapturer photos,
    ConnectivityStatus? connectivity,
  }) : _api = api,
       _photos = photos,
       _connectivity = connectivity ?? ConnectivityStatus.instance,
       super(const PestDetectIdle());

  final ScoutingField field;
  final ScoutingApi _api;
  final PhotoCapturer _photos;
  final ConnectivityStatus _connectivity;
  CapturedPhoto? _last;

  bool get busy => state is PestDetectSending;

  Future<void> captureAndDetect({bool fromCamera = true}) async {
    if (busy) return;
    if (!_connectivity.isOnline) {
      emit(const PestDetectOffline());
      return;
    }
    final CapturedPhoto? photo;
    try {
      photo = await _photos.capture(fromCamera: fromCamera);
    } on PhotoCaptureException catch (e) {
      if (!isClosed) emit(PestDetectIdle(message: e.messageAr));
      return;
    }
    if (photo == null || isClosed) return;
    _last = photo;
    await _send(photo);
  }

  /// يعيد إرسال الصورة الأخيرة (بعد فشل عابر) بلا التقاط جديد.
  Future<void> retry() async {
    final p = _last;
    if (p == null || busy) return;
    if (!_connectivity.isOnline) {
      emit(const PestDetectOffline());
      return;
    }
    await _send(p);
  }

  Future<void> _send(CapturedPhoto photo) async {
    emit(PestDetectSending(photo.path));
    try {
      final bytes = await photo.readBytes();
      final r = await _api.detectPest(
        fieldId: field.id,
        bytes: bytes,
        filename: photo.filename,
        crop: field.crop,
      );
      if (!isClosed) emit(PestDetectDone(photo.path, r));
    } catch (e) {
      if (!isClosed) emit(PestDetectFailed(photo.path, ApiException.from(e)));
    }
  }

  @visibleForTesting
  CapturedPhoto? get lastPhoto => _last;
}
