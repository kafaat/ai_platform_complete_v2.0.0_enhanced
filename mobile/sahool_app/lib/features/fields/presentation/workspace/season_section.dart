// SAHOOL — features/fields/presentation/workspace/season_section.dart
// تبويب «الموسم والمحصول»: الموسم النشط (من مساحة الموسم)، جاهزيّة البيانات
// ونواقصها، التوصيات، المصادر غير المكتملة، وتاريخ المواسم
// (GET /api/v1/fields/{id}/seasons). الحالات مترجمة والتواريخ/الوحدات منسّقة.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../common/cross_feature_routes.dart';
import '../common/field_labels.dart';
import '../common/load_cubit.dart';
import 'workspace_deps.dart';
import 'workspace_widgets.dart';

String cropsText(Object? crops) {
  if (crops is List && crops.isNotEmpty) return crops.join('، ');
  final s = wText(crops, '');
  return s.isEmpty ? 'محصول غير محدّد' : s;
}

class WSeasonSection extends StatefulWidget {
  const WSeasonSection({super.key, required this.fieldId});
  final String fieldId;

  @override
  State<WSeasonSection> createState() => _WSeasonSectionState();
}

class _WSeasonSectionState extends State<WSeasonSection> {
  late final _seasons = LoadCubit<List<Map<String, dynamic>>>(
    () =>
        context.read<WorkspaceDeps>().fields.fetchFieldSeasons(widget.fieldId),
  )..load();

  @override
  void dispose() {
    _seasons.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      BlocBuilder<SeasonWorkspaceCubit, LoadState<Map<String, dynamic>>>(
        builder: (context, ws) {
          final cubit = context.read<SeasonWorkspaceCubit>();
          return RefreshIndicator(
            onRefresh: () => Future.wait([cubit.refresh(), _seasons.refresh()]),
            child: ListView(
              padding: const EdgeInsets.all(SahoolSpacing.page),
              children: [
                WSectionCard(
                  title: 'الموسم النشط',
                  icon: Icons.calendar_month_outlined,
                  child: LoadStateView<Map<String, dynamic>>(
                    state: ws,
                    onRetry: cubit.load,
                    builder: (context, d) => _activeSeason(context, d),
                  ),
                ),
                WSectionCard(
                  title: 'جاهزيّة بيانات الموسم',
                  icon: Icons.fact_check_outlined,
                  child: LoadStateView<Map<String, dynamic>>(
                    state: ws,
                    onRetry: cubit.load,
                    builder: (context, d) => _readiness(context, d),
                  ),
                ),
                WSectionCard(
                  title: 'التوصيات',
                  icon: Icons.recommend_outlined,
                  child: LoadStateView<Map<String, dynamic>>(
                    state: ws,
                    onRetry: cubit.load,
                    builder: (context, d) => _recommendations(context, d),
                  ),
                ),
                WSectionCard(
                  title: 'تاريخ المواسم',
                  icon: Icons.history_rounded,
                  child: InlineLoadView<List<Map<String, dynamic>>>(
                    cubit: _seasons,
                    builder: (context, list) => list.isEmpty
                        ? Text(
                            'لا مواسم مسجّلة لهذا الحقل بعد.',
                            style: context.textStyles.bodyMedium,
                          )
                        : Column(
                            children: [
                              for (final s in list) _seasonTile(context, s),
                            ],
                          ),
                  ),
                ),
                SecondaryButton(
                  icon: Icons.edit_calendar_outlined,
                  label: 'إدارة المواسم والمراحل',
                  onPressed: () => openFeatureRoute<void>(
                    context,
                    CrossFeatureRoutes.cropSeason,
                    query: {'field_id': widget.fieldId},
                  ),
                ),
              ],
            ),
          );
        },
      );

  Widget _activeSeason(BuildContext context, Map<String, dynamic> d) {
    final s = wMap(d['active_season']);
    if (s.isEmpty) {
      return Text(
        'لا موسم نشط لهذا الحقل الآن.',
        key: const ValueKey('no_active_season'),
        style: context.textStyles.bodyMedium,
      );
    }
    final status = wText(s['status'], '');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(cropsText(s['crops']), style: context.textStyles.titleMedium),
        if (status.isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.xs),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: StatusChip(
              key: const ValueKey('season_status'),
              label: kSeasonStatusAr[status] ?? status,
              tone: seasonTone(status),
            ),
          ),
        ],
        WInfoRow('الصنف', wText(s['cultivar'])),
        WInfoRow('تاريخ الزراعة', fmtDay(s['sowing_date'])),
        WInfoRow('نهاية الموسم', fmtDay(s['season_end'])),
        WInfoRow(
          'الإنتاجيّة المستهدفة',
          fmtYieldKgHa(wNum(s['target_yield_kg_ha'])),
        ),
      ],
    );
  }

  Widget _readiness(BuildContext context, Map<String, dynamic> d) {
    final r = wMap(d['readiness']);
    final score = wNum(r['score']);
    final missing = wList(r['missing']);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          score == null ? kNotMeasured : fmtPct(score),
          key: const ValueKey('readiness_score'),
          style: context.textStyles.headlineSmall,
        ),
        if (score != null) ...[
          const SizedBox(height: SahoolSpacing.xs),
          LinearProgressIndicator(value: (score / 100).clamp(0, 1).toDouble()),
        ],
        if (wText(r['label_ar'], '').isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.sm),
          Text(wText(r['label_ar']), style: context.textStyles.bodyMedium),
        ],
        for (final m in missing)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: Icon(
              Icons.warning_amber_rounded,
              color: context.tokens.warning,
            ),
            title: Text(wText(m['label_ar'], 'بيان ناقص')),
            subtitle: wText(m['action_ar'], '').isEmpty
                ? null
                : Text(wText(m['action_ar'])),
          ),
        for (final g in wList(d['gaps']))
          Padding(
            padding: const EdgeInsets.only(top: SahoolSpacing.xs),
            child: Text(
              '• ${wText(g['message_ar'] ?? g['message'], 'مصدر غير مكتمل')}',
              style: context.textStyles.bodySmall,
            ),
          ),
      ],
    );
  }

  Widget _recommendations(BuildContext context, Map<String, dynamic> d) {
    final recs = wMap(d['recommendations']);
    final list = wList(recs['recommendations']);
    if (list.isEmpty) {
      return Text(
        'لا توصيات قابلة للعرض حاليّاً.',
        style: context.textStyles.bodyMedium,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (recs['requires_review'] == true)
          Padding(
            padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
            child: StatusChip(
              label: 'تحتاج مراجعة قبل التنفيذ',
              tone: StatusTone.warning,
            ),
          ),
        for (final r in list.take(5))
          ListTile(
            contentPadding: EdgeInsets.zero,
            title: Text(
              wText(r['title_ar'] ?? r['title'] ?? r['kind'], 'توصية'),
            ),
            subtitle: Text(
              wText(r['rationale_ar'] ?? r['action_ar'] ?? r['message_ar']),
            ),
          ),
      ],
    );
  }

  Widget _seasonTile(BuildContext context, Map<String, dynamic> s) {
    final status = wText(s['status'], '');
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(cropsText(s['crops'])),
      subtitle: Text(
        [
          'الزراعة ${fmtDay(s['sowing_date'])}',
          if (s['season_end'] != null) 'النهاية ${fmtDay(s['season_end'])}',
        ].join(' · '),
      ),
      trailing: status.isEmpty
          ? null
          : StatusChip(
              label: kSeasonStatusAr[status] ?? status,
              tone: seasonTone(status),
            ),
    );
  }
}
