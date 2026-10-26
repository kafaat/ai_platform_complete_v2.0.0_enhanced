// SAHOOL — features/crop_season/presentation/seasons_cubit.dart
// حالة شاشة مواسم الحقل: قائمة المواسم + فينولوجيا الموسم النشط + إجراءات طوره
// + فهرس المحاصيل (للعرض بالاسم العربيّ). فشل الفينولوجيا لا يُسقط القائمة:
// يُحمَل خطؤه بجانبها ويُعرَض في بطاقتها وحدها.
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../data/crop_season_api.dart';
import '../data/season_models.dart';
import 'season_form_logic.dart';

sealed class SeasonsState {
  const SeasonsState();
}

class SeasonsLoading extends SeasonsState {
  const SeasonsLoading();
}

class SeasonsFailed extends SeasonsState {
  const SeasonsFailed(this.error);
  final ApiException error;
}

class SeasonsLoaded extends SeasonsState {
  const SeasonsLoaded({
    required this.seasons,
    this.phenology,
    this.phenologyError,
    this.stageActions,
    this.stageActionsError,
    this.catalog = const [],
    this.busySeasonIds = const {},
  });

  final List<Season> seasons;
  final Phenology? phenology;
  final ApiException? phenologyError;
  final StageActions? stageActions;
  final ApiException? stageActionsError;
  final List<CropOption> catalog;

  /// مواسم يجري تغيير حالتها الآن — يمنع الضغط المزدوج.
  final Set<String> busySeasonIds;

  Season? get activeSeason {
    for (final s in seasons) {
      if (s.status == SeasonStatus.active) return s;
    }
    return null;
  }

  SeasonsLoaded copyWith({Set<String>? busySeasonIds}) => SeasonsLoaded(
    seasons: seasons,
    phenology: phenology,
    phenologyError: phenologyError,
    stageActions: stageActions,
    stageActionsError: stageActionsError,
    catalog: catalog,
    busySeasonIds: busySeasonIds ?? this.busySeasonIds,
  );
}

class SeasonsCubit extends Cubit<SeasonsState> {
  SeasonsCubit(this._api, this.fieldId) : super(const SeasonsLoading());

  final CropSeasonApi _api;
  final String fieldId;

  /// مفتاح ثابت لكلّ نيّة انتقال (موسم + حالة هدف) طوال عمر الشاشة.
  final Map<String, IdempotencyKey> _transitionKeys = {};

  Future<void> load() async {
    if (state is! SeasonsLoaded) emit(const SeasonsLoading());
    final List<Season> seasons;
    try {
      seasons = await _api.listSeasons(fieldId);
    } catch (e) {
      if (!isClosed) emit(SeasonsFailed(ApiException.from(e)));
      return;
    }
    Phenology? pheno;
    ApiException? phenoErr;
    StageActions? actions;
    ApiException? actionsErr;
    var catalog = const <CropOption>[];
    await Future.wait<void>([
      () async {
        try {
          pheno = await _api.getPhenology(fieldId);
        } catch (e) {
          phenoErr = ApiException.from(e);
        }
      }(),
      () async {
        try {
          actions = await _api.getStageActions(fieldId);
        } catch (e) {
          actionsErr = ApiException.from(e);
        }
      }(),
      () async {
        // الفهرس للعرض فقط؛ تعذّره يُبقي اسم المحصول كما خُزّن.
        try {
          catalog = await _api.listCropCards();
        } catch (_) {}
      }(),
    ]);
    if (isClosed) return;
    emit(
      SeasonsLoaded(
        seasons: seasons,
        phenology: pheno,
        phenologyError: phenoErr,
        stageActions: actions,
        stageActionsError: actionsErr,
        catalog: catalog,
      ),
    );
  }

  /// ينقل حالة الموسم. يُرجع رسالة خطأ عربيّة أو null عند النجاح.
  Future<String?> transition(Season season, SeasonStatus target) async {
    final s = state;
    if (s is! SeasonsLoaded || s.busySeasonIds.contains(season.seasonId)) {
      return null;
    }
    final from = season.status;
    if (from == null || !from.canTransitionTo(target)) {
      return 'انتقال غير مسموح: ${from?.labelAr ?? season.statusRaw} ← ${target.labelAr}';
    }
    final key = _transitionKeys.putIfAbsent(
      '${season.seasonId}:${target.wire}',
      IdempotencyKey.generate,
    );
    emit(s.copyWith(busySeasonIds: {...s.busySeasonIds, season.seasonId}));
    try {
      await _api.updateSeason(fieldId, season.seasonId, {
        'status': target.wire,
      }, idempotencyKey: key);
      _transitionKeys.remove('${season.seasonId}:${target.wire}');
      await load();
      return null;
    } catch (e) {
      final now = state;
      if (!isClosed && now is SeasonsLoaded) {
        emit(
          now.copyWith(
            busySeasonIds: {...now.busySeasonIds}..remove(season.seasonId),
          ),
        );
      }
      return seasonWriteError(e);
    }
  }
}
