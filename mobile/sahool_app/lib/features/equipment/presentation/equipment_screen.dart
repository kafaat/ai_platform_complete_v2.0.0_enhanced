// SAHOOL — features/equipment/presentation/equipment_screen.dart
// المعدّات: الأسطول بحالته (تعمل / في الصيانة / معطّلة / خارج الخدمة) وساعات
// تشغيله، تصفية بالحالة، وفتح تفاصيل المعدّة وسجلّ صيانتها. عبر
// /api/v1/equipment/* (equipment:view للعرض، equipment:manage — المالك/المدير —
// للإضافة والصيانة). لا بيانات مُلفَّقة. تقابل EquipmentPage في الويب.
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
import 'package:sahool_app/features/operations_hub/presentation/widgets/ops_refresh_banner.dart';
import 'package:sahool_app/features/operations_hub/presentation/widgets/ops_tile.dart';

import 'equipment_cubit.dart';
import 'equipment_detail_screen.dart';
import 'equipment_sheets.dart';

StatusTone equipmentStatusTone(String status) => switch (status) {
  'operational' => StatusTone.success,
  'maintenance' => StatusTone.warning,
  'broken' => StatusTone.danger,
  _ => StatusTone.neutral,
};

IconData equipmentStatusIcon(String status) => switch (status) {
  'operational' => Icons.check_circle_outline_rounded,
  'maintenance' => Icons.build_circle_outlined,
  'broken' => Icons.report_problem_outlined,
  'retired' => Icons.do_not_disturb_on_outlined,
  _ => Icons.help_outline_rounded,
};

IconData equipmentTypeIcon(String type) => switch (type) {
  'tractor' => Icons.agriculture_outlined,
  'pump' => Icons.water_outlined,
  'harvester' => Icons.grass_outlined,
  'sprayer' => Icons.shower_outlined,
  _ => Icons.precision_manufacturing_outlined,
};

StatusChip equipmentStatusChip(Equipment e) => StatusChip(
  label: e.statusLabel,
  tone: equipmentStatusTone(e.status),
  icon: equipmentStatusIcon(e.status),
);

String fmtHours(num? hours) =>
    hours == null ? kNotMeasured : '${fmtNumber(hours, decimals: 1)} ساعة';

class EquipmentScreen extends StatelessWidget {
  const EquipmentScreen({
    super.key,
    this.api,
    this.role,
    this.outbox,
    this.clock,
  });

  final EquipmentApi? api;
  final AppRole? role;
  final OfflineOutbox? outbox;
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context) {
    final a = api ?? EquipmentApi.instance;
    return BlocProvider(
      create: (_) => EquipmentCubit(a, clock: clock)..load(),
      child: _EquipmentView(
        api: a,
        role: role ?? normalizeRole(currentRole()),
        outbox: outbox,
        clock: clock ?? DateTime.now,
      ),
    );
  }
}

class _EquipmentView extends StatelessWidget {
  const _EquipmentView({
    required this.api,
    required this.role,
    required this.outbox,
    required this.clock,
  });

  final EquipmentApi api;
  final AppRole role;
  final OfflineOutbox? outbox;
  final DateTime Function() clock;

  // equipment:manage للمالك/المدير فقط (core/authorization.py).
  bool get _canManage => canManage(role.name);

  Future<void> _add(BuildContext context) async {
    final cubit = context.read<EquipmentCubit>();
    final result = await showAppBottomSheet<EquipmentWriteResult>(
      context,
      builder: (_) => AddEquipmentSheet(api: api, today: clock()),
    );
    if (!context.mounted || result == null) return;
    showSnack(context, equipmentResultMessage(result, 'سُجّلت المعدّة'));
    await cubit.load();
  }

  Future<void> _open(BuildContext context, Equipment e) async {
    final cubit = context.read<EquipmentCubit>();
    final changed = await Navigator.of(context).push<bool>(
      MaterialPageRoute(
        settings: const RouteSettings(name: '/equipment/detail'),
        builder: (_) => EquipmentDetailScreen(
          equipmentId: e.id,
          initial: e,
          api: api,
          role: role,
          outbox: outbox,
          clock: clock,
        ),
      ),
    );
    if (changed == true) await cubit.load();
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.watch<EquipmentCubit>();
    final state = cubit.state;
    return AppScaffold(
      title: 'المعدّات',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: state is EquipmentLoading ? null : cubit.load,
        ),
      ],
      floatingActionButton: _canManage && state is EquipmentLoaded
          ? AppFab(
              heroKey: '/equipment',
              label: 'معدّة جديدة',
              icon: Icons.add_rounded,
              onPressed: () => _add(context),
            )
          : null,
      body: switch (state) {
        EquipmentLoading() => const LoadingState(
          message: 'جارٍ تحميل المعدّات…',
        ),
        EquipmentFailed(:final error) => ErrorState(
          error: error,
          onRetry: cubit.load,
        ),
        EquipmentLoaded() => RefreshIndicator(
          onRefresh: cubit.load,
          child: _loaded(context, cubit, state),
        ),
      },
    );
  }

  Widget _loaded(
    BuildContext context,
    EquipmentCubit cubit,
    EquipmentLoaded s,
  ) {
    final banner = s.refreshError == null
        ? null
        : OpsRefreshBanner(
            error: s.refreshError!,
            fetchedAt: s.fetchedAt,
            now: clock(),
          );
    if (s.equipment.isEmpty) {
      return CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (banner != null) SliverToBoxAdapter(child: banner),
          SliverFillRemaining(
            child: EmptyState(
              icon: Icons.precision_manufacturing_outlined,
              title: 'لا توجد معدّات مسجّلة بعد',
              message: _canManage
                  ? 'سجّل الجرّارات والمضخّات والرشّاشات لتتبّع حالتها وصيانتها.'
                  : 'لم يسجّل المالك أو المدير أيّ معدّة بعد.',
              actionLabel: _canManage ? 'سجّل أوّل معدّة' : null,
              onAction: _canManage ? () => _add(context) : null,
            ),
          ),
        ],
      );
    }
    final visible = s.visible;
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsetsDirectional.only(bottom: 96),
      children: [
        if (banner != null) banner,
        Padding(
          padding: const EdgeInsetsDirectional.fromSTEB(
            SahoolSpacing.md,
            SahoolSpacing.md,
            SahoolSpacing.md,
            0,
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final st in const ['operational', 'maintenance', 'broken'])
                Expanded(
                  child: MetricTile(
                    label: kEquipmentStatuses[st]!,
                    value: s.count(st),
                    decimals: 0,
                    icon: equipmentStatusIcon(st),
                  ),
                ),
            ],
          ),
        ),
        SizedBox(
          height: SahoolSizes.minTouchTarget + SahoolSpacing.md,
          child: ListView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: SahoolSpacing.lg,
              vertical: SahoolSpacing.xs,
            ),
            children: [
              ChoiceChip(
                label: const Text('الكلّ'),
                selected: s.status == null,
                onSelected: (_) => cubit.setStatus(null),
              ),
              for (final e in kEquipmentStatuses.entries) ...[
                const SizedBox(width: SahoolSpacing.sm),
                ChoiceChip(
                  label: Text(e.value),
                  selected: s.status == e.key,
                  onSelected: (sel) => cubit.setStatus(sel ? e.key : null),
                ),
              ],
            ],
          ),
        ),
        if (visible.isEmpty)
          Padding(
            padding: const EdgeInsets.all(SahoolSpacing.xl),
            child: Text(
              'لا معدّات بهذه الحالة.',
              textAlign: TextAlign.center,
              style: context.textStyles.bodyLarge?.copyWith(
                color: context.tokens.muted,
              ),
            ),
          )
        else
          for (final e in visible)
            Card(
              margin: const EdgeInsetsDirectional.symmetric(
                horizontal: SahoolSpacing.lg,
                vertical: SahoolSpacing.xs,
              ),
              child: OpsTile(
                key: ValueKey('equipment:${e.id}'),
                title: e.name.isEmpty ? '—' : e.name,
                subtitle:
                    '${e.typeLabel} · ساعات التشغيل: ${fmtHours(e.operatingHours)}',
                icon: equipmentTypeIcon(e.type),
                iconColor: context.colors.primary,
                chips: [equipmentStatusChip(e)],
                onTap: () => _open(context, e),
              ),
            ),
      ],
    );
  }
}
