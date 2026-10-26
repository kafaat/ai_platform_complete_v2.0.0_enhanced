// SAHOOL — features/devices/presentation/device_detail_screen.dart
// جهاز واحد: حالة اتّصاله وآخر ظهور، الحقل المرتبط، تشخيص الصمت من صحّة الأسطول،
// ثمّ قراءاته مجمّعة بالمستشعر — آخر قيمة بعمرها ورسم خطّيّ لكلّ مستشعر. لا
// قراءات ⇒ «لا قراءات» صريحة، لا رسم فارغ ولا صفر. لا أوامر تشغيل (المشغّلات تُراقَب
// فقط). رابط عميق: `/devices/detail?device_id=dev_…`.
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/devices/data/devices_api.dart';
import 'package:sahool_app/features/devices/data/devices_models.dart';
import 'package:sahool_app/features/operations_hub/presentation/widgets/ops_refresh_banner.dart';

import 'devices_cubit.dart';
import 'devices_screen.dart'
    show deviceConnectionChip, deviceTypeIcon, lastSeenText;
import 'widgets/sensor_chart.dart';

const String kNoReadings = 'لا قراءات من هذا الجهاز بعد.';
const String kActuatorMonitorOnly =
    'هذا مُشغِّل: التطبيق يعرض حالته فقط ولا يرسل أوامر فتح/إغلاق.';

class DeviceDetailScreen extends StatelessWidget {
  const DeviceDetailScreen({
    super.key,
    required this.deviceId,
    this.device,
    this.fieldName,
    this.silent,
    this.api,
    this.clock,
  });

  final String deviceId;

  /// من القائمة إن وُجد — عنوان فوريّ أثناء التحميل.
  final Device? device;
  final String? fieldName;

  /// تشخيص الصمت من صحّة الأسطول، إن كان الجهاز صامتاً.
  final SilentDevice? silent;
  final DevicesApi? api;
  final DateTime Function()? clock;

  @override
  Widget build(BuildContext context) => BlocProvider(
    create: (_) =>
        TelemetryCubit(api ?? DevicesApi.instance, deviceId, clock: clock)
          ..load(),
    child: _DetailView(
      initial: device,
      fieldName: fieldName,
      silent: silent,
      clock: clock ?? DateTime.now,
    ),
  );
}

class _DetailView extends StatelessWidget {
  const _DetailView({
    required this.initial,
    required this.fieldName,
    required this.silent,
    required this.clock,
  });

  final Device? initial;
  final String? fieldName;
  final SilentDevice? silent;
  final DateTime Function() clock;

  @override
  Widget build(BuildContext context) {
    final cubit = context.watch<TelemetryCubit>();
    final state = cubit.state;
    final title = switch (state) {
      TelemetryLoaded(:final device) => device.name,
      _ => initial?.name ?? 'الجهاز',
    };
    return AppScaffold(
      title: title.isEmpty ? 'الجهاز' : title,
      actions: [
        AppIconButton(
          icon: Icons.refresh_rounded,
          tooltip: 'تحديث',
          onPressed: state is TelemetryLoading ? null : cubit.load,
        ),
      ],
      body: switch (state) {
        TelemetryLoading() => const LoadingState(
          message: 'جارٍ تحميل القراءات…',
        ),
        TelemetryFailed(:final error) => ErrorState(
          error: error,
          onRetry: cubit.load,
        ),
        TelemetryLoaded() => RefreshIndicator(
          onRefresh: cubit.load,
          child: _body(context, state),
        ),
      },
    );
  }

  Widget _body(BuildContext context, TelemetryLoaded s) {
    final d = s.device;
    final t = context.tokens;
    final now = clock();
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.all(SahoolSpacing.lg),
      children: [
        if (s.refreshError != null) ...[
          OpsRefreshBanner(
            error: s.refreshError!,
            fetchedAt: s.fetchedAt,
            now: now,
          ),
          const SizedBox(height: SahoolSpacing.md),
        ],
        SectionCard(
          title: d.typeLabel,
          icon: deviceTypeIcon(d.type),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              deviceConnectionChip(d),
              const SizedBox(height: SahoolSpacing.md),
              Text(lastSeenText(d, now), style: context.textStyles.bodyLarge),
              if (d.lastSeenAt != null)
                Text(
                  fmtDateTime(d.lastSeenAt),
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              const SizedBox(height: SahoolSpacing.sm),
              Text(
                d.fieldId == null
                    ? 'غير مرتبط بحقل'
                    : 'الحقل: ${fieldName ?? 'مرتبط بحقل'}',
                style: context.textStyles.bodyMedium,
              ),
              if ((d.firmwareVersion ?? '').isNotEmpty)
                Text(
                  'البرنامج الثابت: ${d.firmwareVersion}',
                  style: context.textStyles.bodySmall,
                ),
              if (silent != null) ...[
                const SizedBox(height: SahoolSpacing.md),
                StatusChip(
                  label: silent!.isCritical ? 'صامت — حرج' : 'صامت',
                  tone: silent!.isCritical
                      ? StatusTone.danger
                      : StatusTone.warning,
                  icon: Icons.notifications_paused_outlined,
                ),
                const SizedBox(height: SahoolSpacing.xs),
                Text(
                  [
                    silent!.detailAr,
                    silent!.criticalityNoteAr,
                  ].where((x) => x.isNotEmpty).join('\n'),
                  style: context.textStyles.bodySmall,
                ),
              ],
              if (d.isActuator) ...[
                const SizedBox(height: SahoolSpacing.md),
                Text(
                  kActuatorMonitorOnly,
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              ],
            ],
          ),
        ),
        const SizedBox(height: SahoolSpacing.lg),
        if (s.isEmpty)
          SectionCard(
            title: 'القراءات',
            icon: Icons.show_chart_rounded,
            child: Row(
              children: [
                Icon(Icons.sensors_off_outlined, color: t.muted),
                const SizedBox(width: SahoolSpacing.sm),
                Expanded(
                  child: Text(
                    s.rawCount == 0
                        ? kNoReadings
                        : 'وصلت ${s.rawCount} قراءة بلا قيمة أو وقت صالحين — '
                              'لا شيء يُعرض.',
                    style: context.textStyles.bodyLarge,
                  ),
                ),
              ],
            ),
          )
        else
          for (final series in s.series) ...[
            _SeriesCard(series: series, now: now),
            const SizedBox(height: SahoolSpacing.md),
          ],
        if (s.rawCount >= kTelemetryWindow)
          Text(
            'يُعرض آخر $kTelemetryWindow قراءة فقط.',
            style: context.textStyles.bodySmall?.copyWith(color: t.muted),
          ),
      ],
    );
  }
}

class _SeriesCard extends StatelessWidget {
  const _SeriesCard({required this.series, required this.now});
  final SensorSeries series;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final latest = series.latest!;
    return SectionCard(
      key: ValueKey('series:${series.sensorType}'),
      title: series.label,
      icon: Icons.show_chart_rounded,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          MetricTile(
            label: 'آخر قراءة',
            value: latest.value,
            unit: latest.unit,
            decimals: 2,
            caption:
                '${fmtAge(latest.recordedAt, now: now)} · '
                '${fmtDateTime(latest.recordedAt)}',
          ),
          const SizedBox(height: SahoolSpacing.md),
          SensorChart(series: series),
        ],
      ),
    );
  }
}
