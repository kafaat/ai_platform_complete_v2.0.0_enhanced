// SAHOOL — lib/core/widgets/section_card.dart
// بطاقة قسم: عنوان + أيقونة + إجراء اختياريّ + محتوى. حدّ شعريّ بلا ظلّ (رموز
// الويب). الحشوات اتّجاهيّة (RTL).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

class SectionCard extends StatelessWidget {
  const SectionCard({
    super.key,
    required this.child,
    this.title,
    this.icon,
    this.trailing,
    this.onTap,
    this.padding = const EdgeInsets.all(SahoolSpacing.lg),
  });

  final String? title;
  final IconData? icon;
  final Widget? trailing;
  final Widget child;
  final VoidCallback? onTap;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final content = Padding(
      padding: padding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (title != null) ...[
            Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, size: SahoolSizes.iconMd, color: t.muted),
                  const SizedBox(width: SahoolSpacing.sm),
                ],
                Expanded(
                  child: Semantics(
                    header: true,
                    child: Text(title!, style: context.textStyles.titleMedium),
                  ),
                ),
                if (trailing != null) trailing!,
              ],
            ),
            const SizedBox(height: SahoolSpacing.md),
          ],
          child,
        ],
      ),
    );
    return Card(
      clipBehavior: Clip.antiAlias,
      child: onTap == null
          ? content
          : InkWell(onTap: onTap, child: content),
    );
  }
}
