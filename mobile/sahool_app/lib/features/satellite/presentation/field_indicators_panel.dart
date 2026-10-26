// SAHOOL — features/satellite/presentation/field_indicators_panel.dart
// لوحة مؤشّرات حقل واحد (بطاقات + مبدّل مؤشّر + رسم زمنيّ fl_chart). تُستعمل في
// شاشة الأقمار وفي تبويب «المراقبة» بمساحة عمل الحقل. طبقة الخريطة ليست هنا
// (ميزة الخرائط). صدق: المؤشّر الغائب «غير مقيس»، والسلسلة الفارغة تُعلَن بملاحظة
// الخادم، والتقدير (estimated) يُوسَم صراحةً.
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/fields/presentation/common/field_labels.dart';
import 'package:sahool_app/features/fields/presentation/common/load_cubit.dart';
import 'package:sahool_app/features/satellite/data/satellite_models.dart';

import 'field_indicators_cubit.dart';

/// تسميات عربيّة للمؤشّرات المشتقّة التي لا تأتي في الكتالوج.
const Map<String, String> kIndicatorNameAr = {
  'lai': 'LAI (مساحة الأوراق)',
  'water_stress': 'إجهاد مائي تفسيريّ',
};

String indicatorLabel(String id, List<IndexOption> options) {
  for (final o in options) {
    if (o.id == id) return o.nameAr;
  }
  return kIndicatorNameAr[id] ?? id.toUpperCase();
}

class FieldIndicatorsPanel extends StatelessWidget {
  const FieldIndicatorsPanel({super.key});

  @override
  Widget build(BuildContext context) =>
      BlocBuilder<FieldIndicatorsCubit, FieldIndicatorsState>(
        builder: (context, s) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            _HealthCard(state: s),
            const SizedBox(height: SahoolSpacing.md),
            IndexSelector(
              options: s.options,
              selected: s.index,
              fromCatalog: s.optionsFromCatalog,
              onSelected: context.read<FieldIndicatorsCubit>().selectIndex,
            ),
            const SizedBox(height: SahoolSpacing.md),
            _SeriesCard(state: s),
            const SizedBox(height: SahoolSpacing.md),
            _AllIndicatorsCard(state: s),
          ],
        ),
      );
}

class _HealthCard extends StatelessWidget {
  const _HealthCard({required this.state});
  final FieldIndicatorsState state;

  @override
  Widget build(BuildContext context) => SectionCard(
    title: 'صحّة الغطاء النباتيّ',
    icon: Icons.eco_outlined,
    child: LoadStateView<IndicatorSnapshot>(
      state: state.snapshot,
      onRetry: context.read<FieldIndicatorsCubit>().retrySnapshot,
      builder: (context, snap) {
        final ndvi = snap.reading('ndvi');
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: SahoolSpacing.sm,
              runSpacing: SahoolSpacing.sm,
              children: [
                StatusChip(
                  key: const ValueKey('health_chip'),
                  label: snap.health?.labelAr ?? 'الصحّة غير مصنّفة',
                  tone: healthTone(snap.health?.status),
                ),
                if (ndvi?.estimated == true)
                  const StatusChip(
                    label: 'تقدير لا رصد مباشر',
                    tone: StatusTone.warning,
                  ),
              ],
            ),
            const SizedBox(height: SahoolSpacing.sm),
            Text(
              'NDVI الحاليّ: ${ndvi?.value == null ? kNotMeasured : fmtNumber(ndvi!.value, decimals: 2)}',
              style: context.textStyles.titleMedium,
            ),
            if (snap.observedAt != null)
              Text(
                'آخر بيانات متاحة: ${fmtDateTime(snap.observedAt)}',
                style: context.textStyles.bodySmall,
              ),
          ],
        );
      },
    ),
  );
}

/// مبدّل المؤشّر (NDVI/NDWI/…) — شرائح كبيرة قابلة للّمس، أفقيّة التمرير.
class IndexSelector extends StatelessWidget {
  const IndexSelector({
    super.key,
    required this.options,
    required this.selected,
    required this.onSelected,
    this.fromCatalog = true,
  });

  final List<IndexOption> options;
  final String selected;
  final ValueChanged<String> onSelected;
  final bool fromCatalog;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      SizedBox(
        height: SahoolSizes.minTouchTarget + SahoolSpacing.sm,
        child: ListView.separated(
          scrollDirection: Axis.horizontal,
          itemCount: options.length,
          separatorBuilder: (_, _) => const SizedBox(width: SahoolSpacing.sm),
          itemBuilder: (context, i) {
            final o = options[i];
            return Center(
              child: ChoiceChip(
                key: ValueKey('index_${o.id}'),
                label: Text(o.nameAr),
                selected: o.id == selected,
                materialTapTargetSize: MaterialTapTargetSize.padded,
                onSelected: (_) => onSelected(o.id),
              ),
            );
          },
        ),
      ),
      if (!fromCatalog)
        Text(
          'قائمة المؤشّرات احتياطيّة — تعذّر جلب الكتالوج من الخادم.',
          style: context.textStyles.bodySmall,
        ),
    ],
  );
}

class _SeriesCard extends StatelessWidget {
  const _SeriesCard({required this.state});
  final FieldIndicatorsState state;

  @override
  Widget build(BuildContext context) {
    final name = state.selectedOption.nameAr;
    return SectionCard(
      title: 'تطوّر $name',
      icon: Icons.show_chart_rounded,
      child: LoadStateView<IndexSeries>(
        state: state.series,
        onRetry: context.read<FieldIndicatorsCubit>().retrySeries,
        builder: (context, series) {
          if (!series.available) {
            return Text(
              series.noteAr ??
                  'لا سلسلة زمنيّة لـ$name لهذا الحقل بعد — تظهر عند معالجة مشاهد الأقمار.',
              key: const ValueKey('series_empty'),
              style: context.textStyles.bodyMedium,
            );
          }
          final hasCloud = series.points.any((p) => p.cloudPct != null);
          final points = (state.hideCloudy && hasCloud)
              ? series.points
                    .where((p) => p.cloudPct == null || p.cloudPct! <= 50)
                    .toList()
              : series.points;
          final latest = series.latest!;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                'آخر قيمة: ${fmtNumber(latest.mean, decimals: 2)} · ${fmtDate(latest.date)}',
                style: context.textStyles.titleMedium,
              ),
              const SizedBox(height: SahoolSpacing.md),
              if (points.isEmpty)
                Text(
                  'كلّ المشاهد غائمة — أوقف الفلتر لعرضها.',
                  style: context.textStyles.bodyMedium,
                )
              else
                IndexSeriesChart(points: points, indexName: name),
              if (hasCloud)
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('إخفاء المشاهد الغائمة (> 50٪)'),
                  value: state.hideCloudy,
                  onChanged: context.read<FieldIndicatorsCubit>().setHideCloudy,
                )
              else
                Text(
                  'نسبة الغيوم غير مُبلَّغ عنها في هذه المشاهد.',
                  style: context.textStyles.bodySmall,
                ),
            ],
          );
        },
      ),
    );
  }
}

/// رسم خطّيّ لسلسلة مؤشّر (fl_chart). الزمن يتّجه يساراً←يميناً كعادة المحاور.
class IndexSeriesChart extends StatelessWidget {
  const IndexSeriesChart({
    super.key,
    required this.points,
    required this.indexName,
  });

  final List<IndexPoint> points;
  final String indexName;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final scheme = Theme.of(context).colorScheme;
    final origin = points.first.date;
    double x(DateTime d) => d.difference(origin).inHours / 24.0;
    final spots = [for (final p in points) FlSpot(x(p.date), p.mean)];
    final ys = points.map((p) => p.mean);
    final minY = math.min(0.0, ys.reduce(math.min));
    final maxY = math.max(1.0, ys.reduce(math.max));
    final maxX = math.max(1.0, spots.last.x);
    final latest = points.last;
    final style = context.textStyles.bodySmall;
    return Semantics(
      label:
          'رسم $indexName: ${points.length} مشاهدة، الأحدث ${fmtNumber(latest.mean, decimals: 2)} بتاريخ ${fmtDate(latest.date)}',
      excludeSemantics: true,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: SizedBox(
          height: 200,
          child: LineChart(
            LineChartData(
              minX: 0,
              maxX: maxX,
              minY: minY,
              maxY: maxY,
              gridData: FlGridData(
                drawVerticalLine: false,
                getDrawingHorizontalLine: (_) =>
                    FlLine(color: t.line, strokeWidth: 1),
              ),
              borderData: FlBorderData(show: false),
              lineTouchData: const LineTouchData(enabled: false),
              titlesData: FlTitlesData(
                topTitles: const AxisTitles(),
                rightTitles: const AxisTitles(),
                leftTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 36,
                    interval: (maxY - minY) / 4,
                    getTitlesWidget: (v, meta) => SideTitleWidget(
                      axisSide: meta.axisSide,
                      child: Text(fmtNumber(v, decimals: 1), style: style),
                    ),
                  ),
                ),
                bottomTitles: AxisTitles(
                  sideTitles: SideTitles(
                    showTitles: true,
                    reservedSize: 28,
                    interval: maxX,
                    getTitlesWidget: (v, meta) {
                      final d = origin.add(Duration(hours: (v * 24).round()));
                      return SideTitleWidget(
                        axisSide: meta.axisSide,
                        child: Text(
                          '${d.toLocal().day}/${d.toLocal().month}/${d.toLocal().year % 100}',
                          style: style,
                        ),
                      );
                    },
                  ),
                ),
              ),
              lineBarsData: [
                LineChartBarData(
                  spots: spots,
                  color: scheme.primary,
                  barWidth: 3,
                  dotData: const FlDotData(show: true),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AllIndicatorsCard extends StatelessWidget {
  const _AllIndicatorsCard({required this.state});
  final FieldIndicatorsState state;

  @override
  Widget build(BuildContext context) => SectionCard(
    title: 'كلّ المؤشّرات الحاليّة',
    icon: Icons.grid_view_rounded,
    child: LoadStateView<IndicatorSnapshot>(
      state: state.snapshot,
      onRetry: context.read<FieldIndicatorsCubit>().retrySnapshot,
      builder: (context, snap) => snap.readings.isEmpty
          ? Text(
              'لا مؤشّرات متاحة لهذا الحقل بعد.',
              style: context.textStyles.bodyMedium,
            )
          : IndicatorTilesGrid(readings: snap.readings, options: state.options),
    ),
  );
}

/// شبكة بطاقات مؤشّرات متكيّفة: عدد الأعمدة من العرض، وارتفاع كلّ بطاقة من
/// محتواها (لا نسبة أبعاد ثابتة) ⇒ لا فيض عند تكبير النصّ 1.3× أو 2×.
class IndicatorTilesGrid extends StatelessWidget {
  const IndicatorTilesGrid({
    super.key,
    required this.readings,
    required this.options,
  });

  final List<IndicatorReading> readings;
  final List<IndexOption> options;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, c) {
      final scale = MediaQuery.textScalerOf(context).scale(1);
      final minTile = 150 * scale.clamp(1.0, 2.0);
      final cols = math.max(1, (c.maxWidth / minTile).floor());
      const gap = SahoolSpacing.sm;
      final w = (c.maxWidth - gap * (cols - 1)) / cols;
      return Wrap(
        spacing: gap,
        runSpacing: gap,
        children: [
          for (final r in readings)
            SizedBox(
              width: w,
              child: MetricTile(
                key: ValueKey('indicator_${r.id}'),
                label: indicatorLabel(r.id, options),
                value: r.value,
                unit: r.unit,
                decimals: 2,
                caption: r.estimated ? 'تقدير' : null,
              ),
            ),
        ],
      );
    },
  );
}
