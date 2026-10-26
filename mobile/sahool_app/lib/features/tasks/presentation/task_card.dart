// SAHOOL — features/tasks/presentation/task_card.dart
// بطاقة مهمّة للعامل في الحقل: نوع كبير واضح، الحقل، الموعد بلغة اليوم
// (اليوم/متأخّرة N يوم)، حالة بلون + أيقونة + نصّ، وأزرار ≥48dp.
// كلّ نصّ داخل Expanded/Wrap فلا فيض مع الأسماء العربيّة الطويلة أو الخطّ الكبير.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';

import 'task_grouping.dart';
import 'task_labels.dart';

class TaskCard extends StatelessWidget {
  const TaskCard({
    super.key,
    required this.task,
    required this.fieldName,
    required this.todayKey,
    required this.canEdit,
    this.busy = false,
    this.queued = false,
    this.undoable = false,
    this.onTap,
    this.onStart,
    this.onComplete,
    this.onUndo,
  });

  final FieldTask task;
  final String fieldName;
  final String todayKey;
  final bool canEdit;
  final bool busy;
  final bool queued;
  final bool undoable;
  final VoidCallback? onTap;
  final VoidCallback? onStart;
  final VoidCallback? onComplete;
  final VoidCallback? onUndo;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final scheme = Theme.of(context).colorScheme;
    final bucket = bucketOf(task, todayKey);
    final p = task.priority;
    final notes = task.notes;
    return Card(
      margin: const EdgeInsetsDirectional.symmetric(
        horizontal: SahoolSpacing.page,
        vertical: SahoolSpacing.xs + 2,
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsetsDirectional.all(SahoolSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    width: SahoolSizes.minTouchTarget - 4,
                    height: SahoolSizes.minTouchTarget - 4,
                    decoration: BoxDecoration(
                      color: scheme.primary.withValues(alpha: 0.10),
                      borderRadius: const BorderRadius.all(
                        Radius.circular(SahoolRadius.md),
                      ),
                    ),
                    child: Icon(
                      taskTypeIcon(task.type),
                      color: scheme.primary,
                      size: SahoolSizes.iconMd,
                    ),
                  ),
                  const SizedBox(width: SahoolSpacing.md),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          taskTypeAr(task.type),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: context.textStyles.titleMedium?.copyWith(
                            fontWeight: SahoolType.bold,
                          ),
                        ),
                        const SizedBox(height: SahoolSpacing.xxs),
                        Text(
                          fieldName,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: context.textStyles.bodyMedium?.copyWith(
                            color: t.muted,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: SahoolSpacing.md),
              Wrap(
                spacing: SahoolSpacing.sm,
                runSpacing: SahoolSpacing.sm,
                children: [
                  StatusChip(
                    label: taskStatusAr(task.status),
                    tone: taskStatusTone(task.status),
                  ),
                  _whenChip(bucket),
                  if (p != null && p <= 2)
                    StatusChip(
                      label: 'أولويّة ${priorityAr(p)}',
                      tone: p == 1 ? StatusTone.danger : StatusTone.warning,
                      icon: Icons.priority_high_rounded,
                    ),
                  if (queued)
                    const StatusChip(
                      label: 'بانتظار المزامنة',
                      tone: StatusTone.info,
                      icon: Icons.cloud_upload_outlined,
                    ),
                ],
              ),
              if (task.estimatedDurationMin != null) ...[
                const SizedBox(height: SahoolSpacing.sm),
                Text(
                  'المدّة التقديريّة: ${fmtDurationMin(task.estimatedDurationMin)}',
                  style: context.textStyles.bodySmall?.copyWith(color: t.muted),
                ),
              ],
              if (notes != null) ...[
                const SizedBox(height: SahoolSpacing.sm),
                Text(
                  notes,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: context.textStyles.bodyMedium,
                ),
              ],
              if (canEdit && undoable) ...[
                const SizedBox(height: SahoolSpacing.md),
                Row(
                  children: [
                    Icon(
                      Icons.hourglass_top_rounded,
                      size: SahoolSizes.iconSm,
                      color: t.info,
                    ),
                    const SizedBox(width: SahoolSpacing.sm),
                    Expanded(
                      child: Text(
                        'ستُنجَز خلال ثوانٍ…',
                        style: context.textStyles.bodyMedium,
                      ),
                    ),
                    TextButton(
                      onPressed: onUndo,
                      style: TextButton.styleFrom(
                        minimumSize: const Size(
                          SahoolSizes.minTouchTarget,
                          SahoolSizes.minTouchTarget,
                        ),
                      ),
                      child: const Text('تراجع'),
                    ),
                  ],
                ),
              ] else if (canEdit && task.isOpen) ...[
                const SizedBox(height: SahoolSpacing.md),
                Row(
                  children: [
                    if (task.status == TaskStatus.pending) ...[
                      Expanded(
                        child: SecondaryButton(
                          label: 'بدء',
                          icon: Icons.play_arrow_rounded,
                          onPressed: busy ? null : onStart,
                        ),
                      ),
                      const SizedBox(width: SahoolSpacing.sm),
                    ],
                    Expanded(
                      child: PrimaryButton(
                        label: 'إنجاز',
                        icon: Icons.check_rounded,
                        loading: busy,
                        onPressed: busy ? null : onComplete,
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _whenChip(TaskBucket bucket) {
    switch (bucket) {
      case TaskBucket.overdue:
        final n = overdueDays(task, todayKey);
        return StatusChip(
          label: n == null ? 'متأخّرة' : 'متأخّرة $n يوم',
          tone: StatusTone.danger,
          icon: Icons.event_busy_outlined,
        );
      case TaskBucket.today:
        return const StatusChip(
          label: 'اليوم',
          tone: StatusTone.warning,
          icon: Icons.today_outlined,
        );
      case TaskBucket.upcoming:
        return StatusChip(
          label: fmtIsoDate(task.dateKey),
          tone: StatusTone.neutral,
          icon: Icons.event_outlined,
        );
      case TaskBucket.undated:
        return const StatusChip(
          label: 'بلا موعد',
          tone: StatusTone.neutral,
          icon: Icons.event_note_outlined,
        );
      case TaskBucket.done:
        return StatusChip(
          label: task.completedAt != null
              ? fmtDate(task.completedAt)
              : fmtIsoDate(task.dateKey),
          tone: StatusTone.neutral,
          icon: Icons.event_available_outlined,
        );
    }
  }
}
