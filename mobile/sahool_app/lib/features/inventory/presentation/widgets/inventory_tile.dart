// SAHOOL — features/inventory/presentation/widgets/inventory_tile.dart
// عنصر قائمة برقاقات حالة تحت النصّ لا في الذيل: ListTile يرمي «Trailing widget
// consumes the entire tile width» حين تكبر الرقاقة (خطّ 1.3× على شاشة 360dp)،
// وهنا يلتفّ النصّ والرقاقات بدل أن يفيضا. هدف لمس ≥56dp وسهم يعكس اتّجاهه في RTL.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

class InventoryTile extends StatelessWidget {
  const InventoryTile({
    super.key,
    required this.title,
    this.subtitle,
    this.icon,
    this.iconColor,
    this.chips = const [],
    this.onTap,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final Color? iconColor;
  final List<Widget> chips;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final color = iconColor ?? t.muted;
    final body = ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 56),
      child: Padding(
        padding: const EdgeInsetsDirectional.symmetric(
          horizontal: SahoolSpacing.lg,
          vertical: SahoolSpacing.md,
        ),
        child: Row(
          children: [
            if (icon != null) ...[
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: SahoolRadius.mdAll,
                ),
                child: Icon(icon, color: color),
              ),
              const SizedBox(width: SahoolSpacing.md),
            ],
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(title, style: context.textStyles.titleSmall),
                  if (subtitle != null) ...[
                    const SizedBox(height: SahoolSpacing.xxs),
                    Text(subtitle!, style: context.textStyles.bodySmall),
                  ],
                  if (chips.isNotEmpty) ...[
                    const SizedBox(height: SahoolSpacing.sm),
                    Wrap(
                      spacing: SahoolSpacing.sm,
                      runSpacing: SahoolSpacing.xs,
                      children: chips,
                    ),
                  ],
                ],
              ),
            ),
            if (onTap != null) ...[
              const SizedBox(width: SahoolSpacing.sm),
              Icon(Icons.chevron_right_rounded, color: t.muted),
            ],
          ],
        ),
      ),
    );
    return onTap == null ? body : InkWell(onTap: onTap, child: body);
  }
}
