// SAHOOL — features/devices/presentation/widgets/sensor_chart.dart
// رسم خطّيّ لقراءات مستشعر واحد (fl_chart): الزمن أفقيّاً (الأقدم يساراً كعادة
// المحاور الزمنيّة حتّى في الواجهات العربيّة)، والقيمة عموديّاً بالوحدة التي أرسلها
// الجهاز — لا وحدة تُخمَّن. قراءة واحدة لا تُرسم خطّاً.
import 'dart:math' as math;

import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/features/devices/data/devices_models.dart';

class SensorChart extends StatelessWidget {
  const SensorChart({super.key, required this.series, this.height = 180});

  final SensorSeries series;
  final double height;

  @override
  Widget build(BuildContext context) {
    final pts = series.points;
    final t = context.tokens;
    if (pts.length < 2) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: SahoolSpacing.md),
        child: Text(
          'قراءة واحدة فقط — لا تكفي لرسم اتّجاه.',
          style: context.textStyles.bodyMedium?.copyWith(color: t.muted),
        ),
      );
    }
    final origin = pts.first.recordedAt!;
    double x(TelemetryPoint p) =>
        p.recordedAt!.difference(origin).inSeconds / 60.0;
    final values = pts.map((p) => p.value!).toList();
    var minY = values.reduce(math.min);
    var maxY = values.reduce(math.max);
    final pad = (maxY - minY).abs() < 1e-9
        ? (maxY.abs() * 0.1 + 1)
        : (maxY - minY) * 0.1;
    minY -= pad;
    maxY += pad;
    final color = context.colors.primary;
    final unit = series.unit;
    final first = pts.first.recordedAt!;
    final last = pts.last.recordedAt!;
    final summary =
        '${series.label}: ${pts.length} قراءة من '
        '${fmtDateTime(first)} إلى ${fmtDateTime(last)}، آخر قيمة '
        '${fmtNumber(pts.last.value, decimals: 2)}${unit == null ? '' : ' $unit'}';

    return Semantics(
      label: summary,
      excludeSemantics: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SizedBox(
            height: height,
            // المحور الزمنيّ يُرسم يسار←يمين؛ عناوين المحور لا تنعكس.
            child: Directionality(
              textDirection: TextDirection.ltr,
              child: LineChart(
                LineChartData(
                  minY: minY,
                  maxY: maxY,
                  clipData: const FlClipData.all(),
                  gridData: FlGridData(
                    drawVerticalLine: false,
                    getDrawingHorizontalLine: (_) =>
                        FlLine(color: t.line, strokeWidth: 1),
                  ),
                  borderData: FlBorderData(show: false),
                  titlesData: FlTitlesData(
                    topTitles: const AxisTitles(),
                    rightTitles: const AxisTitles(),
                    bottomTitles: const AxisTitles(),
                    leftTitles: AxisTitles(
                      sideTitles: SideTitles(
                        showTitles: true,
                        reservedSize: 48,
                        getTitlesWidget: (v, meta) => SideTitleWidget(
                          axisSide: meta.axisSide,
                          child: Text(
                            fmtNumber(v, decimals: 1),
                            style: context.textStyles.labelSmall,
                          ),
                        ),
                      ),
                    ),
                  ),
                  lineTouchData: LineTouchData(
                    touchTooltipData: LineTouchTooltipData(
                      getTooltipColor: (_) => t.surfaceAlt,
                      getTooltipItems: (spots) => [
                        for (final s in spots)
                          LineTooltipItem(
                            '${fmtNumber(s.y, decimals: 2)}'
                            '${unit == null ? '' : ' $unit'}\n'
                            '${fmtDateTime(origin.add(Duration(seconds: (s.x * 60).round())))}',
                            TextStyle(
                              color: t.ink,
                              fontSize: SahoolType.caption,
                            ),
                          ),
                      ],
                    ),
                  ),
                  lineBarsData: [
                    LineChartBarData(
                      spots: [for (final p in pts) FlSpot(x(p), p.value!)],
                      color: color,
                      barWidth: 2.5,
                      isCurved: false,
                      dotData: FlDotData(show: pts.length <= 30),
                      belowBarData: BarAreaData(
                        show: true,
                        color: color.withValues(alpha: 0.10),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: SahoolSpacing.xs),
          Text(
            'من ${fmtDateTime(first)} إلى ${fmtDateTime(last)} · '
            '${pts.length} قراءة',
            style: context.textStyles.bodySmall?.copyWith(color: t.muted),
          ),
        ],
      ),
    );
  }
}
