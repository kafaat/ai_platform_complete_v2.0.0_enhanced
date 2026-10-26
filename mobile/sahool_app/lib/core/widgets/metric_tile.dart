// SAHOOL — lib/core/widgets/metric_tile.dart
// بلاطة مؤشّر (KPI): تسمية + قيمة + وحدة + حالة اختياريّة. قيمة null تُعرَض
// «غير مقيس» صراحةً — لا صفر ولا «null» ولا رقم مُختلَق.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';

import 'status_chip.dart';

class MetricTile extends StatelessWidget {
  const MetricTile({
    super.key,
    required this.label,
    required this.value,
    this.unit,
    this.icon,
    this.decimals = 1,
    this.status,
    this.caption,
    this.onTap,
  });

  final String label;

  /// القيمة المقيسة؛ null ⇒ «غير مقيس».
  final num? value;
  final String? unit;
  final IconData? icon;
  final int decimals;
  final StatusChip? status;

  /// سطر صغير (المصدر، عمر القراءة…).
  final String? caption;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final measured = value != null;
    final valueText = measured ? fmtNumber(value, decimals: decimals) : kNotMeasured;
    final semantic =
        '$label: $valueText${measured && unit != null ? ' $unit' : ''}';
    final body = Padding(
      padding: const EdgeInsets.all(SahoolSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(children: [
            if (icon != null) ...[
              Icon(icon, size: SahoolSizes.iconSm, color: t.muted),
              const SizedBox(width: SahoolSpacing.xs),
            ],
            Expanded(
              child: Text(label,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: context.textStyles.labelMedium),
            ),
          ]),
          const SizedBox(height: SahoolSpacing.sm),
          Wrap(
            crossAxisAlignment: WrapCrossAlignment.end,
            spacing: SahoolSpacing.xs,
            children: [
              Text(valueText,
                  style: measured
                      ? context.textStyles.headlineSmall
                      : context.textStyles.titleMedium?.copyWith(color: t.muted)),
              if (measured && unit != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 4),
                  child: Text(unit!, style: context.textStyles.bodyMedium),
                ),
            ],
          ),
          if (status != null) ...[
            const SizedBox(height: SahoolSpacing.sm),
            status!,
          ],
          if (caption != null) ...[
            const SizedBox(height: SahoolSpacing.xs),
            Text(caption!, style: context.textStyles.bodySmall),
          ],
        ],
      ),
    );
    return Semantics(
      label: semantic,
      button: onTap != null,
      excludeSemantics: true,
      child: Card(
        clipBehavior: Clip.antiAlias,
        child: onTap == null ? body : InkWell(onTap: onTap, child: body),
      ),
    );
  }
}
