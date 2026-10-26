// SAHOOL — features/advisor/presentation/recommendations_cubit.dart
// حالات التوصيات: عمود الحقل الموحَّد، طلب توصية من المحرّك، تفاصيل توصية
// مُخزَّنة، والتغذية الراجعة (قبول/رفض) بمفتاح منع تكرار واحد لكلّ نيّة.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';
import 'package:sahool_app/features/advisor/data/advisor_models.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/field_picker.dart';

enum LoadPhase { idle, loading, loaded, failed }

// ═══════════════════════════════════════════════════════════════════
// توصيات الحقل
// ═══════════════════════════════════════════════════════════════════

class RecommendationsState {
  const RecommendationsState({
    this.field,
    this.resolvingField = false,
    this.columnPhase = LoadPhase.idle,
    this.column,
    this.columnError,
    this.requesting = false,
    this.engine,
    this.engineError,
  });

  final FieldChoice? field;
  final bool resolvingField;
  final LoadPhase columnPhase;
  final FieldRecommendationSet? column;
  final ApiException? columnError;
  final bool requesting;
  final EngineRecommendation? engine;
  final ApiException? engineError;

  RecommendationsState copyWith({
    FieldChoice? Function()? field,
    bool? resolvingField,
    LoadPhase? columnPhase,
    FieldRecommendationSet? Function()? column,
    ApiException? Function()? columnError,
    bool? requesting,
    EngineRecommendation? Function()? engine,
    ApiException? Function()? engineError,
  }) => RecommendationsState(
    field: field != null ? field() : this.field,
    resolvingField: resolvingField ?? this.resolvingField,
    columnPhase: columnPhase ?? this.columnPhase,
    column: column != null ? column() : this.column,
    columnError: columnError != null ? columnError() : this.columnError,
    requesting: requesting ?? this.requesting,
    engine: engine != null ? engine() : this.engine,
    engineError: engineError != null ? engineError() : this.engineError,
  );
}

class RecommendationsCubit extends Cubit<RecommendationsState> {
  RecommendationsCubit(this._api, {FieldLoader? fieldLoader})
    : _fieldLoader = fieldLoader,
      super(const RecommendationsState());

  final AdvisorApi _api;
  final FieldLoader? _fieldLoader;

  /// يفتح الشاشة بحقل معروف المعرّف: يستكمل الاسم/المحصول/المزرعة من قائمة
  /// الحقول (إن تعذّرت يبقى المعرّف وحده — لا اسم مُخترَع).
  Future<void> openWithFieldId(String fieldId) async {
    emit(
      state.copyWith(
        field: () => FieldChoice(id: fieldId, name: fieldId),
        resolvingField: _fieldLoader != null,
      ),
    );
    final loadColumn = load();
    final loader = _fieldLoader;
    if (loader != null) {
      try {
        final match = (await loader())
            .map(FieldChoice.fromJson)
            .whereType<FieldChoice>()
            .where((f) => f.id == fieldId)
            .firstOrNull;
        if (!isClosed && match != null) {
          emit(state.copyWith(field: () => match));
        }
      } catch (_) {
        // الاسم تجميليّ؛ فشل القائمة لا يمنع التوصيات.
      }
      if (!isClosed) emit(state.copyWith(resolvingField: false));
    }
    await loadColumn;
  }

  Future<void> selectField(FieldChoice field) async {
    emit(
      state.copyWith(
        field: () => field,
        engine: () => null,
        engineError: () => null,
      ),
    );
    await load();
  }

  Future<void> load() async {
    final field = state.field;
    if (field == null) return;
    emit(
      state.copyWith(columnPhase: LoadPhase.loading, columnError: () => null),
    );
    try {
      final json = await _api.getFieldRecommendations(field.id);
      final set = FieldRecommendationSet.fromJson(json, field.id);
      if (isClosed || state.field?.id != field.id) return;
      emit(state.copyWith(columnPhase: LoadPhase.loaded, column: () => set));
    } catch (e) {
      if (isClosed || state.field?.id != field.id) return;
      emit(
        state.copyWith(
          columnPhase: LoadPhase.failed,
          column: () => null,
          columnError: () => ApiException.from(e),
        ),
      );
    }
  }

  /// يطلب توصية من المحرّك. لا مفتاح منع تكرار (الخادم لا يحترمه هنا) — لذلك
  /// يُمنَع الإرسال المزدوج محلّيّاً ولا يُعاد الطلب تلقائيّاً.
  Future<void> requestEngine({
    required String crop,
    String? growthStage,
  }) async {
    final field = state.field;
    if (field == null || state.requesting) return;
    emit(
      state.copyWith(
        requesting: true,
        engine: () => null,
        engineError: () => null,
      ),
    );
    try {
      final json = await _api.requestRecommendationForField(
        fieldId: field.id,
        crop: crop,
        farmId: field.farmId ?? '',
        growthStage: growthStage,
      );
      final rec = EngineRecommendation.fromJson(json);
      if (isClosed) return;
      emit(state.copyWith(requesting: false, engine: () => rec));
    } catch (e) {
      if (isClosed) return;
      emit(
        state.copyWith(
          requesting: false,
          engineError: () => ApiException.from(e),
        ),
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// تفاصيل توصية مُخزَّنة
// ═══════════════════════════════════════════════════════════════════

class RecommendationDetailState {
  const RecommendationDetailState({
    this.phase = LoadPhase.loading,
    this.recommendation,
    this.raw = const {},
    this.error,
  });

  final LoadPhase phase;
  final EngineRecommendation? recommendation;
  final Map<String, dynamic> raw;
  final ApiException? error;
}

class RecommendationDetailCubit extends Cubit<RecommendationDetailState> {
  RecommendationDetailCubit(this._api, this.recId)
    : super(const RecommendationDetailState());

  final AdvisorApi _api;
  final String recId;

  Future<void> load() async {
    emit(const RecommendationDetailState());
    try {
      final json = await _api.getRecommendation(recId);
      final rec = EngineRecommendation.fromJson(json);
      if (isClosed) return;
      emit(
        RecommendationDetailState(
          phase: LoadPhase.loaded,
          recommendation: rec,
          raw: json,
        ),
      );
    } catch (e) {
      if (isClosed) return;
      emit(
        RecommendationDetailState(
          phase: LoadPhase.failed,
          error: ApiException.from(e),
        ),
      );
    }
  }
}

// ═══════════════════════════════════════════════════════════════════
// التغذية الراجعة (قبول/رفض)
// ═══════════════════════════════════════════════════════════════════

enum FeedbackPhase { idle, submitting, recorded, failed }

class OutcomeFeedbackState {
  const OutcomeFeedbackState({this.phase = FeedbackPhase.idle, this.error});
  final FeedbackPhase phase;
  final ApiException? error;
}

/// نيّة تغذية واحدة = مفتاح واحد يُولَّد عند فتح الورقة ويُعاد في كلّ محاولة،
/// فلا يُسجَّل القبول/الرفض مرّتين إن ضاعت استجابة الخادم.
class OutcomeFeedbackCubit extends Cubit<OutcomeFeedbackState> {
  OutcomeFeedbackCubit(
    this._api, {
    required this.accepted,
    required this.crop,
    required this.fieldId,
    this.farmId,
    this.recommendationId,
    this.predictedYieldTHa,
    IdempotencyKey? idempotencyKey,
  }) : idempotencyKey = idempotencyKey ?? IdempotencyKey.generate(),
       super(const OutcomeFeedbackState());

  final AdvisorApi _api;
  final bool accepted;
  final String crop;
  final String fieldId;
  final String? farmId;
  final String? recommendationId;
  final double? predictedYieldTHa;
  final IdempotencyKey idempotencyKey;

  Future<void> submit() async {
    if (state.phase == FeedbackPhase.submitting ||
        state.phase == FeedbackPhase.recorded) {
      return;
    }
    emit(const OutcomeFeedbackState(phase: FeedbackPhase.submitting));
    try {
      await _api.recordRecommendationOutcome(
        crop: crop,
        fieldId: fieldId,
        farmId: farmId,
        recommendationId: recommendationId,
        predictedYieldTHa: predictedYieldTHa,
        accepted: accepted,
        idempotencyKey: idempotencyKey,
      );
      if (isClosed) return;
      emit(const OutcomeFeedbackState(phase: FeedbackPhase.recorded));
    } catch (e) {
      if (isClosed) return;
      emit(
        OutcomeFeedbackState(
          phase: FeedbackPhase.failed,
          error: ApiException.from(e),
        ),
      );
    }
  }
}
