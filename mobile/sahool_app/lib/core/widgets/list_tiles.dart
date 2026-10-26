// SAHOOL — lib/core/widgets/list_tiles.dart
// أنماط عناصر القوائم: ارتفاع ≥56dp، أيقونة قائدة في حاوية، وسهم ذيليّ يعكس
// اتّجاهه تلقائيّاً في RTL (Icons.chevron_right يحمل matchTextDirection).
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

class AppListTile extends StatelessWidget {
  const AppListTile({
    super.key,
    required this.title,
    this.subtitle,
    this.icon,
    this.iconColor,
    this.trailing,
    this.onTap,
    this.showChevron,
  });

  final String title;
  final String? subtitle;
  final IconData? icon;
  final Color? iconColor;
  final Widget? trailing;
  final VoidCallback? onTap;

  /// افتراضيّاً يظهر السهم حين يكون العنصر قابلاً للفتح ولا ذيل آخر.
  final bool? showChevron;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final chevron = showChevron ?? (onTap != null && trailing == null);
    return ListTile(
      onTap: onTap,
      leading: icon == null
          ? null
          : Container(
              width: 40,
              height: 40,
              decoration: BoxDecoration(
                color: (iconColor ?? t.muted).withValues(alpha: 0.12),
                borderRadius: SahoolRadius.mdAll,
              ),
              child: Icon(icon, color: iconColor ?? t.muted),
            ),
      title: Text(title, style: context.textStyles.titleSmall),
      subtitle: subtitle == null
          ? null
          : Text(subtitle!, style: context.textStyles.bodySmall),
      trailing: trailing ??
          (chevron ? Icon(Icons.chevron_right_rounded, color: t.muted) : null),
    );
  }
}

/// عنوان مجموعة داخل قائمة.
class ListSectionHeader extends StatelessWidget {
  const ListSectionHeader(this.title, {super.key});
  final String title;

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsetsDirectional.fromSTEB(
            SahoolSpacing.lg, SahoolSpacing.xl, SahoolSpacing.lg, SahoolSpacing.sm),
        child: Semantics(
          header: true,
          child: Text(title,
              style: context.textStyles.labelLarge
                  ?.copyWith(color: context.tokens.muted)),
        ),
      );
}
