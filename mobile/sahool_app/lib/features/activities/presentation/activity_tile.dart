// SAHOOL — features/activities/presentation/activity_tile.dart
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/activities/data/field_activity.dart';

import 'activity_labels.dart';

class ActivityTile extends StatelessWidget {
  const ActivityTile({
    super.key,
    required this.activity,
    this.fieldName,
    this.onTap,
  });

  final FieldActivity activity;

  /// يُعرَض في موجز المزرعة (عدّة حقول).
  final String? fieldName;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final a = activity;
    final scheme = Theme.of(context).colorScheme;
    return Card(
      margin: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.page,
        vertical: SahoolSpacing.xs,
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minHeight: SahoolSizes.minTouchTarget,
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(activityTypeIcon(a.type), color: scheme.primary),
                const SizedBox(width: SahoolSpacing.md),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        a.titleAr == null
                            ? activityTypeAr(a.type)
                            : '${activityTypeAr(a.type)} — ${a.titleAr}',
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: context.textStyles.titleSmall,
                      ),
                      if (fieldName != null)
                        Text(
                          fieldName!,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: context.textStyles.bodySmall?.copyWith(
                            color: t.muted,
                          ),
                        ),
                      const SizedBox(height: SahoolSpacing.xs),
                      Text(
                        activityDateLine(a),
                        style: context.textStyles.bodySmall?.copyWith(
                          color: t.muted,
                        ),
                      ),
                      if (a.notes != null) ...[
                        const SizedBox(height: SahoolSpacing.xs),
                        Text(
                          a.notes!,
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: context.textStyles.bodyMedium,
                        ),
                      ],
                      const SizedBox(height: SahoolSpacing.sm),
                      Wrap(
                        spacing: SahoolSpacing.sm,
                        runSpacing: SahoolSpacing.xs,
                        children: [
                          StatusChip(
                            label: activityStatusAr(a.status),
                            tone: activityStatusTone(a.status),
                          ),
                          if (a.pendingSync)
                            const StatusChip(
                              label: 'بانتظار المزامنة',
                              tone: StatusTone.info,
                              icon: Icons.cloud_upload_outlined,
                            ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
