// SAHOOL — features/crop_season/presentation/season_form_cubit.dart
// إرسال نموذج الموسم (إنشاء/تعديل).
//
// الإنشاء عمليّةٌ مسجَّلة (offline_sync/data/operation_ledger.dart، UI-M3/D1): أوّل
// إرسال يكتب على القرص سجلّاً بالمفتاح والحمولة الأصليّة ومالكها قبل الشبكة؛ فشل
// الكتابة ⇒ لا طلب. نتيجة مجهولة (مهلة/انقطاع/5xx) أو 409 لا تدوّر المفتاح أبداً:
// تُعرض «استعادة نتيجة المحاولة السابقة» (نفس المفتاح ونفس الحمولة)، والنموذج المعدّل
// مسودّةٌ تُعرَض فروقها ولا تُرسَل ضمن الإنشاء. بعد الاستعادة يُربط النموذج بالموسم
// الحقيقيّ، وتطبيق التعديلات تحديثٌ مستقلّ (PATCH) بعد تأكيد المستخدم. كان الإصلاح
// السابق يولّد مفتاحاً جديداً للحمولة المعدّلة فينشئ موسماً ثانياً بجانب الأوّل.
//
// التعديل (PATCH) لا يقرأ الخادم مفتاحه (التحديث متساوي القوّة)؛ يبقى مفتاحه مربوطاً
// بالحمولة كما كان.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../data/crop_season_api.dart';
import '../data/season_models.dart';
import 'season_form_logic.dart';

/// نوع عمليّة إنشاء الموسم في سجلّ العمليّات المعلّقة (النطاق = field_id).
const String kSeasonCreateKind = 'season.create';

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

/// إنشاءٌ سابق لم تُحسَم نتيجته — لا زرّ إنشاء، الاستعادة فقط.
class SeasonFormUnconfirmed extends SeasonFormState {
  const SeasonFormUnconfirmed(this.outcome, {this.busy = false});
  final CreateUnconfirmed outcome;
  final bool busy;
}

/// استُعيد الموسم المُنشأ وبقيت تعديلات لم تُرسَل. [applyError] فشل تطبيقها.
class SeasonFormRecovered extends SeasonFormState {
  const SeasonFormRecovered(
    this.season,
    this.pendingEdits, {
    this.busy = false,
    this.applyError,
  });
  final Season season;
  final List<PayloadChange> pendingEdits;
  final bool busy;
  final String? applyError;
}

class SeasonFormCubit extends Cubit<SeasonFormState> {
  SeasonFormCubit(
    this._api, {
    required this.fieldId,
    this.original,
    OperationLedger? ledger,
  }) : _ledger = ledger ?? OperationLedger.shared,
       super(const SeasonFormEditing());

  final CropSeasonApi _api;
  final String fieldId;
  final Season? original;
  final OperationLedger _ledger;

  /// مفتاح التعديل (PATCH) — مربوط بالحمولة.
  final PayloadIdempotencyKey _editKey = PayloadIdempotencyKey();

  late final CreateOperation _create = CreateOperation(
    ledger: _ledger,
    kind: kSeasonCreateKind,
    scope: fieldId,
    method: 'POST',
    path: '/api/v1/fields/${Uri.encodeComponent(fieldId)}/seasons',
    send: (body, key) =>
        _api.createSeasonRaw(fieldId, body, idempotencyKey: key),
  );

  /// مفتاح العمليّة: مفتاح الإنشاء المسجَّل، أو مفتاح التعديل.
  IdempotencyKey get idempotencyKey =>
      original != null ? _editKey.current : (_create.record?.key ?? _editKey.current);

  /// سجلّ عمليّة الإنشاء الحاليّة (للاختبار والتشخيص).
  OperationRecord? get operation => _create.record;

  bool get isEdit => original != null;

  /// يستعيد إنشاءً معلّقاً لنفس المالك والحقل (إعادة فتح الشاشة/التطبيق).
  Future<void> restore() async {
    if (isEdit) return;
    final o = await _create.restore();
    if (isClosed || o == null) return;
    _emitOutcome(o);
  }

  Future<void> submit(SeasonFormInput input) async {
    final s = state;
    if (s is SeasonFormSubmitting ||
        s is SeasonFormSaved ||
        s is SeasonFormRecovered) {
      return;
    }
    if (s is SeasonFormUnconfirmed && s.busy) return;
    final errors = validateSeasonForm(input, original: original);
    if (errors.isNotEmpty) {
      if (s is SeasonFormUnconfirmed) {
        // المسودّة غير صالحة: لا تُحفَظ، واللوحة تبقى.
        return;
      }
      emit(SeasonFormEditing(errors: errors));
      return;
    }
    if (original != null) return _submitEdit(input);
    final body = buildCreateBody(input);
    if (s is SeasonFormUnconfirmed) {
      emit(SeasonFormUnconfirmed(s.outcome, busy: true));
    } else {
      emit(const SeasonFormSubmitting());
    }
    final o = await _create.submit(body);
    if (!isClosed) _emitOutcome(o);
  }

  /// «استعادة نتيجة المحاولة السابقة»: نفس المفتاح ونفس الحمولة الأصليّة. [draft]
  /// مُدخَل النموذج الحاليّ — يُحفَظ لتُعرَض فروقه فقط.
  Future<void> recover({SeasonFormInput? draft}) async {
    final s = state;
    if (s is! SeasonFormUnconfirmed || s.busy) return;
    Map<String, dynamic>? draftBody;
    if (draft != null && validateSeasonForm(draft).isEmpty) {
      draftBody = buildCreateBody(draft);
    }
    emit(SeasonFormUnconfirmed(s.outcome, busy: true));
    final o = await _create.recover(draft: draftBody);
    if (!isClosed && o != null) _emitOutcome(o);
  }

  /// يحفظ مُدخَل النموذج مسودّةً لإنشاءٍ غير محسوم (إغلاق الشاشة). لا شبكة.
  Future<void> rememberDraft(SeasonFormInput input) async {
    if (isEdit || validateSeasonForm(input).isNotEmpty) return;
    await _create.saveDraft(buildCreateBody(input));
  }

  /// بعد مراجعة بشريّة لعمليّة انقضت مدّة احتفاظها (needs_reconciliation).
  Future<void> dismissReconciled() async {
    if (await _create.dismiss() && !isClosed) {
      emit(const SeasonFormEditing());
    }
  }

  /// تطبيق التعديلات التي لم تُرسَل على الموسم المُستعاد — تحديثٌ مستقلّ بمفتاحه.
  Future<void> applyPendingEdits() async {
    final s = state;
    if (s is! SeasonFormRecovered || s.busy) return;
    final body = <String, dynamic>{
      for (final c in s.pendingEdits) c.key: c.after,
    };
    if (s.season.rowVersion != null) body['base_version'] = s.season.rowVersion;
    emit(SeasonFormRecovered(s.season, s.pendingEdits, busy: true));
    try {
      final saved = await _api.updateSeason(
        fieldId,
        s.season.seasonId,
        body,
        idempotencyKey: IdempotencyKey.generate(),
      );
      if (!isClosed) emit(SeasonFormSaved(saved));
    } catch (e) {
      if (!isClosed) {
        emit(
          SeasonFormRecovered(
            s.season,
            s.pendingEdits,
            applyError: seasonWriteError(e),
          ),
        );
      }
    }
  }

  /// الإبقاء على الموسم المُستعاد دون تطبيق التعديلات.
  void keepRecovered() {
    final s = state;
    if (s is SeasonFormRecovered && !s.busy) emit(SeasonFormSaved(s.season));
  }

  void _emitOutcome(CreateOutcome o) {
    switch (o) {
      case CreateConfirmed(:final result, :final pendingEdits):
        final season = Season.fromJson(result);
        emit(
          pendingEdits.isEmpty
              ? SeasonFormSaved(season)
              : SeasonFormRecovered(season, pendingEdits),
        );
      case CreateUnconfirmed():
        emit(SeasonFormUnconfirmed(o));
      case CreateRejected(:final error):
        emit(SeasonFormEditing(submitError: seasonWriteError(error)));
      case CreateNotSaved(:final messageAr):
        emit(SeasonFormEditing(submitError: messageAr));
      case CreateBusy():
        break;
    }
  }

  Future<void> _submitEdit(SeasonFormInput input) async {
    final body = buildPatchBody(input, original!);
    if (body.isEmpty) {
      emit(const SeasonFormEditing(submitError: 'لا تغييرات للحفظ'));
      return;
    }
    final key = _editKey.forPayload(body);
    emit(const SeasonFormSubmitting());
    try {
      final saved = await _api.updateSeason(
        fieldId,
        original!.seasonId,
        body,
        idempotencyKey: key,
      );
      if (!isClosed) emit(SeasonFormSaved(saved));
    } catch (e) {
      if (!isClosed) {
        emit(
          SeasonFormEditing(submitError: seasonWriteError(ApiException.from(e))),
        );
      }
    }
  }
}
