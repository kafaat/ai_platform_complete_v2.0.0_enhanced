// SAHOOL — features/tasks/presentation/tasks_screen.dart
// تبويب «المهام»: شاشة العامل الأولى (الغلاف يفتح عليها للعامل).
//
//  * مجموعات حسب الموعد (متأخّرة/اليوم/القادمة/بلا موعد/المنجزة) أو حسب الحقل.
//  * رقائق ترشيح: الحالة (بعدّاد)، الحقل، «المُسندة إليّ».
//  * سحب البطاقة للإنجاز مع مهلة تراجع؛ «إنجاز» يفتح ورقة ملاحظة + صورة محلّيّة.
//  * التحديث يُبقي القائمة وموضع التمرير، وفشله لافتة فوق آخر بيانات معروفة.
//  * لا زرّ «مهمّة جديدة»: لا نقطة إنشاء يدويّ في الخادم (POST /api/v1/tasks
//    غير موجود) — الشاشة تقول من أين تأتي المهام.
//  * أزرار الكتابة مخفيّة عن المُشاهِد (viewer).
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';
import 'package:sahool_app/features/tasks/data/task_photo_store.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'complete_task_sheet.dart';
import 'task_card.dart';
import 'task_detail_screen.dart';
import 'task_grouping.dart';
import 'tasks_cubit.dart';
import 'tasks_state.dart';

/// من أين تأتي المهام (لا إنشاء يدويّ في الخادم).
const String kTasksOriginAr =
    'تُنشأ المهام على المنصّة من خطط العمليّات (نوافذ الطقس للرشّ والريّ والحصاد) '
    'ومن توصيات المهندس الزراعيّ، ثمّ تُسنَد إلى الفريق. لا يمكن إنشاء مهمّة يدويّاً '
    'من التطبيق بعد. لتسجيل عمل نُفِّذ بلا مهمّة استخدم «سجلّ الأنشطة».';

/// أدوات الصور (قابلة للحقن في الاختبارات).
class TaskPhotoTools {
  const TaskPhotoTools({required this.store, this.pick});
  final TaskPhotoStore store;
  final PhotoPicker? pick;

  static TaskPhotoTools get standard => TaskPhotoTools(
    store: TaskPhotoStore(
      tenantId: () => AuthService.instance.tenantId,
      userId: () => AuthService.instance.userId,
    ),
    pick: cameraPhotoPicker,
  );
}

class TasksScreen extends StatelessWidget {
  const TasksScreen({super.key, this.cubit, this.role, this.photos});

  /// للاختبارات: cubit بواجهات مزيّفة. الافتراضيّ يُنشأ ويُحمَّل هنا.
  final TasksCubit? cubit;
  final String? role;
  final TaskPhotoTools? photos;

  @override
  Widget build(BuildContext context) => BlocProvider<TasksCubit>(
    create: (_) =>
        cubit ?? (TasksCubit(userId: AuthService.instance.userId)..load()),
    child: TasksView(
      canEdit: canMutate(role ?? currentRole()),
      photos: photos ?? TaskPhotoTools.standard,
    ),
  );
}

class TasksView extends StatefulWidget {
  const TasksView({super.key, required this.canEdit, required this.photos});
  final bool canEdit;
  final TaskPhotoTools photos;

  @override
  State<TasksView> createState() => _TasksViewState();
}

class _TasksViewState extends State<TasksView> {
  StreamSubscription<TaskWriteEvent>? _sub;
  final Set<String> _expanded = {};

  /// ورقة الإنجاز مفتوحة ⇒ أخطاؤها تُعرَض داخلها لا في SnackBar تحتها.
  bool _sheetOpen = false;

  /// التفاصيل مفتوحة فوق القائمة ⇒ هي من تعرض نتائج الكتابة (لا رسالة مكرّرة).
  bool _detailOpen = false;

  @override
  void initState() {
    super.initState();
    _sub = context.read<TasksCubit>().events.listen(_onEvent);
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  void _onEvent(TaskWriteEvent e) {
    if (!mounted) return;
    if (_detailOpen) return;
    if (_sheetOpen && e.outcome.isFailed) return;
    final cubit = context.read<TasksCubit>();
    final retry = e.outcome.isFailed && e.action != TaskAction.note
        ? SnackBarAction(
            label: 'إعادة المحاولة',
            onPressed: () => e.action == TaskAction.start
                ? cubit.start(e.taskId)
                : cubit.complete(e.taskId),
          )
        : null;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(e.messageAr), action: retry));
  }

  Future<void> _openComplete(FieldTask task) async {
    final cubit = context.read<TasksCubit>();
    _sheetOpen = true;
    await showAppBottomSheet<WriteOutcome<FieldTask>>(
      context,
      builder: (_) => CompleteTaskSheet(
        title: 'إنجاز المهمّة',
        submitLabel: 'تأكيد الإنجاز',
        existingNotes: task.notes,
        onSubmit: (note) => cubit.complete(task.id, note: note),
        pickPhoto: widget.photos.pick,
        savePhoto: (path) => widget.photos.store.save(task.id, path),
      ),
    );
    _sheetOpen = false;
  }

  void _swipe(FieldTask task) {
    final cubit = context.read<TasksCubit>();
    if (!cubit.swipeComplete(task.id)) return;
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: const Text('ستُنجَز المهمّة خلال ثوانٍ.'),
          duration: cubit.undoWindow,
          action: SnackBarAction(
            label: 'تراجع',
            onPressed: () => cubit.undoSwipe(task.id),
          ),
        ),
      );
  }

  Future<void> _openDetail(FieldTask task) async {
    final cubit = context.read<TasksCubit>();
    _detailOpen = true;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => BlocProvider.value(
          value: cubit,
          child: TaskDetailScreen(
            taskId: task.id,
            canEdit: widget.canEdit,
            photos: widget.photos,
          ),
        ),
      ),
    );
    _detailOpen = false;
  }

  void _showOrigin() => showDialog<void>(
    context: context,
    builder: (c) => AlertDialog(
      title: const Text('من أين تأتي المهام؟'),
      content: const Text(kTasksOriginAr),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(c).pop(),
          child: const Text('حسناً'),
        ),
      ],
    ),
  );

  @override
  Widget build(BuildContext context) {
    final cubit = context.read<TasksCubit>();
    return AppScaffold(
      title: 'المهام',
      actions: [
        AppIconButton(
          icon: Icons.help_outline_rounded,
          tooltip: 'من أين تأتي المهام؟',
          onPressed: _showOrigin,
        ),
        BlocBuilder<TasksCubit, TasksState>(
          buildWhen: (a, b) => a.refreshing != b.refreshing,
          builder: (_, s) => AppIconButton(
            icon: Icons.refresh_rounded,
            tooltip: 'تحديث المهام',
            onPressed: s.refreshing ? null : cubit.load,
          ),
        ),
      ],
      body: BlocBuilder<TasksCubit, TasksState>(
        builder: (context, s) {
          switch (s.load) {
            case TasksLoad.loading:
              return const LoadingState(message: 'جارٍ تحميل المهام…');
            case TasksLoad.failed:
              return ErrorState(error: s.error!, onRetry: cubit.load);
            case TasksLoad.loaded:
              return RefreshIndicator(
                onRefresh: cubit.load,
                child: _list(context, s, cubit),
              );
          }
        },
      ),
    );
  }

  Widget _list(BuildContext context, TasksState s, TasksCubit cubit) {
    final today = cubit.todayKey;
    final visible = s.visible(cubit.userId);
    final groups = s.groupByField
        ? groupByField(visible, s.fieldNames)
        : groupByWhen(visible, today);
    final items = <Widget>[
      _FilterBar(state: s, cubit: cubit),
      if (s.refreshing) const LinearProgressIndicator(),
      if (s.error != null)
        _StaleBanner(message: s.error!.messageAr, loadedAt: s.loadedAt),
    ];

    if (s.tasks.isEmpty) {
      items.add(
        const EmptyState(
          title: 'لا توجد مهام حاليّاً',
          message: kTasksOriginAr,
          icon: Icons.task_alt_rounded,
        ),
      );
    } else if (visible.isEmpty) {
      items.add(
        EmptyState(
          title: 'لا مهام تطابق هذا المرشِّح',
          message: 'غيّر المرشِّح أو اعرض كلّ المهام.',
          icon: Icons.filter_alt_off_outlined,
          actionLabel: 'عرض كلّ المهام',
          onAction: cubit.clearFilters,
        ),
      );
    } else {
      for (final g in groups) {
        final collapsible = g.key == TaskBucket.done.name;
        final open = !collapsible || _expanded.contains(g.key);
        items.add(
          _GroupHeader(
            title: '${g.titleAr} (${g.tasks.length})',
            collapsible: collapsible,
            expanded: open,
            onToggle: () => setState(() {
              if (!_expanded.remove(g.key)) _expanded.add(g.key);
            }),
          ),
        );
        if (open) {
          for (final t in g.tasks) {
            items.add(_card(t, s, today));
          }
        }
      }
      if (s.hasMore) {
        items.add(
          Padding(
            padding: const EdgeInsetsDirectional.all(SahoolSpacing.page),
            child: Column(
              children: [
                Text(
                  s.total != null
                      ? 'يُعرض ${s.tasks.length} من ${s.total} مهمّة.'
                      : 'توجد مهام أخرى لم تُحمَّل بعد.',
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: SahoolSpacing.sm),
                s.loadingMore
                    ? const CircularProgressIndicator()
                    : SecondaryButton(
                        label: 'تحميل المزيد',
                        onPressed: cubit.loadMore,
                      ),
              ],
            ),
          ),
        );
      }
    }
    items.add(const SizedBox(height: SahoolSpacing.xxl));
    return ListView(
      key: const PageStorageKey('tasks-list'),
      physics: const AlwaysScrollableScrollPhysics(),
      children: items,
    );
  }

  Widget _card(FieldTask t, TasksState s, String today) {
    final cubit = context.read<TasksCubit>();
    final busy = s.busy.contains(t.id);
    final undoable = s.undoable.contains(t.id);
    final card = TaskCard(
      key: ValueKey('task-${t.id}'),
      task: t,
      fieldName: fieldLabel(t.fieldId, s.fieldNames),
      todayKey: today,
      canEdit: widget.canEdit,
      busy: busy,
      queued: s.queued.containsKey(t.id),
      undoable: undoable,
      onTap: () => _openDetail(t),
      onStart: () => cubit.start(t.id),
      onComplete: () => _openComplete(t),
      onUndo: () => cubit.undoSwipe(t.id),
    );
    if (!widget.canEdit || t.isDone || busy || undoable) return card;
    final tk = context.tokens;
    return Dismissible(
      key: ValueKey('swipe-${t.id}'),
      direction: DismissDirection.startToEnd,
      confirmDismiss: (_) async {
        _swipe(t);
        return false; // البطاقة تبقى؛ حالتها تتغيّر.
      },
      background: Container(
        margin: const EdgeInsetsDirectional.symmetric(
          horizontal: SahoolSpacing.page,
          vertical: SahoolSpacing.xs + 2,
        ),
        decoration: BoxDecoration(
          color: tk.success.withValues(alpha: 0.18),
          borderRadius: const BorderRadius.all(
            Radius.circular(SahoolRadius.md),
          ),
        ),
        alignment: AlignmentDirectional.centerStart,
        padding: const EdgeInsetsDirectional.only(start: SahoolSpacing.xl),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.check_circle_rounded, color: tk.success),
            const SizedBox(width: SahoolSpacing.sm),
            Text('إنجاز', style: TextStyle(color: tk.ink)),
          ],
        ),
      ),
      child: card,
    );
  }
}

class _GroupHeader extends StatelessWidget {
  const _GroupHeader({
    required this.title,
    required this.collapsible,
    required this.expanded,
    required this.onToggle,
  });
  final String title;
  final bool collapsible;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    if (!collapsible) return ListSectionHeader(title);
    return InkWell(
      onTap: onToggle,
      child: ConstrainedBox(
        constraints: const BoxConstraints(
          minHeight: SahoolSizes.minTouchTarget,
        ),
        child: Row(
          children: [
            Expanded(child: ListSectionHeader(title)),
            Padding(
              padding: const EdgeInsetsDirectional.only(end: SahoolSpacing.lg),
              child: Icon(
                expanded
                    ? Icons.expand_less_rounded
                    : Icons.expand_more_rounded,
                semanticLabel: expanded ? 'طيّ' : 'عرض',
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _StaleBanner extends StatelessWidget {
  const _StaleBanner({required this.message, this.loadedAt});
  final String message;
  final DateTime? loadedAt;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    return Container(
      margin: const EdgeInsetsDirectional.fromSTEB(
        SahoolSpacing.page,
        SahoolSpacing.sm,
        SahoolSpacing.page,
        0,
      ),
      padding: const EdgeInsetsDirectional.all(SahoolSpacing.md),
      decoration: BoxDecoration(
        color: t.warning.withValues(alpha: 0.12),
        borderRadius: const BorderRadius.all(Radius.circular(SahoolRadius.md)),
        border: Border.all(color: t.warning.withValues(alpha: 0.45)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.cloud_off_outlined, color: t.warning),
          const SizedBox(width: SahoolSpacing.sm),
          Expanded(
            child: Text(
              'تعذّر التحديث: $message\nالمعروض من آخر تحميل (${fmtAge(loadedAt)}).',
              style: context.textStyles.bodyMedium,
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterBar extends StatelessWidget {
  const _FilterBar({required this.state, required this.cubit});
  final TasksState state;
  final TasksCubit cubit;

  Future<void> _pickField(BuildContext context) async {
    final ids = state.effective.map((t) => t.fieldId).toSet().toList()
      ..sort(
        (a, b) => fieldLabel(
          a,
          state.fieldNames,
        ).compareTo(fieldLabel(b, state.fieldNames)),
      );
    final chosen = await showAppBottomSheet<String>(
      context,
      builder: (c) => AppSheet(
        title: 'اختر الحقل',
        children: [
          AppListTile(
            title: 'كلّ الحقول',
            icon: state.fieldFilter == null
                ? Icons.radio_button_checked
                : Icons.radio_button_unchecked,
            onTap: () => Navigator.of(c).pop(''),
          ),
          for (final id in ids)
            AppListTile(
              title: fieldLabel(id, state.fieldNames),
              icon: state.fieldFilter == id
                  ? Icons.radio_button_checked
                  : Icons.radio_button_unchecked,
              onTap: () => Navigator.of(c).pop(id),
            ),
        ],
      ),
    );
    if (chosen == null) return;
    cubit.setFieldFilter(chosen.isEmpty ? null : chosen);
  }

  @override
  Widget build(BuildContext context) {
    final showMine =
        cubit.userId != null &&
        state.effective.any((t) => t.assignedTo != null);
    final fieldChosen = state.fieldFilter;
    return Padding(
      padding: const EdgeInsetsDirectional.only(top: SahoolSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsetsDirectional.symmetric(
              horizontal: SahoolSpacing.page,
            ),
            child: Row(
              children: [
                for (final f in StatusFilter.values)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(
                      end: SahoolSpacing.sm,
                    ),
                    child: ChoiceChip(
                      label: Text(
                        '${kStatusFilterLabelAr[f]} (${state.countFor(f)})',
                      ),
                      selected: state.statusFilter == f,
                      onSelected: (_) => cubit.setStatusFilter(f),
                    ),
                  ),
                Padding(
                  padding: const EdgeInsetsDirectional.only(
                    end: SahoolSpacing.sm,
                  ),
                  child: FilterChip(
                    avatar: const Icon(Icons.grid_view_rounded, size: 18),
                    label: Text(
                      fieldChosen == null
                          ? 'كلّ الحقول'
                          : fieldLabel(fieldChosen, state.fieldNames),
                    ),
                    selected: fieldChosen != null,
                    onSelected: (_) => _pickField(context),
                  ),
                ),
                if (showMine)
                  FilterChip(
                    label: const Text('المُسندة إليّ'),
                    selected: state.mineOnly,
                    onSelected: cubit.setMineOnly,
                  ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(
              SahoolSpacing.page,
              SahoolSpacing.sm,
              SahoolSpacing.page,
              0,
            ),
            child: SegmentedButton<bool>(
              segments: const [
                ButtonSegment(
                  value: false,
                  label: Text('حسب الموعد'),
                  icon: Icon(Icons.event_outlined),
                ),
                ButtonSegment(
                  value: true,
                  label: Text('حسب الحقل'),
                  icon: Icon(Icons.grid_view_rounded),
                ),
              ],
              selected: {state.groupByField},
              onSelectionChanged: (v) => cubit.setGroupByField(v.first),
            ),
          ),
        ],
      ),
    );
  }
}
