// SAHOOL — features/crop_season/presentation/season_state_screen.dart
// «حالة الموسم»: الحقيقة التشغيليّة الموحّدة للحقل-الموسم
// (GET /fields/{id}/seasons/{sid}/state — field_season_projection.py). كلّ رقم من
// الخادم؛ الناقص يُعرَض «غير مقيس» وتُسرَد evidence_missing صراحةً.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/crop_season_api.dart';
import '../data/season_models.dart';

sealed class SeasonStateViewState {
  const SeasonStateViewState();
}

class SeasonStateLoading extends SeasonStateViewState {
  const SeasonStateLoading();
}

class SeasonStateFailed extends SeasonStateViewState {
  const SeasonStateFailed(this.error);
  final ApiException error;
}

class SeasonStateLoaded extends SeasonStateViewState {
  const SeasonStateLoaded(this.data);
  final Map<String, dynamic> data;
}

class SeasonStateCubit extends Cubit<SeasonStateViewState> {
  SeasonStateCubit(this._api, this.fieldId, this.seasonId)
    : super(const SeasonStateLoading());
  final CropSeasonApi _api;
  final String fieldId;
  final String seasonId;

  Future<void> load() async {
    emit(const SeasonStateLoading());
    try {
      final d = await _api.getSeasonState(fieldId, seasonId);
      if (!isClosed) emit(SeasonStateLoaded(d));
    } catch (e) {
      if (!isClosed) emit(SeasonStateFailed(ApiException.from(e)));
    }
  }
}

/// أسماء الإشارات الجوهريّة كما يسمّيها الخادم في evidence_used/missing.
const Map<String, String> kEvidenceLabelsAr = {
  'crop': 'المحصول',
  'sowing_date': 'تاريخ الزراعة',
  'days_after_sowing': 'عمر المحصول',
  'accumulated_gdd': 'الوحدات الحراريّة المتراكمة',
  'ndvi': 'مؤشّر الغطاء النباتيّ (NDVI)',
  'weather': 'إشارات الطقس',
  'water': 'ميزان الماء',
  'open_tasks': 'المهامّ المفتوحة',
  'outcomes': 'نتائج القرارات السابقة',
};

num? _n(Object? v) => v is num ? v : null;

class SeasonStateScreen extends StatelessWidget {
  const SeasonStateScreen({
    super.key,
    required this.fieldId,
    required this.season,
    this.cropName,
    this.api,
  });

  final String fieldId;
  final Season season;
  final String? cropName;
  final CropSeasonApi? api;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) => SeasonStateCubit(
      api ?? CropSeasonApi.instance,
      fieldId,
      season.seasonId,
    )..load(),
    child: BlocBuilder<SeasonStateCubit, SeasonStateViewState>(
      builder: (context, state) => AppScaffold(
        title: 'حالة الموسم',
        onRefresh: () => context.read<SeasonStateCubit>().load(),
        body: switch (state) {
          SeasonStateLoading() => const LoadingState(),
          SeasonStateFailed(:final error) => ErrorState(
            error: error,
            onRetry: () => context.read<SeasonStateCubit>().load(),
          ),
          SeasonStateLoaded(:final data) => _body(context, data),
        },
      ),
    ),
  );

  Widget _body(BuildContext context, Map<String, dynamic> d) {
    final t = context.tokens;
    final calendar = d['calendar'] is Map ? d['calendar'] as Map : const {};
    final missing = d['evidence_missing'] is List
        ? (d['evidence_missing'] as List).map((e) => e.toString()).toList()
        : const <String>[];
    final confidence = d['season_confidence']?.toString();
    final stageSource = switch (d['stage_source']) {
      'gdd' => 'حسب الوحدات الحراريّة',
      'days' => 'حسب عدد الأيّام',
      _ => null,
    };
    return ListView(
      padding: const EdgeInsets.all(SahoolSpacing.page),
      children: [
        Text(
          cropName ?? season.primaryCrop ?? '—',
          style: context.textStyles.titleLarge,
        ),
        Text(
          'زُرع ${fmtIsoDate(season.sowingDate)} · الحصاد المتوقّع ${fmtIsoDate(season.seasonEnd)}',
          style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
        ),
        const SizedBox(height: SahoolSpacing.md),
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.sm,
          children: [
            if (d['requires_review'] == true)
              const StatusChip(label: 'يحتاج مراجعة', tone: StatusTone.warning),
            if (confidence != null)
              StatusChip(
                label:
                    'الثقة: ${confidence == 'medium'
                        ? 'متوسّطة'
                        : confidence == 'low'
                        ? 'منخفضة'
                        : confidence}',
                tone: confidence == 'medium'
                    ? StatusTone.info
                    : StatusTone.neutral,
              ),
          ],
        ),
        SectionCard(
          title: 'الطور',
          icon: Icons.eco_outlined,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                d['current_stage_ar']?.toString() ?? kNotMeasured,
                style: context.textStyles.titleMedium,
              ),
              if (stageSource != null)
                Text(
                  stageSource,
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
            ],
          ),
        ),
        const SizedBox(height: SahoolSpacing.sm),
        MetricTile(
          label: 'أيّام بعد الزراعة',
          value: _n(d['days_after_sowing']),
          decimals: 0,
        ),
        MetricTile(
          label: 'معامل المحصول Kc',
          value: _n(d['current_kc']),
          decimals: 2,
        ),
        MetricTile(
          label: 'عجز الماء (7 أيّام)',
          value: _n(d['water_deficit_7d_mm']),
          unit: 'مم',
        ),
        MetricTile(
          label: 'عجز الماء (14 يوماً)',
          value: _n(d['water_deficit_14d_mm']),
          unit: 'مم',
        ),
        MetricTile(
          label: 'عمليّات مفتوحة',
          value: _n(d['open_operations']),
          decimals: 0,
        ),
        if (calendar['reason_ar'] != null)
          SectionCard(
            title: 'تقويم الموسم',
            icon: Icons.calendar_month_outlined,
            child: Text(calendar['reason_ar'].toString()),
          ),
        if (missing.isNotEmpty)
          SectionCard(
            title: 'بيانات غير متاحة بعد',
            icon: Icons.help_outline,
            child: Text(
              missing.map((k) => kEvidenceLabelsAr[k] ?? k).join('، '),
            ),
          ),
        if (d['disclaimer_ar'] != null)
          Padding(
            padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.md),
            child: Text(
              d['disclaimer_ar'].toString(),
              style: context.textStyles.bodySmall?.copyWith(color: t.muted),
            ),
          ),
      ],
    );
  }
}
