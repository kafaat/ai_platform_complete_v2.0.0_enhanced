// SAHOOL — lib/core/widgets/status_chip.dart
// رقاقة حالة: لون + أيقونة + نصّ معاً (لا يُرمَّز معنى باللون وحده — عمى الألوان
// وضوء الشمس).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

enum StatusTone { success, warning, danger, info, neutral }

class StatusChip extends StatelessWidget {
  const StatusChip({
    super.key,
    required this.label,
    this.tone = StatusTone.neutral,
    this.icon,
  });

  final String label;
  final StatusTone tone;

  /// يُشتقّ من [tone] إن لم يُمرَّر.
  final IconData? icon;

  static IconData defaultIcon(StatusTone tone) => switch (tone) {
        StatusTone.success => Icons.check_circle_outline_rounded,
        StatusTone.warning => Icons.warning_amber_rounded,
        StatusTone.danger => Icons.error_outline_rounded,
        StatusTone.info => Icons.info_outline_rounded,
        StatusTone.neutral => Icons.circle_outlined,
      };

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final color = switch (tone) {
      StatusTone.success => t.success,
      StatusTone.warning => t.warning,
      StatusTone.danger => t.danger,
      StatusTone.info => t.info,
      StatusTone.neutral => t.muted,
    };
    return Semantics(
      label: label,
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsetsDirectional.symmetric(
            horizontal: SahoolSpacing.sm + 2, vertical: SahoolSpacing.xs),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: const BorderRadius.all(Radius.circular(SahoolRadius.pill)),
          border: Border.all(color: color.withValues(alpha: 0.45)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon ?? defaultIcon(tone), size: SahoolSizes.iconSm, color: color),
            const SizedBox(width: SahoolSpacing.xs),
            Flexible(
              child: Text(label,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                      color: color,
                      fontSize: SahoolType.caption,
                      fontWeight: SahoolType.semibold)),
            ),
          ],
        ),
      ),
    );
  }
}
