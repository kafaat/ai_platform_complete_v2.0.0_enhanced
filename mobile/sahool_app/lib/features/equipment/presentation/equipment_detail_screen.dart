// SAHOOL — features/equipment/presentation/equipment_detail_screen.dart
// تفاصيل معدّة: حالتها وساعات تشغيلها وتاريخ شرائها، جدول الصيانة القادمة
// (المتأخّرة مُعلَّمة) وسجلّ ما نُفّذ أو أُلغي، وتسجيل صيانة للمالك/المدير.
// رابط عميق: `/equipment/detail?equipment_id=eqp_…` (لا نقطة لقراءة معدّة واحدة
// على الخادم، فتُقرأ من القائمة).
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart' show showSnack;
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/equipment/data/equipment_api.dart';
import 'package:sahool_app/features/equipment/data/equipment_models.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import 'equipment_cubit.dart';
import 'equipment_screen.dart'
    show equipmentStatusChip, equipmentTypeIcon, fmtHours;
import 'equipment_sheets.dart';

IconData maintenanceKindIcon(String kind) => switch (kind) {
  'scheduled' => Icons.event_repeat_outlined,
  'repair' => Icons.build_outlined,
  'breakdown' => Icons.report_problem_outlined,
  'inspection' => Icons.fact_check_outlined,
  _ => Icons.handyman_outlined,
};

class EquipmentDetailScreen extends StatelessWidget {
  const EquipmentDetailScreen({
    super.key,
    required this.equipmentId,
    this.initial,
    this.api,
    this.role,
    this.outbox,
    this.clock,
  });

  final String equipmentId;
  final Equipment? initial;
  final EquipmentApi? api;
  final AppRole? role;
  final OfflineOutbox? outbox;
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context) {
    final a = api ?? EquipmentApi.instance;
    return BlocProvider(
      create: (_) => EquipmentDetailCubit(a, equipmentId, clock: clock)..load(),
      child: _DetailView(
        initial: initial,
        api: a,
        role: role ?? normalizeRole(currentRole()),
        outbox: outbox,
        clock: clock ?? DateTime.now,
      ),
    );
  }
}

class _DetailView extends StatefulWidget {
  const _DetailView({
    required this.initial,
    required this.api,
    required this.role,
    required this.outbox,
    required this.clock,
  });

  final Equipment? initial;
  final EquipmentApi api;
  final AppRole role;
  final OfflineOutbox? outbox;
  final DateTime Function() clock;

  @override
  State<_DetailView> createState() => _DetailViewState();
}

class _DetailViewState extends State<_DetailView> {
  bool _changed = false;

  bool get _canManage => canManage(widget.role.name);

  Future<void> _log(Equipment e) async {
    final cubit = context.read<EquipmentDetailCubit>();
    final result = await showAppBottomSheet<EquipmentWriteResult>(
      context,
      builder: (_) => LogMaintenanceSheet(
        api: widget.api,
        equipment: e,
        outbox: widget.outbox,
        today: widget.clock(),
      ),
    );
    if (!mounted || result == null) return;
    _changed = true;
    showSnack(context, equipmentResultMessage(result, 'سُجّلت الصيانة'));
    if (result == EquipmentWriteResult.saved) await cubit.load();
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.watch<EquipmentDetailCubit>();
    final state = cubit.state;
    final title = switch (state) {
      EquipmentDetailLoaded(:final equipment) => equipment.name,
      _ => widget.initial?.name ?? 'المعدّة',
    };
    return PopScope<bool>(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) Navigator.of(context).pop(_changed);
      },
      child: AppScaffold(
        title: title,
        actions: [
          AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث',
            onPressed: cubit.load,
          ),
        ],
        floatingActionButton: _canManage && state is EquipmentDetailLoaded
            ? AppFab(
                heroKey: '/equipment/detail',
                label: 'تسجيل صيانة',
                icon: Icons.add_rounded,
                onPressed: () => _log(state.equipment),
              )
            : null,
        body: switch (state) {
          EquipmentDetailLoading() => const LoadingState(),
          EquipmentDetailFailed(:final error) => ErrorState(
            error: error,
            onRetry: cubit.load,
          ),
          EquipmentDetailLoaded() => RefreshIndicator(
            onRefresh: cubit.load,
            child: _body(context, state),
          ),
        },
      ),
    );
  }

  Widget _body(BuildContext context, EquipmentDetailLoaded s) {
    final e = s.equipment;
    final t = context.tokens;
    final upcoming = s.upcoming;
    final history = s.history;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.lg,
        SahoolSpacing.lg,
        SahoolSpacing.lg,
        96,
      ),
      children: [
        if (s.refreshError != null) ...[
          OpsRefreshBanner(error: s.refreshError!),
          const SizedBox(height: SahoolSpacing.md),
        ],
        SectionCard(
          title: e.typeLabel,
          icon: equipmentTypeIcon(e.type),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              equipmentStatusChip(e),
              const SizedBox(height: SahoolSpacing.md),
              Text(
                'ساعات التشغيل: ${fmtHours(e.operatingHours)}',
                style: context.textStyles.bodyLarge,
              ),
              const SizedBox(height: SahoolSpacing.xs),
              Text(
                'تاريخ الشراء: '
                '${e.purchaseDate == null ? 'غير مسجّل' : fmtDate(e.purchaseDate)}',
                style: context.textStyles.bodyMedium,
              ),
            ],
          ),
        ),
        _SectionHeader(
          title: 'الصيانة القادمة',
          trailing: s.overdueCount > 0
              ? StatusChip(
                  label: '${s.overdueCount} متأخّرة',
                  tone: StatusTone.danger,
                  icon: Icons.schedule_rounded,
                )
              : null,
        ),
        Card(
          margin: EdgeInsets.zero,
          child: upcoming.isEmpty
              ? _EmptyLine('لا صيانة مخطّطة لهذه المعدّة.', color: t.muted)
              : Column(
                  children: [
                    for (final r in upcoming)
                      _RecordTile(record: r, now: s.now),
                  ],
                ),
        ),
        const _SectionHeader(title: 'سجلّ الصيانة'),
        Card(
          margin: EdgeInsets.zero,
          child: history.isEmpty
              ? _EmptyLine('لا سجلّات صيانة منفّذة بعد.', color: t.muted)
              : Column(
                  children: [
                    for (final r in history) _RecordTile(record: r, now: s.now),
                  ],
                ),
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, this.trailing});
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.only(
      top: SahoolSpacing.xl,
      bottom: SahoolSpacing.sm,
    ),
    child: Row(
      children: [
        Expanded(
          child: Semantics(
            header: true,
            child: Text(title, style: context.textStyles.titleMedium),
          ),
        ),
        if (trailing != null) trailing!,
      ],
    ),
  );
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine(this.text, {required this.color});
  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.all(SahoolSpacing.lg),
    child: Text(
      text,
      style: context.textStyles.bodyMedium?.copyWith(color: color),
    ),
  );
}

class _RecordTile extends StatelessWidget {
  const _RecordTile({required this.record, required this.now});
  final MaintenanceRecord record;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final r = record;
    final overdue = r.isOverdue(now);
    final parts = <String>[
      if (r.scheduledDate != null) 'الموعد: ${fmtDate(r.scheduledDate)}',
      if (r.performedDate != null) 'نُفّذت: ${fmtDate(r.performedDate)}',
      if (r.costUsd != null)
        'التكلفة: ${fmtNumber(r.costUsd, decimals: 2)} دولار',
    ];
    final notes = (r.notes ?? '').trim();
    return OpsTile(
      key: ValueKey('maintenance:${r.id}'),
      title: r.kindLabel,
      subtitle: [
        if (parts.isNotEmpty) parts.join(' · '),
        if (notes.isNotEmpty) notes,
      ].join('\n'),
      icon: maintenanceKindIcon(r.kind),
      iconColor: r.kind == 'breakdown' ? t.danger : context.colors.primary,
      chips: [
        StatusChip(
          label: r.statusLabel,
          tone: switch (r.status) {
            'done' => StatusTone.success,
            'cancelled' => StatusTone.neutral,
            _ => StatusTone.info,
          },
        ),
        if (overdue)
          const StatusChip(
            label: 'متأخّرة',
            tone: StatusTone.danger,
            icon: Icons.schedule_rounded,
          ),
      ],
    );
  }
}
