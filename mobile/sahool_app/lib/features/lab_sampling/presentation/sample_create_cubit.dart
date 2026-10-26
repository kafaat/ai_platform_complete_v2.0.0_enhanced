// SAHOOL — features/lab_sampling/presentation/sample_create_cubit.dart
// تسجيل عيّنة تربة/ماء من الحقل: التحقّق (يطابق LabSampleIn وقيود lab_samples)،
// ثمّ الإرسال، أو الإيداع في صندوق الإرسال دون اتّصال بنفس Idempotency-Key.
// الإيصال صادق: «محفوظة للإرسال» فقط إن قال الصندوق queued؛ وإلّا يبقى النموذج
// بمحتواه ويُقال للمستخدم إنّ الحفظ دون اتّصال غير متاح — لا ادّعاء حفظ.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../data/lab_models.dart';
import '../data/lab_sampling_api.dart';

/// نقطة GPS ملتقطة.
class GpsFix {
  const GpsFix(this.latitude, this.longitude, {this.accuracyM});
  final double latitude;
  final double longitude;
  final double? accuracyM;
}

class SampleDraft {
  const SampleDraft({
    required this.fieldId,
    this.kind = 'soil',
    this.latitudeText = '',
    this.longitudeText = '',
    this.accuracyM,
    this.depthFromText = '',
    this.depthToText = '',
    this.sampledOn,
    this.source = '',
    this.barcode = '',
  });

  final String fieldId;
  final String kind;
  final String latitudeText;
  final String longitudeText;
  final double? accuracyM;
  final String depthFromText;
  final String depthToText;
  final DateTime? sampledOn;
  final String source;
  final String barcode;
}

abstract final class SampleField {
  static const location = 'location';
  static const depthFrom = 'depth_from';
  static const depthTo = 'depth_to';
  static const source = 'source';
  static const barcode = 'barcode';
}

Map<String, String> validateSampleDraft(SampleDraft d) {
  final e = <String, String>{};
  final lat = parseLocalizedNum(d.latitudeText);
  final lon = parseLocalizedNum(d.longitudeText);
  if (lat == null || lon == null) {
    e[SampleField.location] = 'التقط موقع العيّنة بالـGPS أو أدخل الإحداثيّات';
  } else if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    e[SampleField.location] = 'إحداثيّات خارج النطاق';
  }
  final fromT = d.depthFromText.trim(), toT = d.depthToText.trim();
  final from = parseLocalizedNum(fromT), to = parseLocalizedNum(toT);
  bool isInt(double? v) => v != null && v == v.roundToDouble();
  if (fromT.isNotEmpty && !isInt(from)) {
    e[SampleField.depthFrom] = 'أدخل عمقاً بعدد صحيح من السنتيمترات';
  }
  if (toT.isNotEmpty && !isInt(to)) {
    e[SampleField.depthTo] = 'أدخل عمقاً بعدد صحيح من السنتيمترات';
  }
  if (d.kind == 'soil') {
    if (fromT.isEmpty) {
      e[SampleField.depthFrom] = 'عمق البداية مطلوب لعيّنة التربة';
    }
    if (toT.isEmpty) {
      e[SampleField.depthTo] = 'عمق النهاية مطلوب لعيّنة التربة';
    }
  }
  if (from != null && from < 0) {
    e[SampleField.depthFrom] = 'العمق لا يكون سالباً';
  }
  if (from != null &&
      to != null &&
      !e.containsKey(SampleField.depthTo) &&
      to <= from) {
    e[SampleField.depthTo] = 'عمق النهاية يجب أن يكون أكبر من البداية';
  }
  if (d.source.trim().length > 120) {
    e[SampleField.source] = 'النصّ أطول من 120 حرفاً';
  }
  if (d.barcode.trim().length > 128) {
    e[SampleField.barcode] = 'الرمز أطول من 128 حرفاً';
  }
  return e;
}

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}'
    '-${d.day.toString().padLeft(2, '0')}';

/// جسم LabSampleIn. الحالة «collected» يحوّلها الخادم إلى «sampled».
Map<String, dynamic> buildSampleBody(SampleDraft d) {
  final from = parseLocalizedNum(d.depthFromText);
  final to = parseLocalizedNum(d.depthToText);
  return {
    'field_id': d.fieldId,
    'kind': d.kind,
    'latitude': parseLocalizedNum(d.latitudeText),
    'longitude': parseLocalizedNum(d.longitudeText),
    if (d.sampledOn != null) 'sampled_on': _iso(d.sampledOn!),
    if (from != null) 'depth_cm_from': from.round(),
    if (to != null) 'depth_cm_to': to.round(),
    if (d.source.trim().isNotEmpty) 'source': d.source.trim(),
    if (d.barcode.trim().isNotEmpty) 'barcode': d.barcode.trim(),
    if (d.accuracyM != null) 'gps_accuracy_m': d.accuracyM,
    'status': 'collected',
  };
}

sealed class SampleCreateState {
  const SampleCreateState();
}

class SampleEditing extends SampleCreateState {
  const SampleEditing({this.errors = const {}, this.submitError});
  final Map<String, String> errors;
  final String? submitError;
}

class SampleSubmitting extends SampleCreateState {
  const SampleSubmitting();
}

/// أُرسلت وحفظها الخادم.
class SampleSent extends SampleCreateState {
  const SampleSent(this.sample);
  final LabSample sample;
}

/// أُودعت في صندوق الإرسال وستُرسَل عند عودة الاتّصال.
class SampleQueued extends SampleCreateState {
  const SampleQueued();
}

/// رسالة حين يرفض الصندوق الإيداع.
String notQueuedMessage(String? reason) => reason == 'offline_queue_unavailable'
    ? 'لا اتّصال، والحفظ دون اتّصال غير متاح بعد على هذا الجهاز. لم تُحفَظ العيّنة؛ '
          'بياناتها باقية في النموذج — أعد المحاولة عند عودة الاتّصال.'
    : 'لا اتّصال، وتعذّر حفظ العيّنة للإرسال لاحقاً${reason == null ? '' : ' ($reason)'}. '
          'بياناتها باقية في النموذج.';

class SampleCreateCubit extends Cubit<SampleCreateState> {
  SampleCreateCubit(
    this._api, {
    OfflineOutbox? outbox,
    bool Function()? isOnline,
    this.fieldLabel,
  }) : _outbox = outbox,
       _isOnline = isOnline ?? (() => true),
       super(const SampleEditing());

  final LabSamplingApi _api;
  final OfflineOutbox? _outbox;
  final bool Function() _isOnline;
  final String? fieldLabel;

  /// نيّة كتابة واحدة لكلّ فتح للنموذج — نفسها في الإرسال المباشر والصندوق.
  final IdempotencyKey idempotencyKey = IdempotencyKey.generate();

  Future<void> submit(SampleDraft draft) async {
    if (state is SampleSubmitting ||
        state is SampleSent ||
        state is SampleQueued) {
      return;
    }
    final errors = validateSampleDraft(draft);
    if (errors.isNotEmpty) {
      emit(SampleEditing(errors: errors));
      return;
    }
    final body = buildSampleBody(draft);
    emit(const SampleSubmitting());
    if (!_isOnline()) {
      await _enqueue(draft, body);
      return;
    }
    try {
      final saved = await _api.createSample(
        body,
        idempotencyKey: idempotencyKey,
      );
      if (!isClosed) emit(SampleSent(saved));
    } catch (e) {
      final ex = ApiException.from(e);
      if (ex.isConnectivity) {
        await _enqueue(draft, body);
      } else if (!isClosed) {
        emit(SampleEditing(submitError: ex.messageAr));
      }
    }
  }

  Future<void> _enqueue(SampleDraft draft, Map<String, dynamic> body) async {
    final outbox = _outbox ?? OfflineOutbox.instance;
    OutboxReceipt receipt;
    try {
      receipt = await outbox.enqueue(
        OutboxOp(
          kind: 'lab_sample_create',
          method: 'POST',
          path: LabSamplingApi.samplesPath,
          body: body,
          idempotencyKey: idempotencyKey.value,
          fieldId: draft.fieldId,
          labelAr:
              '${draft.kind == 'soil' ? 'عيّنة تربة' : 'عيّنة ماء'}${fieldLabel == null ? '' : ' — $fieldLabel'}',
        ),
      );
    } catch (e) {
      receipt = OutboxReceipt.notQueued(e.toString());
    }
    if (isClosed) return;
    emit(
      receipt.queued
          ? const SampleQueued()
          : SampleEditing(submitError: notQueuedMessage(receipt.reason)),
    );
  }
}
