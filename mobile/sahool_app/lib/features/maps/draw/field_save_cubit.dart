// SAHOOL — features/maps/draw/field_save_cubit.dart
// حفظ الحقل من المعالج: إنشاء ← (موسم إن اختير محصول) ← (تقدير إنتاجيّة يُعرَض
// فقط إن ردّ الخادم رقماً).
//
// إنشاء الحقل عمليّةٌ مسجَّلة (offline_sync/data/operation_ledger.dart، UI-M3/D1):
// أوّل حفظ يكتب على القرص سجلّاً بالمفتاح (= operation_id) والحمولة الأصليّة
// ومالكها قبل الشبكة؛ فشل الكتابة ⇒ لا طلب. مهلة/انقطاع/5xx/إغلاق الشاشة لا تدوّر
// المفتاح ولا تستبدل الحمولة: الحالة [FieldSaveUnconfirmed] تعرض «استعادة نتيجة
// المحاولة السابقة» (نفس المفتاح ونفس الحمولة)، والمسودّة المعدّلة تُحفَظ وتُعرَض
// فروقها ولا تُرسَل ضمن الإنشاء. كان الإصلاح السابق يولّد مفتاحاً جديداً للمسودّة
// المعدّلة فيُنشئ حقلاً ثانياً بجانب الأوّل المُلتزَم. 409 لا يقود إلى مفتاح جديد.
// وإن نجح الإنشاء وفشل الموسم لا يُعاد الإنشاء.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import 'field_create_api.dart';
import 'field_create_errors.dart';
import 'field_created_events.dart';

/// نوع عمليّة إنشاء الحقل في سجلّ العمليّات المعلّقة.
const String kFieldCreateKind = 'field.create';

enum SaveStage { creating, season, estimate }

sealed class FieldSaveState {
  const FieldSaveState();
}

class FieldSaveIdle extends FieldSaveState {
  const FieldSaveIdle();
}

class FieldSaveInProgress extends FieldSaveState {
  const FieldSaveInProgress(this.stage);
  final SaveStage stage;
}

class FieldSaveFailed extends FieldSaveState {
  const FieldSaveFailed(this.error, this.view);
  final ApiException error;
  final CreateErrorView view;
}

/// إنشاءٌ سابق لم تُحسَم نتيجته — لا حفظ جديد، الاستعادة فقط.
class FieldSaveUnconfirmed extends FieldSaveState {
  const FieldSaveUnconfirmed(this.outcome, {this.busy = false});
  final CreateUnconfirmed outcome;
  final bool busy;
}

class FieldSaveDone extends FieldSaveState {
  const FieldSaveDone({
    required this.field,
    this.seasonWarning,
    this.yieldEstimate,
    this.pendingEdits = const [],
  });

  /// استجابة الخادم (FieldSummary): مصدر المعرّف والمساحة المخزّنة.
  final Map<String, dynamic> field;
  final String? seasonWarning;

  /// تقدير الإنتاجيّة إن ردّ الخادم `estimated_yield_kg_ha` رقماً، وإلّا null.
  final Map<String, dynamic>? yieldEstimate;

  /// تعديلات المسودّة بعد نتيجة مجهولة — لم تُرسَل ضمن الإنشاء المُستعاد.
  final List<PayloadChange> pendingEdits;

  String get fieldId => (field['field_id'] ?? '').toString();
  double? get areaHa =>
      field['area_ha'] is num ? (field['area_ha'] as num).toDouble() : null;
}

class FieldSaveCubit extends Cubit<FieldSaveState> {
  FieldSaveCubit({
    FieldCreateApi? createApi,
    FieldsApi? fieldsApi,
    ResponseCache? cache,
    FieldCreatedEvents? events,
    OperationLedger? ledger,
  }) : _create = createApi ?? FieldCreateApi.instance,
       _fields = fieldsApi ?? FieldsApi.instance,
       _cache = cache ?? ResponseCache.instance,
       _events = events ?? FieldCreatedEvents.instance,
       _ledger = ledger ?? OperationLedger.shared,
       super(const FieldSaveIdle());

  final FieldCreateApi _create;
  final FieldsApi _fields;
  final ResponseCache _cache;
  final FieldCreatedEvents _events;
  final OperationLedger _ledger;

  late final CreateOperation _op = CreateOperation(
    ledger: _ledger,
    kind: kFieldCreateKind,
    method: 'POST',
    path: '/api/v1/fields',
    send: (payload, key) =>
        _create.createFieldPayload(payload, idempotencyKey: key),
  );

  /// مفتاح «أنشئ هذا الحقل» = operation_id للسجلّ؛ null قبل أوّل حفظ.
  IdempotencyKey? get createKey => _op.record?.key;

  /// سجلّ العمليّة الحاليّ (للاختبار والتشخيص).
  OperationRecord? get operation => _op.record;
  final IdempotencyKey seasonKey = IdempotencyKey.generate();

  Map<String, dynamic>? _created;

  bool get busy =>
      state is FieldSaveInProgress ||
      (state is FieldSaveUnconfirmed && (state as FieldSaveUnconfirmed).busy);

  /// يستعيد إنشاءً معلّقاً لنفس المالك (إعادة فتح المعالج أو التطبيق).
  Future<void> restore() async {
    final o = await _op.restore();
    if (isClosed || o is! CreateUnconfirmed) return;
    emit(FieldSaveUnconfirmed(o));
  }

  Future<void> save(
    FieldCreateDraft draft, {
    String? seasonCrop,
    String? sowingDate,
  }) async {
    if (busy) return; // منع الإرسال المزدوج
    if (state is FieldSaveDone) return;
    var field = _created;
    var pendingEdits = const <PayloadChange>[];
    if (field == null) {
      final s = state;
      emit(
        s is FieldSaveUnconfirmed
            ? FieldSaveUnconfirmed(s.outcome, busy: true)
            : const FieldSaveInProgress(SaveStage.creating),
      );
      final o = await _op.submit(
        draft.toJson(),
        context: {'season_crop': ?seasonCrop, 'sowing_date': ?sowingDate},
      );
      if (isClosed) return;
      final confirmed = _onCreateOutcome(o);
      if (confirmed == null) return;
      field = confirmed.result;
      pendingEdits = confirmed.pendingEdits;
    }
    await _afterCreate(
      field,
      seasonCrop: seasonCrop,
      sowingDate: sowingDate,
      irrigationType: draft.toJson()['irrigation_type'] as String?,
      pendingEdits: pendingEdits,
    );
  }

  /// «استعادة نتيجة المحاولة السابقة»: نفس المفتاح ونفس الحمولة الأصليّة. [draft]
  /// المسودّة الحاليّة — تُحفَظ لتُعرَض فروقها، ولا تُرسَل.
  Future<void> recover({FieldCreateDraft? draft}) async {
    final s = state;
    if (s is! FieldSaveUnconfirmed || s.busy) return;
    emit(FieldSaveUnconfirmed(s.outcome, busy: true));
    final o = await _op.recover(draft: draft?.toJson());
    if (isClosed || o == null) return;
    final confirmed = _onCreateOutcome(o);
    if (confirmed == null) return;
    final ctx = confirmed.record.context;
    await _afterCreate(
      confirmed.result,
      seasonCrop: ctx['season_crop'] as String?,
      sowingDate: ctx['sowing_date'] as String?,
      irrigationType: confirmed.record.payload['irrigation_type'] as String?,
      pendingEdits: confirmed.pendingEdits,
    );
  }

  /// يحفظ المسودّة لإنشاءٍ غير محسوم (إغلاق المعالج). لا شبكة.
  Future<void> rememberDraft(FieldCreateDraft draft) =>
      _op.saveDraft(draft.toJson());

  /// يغلق عمليّة انقضت مدّة احتفاظها بعد مراجعة المستخدم للقائمة (R13).
  Future<void> dismissReconciled() async {
    if (await _op.dismiss() && !isClosed) emit(const FieldSaveIdle());
  }

  /// يُصدر حالة النتيجة؛ يُعيد التأكيد إن أُنشئ الحقل.
  CreateConfirmed? _onCreateOutcome(CreateOutcome o) {
    switch (o) {
      case CreateConfirmed(:final result):
        _created = result;
        // قائمة الحقول ولوحة القيادة صارتا قديمتين.
        _cache.clear();
        _events.notifyCreated(result);
        return o;
      case CreateUnconfirmed():
        emit(FieldSaveUnconfirmed(o));
      case CreateRejected(:final error):
        emit(FieldSaveFailed(error, describeCreateError(error)));
      case CreateNotSaved(:final messageAr):
        final e = ApiException(kind: ApiErrorKind.unknown, messageAr: messageAr);
        emit(FieldSaveFailed(e, CreateErrorView(messageAr, FixStep.none)));
      case CreateBusy():
        break;
    }
    return null;
  }

  Future<void> _afterCreate(
    Map<String, dynamic> field, {
    String? seasonCrop,
    String? sowingDate,
    String? irrigationType,
    List<PayloadChange> pendingEdits = const [],
  }) async {
    final fieldId = (field['field_id'] ?? '').toString();
    String? seasonWarning;
    Map<String, dynamic>? estimate;
    if (seasonCrop != null && fieldId.isNotEmpty) {
      if (!isClosed) emit(const FieldSaveInProgress(SaveStage.season));
      try {
        await _fields.createSeason(
          fieldId,
          crop: seasonCrop,
          irrigationType: field['irrigation_type']?.toString() ?? irrigationType,
          sowingDate: sowingDate,
          idempotencyKey: seasonKey,
        );
      } catch (e) {
        seasonWarning =
            'أُنشئ الحقل، لكن تعذّر إنشاء الموسم: '
            '${ApiException.from(e).messageAr} أضِفه من مساحة العمل.';
      }
      if (!isClosed) emit(const FieldSaveInProgress(SaveStage.estimate));
      try {
        final r = await _fields.requestYieldEstimate(fieldId, crop: seasonCrop);
        if (r['estimated_yield_kg_ha'] is num) estimate = r;
      } catch (_) {
        // التقدير اختياريّ: غيابه لا يُعرَض رقماً ولا يوقف الانتقال.
      }
    }
    if (isClosed) return;
    emit(
      FieldSaveDone(
        field: field,
        seasonWarning: seasonWarning,
        yieldEstimate: estimate,
        pendingEdits: pendingEdits,
      ),
    );
  }

  /// يعيد الحالة إلى الخمول بعد عرض رفضٍ مثبت قبل التنفيذ (المفتاح يبقى للعمليّة).
  void acknowledgeError() {
    if (state is FieldSaveFailed) emit(const FieldSaveIdle());
  }
}
