// SAHOOL — features/fields/presentation/workspace/overview_section.dart
// تبويب «نظرة عامّة»: رأس الحقل، المقاييس الأساسيّة، آخر NDVI، شريط الطقس،
// الإجراءات السريعة (كشف · نشاط · ريّ · المستشار)، ما يجب فعله الآن، والحالة
// الموحّدة. صدق: كلّ رقم من الخادم أو «غير مقيس» — لا 0 تنبيهات ولا 0٪ جاهزيّة
// افتراضيّة، ولا «بيانات ناقصة» تُنسب للخادم حين لم يرسل شيئاً.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/satellite/data/satellite_models.dart';

import '../common/cross_feature_routes.dart';
import '../common/field_labels.dart';
import '../common/load_cubit.dart';
import 'activity_form_sheet.dart';
import 'workspace_deps.dart';
import 'workspace_widgets.dart';

const Map<String, String> kValidityAr = {
  'valid': 'صالحة',
  'degraded': 'متدهورة',
  'conflicted': 'متعارضة',
  'invalid': 'غير صالحة',
  'insufficient': 'بيانات ناقصة',
};
const Map<String, String> kExecutionModeAr = {
  'auto': 'تلقائيّ',
  'human_review': 'يحتاج مراجعة بشريّة',
  'blocked': 'محجوب',
};
const Map<String, String> kUrgencyAr = {
  'none': 'لا حاجة للريّ',
  'low': 'ريّ منخفض الإلحاح',
  'moderate': 'ريّ متوسّط الإلحاح',
  'high': 'ريّ عاجل',
};

class WOverviewSection extends StatefulWidget {
  const WOverviewSection({
    super.key,
    required this.fieldId,
    required this.field,
    this.role,
  });

  final String fieldId;
  final Map<String, dynamic> field;
  final AppRole? role;

  @override
  State<WOverviewSection> createState() => _WOverviewSectionState();
}

class _WOverviewSectionState extends State<WOverviewSection> {
  late final WorkspaceDeps _deps = context.read<WorkspaceDeps>();
  late final _priority = LoadCubit<Map<String, dynamic>>(
    () => _deps.fields.fetchFieldPriorityQueue(widget.fieldId),
  )..load();
  late final _ndvi = LoadCubit<IndicatorSnapshot>(
    () => _deps.satellite.getIndicatorSnapshot(widget.fieldId),
  )..load();
  late final _disease = LoadCubit<Map<String, dynamic>>(
    () => _deps.fields.fetchDiseaseRisk(widget.fieldId),
  )..load();
  late final _advice = LoadCubit<Map<String, dynamic>>(
    () => _deps.fields.fetchIrrigationAdvice(widget.fieldId),
  )..load();

  AppRole get _role => widget.role ?? normalizeRole(currentRole());

  @override
  void dispose() {
    _priority.close();
    _ndvi.close();
    _disease.close();
    _advice.close();
    super.dispose();
  }

  Future<void> _refresh() => Future.wait([
    context.read<SeasonWorkspaceCubit>().refresh(),
    _priority.refresh(),
    _ndvi.refresh(),
    _disease.refresh(),
    _advice.refresh(),
  ]);

  Future<void> _logActivity() async {
    if (routeExists(CrossFeatureRoutes.activityNew)) {
      await openFeatureRoute<void>(
        context,
        CrossFeatureRoutes.activityNew,
        query: {'field_id': widget.fieldId},
      );
      return;
    }
    final messenger = ScaffoldMessenger.of(context);
    final saved = await showActivityFormSheet(
      context,
      fieldId: widget.fieldId,
      api: _deps.fields,
    );
    if (saved) {
      messenger.showSnackBar(
        const SnackBar(content: Text('سُجّل النشاط في سجلّ الحقل')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final editor = canMutate(_role.name);
    final q = {'field_id': widget.fieldId};
    return RefreshIndicator(
      onRefresh: _refresh,
      child: ListView(
        padding: const EdgeInsets.all(SahoolSpacing.page),
        children: [
          WorkspaceHeader(field: widget.field),
          _metrics(),
          const SizedBox(height: SahoolSpacing.md),
          _ndviCard(),
          _weatherStrip(),
          WSectionCard(
            title: 'إجراءات سريعة',
            icon: Icons.bolt_rounded,
            child: AdaptiveTileGrid(
              minTileWidth: 140,
              children: [
                if (editor)
                  QuickActionButton(
                    key: const ValueKey('qa_scout'),
                    icon: Icons.pest_control_outlined,
                    label: 'كشف ميدانيّ',
                    onPressed: () => openFeatureRoute<void>(
                      context,
                      CrossFeatureRoutes.scoutingNew,
                      query: q,
                    ),
                  ),
                if (editor)
                  QuickActionButton(
                    key: const ValueKey('qa_activity'),
                    icon: Icons.edit_note_rounded,
                    label: 'تسجيل نشاط',
                    onPressed: _logActivity,
                  ),
                if (editor)
                  QuickActionButton(
                    key: const ValueKey('qa_irrigate'),
                    icon: Icons.water_drop_outlined,
                    label: 'الريّ',
                    onPressed: () => openFeatureRoute<void>(
                      context,
                      CrossFeatureRoutes.irrigation,
                      query: q,
                    ),
                  ),
                QuickActionButton(
                  key: const ValueKey('qa_advisor'),
                  icon: Icons.psychology_outlined,
                  label: 'اسأل المستشار',
                  onPressed: () => openFeatureRoute<void>(
                    context,
                    CrossFeatureRoutes.advisor,
                    query: q,
                  ),
                ),
              ],
            ),
          ),
          _nextActions(),
          _canonicalState(),
        ],
      ),
    );
  }

  Widget _metrics() =>
      BlocBuilder<SeasonWorkspaceCubit, LoadState<Map<String, dynamic>>>(
        builder: (context, ws) =>
            BlocBuilder<
              LoadCubit<Map<String, dynamic>>,
              LoadState<Map<String, dynamic>>
            >(
              bloc: _priority,
              builder: (context, pq) {
                String? caption(LoadState<Object?> s) => switch (s) {
                  LoadLoading() => 'جارٍ التحميل',
                  LoadFailed() => 'تعذّر التحميل',
                  _ => null,
                };
                final data = switch (ws) {
                  LoadLoaded(:final data) => data,
                  _ => const <String, dynamic>{},
                };
                final season = wMap(data['active_season']);
                final sown = parseDate(season['sowing_date']);
                final days = sown == null
                    ? null
                    : DateTime.now().difference(sown.toLocal()).inDays;
                final score = wNum(wMap(data['readiness'])['score']);
                final items = switch (pq) {
                  LoadLoaded(:final data) =>
                    data['items'] is List
                        ? (data['items'] as List).length
                        : null,
                  _ => null,
                };
                return AdaptiveTileGrid(
                  children: [
                    MetricTile(
                      key: const ValueKey('metric_area'),
                      label: 'المساحة',
                      value: areaOf(widget.field),
                      unit: 'هـ',
                      icon: Icons.straighten_rounded,
                    ),
                    MetricTile(
                      key: const ValueKey('metric_days'),
                      label: 'أيّام منذ الزراعة',
                      value: days,
                      unit: 'يوم',
                      decimals: 0,
                      icon: Icons.calendar_month_outlined,
                      caption:
                          caption(ws) ??
                          (season.isEmpty ? 'لا موسم نشط' : null),
                    ),
                    MetricTile(
                      key: const ValueKey('metric_readiness'),
                      label: 'جاهزيّة البيانات',
                      value: score,
                      unit: '٪',
                      decimals: 0,
                      icon: Icons.fact_check_outlined,
                      caption: caption(ws),
                    ),
                    MetricTile(
                      key: const ValueKey('metric_open_items'),
                      label: 'تنبيهات ومهامّ مفتوحة',
                      value: items,
                      decimals: 0,
                      icon: Icons.notifications_active_outlined,
                      caption: caption(pq),
                    ),
                  ],
                );
              },
            ),
      );

  Widget _ndviCard() => WSectionCard(
    title: 'آخر NDVI',
    icon: Icons.eco_outlined,
    child: InlineLoadView<IndicatorSnapshot>(
      cubit: _ndvi,
      builder: (context, snap) {
        final v = snap.reading('ndvi')?.value;
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: SahoolSpacing.md,
              runSpacing: SahoolSpacing.sm,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  v == null ? kNotMeasured : fmtNumber(v, decimals: 2),
                  key: const ValueKey('overview_ndvi'),
                  style: context.textStyles.headlineSmall,
                ),
                if (snap.health != null)
                  StatusChip(
                    label: snap.health!.labelAr,
                    tone: healthTone(snap.health!.status),
                  ),
              ],
            ),
            if (snap.observedAt != null)
              Text(
                'آخر بيانات: ${fmtDateTime(snap.observedAt)}',
                style: context.textStyles.bodySmall,
              ),
          ],
        );
      },
    ),
  );

  Widget _weatherStrip() => WSectionCard(
    title: 'الطقس والإرشاد اليوم',
    icon: Icons.wb_sunny_outlined,
    child: Wrap(
      spacing: SahoolSpacing.sm,
      runSpacing: SahoolSpacing.sm,
      children: [
        InlineLoadView<Map<String, dynamic>>(
          cubit: _disease,
          builder: (context, d) => Wrap(
            spacing: SahoolSpacing.sm,
            runSpacing: SahoolSpacing.sm,
            children: [
              StatusChip(
                icon: Icons.thermostat_rounded,
                label: 'الحرارة ${fmtTempC(wNum(d['temperature_c']))}',
              ),
              StatusChip(
                icon: Icons.water_outlined,
                label: 'الرطوبة ${fmtPct(wNum(d['humidity_pct']))}',
              ),
              if (wText(d['risk_level'], '').isNotEmpty)
                StatusChip(
                  label:
                      'خطر الأمراض ${kSeverityAr[d['risk_level']] ?? (d['risk_level'] == 'moderate' ? 'متوسّط' : wText(d['risk_level']))}',
                  tone: severityTone('${d['risk_level']}'),
                ),
            ],
          ),
        ),
        InlineLoadView<Map<String, dynamic>>(
          cubit: _advice,
          builder: (context, a) {
            final urgency = wText(a['urgency'], '');
            final mm = wNum(a['recommended_mm']);
            if (urgency.isEmpty && mm == null) return const SizedBox.shrink();
            return StatusChip(
              icon: Icons.water_drop_outlined,
              label: [
                kUrgencyAr[urgency] ?? urgency,
                if (mm != null && mm > 0) fmtMm(mm),
              ].where((s) => s.isNotEmpty).join(' · '),
              tone: switch (urgency) {
                'high' => StatusTone.danger,
                'moderate' => StatusTone.warning,
                'low' => StatusTone.info,
                _ => StatusTone.neutral,
              },
            );
          },
        ),
      ],
    ),
  );

  Widget _nextActions() =>
      BlocBuilder<SeasonWorkspaceCubit, LoadState<Map<String, dynamic>>>(
        builder: (context, ws) => WSectionCard(
          title: 'ما يجب فعله الآن',
          icon: Icons.playlist_add_check_rounded,
          child: LoadStateView<Map<String, dynamic>>(
            state: ws,
            onRetry: context.read<SeasonWorkspaceCubit>().load,
            builder: (context, data) {
              final actions = wList(data['next_actions']);
              if (actions.isEmpty) {
                return Text(
                  'لا إجراءات فوريّة مسجّلة لهذا الحقل.',
                  style: context.textStyles.bodyMedium,
                );
              }
              return Column(
                children: [
                  for (final a in actions.take(5))
                    ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: Icon(
                        a['type'] == 'data_gap'
                            ? Icons.warning_amber_rounded
                            : (a['type'] == 'task'
                                  ? Icons.task_alt_rounded
                                  : Icons.recommend_outlined),
                        color: a['type'] == 'data_gap'
                            ? context.tokens.warning
                            : context.tokens.muted,
                      ),
                      title: Text(wText(a['title_ar'], 'إجراء')),
                      subtitle: wText(a['action_ar'], '').isEmpty
                          ? null
                          : Text(wText(a['action_ar'])),
                    ),
                ],
              );
            },
          ),
        ),
      );

  Widget _canonicalState() =>
      BlocBuilder<SeasonWorkspaceCubit, LoadState<Map<String, dynamic>>>(
        builder: (context, ws) => WSectionCard(
          title: 'الحالة الموحّدة للحقل',
          icon: Icons.verified_outlined,
          child: LoadStateView<Map<String, dynamic>>(
            state: ws,
            onRetry: context.read<SeasonWorkspaceCubit>().load,
            builder: (context, data) {
              final s = wMap(data['canonical_state']);
              if (s.isEmpty) {
                return Text(
                  'لم تُحسب الحالة الموحّدة لهذا الحقل بعد ($kNotMeasured).',
                  style: context.textStyles.bodyMedium,
                );
              }
              final validity = wText(s['validity'], '');
              final exec = wText(s['execution_mode'], '');
              final reasons = (s['reasons_ar'] is List)
                  ? (s['reasons_ar'] as List).map((e) => '$e').toList()
                  : const <String>[];
              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  WInfoRow(
                    'صلاحيّة القرار',
                    validity.isEmpty
                        ? kNotMeasured
                        : (kValidityAr[validity] ?? validity),
                  ),
                  WInfoRow(
                    'نمط التنفيذ',
                    exec.isEmpty
                        ? kNotMeasured
                        : (kExecutionModeAr[exec] ?? exec),
                  ),
                  for (final r in reasons)
                    Padding(
                      padding: const EdgeInsets.only(top: SahoolSpacing.xs),
                      child: Text('• $r', style: context.textStyles.bodySmall),
                    ),
                ],
              );
            },
          ),
        ),
      );
}

/// رأس الحقل: الاسم (يلتفّ حتّى 3 أسطر ثمّ يُختصر — لا فيض)، المحصول
/// والمزرعة، وحالة البيانات.
class WorkspaceHeader extends StatelessWidget {
  const WorkspaceHeader({super.key, required this.field});
  final Map<String, dynamic> field;

  @override
  Widget build(BuildContext context) {
    final grade = wText(field['quality_grade'], '');
    final crop = cropOf(field);
    return WSectionCard(
      title: 'الحقل',
      icon: Icons.grass_outlined,
      child: Column(
        key: const ValueKey('workspace_header'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            fieldNameOf(field),
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
            style: context.textStyles.titleLarge,
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            [
              crop ?? 'بلا محصول مسجّل',
              if (wText(field['field_code'], '').isNotEmpty)
                'رمز ${wText(field['field_code'])}',
              if (wText(field['region'], '').isNotEmpty) wText(field['region']),
            ].join(' · '),
            style: context.textStyles.bodyMedium?.copyWith(
              color: context.tokens.muted,
            ),
          ),
          if (grade.isNotEmpty) ...[
            const SizedBox(height: SahoolSpacing.sm),
            StatusChip(
              label: kQualityGradeAr[grade] ?? grade,
              tone: qualityTone(grade),
            ),
          ],
        ],
      ),
    );
  }
}
