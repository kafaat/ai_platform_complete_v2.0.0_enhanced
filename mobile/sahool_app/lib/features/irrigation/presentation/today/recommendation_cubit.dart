// SAHOOL — features/irrigation/presentation/today/recommendation_cubit.dart
// «هل أروي اليوم؟» لحقل واحد. رمز طلب يمنع استجابةً بطيئة لحقلٍ سابق من الكتابة
// فوق الحقل المختار الآن.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';

sealed class RecommendationState {
  const RecommendationState();
}

class RecommendationIdle extends RecommendationState {
  const RecommendationIdle();
}

class RecommendationLoading extends RecommendationState {
  const RecommendationLoading(this.fieldId);
  final String fieldId;
}

class RecommendationLoaded extends RecommendationState {
  const RecommendationLoaded(this.fieldId, this.recommendation, this.at);
  final String fieldId;
  final IrrigationRecommendation recommendation;
  final DateTime at;
}

class RecommendationFailed extends RecommendationState {
  const RecommendationFailed(this.fieldId, this.error);
  final String fieldId;
  final ApiException error;
}

class RecommendationCubit extends Cubit<RecommendationState> {
  RecommendationCubit(this._api) : super(const RecommendationIdle());

  final IrrigationApi _api;
  int _token = 0;

  Future<void> load(String fieldId) async {
    final token = ++_token;
    emit(RecommendationLoading(fieldId));
    try {
      final json = await _api.getFieldRecommendation(fieldId);
      final rec = IrrigationRecommendation.fromJson(json);
      if (isClosed || token != _token) return;
      emit(RecommendationLoaded(fieldId, rec, DateTime.now()));
    } catch (e) {
      if (isClosed || token != _token) return;
      emit(RecommendationFailed(fieldId, ApiException.from(e)));
    }
  }
}
