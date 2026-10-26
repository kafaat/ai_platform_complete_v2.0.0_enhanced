// SAHOOL — features/alerts/presentation/alert_tile.dart
// بطاقة تنبيه في الصندوق: خطورة + حالة + عنوان + رسالة مختصرة + عمر + إقرار.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

import '../data/alert_models.dart';
import 'alert_visuals.dart';

class AlertTile extends StatelessWidget {
  const AlertTile({
    super.key,
    required this.alert,
    this.onTap,
    this.onAcknowledge,
    this.acknowledging = false,
    this.showField = true,
  });

  final AlertItem alert;
  final VoidCallback? onTap;

  /// null ⇒ لا زرّ إقرار (دور بلا صلاحيّة أو تنبيه غير نشط).
  final VoidCallback? onAcknowledge;
  final bool acknowledging;
  final bool showField;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final meta = <String>[
      if (showField && alert.fieldId != null) 'الحقل: ${alert.fieldId}',
      if (alert.createdAt != null) fmtAge(alert.createdAt!.toLocal()),
    ].join(' · ');
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(SahoolSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Wrap(
                spacing: SahoolSpacing.sm,
                runSpacing: SahoolSpacing.xs,
                children: [
                  severityChip(alert.severity),
                  if (!alert.isActive) alertStatusChip(alert),
                ],
              ),
              const SizedBox(height: SahoolSpacing.sm),
              Text(
                alert.displayTitle,
                style: context.textStyles.titleMedium?.copyWith(
                  color: alert.isActive ? null : t.muted,
                ),
              ),
              if (alert.messageAr != null) ...[
                const SizedBox(height: SahoolSpacing.xs),
                Text(
                  alert.messageAr!,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: context.textStyles.bodyMedium,
                ),
              ],
              if (meta.isNotEmpty) ...[
                const SizedBox(height: SahoolSpacing.xs),
                Text(
                  meta,
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              ],
              if (onAcknowledge != null && alert.isActive) ...[
                const SizedBox(height: SahoolSpacing.sm),
                Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: SecondaryButton(
                    label: acknowledging ? 'جارٍ الإقرار…' : 'إقرار',
                    icon: Icons.done_rounded,
                    expand: false,
                    onPressed: acknowledging ? null : onAcknowledge,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
