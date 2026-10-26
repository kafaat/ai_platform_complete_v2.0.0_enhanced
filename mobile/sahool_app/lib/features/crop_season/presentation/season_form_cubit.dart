// SAHOOL — features/crop_season/presentation/season_form_cubit.dart
// إرسال نموذج الموسم (إنشاء/تعديل). مفتاح Idempotency واحد لكلّ فتح للنموذج
// يُعاد في كلّ محاولة حفظ — فإعادة الضغط بعد انقطاع لا تُنشئ موسماً ثانياً
// (الخادم يحترم المفتاح على POST seasons).
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/crop_season_api.dart';
import '../data/season_models.dart';
import 'season_form_logic.dart';

sealed class SeasonFormState {
  const SeasonFormState();
}

class SeasonFormEditing extends SeasonFormState {
  const SeasonFormEditing({this.errors = const {}, this.submitError});
  final Map<String, String> errors;
  final String? submitError;
}

class SeasonFormSubmitting extends SeasonFormState {
  const SeasonFormSubmitting();
}

class SeasonFormSaved extends SeasonFormState {
  const SeasonFormSaved(this.season);
  final Season season;
}

class SeasonFormCubit extends Cubit<SeasonFormState> {
  SeasonFormCubit(this._api, {required this.fieldId, this.original})
    : super(const SeasonFormEditing());

  final CropSeasonApi _api;
  final String fieldId;
  final Season? original;

  /// ثابت طوال عمر النموذج (نيّة كتابة واحدة).
  final IdempotencyKey idempotencyKey = IdempotencyKey.generate();

  bool get isEdit => original != null;

  Future<void> submit(SeasonFormInput input) async {
    if (state is SeasonFormSubmitting || state is SeasonFormSaved) return;
    final errors = validateSeasonForm(input, original: original);
    if (errors.isNotEmpty) {
      emit(SeasonFormEditing(errors: errors));
      return;
    }
    final Map<String, dynamic> body;
    if (original != null) {
      body = buildPatchBody(input, original!);
      if (body.isEmpty) {
        emit(const SeasonFormEditing(submitError: 'لا تغييرات للحفظ'));
        return;
      }
    } else {
      body = buildCreateBody(input);
    }
    emit(const SeasonFormSubmitting());
    try {
      final saved = original != null
          ? await _api.updateSeason(
              fieldId,
              original!.seasonId,
              body,
              idempotencyKey: idempotencyKey,
            )
          : await _api.createSeason(
              fieldId,
              body,
              idempotencyKey: idempotencyKey,
            );
      if (!isClosed) emit(SeasonFormSaved(saved));
    } catch (e) {
      if (!isClosed) emit(SeasonFormEditing(submitError: seasonWriteError(e)));
    }
  }
}
