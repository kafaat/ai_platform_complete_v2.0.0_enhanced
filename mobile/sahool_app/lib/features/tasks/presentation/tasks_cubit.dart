// SAHOOL — features/tasks/presentation/tasks_cubit.dart
// حالة قائمة المهام وكتاباتها.
//
// إصلاحات عن الشاشة القديمة:
//  * تغيير الحالة كان يستبدل القائمة بمؤشّر تحميل ويُعيد جلبها كاملةً فيضيع موضع
//    التمرير. الآن تُستبدَل المهمّة وحدها بما ردّه الخادم.
//  * لا إرسال مزدوج: مهمّة عليها كتابة جارية ([TasksState.busy]) تتجاهل الضغطة الثانية.
//  * مفتاح Idempotency-Key ثابت لكلّ نيّة عبر الإعادات ([IntentKeys]).
//  * بلا اتّصال ⇒ صندوق الإرسال؛ لا عرض محلّيّ إلّا إن أكّد الإيداع.
import 'dart:async';

import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/features/fields/data/fields_api.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';

import 'task_grouping.dart';
import 'task_labels.dart';
import 'tasks_state.dart';

class TasksCubit extends Cubit<TasksState> {
  TasksCubit({
    TasksApi? api,
    FieldsApi? fieldsApi,
    OfflineOutbox? outbox,
    bool Function()? isOnline,
    IntentKeys? keys,
    this.userId,
    DateTime Function()? clock,
    this.undoWindow = const Duration(seconds: 5),
    this.pageSize = 200,
  }) : _api = api ?? TasksApi.instance,
       _fieldsApi = fieldsApi ?? FieldsApi.instance,
       _outbox = outbox,
       _isOnline = isOnline ?? (() => ConnectivityStatus.instance.isOnline),
       _keys = keys ?? IntentKeys(),
       _clock = clock ?? DateTime.now,
       super(const TasksState());

  final TasksApi _api;
  final FieldsApi _fieldsApi;

  /// null ⇒ [OfflineOutbox.instance] وقت الكتابة (يستبدله وكيل المزامنة).
  final OfflineOutbox? _outbox;
  final bool Function() _isOnline;
  final IntentKeys _keys;
  final DateTime Function() _clock;

  /// المستخدم الحاليّ لمرشِّح «مهامي» (assigned_to).
  final String? userId;
  final Duration undoWindow;
  final int pageSize;

  final Map<String, Timer> _undoTimers = {};
  final StreamController<TaskWriteEvent> _events =
      StreamController<TaskWriteEvent>.broadcast();

  /// نتائج الكتابات للواجهة (SnackBar).
  Stream<TaskWriteEvent> get events => _events.stream;

  String get todayKey => localDateKey(_clock());

  void _emit(TasksState s) {
    if (!isClosed) emit(s);
  }

  // ── القراءة ────────────────────────────────────────────────────────

  /// التحميل الأوّل (مؤشّر كامل) أو التحديث (يُبقي القائمة ظاهرة).
  Future<void> load() async {
    final hasData = state.tasks.isNotEmpty || state.load == TasksLoad.loaded;
    _emit(
      hasData
          ? state.copyWith(refreshing: true)
          : state.copyWith(load: TasksLoad.loading, error: null),
    );
    final names = _loadFieldNames();
    try {
      final page = await _api.fetchTaskPage(limit: pageSize);
      final fieldNames = await names;
      // نسخة الصندوق تسقط حين يُظهر الخادم الحالة نفسها (وصلت المزامنة).
      final queued = Map<String, FieldTask>.of(state.queued)
        ..removeWhere(
          (id, local) =>
              page.tasks.any((t) => t.id == id && t.status == local.status),
        );
      _emit(
        state.copyWith(
          load: TasksLoad.loaded,
          tasks: page.tasks,
          error: null,
          loadedAt: _clock(),
          refreshing: false,
          total: page.total,
          nextCursor: page.nextCursor,
          fieldNames: fieldNames ?? state.fieldNames,
          queued: queued,
        ),
      );
    } catch (e) {
      final err = ApiException.from(e);
      _emit(
        hasData
            ? state.copyWith(refreshing: false, error: err)
            : state.copyWith(load: TasksLoad.failed, error: err),
      );
    }
  }

  /// الصفحة التالية (الخادم يقصر الصفحة إلى 500).
  Future<void> loadMore() async {
    final cursor = int.tryParse(state.nextCursor ?? '');
    if (cursor == null || state.loadingMore) return;
    _emit(state.copyWith(loadingMore: true));
    try {
      final page = await _api.fetchTaskPage(limit: pageSize, offset: cursor);
      final seen = state.tasks.map((t) => t.id).toSet();
      _emit(
        state.copyWith(
          loadingMore: false,
          tasks: [
            ...state.tasks,
            ...page.tasks.where((t) => !seen.contains(t.id)),
          ],
          total: page.total,
          nextCursor: page.nextCursor,
        ),
      );
    } catch (e) {
      _emit(state.copyWith(loadingMore: false, error: ApiException.from(e)));
    }
  }

  /// أسماء الحقول (المهمّة تحمل field_id فقط). فشلها لا يُسقط القائمة: يُعرَض
  /// معرّف الحقل صراحةً بدل اسم مُختلَق.
  Future<Map<String, String>?> _loadFieldNames() async {
    try {
      final fields = await _fieldsApi.listFields();
      return {
        for (final f in fields)
          if ((f['field_id'] ?? f['id']) != null)
            (f['field_id'] ?? f['id'])
                .toString(): (f['name']?.toString().trim().isNotEmpty ?? false)
                ? f['name'].toString()
                : (f['field_id'] ?? f['id']).toString(),
      };
    } catch (_) {
      return null;
    }
  }

  // ── المرشِّحات ─────────────────────────────────────────────────────

  void setStatusFilter(StatusFilter f) =>
      _emit(state.copyWith(statusFilter: f));
  void setFieldFilter(String? fieldId) =>
      _emit(state.copyWith(fieldFilter: fieldId));
  void setMineOnly(bool v) => _emit(state.copyWith(mineOnly: v));
  void setGroupByField(bool v) => _emit(state.copyWith(groupByField: v));
  void clearFilters() => _emit(
    state.copyWith(
      statusFilter: StatusFilter.all,
      fieldFilter: null,
      mineOnly: false,
    ),
  );

  // ── الكتابة ────────────────────────────────────────────────────────

  Future<WriteOutcome<FieldTask>?> start(String taskId) =>
      _write(taskId, TaskAction.start, const {'status': TaskStatus.inProgress});

  /// إنجاز مع ملاحظة اختياريّة تُلحَق بملاحظات المهمّة (لا تستبدلها).
  Future<WriteOutcome<FieldTask>?> complete(String taskId, {String? note}) {
    final notes = composeNotes(state.byId(taskId)?.notes, note);
    return _write(taskId, TaskAction.complete, {
      'status': TaskStatus.completed,
      'notes': ?notes,
    });
  }

  /// ملاحظة دون تغيير الحالة.
  Future<WriteOutcome<FieldTask>?> addNote(String taskId, String note) {
    final notes = composeNotes(state.byId(taskId)?.notes, note);
    if (notes == null) return Future.value(null);
    return _write(taskId, TaskAction.note, {'notes': notes});
  }

  /// يُعيد null إن تُجوهلت (كتابة جارية على المهمّة نفسها).
  Future<WriteOutcome<FieldTask>?> _write(
    String taskId,
    TaskAction action,
    Map<String, dynamic> body,
  ) async {
    if (state.busy.contains(taskId)) return null;
    final task = state.byId(taskId);
    final intent = 'task:$taskId';
    final key = _keys.keyFor(intent, body);
    _emit(state.copyWith(busy: {...state.busy, taskId}));

    final label = switch (action) {
      TaskAction.start => 'بدء مهمّة',
      TaskAction.complete => 'إنجاز مهمّة',
      TaskAction.note => 'ملاحظة مهمّة',
    };
    final outcome = await writeOrQueue<FieldTask>(
      key: key,
      online: _isOnline(),
      outbox: _outbox ?? OfflineOutbox.instance,
      send: (k) => _api.updateTask(taskId, body, idempotencyKey: k),
      op: (k) => OutboxOp(
        kind: 'task_update',
        method: 'PATCH',
        path: TasksApi.taskPath(taskId),
        body: body,
        idempotencyKey: k.value,
        fieldId: task?.fieldId,
        labelAr: '$label: ${taskTypeAr(task?.type ?? '')}',
      ),
    );

    final busy = {...state.busy}..remove(taskId);
    switch (outcome.kind) {
      case WriteOutcomeKind.saved:
        _keys.settle(intent);
        final updated = outcome.value!;
        _emit(
          state.copyWith(
            busy: busy,
            tasks: [for (final t in state.tasks) t.id == taskId ? updated : t],
            queued: Map.of(state.queued)..remove(taskId),
          ),
        );
      case WriteOutcomeKind.queued:
        _keys.settle(intent);
        final base = task;
        _emit(
          state.copyWith(
            busy: busy,
            queued: base == null
                ? state.queued
                : {
                    ...state.queued,
                    taskId: base.copyWith(
                      status: body['status'] as String?,
                      notes: body['notes'] as String?,
                    ),
                  },
          ),
        );
      case WriteOutcomeKind.failed:
        // المفتاح يبقى مفتوحاً: «أعد المحاولة» يرسل المفتاح نفسه.
        _emit(state.copyWith(busy: busy));
    }
    if (!_events.isClosed) _events.add(TaskWriteEvent(taskId, action, outcome));
    return outcome;
  }

  // ── السحب للإنجاز مع التراجع ────────────────────────────────────────

  /// يبدأ مهلة التراجع؛ لا يُرسَل شيء قبل انقضائها.
  bool swipeComplete(String taskId) {
    final t = state.byId(taskId);
    if (t == null ||
        t.isDone ||
        state.busy.contains(taskId) ||
        state.undoable.contains(taskId)) {
      return false;
    }
    _emit(state.copyWith(undoable: {...state.undoable, taskId}));
    _undoTimers[taskId] = Timer(undoWindow, () => _commitSwipe(taskId));
    return true;
  }

  void undoSwipe(String taskId) {
    _undoTimers.remove(taskId)?.cancel();
    if (state.undoable.contains(taskId)) {
      _emit(state.copyWith(undoable: {...state.undoable}..remove(taskId)));
    }
  }

  Future<void> _commitSwipe(String taskId) async {
    _undoTimers.remove(taskId);
    if (!state.undoable.contains(taskId)) return;
    _emit(state.copyWith(undoable: {...state.undoable}..remove(taskId)));
    await complete(taskId);
  }

  @override
  Future<void> close() async {
    // مغادرة الشاشة خلال مهلة التراجع = تأكيد: يُرسَل الإنجاز ولا يضيع.
    final pending = _undoTimers.keys.toList();
    for (final t in _undoTimers.values) {
      t.cancel();
    }
    _undoTimers.clear();
    for (final id in pending) {
      unawaited(complete(id));
    }
    await super.close();
    await _events.close();
  }
}
