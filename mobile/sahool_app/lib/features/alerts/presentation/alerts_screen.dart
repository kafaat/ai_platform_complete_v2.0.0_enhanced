// SAHOOL — features/alerts/presentation/alerts_screen.dart
// صندوق التنبيهات (وتنبيهات حقل واحد حين يُمرَّر fieldId). مرآة سلوك الويب
// AlertSystemPage.tsx: ترشيح بالخطورة، إخفاء المُقَرّة افتراضيّاً، إقرار مُحكَم
// بالدور، وإدراج حيّ من قناة الإشعارات.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/routing/app_navigator.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/services/websocket_service.dart';

import '../alerts_paths.dart';
import '../data/alert_models.dart';
import '../data/alerts_api.dart';
import '../data/alerts_unread.dart';
import 'alert_detail_screen.dart';
import 'alert_tile.dart';
import 'alert_visuals.dart';
import 'alerts_cubit.dart';
import 'field_alerts_cubit.dart';

class AlertsScreen extends StatelessWidget {
  const AlertsScreen({
    super.key,
    this.fieldId,
    this.api,
    this.events,
    this.counter,
    this.role,
  });

  final String? fieldId;
  final AlertsApi? api;
  final Stream<WsEvent>? events;
  final AlertsUnreadCounter? counter;

  /// للاختبار؛ الافتراضيّ دور الجلسة.
  final String? role;

  @override
  Widget build(BuildContext context) {
    final a = api ?? AlertsApi.instance;
    final fid = fieldId;
    return MultiBlocProvider(
      providers: [
        BlocProvider(
          create: (_) =>
              AlertsCubit(a, fieldId: fid, events: events, counter: counter)
                ..load(),
        ),
        if (fid != null)
          BlocProvider(create: (_) => FieldAlertsCubit(a, fid)..loadDerived()),
      ],
      child: _AlertsView(fieldId: fid, api: a, canAct: canActOnAlerts(role)),
    );
  }
}

class _AlertsView extends StatelessWidget {
  const _AlertsView({
    required this.fieldId,
    required this.api,
    required this.canAct,
  });
  final String? fieldId;
  final AlertsApi api;
  final bool canAct;

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<AlertsCubit>();
    return BlocListener<AlertsCubit, AlertsState>(
      listenWhen: (a, b) => a.messageSeq != b.messageSeq && b.message != null,
      listener: (context, s) => ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(s.message!))),
      child: AppScaffold(
        title: fieldId == null ? 'التنبيهات' : 'تنبيهات الحقل',
        actions: [
          AppIconButton(
            icon: Icons.tune_rounded,
            tooltip: 'تفضيلات الإشعار',
            onPressed: () => context.openRoute<void>(AlertsPaths.preferences),
          ),
        ],
        onRefresh: () async {
          await cubit.refresh();
          if (context.mounted && fieldId != null) {
            await context.read<FieldAlertsCubit>().loadDerived();
          }
        },
        body: BlocBuilder<AlertsCubit, AlertsState>(
          builder: (context, s) {
            switch (s.status) {
              case AlertsStatus.loading:
                return const LoadingState(message: 'جارٍ تحميل التنبيهات…');
              case AlertsStatus.failed:
                return ErrorState(
                  title: 'تعذّر تحميل التنبيهات',
                  error: s.error!,
                  onRetry: cubit.load,
                );
              case AlertsStatus.ready:
                return _list(context, s);
            }
          },
        ),
      ),
    );
  }

  Widget _list(BuildContext context, AlertsState s) {
    final cubit = context.read<AlertsCubit>();
    final visible = s.visible;
    final children = <Widget>[
      if (fieldId != null)
        _FieldSection(canAct: canAct, onCreated: cubit.refresh),
      _SeverityFilter(state: s, onSelect: cubit.setSeverity),
      SwitchListTile(
        title: const Text('إظهار المُقَرّة والمحلولة'),
        value: s.showAcknowledged,
        onChanged: cubit.setShowAcknowledged,
      ),
      if (s.pageFull)
        Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.lg,
          ),
          child: Text(
            'تُعرَض أحدث ${AlertsApi.pageSize} تنبيه فقط — الأقدم غير محمّلة.',
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
      if (fieldId != null)
        const ListSectionHeader('التنبيهات المخزّنة لهذا الحقل'),
      if (visible.isEmpty)
        Padding(
          padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.xl),
          child: EmptyState(
            icon: Icons.notifications_off_outlined,
            title: s.alerts.isEmpty ? 'لا تنبيهات' : null,
            message: s.alerts.isEmpty
                ? 'لا توجد تنبيهات مسجّلة${fieldId == null ? '' : ' لهذا الحقل'}.'
                : 'لا تنبيهات نشطة مطابقة للمرشّح.',
          ),
        )
      else
        for (final a in visible)
          Padding(
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: SahoolSpacing.md,
              vertical: SahoolSpacing.xs,
            ),
            child: AlertTile(
              alert: a,
              showField: fieldId == null,
              acknowledging: s.acking.contains(a.alertId),
              onAcknowledge: canAct ? () => cubit.acknowledge(a.alertId) : null,
              onTap: () => _openDetail(context, a),
            ),
          ),
      const SizedBox(height: SahoolSpacing.xl),
    ];
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      children: children,
    );
  }

  Future<void> _openDetail(BuildContext context, AlertItem a) async {
    final cubit = context.read<AlertsCubit>();
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        builder: (_) => AlertDetailScreen(
          alertId: a.alertId,
          initial: a,
          api: api,
          canAct: canAct,
        ),
      ),
    );
    if (changed == true && !cubit.isClosed) await cubit.refresh();
  }
}

class _SeverityFilter extends StatelessWidget {
  const _SeverityFilter({required this.state, required this.onSelect});
  final AlertsState state;
  final ValueChanged<AlertSeverity?> onSelect;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.fromSTEB(
      SahoolSpacing.md,
      SahoolSpacing.md,
      SahoolSpacing.md,
      0,
    ),
    child: Wrap(
      spacing: SahoolSpacing.sm,
      runSpacing: SahoolSpacing.sm,
      children: [
        ChoiceChip(
          label: Text('الكلّ (${state.activeTotal})'),
          selected: state.severity == null,
          onSelected: (_) => onSelect(null),
          materialTapTargetSize: MaterialTapTargetSize.padded,
        ),
        for (final sev in AlertSeverity.filterable)
          ChoiceChip(
            avatar: Icon(severityIcon(sev), size: SahoolSizes.iconSm),
            label: Text('${sev.labelAr} (${state.activeCount(sev)})'),
            selected: state.severity == sev,
            onSelected: (_) => onSelect(sev),
            materialTapTargetSize: MaterialTapTargetSize.padded,
          ),
      ],
    ),
  );
}

/// قسم الحقل: المشتقّة من الحالة القانونيّة + زرّ التقييم.
class _FieldSection extends StatelessWidget {
  const _FieldSection({required this.canAct, required this.onCreated});
  final bool canAct;
  final Future<void> Function() onCreated;

  @override
  Widget build(BuildContext context) =>
      BlocBuilder<FieldAlertsCubit, FieldAlertsState>(
        builder: (context, s) {
          final cubit = context.read<FieldAlertsCubit>();
          final t = context.tokens;
          Widget derived;
          if (s.loading) {
            derived = const Padding(
              padding: EdgeInsets.all(SahoolSpacing.md),
              child: LinearProgressIndicator(),
            );
          } else if (s.error != null) {
            derived = Text(
              'تعذّر اشتقاق تنبيهات الحقل: ${s.error!.messageAr}',
              style: context.textStyles.bodyMedium?.copyWith(color: t.danger),
            );
          } else if (s.derived.isEmpty) {
            derived = Text(
              'لا تنبيهات مشتقّة — الحالة القانونيّة لا تُظهر خطراً معروفاً.',
              style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
            );
          } else {
            derived = Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final d in s.derived)
                  Padding(
                    padding: const EdgeInsets.only(bottom: SahoolSpacing.sm),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            severityChip(d.severity),
                            const SizedBox(width: SahoolSpacing.sm),
                            Expanded(
                              child: Text(
                                d.displayTitle,
                                style: context.textStyles.titleSmall,
                              ),
                            ),
                          ],
                        ),
                        if (d.messageAr != null)
                          Padding(
                            padding: const EdgeInsets.only(
                              top: SahoolSpacing.xs,
                            ),
                            child: Text(
                              d.messageAr!,
                              style: context.textStyles.bodyMedium,
                            ),
                          ),
                      ],
                    ),
                  ),
              ],
            );
          }
          return Padding(
            padding: const EdgeInsets.all(SahoolSpacing.md),
            child: SectionCard(
              title: 'من الحالة القانونيّة للحقل',
              icon: Icons.fact_check_outlined,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  derived,
                  if (canAct) ...[
                    const SizedBox(height: SahoolSpacing.md),
                    PrimaryButton(
                      label: 'تقييم الحقل الآن',
                      icon: Icons.play_arrow_rounded,
                      loading: s.evaluating,
                      onPressed: () async {
                        final created = await cubit.evaluate();
                        if (created) await onCreated();
                      },
                    ),
                  ],
                  if (s.evalNote != null) ...[
                    const SizedBox(height: SahoolSpacing.sm),
                    Text(
                      s.evalNote!,
                      style: context.textStyles.bodyMedium?.copyWith(
                        color: s.evalFailed ? t.danger : t.success,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        },
      );
}
