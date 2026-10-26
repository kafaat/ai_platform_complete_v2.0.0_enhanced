// SAHOOL — features/devices/presentation/devices_screen.dart
// أجهزة IoT: السجلّ بحالة الاتّصال (محسوبة خادميّاً من last_seen_at) وعمر آخر
// ظهور، صحّة الأسطول (الأجهزة الصامتة مرتّبة بالخطورة)، والحقل المرتبط، وفتح
// قراءات كلّ جهاز. عبر /api/v1/devices/* (device:view للعرض، device:manage —
// المالك/المدير — للتسجيل). مراقبة فقط: لا أوامر تشغيل للمشغّلات من التطبيق.
// لا قراءات مُلفَّقة. تقابل DevicesPage في الويب.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/state_views.dart' show showSnack;
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/devices/data/devices_api.dart';
import 'package:sahool_app/features/devices/data/devices_models.dart';
import 'package:sahool_app/features/operations_hub/presentation/widgets/ops_refresh_banner.dart';
import 'package:sahool_app/features/operations_hub/presentation/widgets/ops_tile.dart';

import 'device_detail_screen.dart';
import 'devices_cubit.dart';
import 'register_device_sheet.dart';

IconData deviceTypeIcon(String type) => switch (type) {
  'soil_moisture' => Icons.water_drop_outlined,
  'weather_station' => Icons.thermostat_outlined,
  'water_meter' => Icons.speed_outlined,
  'camera' => Icons.videocam_outlined,
  'actuator' => Icons.settings_input_component_outlined,
  _ => Icons.sensors,
};

/// حالة الاتّصال كرقاقة (لون + أيقونة + نصّ).
StatusChip deviceConnectionChip(Device d) {
  if (d.online) {
    return const StatusChip(
      label: 'متّصل',
      tone: StatusTone.success,
      icon: Icons.wifi_rounded,
    );
  }
  if (d.neverSeen) {
    return const StatusChip(
      label: 'لم يتّصل قطّ',
      tone: StatusTone.neutral,
      icon: Icons.portable_wifi_off_rounded,
    );
  }
  return const StatusChip(
    label: 'غير متّصل',
    tone: StatusTone.warning,
    icon: Icons.wifi_off_rounded,
  );
}

String lastSeenText(Device d, DateTime now) => d.lastSeenAt == null
    ? 'لم يُرسل أيّ قراءة بعد'
    : 'آخر ظهور ${fmtAge(d.lastSeenAt, now: now)}';

class DevicesScreen extends StatelessWidget {
  const DevicesScreen({
    super.key,
    this.api,
    this.role,
    this.fields,
    this.clock,
  });

  final DevicesApi? api;
  final AppRole? role;
  final FieldsLoader? fields;
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context) {
    final a = api ?? DevicesApi.instance;
    return BlocProvider(
      create: (_) => DevicesCubit(a, fields: fields, clock: clock)..load(),
      child: _DevicesView(
        api: a,
        role: role ?? normalizeRole(currentRole()),
        fields: fields,
        clock: clock ?? DateTime.now,
      ),
    );
  }
}

class _DevicesView extends StatelessWidget {
  const _DevicesView({
    required this.api,
    required this.role,
    required this.fields,
    required this.clock,
  });

  final DevicesApi api;
  final AppRole role;
  final FieldsLoader? fields;
  final DateTime Function() clock;

  // device:manage للمالك/المدير فقط (core/authorization.py).
  bool get _canManage => canManage(role.name);

  Future<void> _register(BuildContext context) async {
    final cubit = context.read<DevicesCubit>();
    final ok = await showAppBottomSheet<bool>(
      context,
      builder: (_) => RegisterDeviceSheet(api: api, fields: fields),
    );
    if (!context.mounted || ok != true) return;
    showSnack(context, 'سُجّل الجهاز');
    await cubit.load();
  }

  void _open(BuildContext context, Device d, DevicesLoaded s) {
    Navigator.of(context).push<void>(
      MaterialPageRoute(
        settings: const RouteSettings(name: '/devices/detail'),
        builder: (_) => DeviceDetailScreen(
          deviceId: d.id,
          device: d,
          fieldName: d.fieldId == null ? null : s.fieldNames?[d.fieldId],
          silent: s.fleet?.silentFor(d.id),
          api: api,
          clock: clock,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.watch<DevicesCubit>();
    final state = cubit.state;
    return AppScaffold(
      title: 'أجهزة الاستشعار',
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: state is DevicesLoading ? null : cubit.load,
        ),
      ],
      floatingActionButton: _canManage && state is DevicesLoaded
          ? AppFab(
              heroKey: '/devices',
              label: 'تسجيل جهاز',
              icon: Icons.add_rounded,
              onPressed: () => _register(context),
            )
          : null,
      body: switch (state) {
        DevicesLoading() => const LoadingState(message: 'جارٍ تحميل الأجهزة…'),
        DevicesFailed(:final error) => ErrorState(
          error: error,
          onRetry: cubit.load,
        ),
        DevicesLoaded() => RefreshIndicator(
          onRefresh: cubit.load,
          child: _loaded(context, state),
        ),
      },
    );
  }

  Widget _loaded(BuildContext context, DevicesLoaded s) {
    final now = clock();
    final banner = s.refreshError == null
        ? null
        : OpsRefreshBanner(
            error: s.refreshError!,
            fetchedAt: s.fetchedAt,
            now: now,
          );
    if (s.devices.isEmpty) {
      return CustomScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        slivers: [
          if (banner != null) SliverToBoxAdapter(child: banner),
          SliverFillRemaining(
            child: EmptyState(
              icon: Icons.sensors_off_outlined,
              title: 'لا أجهزة مسجّلة بعد',
              message: _canManage
                  ? 'سجّل حسّاسات الرطوبة ومحطّات الطقس وعدّادات الماء لترى '
                        'قراءاتها هنا.'
                  : 'لم يسجّل المالك أو المدير أيّ جهاز بعد.',
              actionLabel: _canManage ? 'سجّل أوّل جهاز' : null,
              onAction: _canManage ? () => _register(context) : null,
            ),
          ),
        ],
      );
    }
    final fleet = s.fleet;
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
              Expanded(
                child: MetricTile(
                  label: 'الأجهزة',
                  value: s.devices.length,
                  decimals: 0,
                  icon: Icons.sensors,
                ),
              ),
              Expanded(
                child: MetricTile(
                  label: 'متّصلة الآن',
                  value: s.onlineCount,
                  decimals: 0,
                  icon: Icons.wifi_rounded,
                ),
              ),
              Expanded(
                child: MetricTile(
                  label: 'صامتة',
                  value: fleet?.silent,
                  decimals: 0,
                  icon: Icons.notifications_paused_outlined,
                  caption: fleet == null ? 'تعذّر حساب صحّة الأسطول' : null,
                ),
              ),
            ],
          ),
        ),
        if (fleet != null && (fleet.criticalSilent ?? 0) > 0)
          _CriticalCard(fleet: fleet),
        const ListSectionHeader('الأجهزة'),
        for (final d in s.devices)
          Card(
            margin: const EdgeInsetsDirectional.symmetric(
              horizontal: SahoolSpacing.lg,
              vertical: SahoolSpacing.xs,
            ),
            child: OpsTile(
              key: ValueKey('device:${d.id}'),
              title: d.name.isEmpty ? '—' : d.name,
              subtitle: [
                d.typeLabel,
                lastSeenText(d, now),
                if (d.fieldId != null)
                  'الحقل: ${s.fieldNames?[d.fieldId] ?? 'مرتبط بحقل'}',
              ].join(' · '),
              icon: deviceTypeIcon(d.type),
              iconColor: d.online
                  ? context.tokens.success
                  : context.tokens.muted,
              chips: [
                deviceConnectionChip(d),
                if (fleet?.silentFor(d.id)?.isCritical ?? false)
                  const StatusChip(
                    label: 'صامت — حرج',
                    tone: StatusTone.danger,
                    icon: Icons.priority_high_rounded,
                  ),
              ],
              onTap: () => _open(context, d, s),
            ),
          ),
        const SizedBox(height: SahoolSpacing.md),
        Padding(
          padding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.lg,
          ),
          child: Text(
            'مراقبة فقط: لا تُرسَل أوامر تشغيل إلى الأجهزة من التطبيق.',
            style: context.textStyles.bodySmall?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
      ],
    );
  }
}

class _CriticalCard extends StatelessWidget {
  const _CriticalCard({required this.fleet});
  final FleetHealth fleet;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final critical = fleet.silentDevices.where((d) => d.isCritical).toList();
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.lg,
        SahoolSpacing.md,
        SahoolSpacing.lg,
        0,
      ),
      child: Semantics(
        liveRegion: true,
        child: Container(
          padding: const EdgeInsets.all(SahoolSpacing.md),
          decoration: BoxDecoration(
            color: t.danger.withValues(alpha: 0.10),
            borderRadius: SahoolRadius.mdAll,
            border: Border.all(color: t.danger.withValues(alpha: 0.45)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.report_rounded, color: t.danger),
                  const SizedBox(width: SahoolSpacing.sm),
                  Expanded(
                    child: Text(
                      '${fleet.criticalSilent} جهاز حرج صامت — يحتاج تدخّلاً',
                      style: context.textStyles.titleSmall,
                    ),
                  ),
                ],
              ),
              for (final d in critical) ...[
                const SizedBox(height: SahoolSpacing.xs),
                Text(
                  '• ${d.name}: ${d.detailAr}',
                  style: context.textStyles.bodySmall,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
