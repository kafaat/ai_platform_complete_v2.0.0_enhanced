// SAHOOL — features/tasks/data/field_task.dart
// مهمّة حقل كما يردّها الخادم (TaskSummary في services/sahool-platform/api/
// api_models.py:87): task_id, field_id, task_type, priority(1 أعلى … 5 روتينيّ),
// status(pending/in_progress/completed/cancelled), recommended_date (تاريخ بلا
// وقت YYYY-MM-DD), estimated_duration_min, estimated_cost_usd, assigned_to,
// notes, photo_url, completed_at, created_at.
//
// لا قيمة مُختلَقة: الحقل الغائب يبقى null ويُعرَض «—» أو «غير محدّد»، والنوع
// الغائب لا يُفترَض «كشف ميدانيّ» (كان خطأً في الشاشة القديمة).
import 'package:flutter/foundation.dart';

/// حالات المهمّة المعتمدة على الخادم (`_TASK_STATUSES`, api/main.py:1468).
abstract final class TaskStatus {
  static const pending = 'pending';
  static const inProgress = 'in_progress';
  static const completed = 'completed';
  static const cancelled = 'cancelled';

  static const all = {pending, inProgress, completed, cancelled};
}

@immutable
class FieldTask {
  const FieldTask({
    required this.id,
    required this.fieldId,
    required this.type,
    required this.status,
    this.priority,
    this.recommendedDate,
    this.estimatedDurationMin,
    this.estimatedCostUsd,
    this.assignedTo,
    this.notes,
    this.photoUrl,
    this.completedAt,
    this.createdAt,
  });

  final String id;
  final String fieldId;

  /// فارغ إن لم يُرسله الخادم.
  final String type;
  final String status;
  final int? priority;

  /// «YYYY-MM-DD» كما يرسله الخادم (تاريخ تقويميّ لا لحظة زمنيّة).
  final String? recommendedDate;
  final int? estimatedDurationMin;
  final double? estimatedCostUsd;
  final String? assignedTo;
  final String? notes;
  final String? photoUrl;
  final DateTime? completedAt;
  final DateTime? createdAt;

  bool get isDone =>
      status == TaskStatus.completed || status == TaskStatus.cancelled;
  bool get isOpen => !isDone;

  /// تاريخ التقويم فقط (أوّل ١٠ محارف) أو null إن كان غائباً/مشوّهاً.
  String? get dateKey {
    final d = recommendedDate;
    if (d == null || d.length < 10) return null;
    final key = d.substring(0, 10);
    return DateTime.tryParse(key) == null ? null : key;
  }

  static String? _str(Object? v) {
    final s = v?.toString().trim() ?? '';
    return s.isEmpty ? null : s;
  }

  static int? _int(Object? v) =>
      v is num ? v.toInt() : int.tryParse(v?.toString() ?? '');

  static double? _double(Object? v) =>
      v is num ? v.toDouble() : double.tryParse(v?.toString() ?? '');

  static DateTime? _time(Object? v) {
    final s = _str(v);
    return s == null ? null : DateTime.tryParse(s);
  }

  /// يرمي [FormatException] إن غاب المعرّف: مهمّة بلا معرّف لا يمكن تحديثها،
  /// وعرضها بزرّ «إنجاز» معطّل صامت كان يُخفي عطل العقد.
  factory FieldTask.fromJson(Map<String, dynamic> j) {
    final id = _str(j['task_id'] ?? j['id']);
    if (id == null) {
      throw const FormatException('استجابة غير متوقّعة: مهمّة بلا معرّف.');
    }
    return FieldTask(
      id: id,
      fieldId: _str(j['field_id']) ?? '',
      type: _str(j['task_type']) ?? '',
      status: _str(j['status']) ?? TaskStatus.pending,
      priority: _int(j['priority']),
      recommendedDate: _str(j['recommended_date']),
      estimatedDurationMin: _int(j['estimated_duration_min']),
      estimatedCostUsd: _double(j['estimated_cost_usd']),
      assignedTo: _str(j['assigned_to']),
      notes: _str(j['notes']),
      photoUrl: _str(j['photo_url']),
      completedAt: _time(j['completed_at']),
      createdAt: _time(j['created_at']),
    );
  }

  FieldTask copyWith({String? status, String? notes}) => FieldTask(
    id: id,
    fieldId: fieldId,
    type: type,
    status: status ?? this.status,
    priority: priority,
    recommendedDate: recommendedDate,
    estimatedDurationMin: estimatedDurationMin,
    estimatedCostUsd: estimatedCostUsd,
    assignedTo: assignedTo,
    notes: notes ?? this.notes,
    photoUrl: photoUrl,
    completedAt: completedAt,
    createdAt: createdAt,
  );
}

/// صفحة من GET /api/v1/tasks?limit=&offset= (TaskListResponse).
@immutable
class TasksPage {
  const TasksPage({required this.tasks, this.total, this.nextCursor});
  final List<FieldTask> tasks;

  /// null حين لم يُرقَّم الطلب.
  final int? total;

  /// الإزاحة التالية كنصّ، أو null عند النهاية.
  final String? nextCursor;
}

/// يُلحِق ملاحظة الإنجاز بملاحظات المهمّة بدل استبدالها: PATCH يضبط `notes`
/// كاملاً (tasks.py:107)، وملاحظات المهمّة تحمل تعليمات من خطّة العمليّة؛
/// استبدالها بملاحظة العامل كان يمحو التعليمات من السجلّ.
String? composeNotes(String? existing, String? added) {
  final a = added?.trim() ?? '';
  if (a.isEmpty) return null;
  final e = existing?.trim() ?? '';
  if (e.isEmpty) return a;
  return '$e\n\nملاحظة ميدانيّة: $a';
}
