// SAHOOL — features/maps/draw/field_save_cubit.dart
// حفظ الحقل من المعالج: إنشاء ← (موسم إن اختير محصول) ← (تقدير إنتاجيّة يُعرَض
// فقط إن ردّ الخادم رقماً).
//
// مفاتيح منع التكرار تُولَّد **مرّة لكلّ معالج** وتُعاد في كلّ محاولة: إعادةٌ بعد
// انقطاع تُرجع الحقل نفسه من مخزن الأوامر في الخادم بدل 409 «اسم مكرّر» (كانت
// علّة: لا مفتاح على الإطلاق). وإن نجح الإنشاء وفشل الموسم لا يُعاد الإنشاء.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/response_cache.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';

import 'field_create_api.dart';
import 'field_create_errors.dart';
import 'field_created_events.dart';

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

class FieldSaveDone extends FieldSaveState {
  const FieldSaveDone({
    required this.field,
    this.seasonWarning,
    this.yieldEstimate,
  });

  /// استجابة الخادم (FieldSummary): مصدر المعرّف والمساحة المخزّنة.
  final Map<String, dynamic> field;
  final String? seasonWarning;

  /// تقدير الإنتاجيّة إن ردّ الخادم `estimated_yield_kg_ha` رقماً، وإلّا null.
  final Map<String, dynamic>? yieldEstimate;

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
  }) : _create = createApi ?? FieldCreateApi.instance,
       _fields = fieldsApi ?? FieldsApi.instance,
       _cache = cache ?? ResponseCache.instance,
       _events = events ?? FieldCreatedEvents.instance,
       super(const FieldSaveIdle());

  final FieldCreateApi _create;
  final FieldsApi _fields;
  final ResponseCache _cache;
  final FieldCreatedEvents _events;

  /// مفتاح نيّة «أنشئ هذا الحقل» — ثابت طوال عمر المعالج.
  final IdempotencyKey createKey = IdempotencyKey.generate();
  final IdempotencyKey seasonKey = IdempotencyKey.generate();

  Map<String, dynamic>? _created;

  bool get busy => state is FieldSaveInProgress;

  Future<void> save(
    FieldCreateDraft draft, {
    String? seasonCrop,
    String? sowingDate,
  }) async {
    if (busy) return; // منع الإرسال المزدوج
    if (state is FieldSaveDone) return;
    var field = _created;
    if (field == null) {
      emit(const FieldSaveInProgress(SaveStage.creating));
      try {
        field = await _create.createField(draft, idempotencyKey: createKey);
      } catch (e) {
        if (isClosed) return;
        emit(FieldSaveFailed(ApiException.from(e), describeCreateError(e)));
        return;
      }
      _created = field;
      // قائمة الحقول ولوحة القيادة صارتا قديمتين.
      _cache.clear();
      _events.notifyCreated(field);
    }
    final fieldId = (field['field_id'] ?? '').toString();

    String? seasonWarning;
    Map<String, dynamic>? estimate;
    if (seasonCrop != null && fieldId.isNotEmpty) {
      if (!isClosed) emit(const FieldSaveInProgress(SaveStage.season));
      try {
        await _fields.createSeason(
          fieldId,
          crop: seasonCrop,
          irrigationType:
              field['irrigation_type']?.toString() ??
              draft.toJson()['irrigation_type'] as String?,
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
      ),
    );
  }

  /// يعيد الحالة إلى الخمول بعد عرض الخطأ (المفتاح يبقى كما هو).
  void acknowledgeError() {
    if (state is FieldSaveFailed) emit(const FieldSaveIdle());
  }
}
