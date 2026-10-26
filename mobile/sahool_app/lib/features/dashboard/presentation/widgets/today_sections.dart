// SAHOOL — features/dashboard/presentation/widgets/today_sections.dart
// أقسام شاشة «اليوم». كلّ صفّ نصّيّ مقيَّد (Expanded/Flexible/Wrap) كي لا يفيض
// على 360dp وبمقياس نصّ 1.3؛ كلّ قيمة غائبة «غير مقيس»؛ كلّ لون حالة مقرون
// بأيقونة ونصّ (StatusChip)؛ الحشوات اتّجاهيّة (RTL).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/dashboard/data/today_models.dart';

import '../dashboard_state.dart';

/// تحيّة بحسب ساعة الجهاز + اسم المستخدم إن عُرِف + تاريخ اليوم.
class TodayHeader extends StatelessWidget {
  const TodayHeader({
    super.key,
    required this.now,
    this.userName,
    this.fetchedAt,
    this.refreshing = false,
  });

  final DateTime now;
  final String? userName;
  final DateTime? fetchedAt;
  final bool refreshing;

  @override
  Widget build(BuildContext context) {
    final greeting = now.hour < 12 ? 'صباح الخير' : 'مساء الخير';
    final name = userName?.trim();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          header: true,
          child: Text(
            name == null || name.isEmpty ? greeting : '$greeting، $name',
            style: context.textStyles.titleLarge,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(height: SahoolSpacing.xs),
        Wrap(
          spacing: SahoolSpacing.sm,
          runSpacing: SahoolSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Text('اليوم ${fmtDate(now)}', style: context.textStyles.bodyMedium),
            if (fetchedAt != null)
              Text(
                'آخر تحديث: ${fmtAge(fetchedAt, now: now)}',
                key: const ValueKey('today-last-updated'),
                style: context.textStyles.bodySmall,
              ),
            if (refreshing)
              const SizedBox.square(
                dimension: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
      ],
    );
  }
}

/// لافتة «تعرض آخر نسخة محفوظة» مع سبب الفشل وعمر البيانات.
class StaleBanner extends StatelessWidget {
  const StaleBanner({
    super.key,
    required this.fetchedAt,
    required this.now,
    this.error,
    this.fromSnapshot = false,
    this.onRetry,
  });

  final DateTime fetchedAt;
  final DateTime now;
  final ApiException? error;
  final bool fromSnapshot;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final offline = error?.isConnectivity ?? false;
    final title = fromSnapshot
        ? 'تعرض آخر نسخة محفوظة على الجهاز'
        : 'تعذّر التحديث — تعرض آخر بيانات وصلت';
    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        key: const ValueKey('today-stale-banner'),
        padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
        decoration: BoxDecoration(
          color: t.warning.withValues(alpha: 0.12),
          borderRadius: SahoolRadius.mdAll,
          border: Border.all(color: t.warning.withValues(alpha: 0.5)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              offline ? Icons.wifi_off_rounded : Icons.cloud_off_rounded,
              color: t.warning,
            ),
            const SizedBox(width: SahoolSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title, style: context.textStyles.titleSmall),
                  if (error != null)
                    Text(error!.messageAr, style: context.textStyles.bodySmall),
                  Text(
                    'آخر تحديث: ${fmtDateTime(fetchedAt)} '
                    '(${fmtAge(fetchedAt, now: now)})',
                    style: context.textStyles.bodySmall,
                  ),
                  if (onRetry != null)
                    Align(
                      alignment: AlignmentDirectional.centerEnd,
                      child: TextButton.icon(
                        onPressed: onRetry,
                        icon: const Icon(Icons.refresh_rounded),
                        label: const Text('إعادة المحاولة'),
                      ),
                    ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// اختيار المزرعة: رقائق أفقيّة قابلة للتمرير (≥48dp للمس).
class FarmSelector extends StatelessWidget {
  const FarmSelector({
    super.key,
    required this.farms,
    required this.selectedId,
    required this.onSelect,
  });

  final SectionState<List<TodayFarm>> farms;
  final String? selectedId;
  final ValueChanged<String?> onSelect;

  @override
  Widget build(BuildContext context) {
    final f = farms;
    if (f is SectionFailed<List<TodayFarm>>) {
      return Text(
        'تعذّر تحميل المزارع: ${f.error.messageAr}',
        style: context.textStyles.bodySmall,
      );
    }
    if (f is! SectionReady<List<TodayFarm>> || f.data.isEmpty) {
      return const SizedBox.shrink();
    }
    final list = f.data;
    Widget chip(String? id, String label) => Padding(
      padding: const EdgeInsetsDirectional.only(end: SahoolSpacing.sm),
      child: ChoiceChip(
        label: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 200),
          child: Text(label, overflow: TextOverflow.ellipsis),
        ),
        selected: selectedId == id,
        materialTapTargetSize: MaterialTapTargetSize.padded,
        onSelected: (_) => onSelect(id),
      ),
    );
    return SingleChildScrollView(
      key: const ValueKey('today-farm-selector'),
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          if (list.length > 1) chip(null, 'كلّ المزارع'),
          for (final farm in list) chip(farm.id, farm.name),
        ],
      ),
    );
  }
}

/// المؤشّرات كما يُصدرها الخادم، في شبكة عمودين.
class KpiGrid extends StatelessWidget {
  const KpiGrid({super.key, required this.kpis});
  final List<TodayKpi> kpis;

  static const _icons = {
    'fields_total': Icons.layers_outlined,
    'area_total': Icons.straighten_rounded,
    'active_seasons': Icons.grass_rounded,
    'open_alerts': Icons.notifications_active_outlined,
  };

  StatusChip? _status(TodayKpi k) => switch (k.status) {
    'critical' || 'poor' => const StatusChip(
      label: 'يحتاج انتباهاً',
      tone: StatusTone.danger,
    ),
    'fair' => const StatusChip(label: 'للمتابعة', tone: StatusTone.warning),
    _ => null, // «good» على عدّاد لا يقول شيئاً عن صحّة المحصول — لا نعرضه.
  };

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      final w = (c.maxWidth - SahoolSpacing.sm) / 2;
      return Wrap(
        spacing: SahoolSpacing.sm,
        runSpacing: SahoolSpacing.sm,
        children: [
          for (final k in kpis)
            SizedBox(
              width: w,
              child: MetricTile(
                key: ValueKey('kpi-${k.id}'),
                label: k.labelAr,
                value: k.value,
                unit: k.unit,
                decimals: k.id == 'area_total' ? 1 : 0,
                icon: _icons[k.id],
                status: _status(k),
              ),
            ),
        ],
      );
    },
  );
}

StatusChip severityChip(String? severity) => switch (severity) {
  'critical' => const StatusChip(label: 'حرج', tone: StatusTone.danger),
  'high' => const StatusChip(label: 'أولويّة عالية', tone: StatusTone.danger),
  'warning' => const StatusChip(label: 'تحذير', tone: StatusTone.warning),
  'medium' => const StatusChip(label: 'متوسّط', tone: StatusTone.warning),
  'info' || 'low' => const StatusChip(label: 'للعلم', tone: StatusTone.info),
  _ => const StatusChip(label: 'غير مصنّف'),
};

/// التنبيهات الأشدّ أوّلاً. الضغط يفتح الوجهة إن وُجدت؛ الإقرار للأدوار المعدِّلة.
class AlertsSection extends StatelessWidget {
  const AlertsSection({
    super.key,
    required this.alerts,
    required this.now,
    required this.fieldName,
    required this.canAcknowledge,
    required this.busy,
    required this.onOpen,
    required this.onAcknowledge,
    this.onSeeAll,
    this.limit = 3,
  });

  final List<TodayAlert> alerts;
  final DateTime now;
  final String? Function(String?) fieldName;
  final bool canAcknowledge;
  final Set<String> busy;

  /// null للتنبيه ⇒ لا وجهة له (لا طريق مسدود قابل للضغط).
  final VoidCallback? Function(TodayAlert) onOpen;
  final ValueChanged<TodayAlert> onAcknowledge;
  final VoidCallback? onSeeAll;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final shown = alerts.take(limit).toList();
    return SectionCard(
      key: const ValueKey('today-alerts'),
      title: 'تنبيهات تحتاج انتباهك',
      icon: Icons.notifications_active_outlined,
      trailing: (onSeeAll != null && alerts.length > shown.length)
          ? TextButton(
              onPressed: onSeeAll,
              child: Text('الكلّ (${alerts.length})'),
            )
          : null,
      child: shown.isEmpty
          ? _InlineNote(
              icon: Icons.check_circle_outline_rounded,
              tone: context.tokens.success,
              text: 'لا تنبيهات نشطة الآن.',
            )
          : Column(
              children: [
                for (final a in shown)
                  _AlertTile(
                    alert: a,
                    now: now,
                    fieldName: fieldName(a.fieldId),
                    onTap: onOpen(a),
                    canAcknowledge: canAcknowledge,
                    busy: busy.contains(a.id),
                    onAcknowledge: () => onAcknowledge(a),
                  ),
              ],
            ),
    );
  }
}

class _AlertTile extends StatelessWidget {
  const _AlertTile({
    required this.alert,
    required this.now,
    required this.fieldName,
    required this.onTap,
    required this.canAcknowledge,
    required this.busy,
    required this.onAcknowledge,
  });

  final TodayAlert alert;
  final DateTime now;
  final String? fieldName;
  final VoidCallback? onTap;
  final bool canAcknowledge;
  final bool busy;
  final VoidCallback onAcknowledge;

  @override
  Widget build(BuildContext context) {
    final meta = [
      if (fieldName != null) fieldName!,
      if (alert.createdAt != null) fmtAge(alert.createdAt, now: now),
    ].join(' · ');
    return InkWell(
      key: ValueKey('alert-${alert.id}'),
      onTap: onTap,
      borderRadius: SahoolRadius.smAll,
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          vertical: SahoolSpacing.sm,
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: SahoolSpacing.sm,
              runSpacing: SahoolSpacing.xs,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                severityChip(alert.severity),
                if (meta.isNotEmpty)
                  Text(meta, style: context.textStyles.bodySmall),
              ],
            ),
            const SizedBox(height: SahoolSpacing.xs),
            Text(
              alert.displayTitle,
              style: context.textStyles.titleSmall,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            if (alert.messageAr != null)
              Text(
                alert.messageAr!,
                style: context.textStyles.bodyMedium,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            if (canAcknowledge || onTap != null)
              Wrap(
                alignment: WrapAlignment.end,
                spacing: SahoolSpacing.sm,
                children: [
                  if (canAcknowledge)
                    TextButton.icon(
                      key: ValueKey('ack-${alert.id}'),
                      onPressed: busy ? null : onAcknowledge,
                      icon: busy
                          ? const SizedBox.square(
                              dimension: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.done_rounded),
                      label: const Text('تمّ الاطّلاع'),
                    ),
                  if (onTap != null)
                    TextButton.icon(
                      onPressed: onTap,
                      icon: const Icon(Icons.chevron_right_rounded),
                      label: const Text('فتح'),
                    ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

/// مهامّ اليوم (قراءة فقط هنا؛ التنفيذ في تبويب المهامّ).
class TasksSection extends StatelessWidget {
  const TasksSection({
    super.key,
    required this.tasks,
    required this.today,
    required this.now,
    required this.fieldName,
    this.onSeeAll,
    this.onRetry,
    this.limit = 5,
  });

  final SectionState<List<TodayTask>> tasks;
  final List<TodayTask> today;
  final DateTime now;
  final String? Function(String?) fieldName;
  final VoidCallback? onSeeAll;
  final VoidCallback? onRetry;
  final int limit;

  @override
  Widget build(BuildContext context) {
    final t = tasks;
    final overdue = today.where((x) => x.isOverdue(now)).length;
    Widget body;
    if (t is SectionLoading<List<TodayTask>>) {
      body = const SkeletonLines(lines: 2);
    } else if (t is SectionFailed<List<TodayTask>>) {
      body = _SectionError(error: t.error, onRetry: onRetry);
    } else if (today.isEmpty) {
      body = _InlineNote(
        icon: Icons.event_available_outlined,
        tone: context.tokens.success,
        text: 'لا مهامّ مستحقّة اليوم.',
      );
    } else {
      body = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            overdue > 0
                ? '${today.length} مهمّة مفتوحة · $overdue متأخّرة'
                : '${today.length} مهمّة مفتوحة',
            style: context.textStyles.bodySmall,
          ),
          for (final task in today.take(limit))
            _TaskRow(task: task, now: now, fieldName: fieldName(task.fieldId)),
        ],
      );
    }
    return SectionCard(
      key: const ValueKey('today-tasks'),
      title: 'مهامّ اليوم',
      icon: Icons.task_alt_outlined,
      trailing: onSeeAll == null
          ? null
          : TextButton(onPressed: onSeeAll, child: const Text('كلّ المهامّ')),
      child: body,
    );
  }
}

class _TaskRow extends StatelessWidget {
  const _TaskRow({required this.task, required this.now, this.fieldName});
  final TodayTask task;
  final DateTime now;
  final String? fieldName;

  @override
  Widget build(BuildContext context) {
    final overdue = task.isOverdue(now);
    final due = task.dueDate == null ? 'بلا موعد' : fmtDate(task.dueDate);
    return Padding(
      padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            task.status == 'in_progress'
                ? Icons.play_circle_outline_rounded
                : Icons.radio_button_unchecked_rounded,
            color: context.tokens.muted,
          ),
          const SizedBox(width: SahoolSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  task.displayTitle,
                  style: context.textStyles.titleSmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  [if (fieldName != null) fieldName!, due].join(' · '),
                  style: context.textStyles.bodySmall,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          if (overdue) ...[
            const SizedBox(width: SahoolSpacing.sm),
            const Flexible(
              child: StatusChip(label: 'متأخّرة', tone: StatusTone.danger),
            ),
          ],
        ],
      ),
    );
  }
}

/// شريط الطقس الآن لموقع المزرعة/الحقل. لا طقس مُختلَق: بلا إحداثيّات أو
/// عند فشل الخادم تُعرض الحالة كما هي.
class WeatherStrip extends StatelessWidget {
  const WeatherStrip({super.key, required this.weather, this.onRetry});

  final SectionState<TodayWeather> weather;
  final VoidCallback? onRetry;

  static String _spray(String? s) => switch (s) {
    'optimal' => 'مناسب',
    'acceptable' => 'مقبول',
    'poor' => 'غير مناسب',
    'unsafe' => 'غير آمن',
    _ => kNotMeasured,
  };

  static StatusTone _sprayTone(String? s) => switch (s) {
    'optimal' => StatusTone.success,
    'acceptable' => StatusTone.info,
    'poor' => StatusTone.warning,
    'unsafe' => StatusTone.danger,
    _ => StatusTone.neutral,
  };

  // درجة الريّ في الخادم ترتفع بالحاجة (VPD عالٍ/تربة جافّة) وتنخفض بالمطر.
  static String _irrigation(String? s) => switch (s) {
    'optimal' => 'يُنصح به',
    'acceptable' => 'مقبول',
    'poor' || 'unsafe' => 'لا حاجة ملحّة',
    _ => kNotMeasured,
  };

  @override
  Widget build(BuildContext context) {
    final w = weather;
    Widget body;
    String title = 'الطقس الآن';
    if (w is SectionLoading<TodayWeather>) {
      body = const SkeletonLines(lines: 2);
    } else if (w is SectionUnavailable<TodayWeather>) {
      body = _InlineNote(
        icon: Icons.cloud_off_outlined,
        tone: context.tokens.muted,
        text: 'الطقس غير متاح: ${w.reasonAr}',
      );
    } else if (w is SectionFailed<TodayWeather>) {
      body = _SectionError(error: w.error, onRetry: onRetry);
    } else {
      final d = (w as SectionReady<TodayWeather>).data;
      title = 'الطقس الآن — ${d.placeAr}';
      final wind = d.windKmh == null
          ? kNotMeasured
          : '${fmtNumber(d.windKmh, decimals: 0)} كم/س';
      body = Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: SahoolSpacing.lg,
            runSpacing: SahoolSpacing.sm,
            children: [
              _WeatherValue(
                icon: Icons.thermostat_rounded,
                label: 'الحرارة',
                value: fmtTempC(d.tempC),
              ),
              _WeatherValue(
                icon: Icons.water_drop_outlined,
                label: 'الرطوبة',
                value: fmtPct(d.humidityPct),
              ),
              _WeatherValue(
                icon: Icons.air_rounded,
                label: 'الرياح',
                value: wind,
              ),
              _WeatherValue(
                icon: Icons.umbrella_outlined,
                label: 'الهطول',
                value: fmtMm(d.rainMm),
              ),
            ],
          ),
          const SizedBox(height: SahoolSpacing.sm),
          Wrap(
            spacing: SahoolSpacing.sm,
            runSpacing: SahoolSpacing.xs,
            children: [
              StatusChip(
                label: 'الرشّ: ${_spray(d.spraying)}',
                tone: _sprayTone(d.spraying),
                icon: Icons.sanitizer_outlined,
              ),
              StatusChip(
                label: 'الريّ: ${_irrigation(d.irrigation)}',
                tone: StatusTone.info,
                icon: Icons.water_outlined,
              ),
            ],
          ),
          for (final a in d.alertsAr.take(2))
            Padding(
              padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.xs),
              child: Text('• $a', style: context.textStyles.bodySmall),
            ),
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            d.stale
                ? 'قراءة مخزّنة لدى الخادم لتعذّر المصدر · Open-Meteo'
                : 'المصدر: Open-Meteo',
            style: context.textStyles.bodySmall,
          ),
        ],
      );
    }
    return SectionCard(
      key: const ValueKey('today-weather'),
      title: title,
      icon: Icons.wb_sunny_outlined,
      child: body,
    );
  }
}

class _WeatherValue extends StatelessWidget {
  const _WeatherValue({
    required this.icon,
    required this.label,
    required this.value,
  });
  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Semantics(
    label: '$label: $value',
    excludeSemantics: true,
    child: Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: SahoolSizes.iconSm, color: context.tokens.muted),
        const SizedBox(width: SahoolSpacing.xs),
        Text(value, style: context.textStyles.titleSmall),
      ],
    ),
  );
}

/// الحقول مرتّبة بالأولويّة. لا شارة «صحّة جيدة»: الصحّة الطيفيّة ليست في هذه
/// الحمولة، فنعرض ما هو مقيس فعلاً (عناصر مفتوحة، موسم نشط، مساحة).
class FieldPrioritySection extends StatelessWidget {
  const FieldPrioritySection({
    super.key,
    required this.rows,
    required this.priority,
    required this.onOpenField,
    this.onSeeAll,
    this.limit = 6,
  });

  final List<FieldPriority> rows;
  final SectionState<List<PriorityItem>> priority;
  final ValueChanged<String> onOpenField;
  final VoidCallback? onSeeAll;
  final int limit;

  static StatusChip _rankChip(FieldPriority r) => switch (r.topRank) {
    0 => const StatusChip(label: 'أولويّة حرجة', tone: StatusTone.danger),
    1 => const StatusChip(label: 'أولويّة عالية', tone: StatusTone.warning),
    2 => const StatusChip(label: 'أولويّة متوسّطة', tone: StatusTone.info),
    3 => const StatusChip(label: 'أولويّة منخفضة'),
    _ => const StatusChip(label: 'لا عناصر مفتوحة', tone: StatusTone.success),
  };

  @override
  Widget build(BuildContext context) {
    final p = priority;
    final source = switch (p) {
      SectionReady() => 'الترتيب من طابور أولويّات المزرعة.',
      SectionFailed(:final error) =>
        'تعذّر طابور الأولويّات (${error.messageAr}) — الترتيب من التنبيهات والمهامّ.',
      _ => 'الترتيب من التنبيهات والمهامّ المفتوحة.',
    };
    return SectionCard(
      key: const ValueKey('today-fields'),
      title: 'حقولك حسب الأولويّة',
      icon: Icons.layers_outlined,
      trailing: onSeeAll == null
          ? null
          : TextButton(onPressed: onSeeAll, child: const Text('كلّ الحقول')),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(source, style: context.textStyles.bodySmall),
          if (rows.isEmpty)
            _InlineNote(
              icon: Icons.layers_clear_outlined,
              tone: context.tokens.muted,
              text: 'لا حقول في هذه المزرعة.',
            ),
          for (final r in rows.take(limit))
            InkWell(
              key: ValueKey('field-${r.field.id}'),
              onTap: () => onOpenField(r.field.id),
              borderRadius: SahoolRadius.smAll,
              child: ConstrainedBox(
                constraints: const BoxConstraints(
                  minHeight: SahoolSizes.minTouchTarget,
                ),
                child: Padding(
                  padding: const EdgeInsetsDirectional.symmetric(
                    vertical: SahoolSpacing.sm,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              r.field.name,
                              style: context.textStyles.titleSmall,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            Text(
                              '${r.field.crop ?? 'محصول غير محدّد'} · '
                              '${fmtArea(r.field.areaHa)}',
                              style: context.textStyles.bodySmall,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: SahoolSpacing.xs),
                            Wrap(
                              spacing: SahoolSpacing.xs,
                              runSpacing: SahoolSpacing.xs,
                              children: [
                                _rankChip(r),
                                if (r.openAlerts > 0)
                                  StatusChip(
                                    label: '${r.openAlerts} تنبيه',
                                    tone: StatusTone.warning,
                                    icon: Icons.notifications_none_rounded,
                                  ),
                                if (r.field.hasActiveSeason == true)
                                  const StatusChip(
                                    label: 'موسم نشط',
                                    tone: StatusTone.success,
                                    icon: Icons.grass_rounded,
                                  )
                                else if (r.field.hasActiveSeason == false)
                                  const StatusChip(
                                    label: 'بلا موسم نشط',
                                    icon: Icons.grass_rounded,
                                  ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      Icon(Icons.chevron_right, color: context.tokens.muted),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _InlineNote extends StatelessWidget {
  const _InlineNote({
    required this.icon,
    required this.tone,
    required this.text,
  });
  final IconData icon;
  final Color tone;
  final String text;

  @override
  Widget build(BuildContext context) => Row(
    children: [
      Icon(icon, color: tone),
      const SizedBox(width: SahoolSpacing.sm),
      Expanded(child: Text(text, style: context.textStyles.bodyMedium)),
    ],
  );
}

class _SectionError extends StatelessWidget {
  const _SectionError({required this.error, this.onRetry});
  final ApiException error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      _InlineNote(
        icon: ErrorState.iconFor(error),
        tone: error.isConnectivity
            ? context.tokens.warning
            : context.tokens.danger,
        text: error.messageAr,
      ),
      if (onRetry != null &&
          error.kind != ApiErrorKind.forbidden &&
          error.kind != ApiErrorKind.notFound)
        Align(
          alignment: AlignmentDirectional.centerEnd,
          child: TextButton.icon(
            onPressed: onRetry,
            icon: const Icon(Icons.refresh_rounded),
            label: const Text('إعادة المحاولة'),
          ),
        ),
    ],
  );
}

/// هيكل تحميل: كتل رماديّة بلون الخطّ الفاصل (لا أرقام وهميّة).
class SkeletonLines extends StatelessWidget {
  const SkeletonLines({super.key, this.lines = 3});
  final int lines;

  @override
  Widget build(BuildContext context) {
    final c = context.tokens.line;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (var i = 0; i < lines; i++)
          Padding(
            padding: const EdgeInsetsDirectional.only(bottom: SahoolSpacing.sm),
            child: FractionallySizedBox(
              widthFactor: i.isEven ? 0.9 : 0.6,
              child: Container(
                height: 14,
                decoration: BoxDecoration(
                  color: c,
                  borderRadius: SahoolRadius.smAll,
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// هيكل الشاشة كاملةً في التحميل الأوّل.
class TodaySkeleton extends StatelessWidget {
  const TodaySkeleton({super.key});

  @override
  Widget build(BuildContext context) {
    final c = context.tokens.line;
    Widget block(double h) => Container(
      height: h,
      decoration: BoxDecoration(color: c, borderRadius: SahoolRadius.mdAll),
    );
    return Semantics(
      key: const ValueKey('today-skeleton'),
      label: 'جارٍ تحميل اليوم',
      liveRegion: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const SkeletonLines(lines: 2),
          const SizedBox(height: SahoolSpacing.md),
          Row(
            children: [
              Expanded(child: block(88)),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(child: block(88)),
            ],
          ),
          const SizedBox(height: SahoolSpacing.sm),
          Row(
            children: [
              Expanded(child: block(88)),
              const SizedBox(width: SahoolSpacing.sm),
              Expanded(child: block(88)),
            ],
          ),
          const SizedBox(height: SahoolSpacing.md),
          block(120),
          const SizedBox(height: SahoolSpacing.md),
          block(120),
        ],
      ),
    );
  }
}
