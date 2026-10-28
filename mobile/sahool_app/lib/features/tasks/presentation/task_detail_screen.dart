// SAHOOL — features/tasks/presentation/task_detail_screen.dart
// تفاصيل مهمّة: كلّ ما يرسله الخادم بصدق (الغائب «غير مقيس»/«—»)، الإجراءات
// (بدء/إنجاز/ملاحظة)، وصور الجهاز مع تنبيه أنّ رفعها غير متاح.
//
// لا GET لمهمّة واحدة على الخادم؛ الشاشة تقرأ المهمّة من [TasksCubit] (القائمة
// نفسها حين تُفتح منها، أو تحميل جديد حين تُفتح من رابط عميق).
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';
import 'package:sahool_app/features/tasks/data/task_photo_store.dart';

import 'complete_task_sheet.dart';
import 'irrigation_observations_screen.dart';
import 'task_grouping.dart';
import 'task_labels.dart';
import 'tasks_cubit.dart';
import 'tasks_screen.dart' show TaskPhotoTools;
import 'tasks_state.dart';

class TaskDetailScreen extends StatefulWidget {
  const TaskDetailScreen({
    super.key,
    required this.taskId,
    required this.canEdit,
    required this.photos,
  });

  final String taskId;
  final bool canEdit;
  final TaskPhotoTools photos;

  @override
  State<TaskDetailScreen> createState() => _TaskDetailScreenState();
}

class _TaskDetailScreenState extends State<TaskDetailScreen> {
  late Future<List<File>> _photos;
  bool _sheetOpen = false;

  @override
  void initState() {
    super.initState();
    _photos = _loadPhotos();
    _sub = context.read<TasksCubit>().events.listen((e) {
      if (!mounted || e.taskId != widget.taskId) return;
      if (_sheetOpen && e.outcome.isFailed) return;
      ScaffoldMessenger.of(context)
        ..hideCurrentSnackBar()
        ..showSnackBar(SnackBar(content: Text(e.messageAr)));
    });
  }

  StreamSubscription<TaskWriteEvent>? _sub;

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<List<File>> _loadPhotos() =>
      widget.photos.store.photosFor(widget.taskId).catchError((_) => <File>[]);

  Future<void> _sheet({
    required String title,
    required String submitLabel,
    required bool noteRequired,
    required Future<WriteOutcome<FieldTask>?> Function(String) onSubmit,
    required FieldTask task,
  }) async {
    _sheetOpen = true;
    final r = await showAppBottomSheet<WriteOutcome<FieldTask>>(
      context,
      builder: (_) => CompleteTaskSheet(
        title: title,
        submitLabel: submitLabel,
        noteRequired: noteRequired,
        existingNotes: task.notes,
        onSubmit: onSubmit,
        pickPhoto: widget.photos.pick,
        savePhoto: (p) => widget.photos.store.save(task.id, p),
      ),
    );
    _sheetOpen = false;
    if (r != null && mounted) {
      setState(() {
        _photos = _loadPhotos();
      });
    }
  }

  Future<void> _addPhotoOnly() async {
    final pick = widget.photos.pick;
    if (pick == null) return;
    try {
      final path = await pick();
      if (path == null) return;
      await widget.photos.store.save(widget.taskId, path);
      if (!mounted) return;
      setState(() {
        _photos = _loadPhotos();
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('حُفظت الصورة على هذا الجهاز فقط.')),
      );
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('تعذّر التقاط الصورة أو حفظها.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<TasksCubit>();
    return AppScaffold(
      title: 'تفاصيل المهمّة',
      body: BlocBuilder<TasksCubit, TasksState>(
        builder: (context, s) {
          if (s.load == TasksLoad.loading) {
            return const LoadingState(message: 'جارٍ تحميل المهمّة…');
          }
          if (s.load == TasksLoad.failed) {
            return ErrorState(error: s.error!, onRetry: cubit.load);
          }
          final task = s.byId(widget.taskId);
          if (task == null) {
            return const EmptyState(
              title: 'المهمّة غير موجودة',
              message: 'لم تعد هذه المهمّة ضمن مهامّ حسابك، أو لم تُحمَّل بعد.',
              icon: Icons.search_off_rounded,
            );
          }
          return _body(context, s, task, cubit);
        },
      ),
    );
  }

  Widget _body(
    BuildContext context,
    TasksState s,
    FieldTask task,
    TasksCubit cubit,
  ) {
    final tk = context.tokens;
    final busy = s.busy.contains(task.id);
    final today = cubit.todayKey;
    final bucket = bucketOf(task, today);
    final late = overdueDays(task, today);
    return ListView(
      padding: const EdgeInsetsDirectional.all(SahoolSpacing.page),
      children: [
        Row(
          children: [
            Icon(
              taskTypeIcon(task.type),
              size: SahoolSizes.iconLg,
              color: Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(width: SahoolSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    taskTypeAr(task.type),
                    style: context.textStyles.titleLarge,
                  ),
                  Text(
                    fieldLabel(task.fieldId, s.fieldNames),
                    style: context.textStyles.bodyMedium?.copyWith(
                      color: tk.muted,
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
            if (late != null)
              StatusChip(label: 'متأخّرة $late يوم', tone: StatusTone.danger),
            if (bucket == TaskBucket.today)
              const StatusChip(label: 'اليوم', tone: StatusTone.warning),
            if (s.queued.containsKey(task.id))
              const StatusChip(
                label: 'بانتظار المزامنة',
                tone: StatusTone.info,
                icon: Icons.cloud_upload_outlined,
              ),
          ],
        ),
        const SizedBox(height: SahoolSpacing.lg),
        SectionCard(
          title: 'التفاصيل',
          icon: Icons.info_outline_rounded,
          child: Column(
            children: [
              _InfoRow('الموعد المقترح', fmtIsoDate(task.dateKey)),
              _InfoRow('الأولويّة', priorityAr(task.priority) ?? '—'),
              _InfoRow(
                'المدّة التقديريّة',
                fmtDurationMin(task.estimatedDurationMin),
              ),
              _InfoRow('الكلفة التقديريّة', fmtCostUsd(task.estimatedCostUsd)),
              _InfoRow('مُسندة إلى', task.assignedTo ?? 'غير مُسندة'),
              _InfoRow('أُنشئت', fmtDateTime(task.createdAt)),
              if (task.completedAt != null)
                _InfoRow('أُنجزت', fmtDateTime(task.completedAt)),
            ],
          ),
        ),
        const SizedBox(height: SahoolSpacing.md),
        SectionCard(
          title: 'الملاحظات',
          icon: Icons.notes_rounded,
          child: Text(
            task.notes ?? 'لا ملاحظات.',
            style: context.textStyles.bodyMedium,
          ),
        ),
        const SizedBox(height: SahoolSpacing.md),
        SectionCard(
          title: 'الصور',
          icon: Icons.photo_library_outlined,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (task.photoUrl != null) ...[
                Text(
                  'مرجع صورة مسجَّل على الخادم:',
                  style: context.textStyles.bodySmall?.copyWith(
                    color: tk.muted,
                  ),
                ),
                SelectableText(task.photoUrl!),
                const SizedBox(height: SahoolSpacing.sm),
              ],
              FutureBuilder<List<File>>(
                future: _photos,
                builder: (_, snap) {
                  final files = snap.data ?? const <File>[];
                  if (files.isEmpty) {
                    return Text(
                      'لا صور على هذا الجهاز لهذه المهمّة.',
                      style: context.textStyles.bodyMedium,
                    );
                  }
                  return Wrap(
                    spacing: SahoolSpacing.sm,
                    runSpacing: SahoolSpacing.sm,
                    children: [
                      for (final f in files)
                        ClipRRect(
                          borderRadius: const BorderRadius.all(
                            Radius.circular(SahoolRadius.sm),
                          ),
                          child: Image.file(
                            f,
                            width: 88,
                            height: 88,
                            fit: BoxFit.cover,
                            errorBuilder: (_, _, _) => const SizedBox(
                              width: 88,
                              height: 88,
                              child: Icon(Icons.image_not_supported_outlined),
                            ),
                          ),
                        ),
                    ],
                  );
                },
              ),
              const SizedBox(height: SahoolSpacing.sm),
              Text(
                TaskPhotoStore.notice,
                style: context.textStyles.bodySmall?.copyWith(color: tk.muted),
              ),
              if (widget.canEdit && widget.photos.pick != null) ...[
                const SizedBox(height: SahoolSpacing.sm),
                SecondaryButton(
                  label: 'التقاط صورة',
                  icon: Icons.photo_camera_outlined,
                  onPressed: _addPhotoOnly,
                ),
              ],
            ],
          ),
        ),
        if (task.fieldId.isNotEmpty) ...[
          const SizedBox(height: SahoolSpacing.md),
          SecondaryButton(
            label: 'إفادات الريّ والكشف الميداني',
            icon: Icons.water_drop_outlined,
            onPressed: () => Navigator.of(context).push<void>(
              MaterialPageRoute(builder: (_) => IrrigationObservationsScreen(
                taskId: task.id,
                fieldId: task.fieldId,
                canEdit: widget.canEdit,
              )),
            ),
          ),
        ],
        if (widget.canEdit) ...[
          const SizedBox(height: SahoolSpacing.lg),
          if (task.status == TaskStatus.pending) ...[
            SecondaryButton(
              label: 'بدء المهمّة',
              icon: Icons.play_arrow_rounded,
              onPressed: busy ? null : () => cubit.start(task.id),
            ),
            const SizedBox(height: SahoolSpacing.sm),
          ],
          if (task.isOpen) ...[
            PrimaryButton(
              label: 'إنجاز المهمّة',
              icon: Icons.check_rounded,
              loading: busy,
              onPressed: busy
                  ? null
                  : () => _sheet(
                      title: 'إنجاز المهمّة',
                      submitLabel: 'تأكيد الإنجاز',
                      noteRequired: false,
                      task: task,
                      onSubmit: (n) => cubit.complete(task.id, note: n),
                    ),
            ),
            const SizedBox(height: SahoolSpacing.sm),
          ],
          SecondaryButton(
            label: 'إضافة ملاحظة',
            icon: Icons.edit_note_rounded,
            onPressed: busy
                ? null
                : () => _sheet(
                    title: 'ملاحظة على المهمّة',
                    submitLabel: 'حفظ الملاحظة',
                    noteRequired: true,
                    task: task,
                    onSubmit: (n) => cubit.addNote(task.id, n),
                  ),
          ),
        ],
        const SizedBox(height: SahoolSpacing.xxl),
      ],
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsetsDirectional.symmetric(vertical: SahoolSpacing.xs),
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          flex: 2,
          child: Text(
            label,
            style: context.textStyles.bodyMedium?.copyWith(
              color: context.tokens.muted,
            ),
          ),
        ),
        const SizedBox(width: SahoolSpacing.sm),
        Expanded(
          flex: 3,
          child: Text(
            value,
            textAlign: TextAlign.end,
            style: context.textStyles.bodyMedium,
          ),
        ),
      ],
    ),
  );
}
