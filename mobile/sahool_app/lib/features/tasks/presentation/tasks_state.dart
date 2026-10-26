// SAHOOL — features/tasks/presentation/tasks_state.dart
import 'package:flutter/foundation.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';

import 'task_grouping.dart';

enum TasksLoad { loading, loaded, failed }

@immutable
class TasksState {
  const TasksState({
    this.load = TasksLoad.loading,
    this.tasks = const [],
    this.error,
    this.loadedAt,
    this.refreshing = false,
    this.loadingMore = false,
    this.total,
    this.nextCursor,
    this.fieldNames = const {},
    this.busy = const {},
    this.queued = const {},
    this.undoable = const {},
    this.statusFilter = StatusFilter.open,
    this.fieldFilter,
    this.mineOnly = false,
    this.groupByField = false,
  });

  final TasksLoad load;

  /// ما أكّده الخادم (القائمة + تحديثات PATCH المؤكَّدة).
  final List<FieldTask> tasks;

  /// آخر فشل تحميل/تحديث. مع [tasks] غير فارغة يُعرَض لافتةً فوق آخر بيانات
  /// معروفة مع عمرها، لا بدلاً منها.
  final ApiException? error;
  final DateTime? loadedAt;
  final bool refreshing;
  final bool loadingMore;

  /// إجمالي المهام على الخادم (من الترقيم)، وإزاحة الصفحة التالية.
  final int? total;
  final String? nextCursor;
  final Map<String, String> fieldNames;

  /// مهامّ عليها كتابة جارية (يمنع الإرسال المزدوج).
  final Set<String> busy;

  /// نسخ محلّيّة لإجراءات أودِعت صندوق الإرسال (تُعرَض بشارة «بانتظار المزامنة»).
  final Map<String, FieldTask> queued;

  /// مهامّ سُحبت للإنجاز وما زالت في مهلة التراجع (لم يُرسَل شيء بعد).
  final Set<String> undoable;

  final StatusFilter statusFilter;
  final String? fieldFilter;
  final bool mineOnly;
  final bool groupByField;

  bool get hasMore => nextCursor != null;

  /// القائمة كما تُعرَض: نسخة الصندوق تحلّ محلّ نسخة الخادم حتى المزامنة.
  List<FieldTask> get effective => [for (final t in tasks) queued[t.id] ?? t];

  FieldTask? byId(String id) {
    for (final t in effective) {
      if (t.id == id) return t;
    }
    return null;
  }

  List<FieldTask> visible(String? userId) => [
    for (final t in effective)
      if (matchesStatus(t, statusFilter) &&
          (fieldFilter == null || t.fieldId == fieldFilter) &&
          (!mineOnly || (userId != null && t.assignedTo == userId)))
        t,
  ];

  int countFor(StatusFilter f) =>
      effective.where((t) => matchesStatus(t, f)).length;

  static const _unset = Object();

  TasksState copyWith({
    TasksLoad? load,
    List<FieldTask>? tasks,
    Object? error = _unset,
    DateTime? loadedAt,
    bool? refreshing,
    bool? loadingMore,
    Object? total = _unset,
    Object? nextCursor = _unset,
    Map<String, String>? fieldNames,
    Set<String>? busy,
    Map<String, FieldTask>? queued,
    Set<String>? undoable,
    StatusFilter? statusFilter,
    Object? fieldFilter = _unset,
    bool? mineOnly,
    bool? groupByField,
  }) => TasksState(
    load: load ?? this.load,
    tasks: tasks ?? this.tasks,
    error: identical(error, _unset) ? this.error : error as ApiException?,
    loadedAt: loadedAt ?? this.loadedAt,
    refreshing: refreshing ?? this.refreshing,
    loadingMore: loadingMore ?? this.loadingMore,
    total: identical(total, _unset) ? this.total : total as int?,
    nextCursor: identical(nextCursor, _unset)
        ? this.nextCursor
        : nextCursor as String?,
    fieldNames: fieldNames ?? this.fieldNames,
    busy: busy ?? this.busy,
    queued: queued ?? this.queued,
    undoable: undoable ?? this.undoable,
    statusFilter: statusFilter ?? this.statusFilter,
    fieldFilter: identical(fieldFilter, _unset)
        ? this.fieldFilter
        : fieldFilter as String?,
    mineOnly: mineOnly ?? this.mineOnly,
    groupByField: groupByField ?? this.groupByField,
  );
}

/// إجراء على مهمّة.
enum TaskAction { start, complete, note }

/// نتيجة كتابة تُبَثّ للواجهة (SnackBar) — منفصلة عن الحالة كي لا تتكرّر.
@immutable
class TaskWriteEvent {
  const TaskWriteEvent(this.taskId, this.action, this.outcome);
  final String taskId;
  final TaskAction action;
  final WriteOutcome<FieldTask> outcome;

  String get messageAr {
    if (outcome.isFailed) return outcome.messageAr;
    if (outcome.isQueued) {
      return 'لا اتّصال — حُفظ الإجراء على هذا الجهاز وسيُرسَل تلقائيّاً عند عودة الشبكة.';
    }
    return switch (action) {
      TaskAction.start => 'بدأت المهمّة.',
      TaskAction.complete => 'أُنجزت المهمّة.',
      TaskAction.note => 'حُفظت الملاحظة.',
    };
  }
}
