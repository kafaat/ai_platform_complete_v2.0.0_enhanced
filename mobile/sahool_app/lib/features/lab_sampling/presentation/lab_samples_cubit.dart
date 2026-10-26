// SAHOOL — features/lab_sampling/presentation/lab_samples_cubit.dart
// عيّنات الحقل + سياق المختبر + انتقالات الحالة. فشل سياق المختبر لا يُسقط
// القائمة؛ يُحمَل بجانبها.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/lab_models.dart';
import '../data/lab_sampling_api.dart';

sealed class LabSamplesState {
  const LabSamplesState();
}

class LabSamplesLoading extends LabSamplesState {
  const LabSamplesLoading();
}

class LabSamplesFailed extends LabSamplesState {
  const LabSamplesFailed(this.error);
  final ApiException error;
}

class LabSamplesLoaded extends LabSamplesState {
  const LabSamplesLoaded({
    required this.samples,
    this.context,
    this.contextError,
    this.busy = const {},
  });

  final List<LabSample> samples;
  final LabContext? context;
  final ApiException? contextError;
  final Set<String> busy;

  LabSamplesLoaded copyWith({List<LabSample>? samples, Set<String>? busy}) =>
      LabSamplesLoaded(
        samples: samples ?? this.samples,
        context: context,
        contextError: contextError,
        busy: busy ?? this.busy,
      );
}

class LabSamplesCubit extends Cubit<LabSamplesState> {
  LabSamplesCubit(this._api, this.fieldId) : super(const LabSamplesLoading());

  final LabSamplingApi _api;
  final String fieldId;
  final Map<String, IdempotencyKey> _keys = {};

  Future<void> load() async {
    if (state is! LabSamplesLoaded) emit(const LabSamplesLoading());
    final List<LabSample> samples;
    try {
      samples = await _api.listSamples(fieldId: fieldId);
    } catch (e) {
      if (!isClosed) emit(LabSamplesFailed(ApiException.from(e)));
      return;
    }
    LabContext? ctx;
    ApiException? ctxErr;
    try {
      ctx = await _api.getLabContext(fieldId);
    } catch (e) {
      ctxErr = ApiException.from(e);
    }
    if (isClosed) return;
    emit(
      LabSamplesLoaded(samples: samples, context: ctx, contextError: ctxErr),
    );
  }

  /// يطلب انتقال حالة. يُرجع رسالة خطأ أو null.
  Future<String?> transition(
    LabSample sample,
    LabSampleStatus target, {
    String? location,
    String? conditionNotes,
  }) async {
    final s = state;
    if (s is! LabSamplesLoaded || s.busy.contains(sample.sampleId)) return null;
    final from = sample.status;
    if (from == null || !from.allowedTargets.contains(target)) {
      return 'انتقال غير مسموح من «${from?.labelAr ?? sample.statusRaw}»';
    }
    final k = '${sample.sampleId}:${target.wire}';
    final key = _keys.putIfAbsent(k, IdempotencyKey.generate);
    emit(s.copyWith(busy: {...s.busy, sample.sampleId}));
    try {
      final updated = await _api.transition(
        sample.sampleId,
        target,
        idempotencyKey: key,
        location: location,
        conditionNotes: conditionNotes,
      );
      _keys.remove(k);
      final now = state;
      if (!isClosed && now is LabSamplesLoaded) {
        emit(
          now.copyWith(
            samples: [
              for (final x in now.samples)
                x.sampleId == updated.sampleId ? updated : x,
            ],
            busy: {...now.busy}..remove(sample.sampleId),
          ),
        );
      }
      return null;
    } catch (e) {
      final now = state;
      if (!isClosed && now is LabSamplesLoaded) {
        emit(now.copyWith(busy: {...now.busy}..remove(sample.sampleId)));
      }
      return ApiException.from(e).messageAr;
    }
  }
}
