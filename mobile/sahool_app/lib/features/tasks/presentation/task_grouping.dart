// SAHOOL — features/tasks/presentation/task_grouping.dart
// تجميع المهام (منطق صرف قابل للاختبار): حسب الموعد (متأخّرة/اليوم/القادمة/
// بلا موعد/المنجزة) أو حسب الحقل، والمرشِّحات.
//
// «متأخّرة» تُقارَن بتاريخ التقويم المحلّيّ نصّيّاً (كما يفعل الويب، TasksPage
// F5-12): recommended_date تاريخ بلا وقت، وتحويله إلى لحظة UTC يجعل مهمّة اليوم
// «متأخّرة» عند منتصف ليل UTC (الثالثة فجراً في اليمن).
import 'package:sahool_app/features/tasks/data/field_task.dart';

enum TaskBucket { overdue, today, upcoming, undated, done }

const Map<TaskBucket, String> kBucketLabelAr = {
  TaskBucket.overdue: 'متأخّرة',
  TaskBucket.today: 'اليوم',
  TaskBucket.upcoming: 'القادمة',
  TaskBucket.undated: 'بلا موعد محدّد',
  TaskBucket.done: 'المنجزة والملغاة',
};

/// مفتاح «اليوم» المحلّيّ YYYY-MM-DD.
String localDateKey(DateTime now) {
  final d = now.toLocal();
  return '${d.year.toString().padLeft(4, '0')}-'
      '${d.month.toString().padLeft(2, '0')}-'
      '${d.day.toString().padLeft(2, '0')}';
}

TaskBucket bucketOf(FieldTask t, String todayKey) {
  if (t.isDone) return TaskBucket.done;
  final d = t.dateKey;
  if (d == null) return TaskBucket.undated;
  final c = d.compareTo(todayKey);
  if (c < 0) return TaskBucket.overdue;
  if (c == 0) return TaskBucket.today;
  return TaskBucket.upcoming;
}

int _byDateThenPriority(FieldTask a, FieldTask b) {
  final da = a.dateKey ?? '9999-99-99';
  final db = b.dateKey ?? '9999-99-99';
  final c = da.compareTo(db);
  if (c != 0) return c;
  return (a.priority ?? 9).compareTo(b.priority ?? 9);
}

class TaskGroup {
  const TaskGroup({
    required this.key,
    required this.titleAr,
    required this.tasks,
  });
  final String key;
  final String titleAr;
  final List<FieldTask> tasks;
}

/// مجموعات الموعد بترتيب العرض؛ المجموعات الفارغة تُحذف.
List<TaskGroup> groupByWhen(Iterable<FieldTask> tasks, String todayKey) {
  final buckets = {for (final b in TaskBucket.values) b: <FieldTask>[]};
  for (final t in tasks) {
    buckets[bucketOf(t, todayKey)]!.add(t);
  }
  return [
    for (final b in TaskBucket.values)
      if (buckets[b]!.isNotEmpty)
        TaskGroup(
          key: b.name,
          titleAr: kBucketLabelAr[b]!,
          tasks: buckets[b]!
            ..sort(
              b == TaskBucket.done
                  ? (x, y) => (y.completedAt ?? DateTime(0)).compareTo(
                      x.completedAt ?? DateTime(0),
                    )
                  : _byDateThenPriority,
            ),
        ),
  ];
}

/// مجموعات حسب الحقل (بالاسم إن عُرف). داخل كلّ حقل: المفتوحة أوّلاً بالموعد.
List<TaskGroup> groupByField(
  Iterable<FieldTask> tasks,
  Map<String, String> fieldNames,
) {
  final byField = <String, List<FieldTask>>{};
  for (final t in tasks) {
    byField.putIfAbsent(t.fieldId, () => []).add(t);
  }
  String title(String id) => fieldLabel(id, fieldNames);
  final ids = byField.keys.toList()
    ..sort((a, b) => title(a).compareTo(title(b)));
  return [
    for (final id in ids)
      TaskGroup(
        key: 'field:$id',
        titleAr: title(id),
        tasks: byField[id]!
          ..sort((a, b) {
            if (a.isDone != b.isDone) return a.isDone ? 1 : -1;
            return _byDateThenPriority(a, b);
          }),
      ),
  ];
}

/// اسم الحقل إن عُرف، وإلّا معرّفه صراحةً (لا اسم مُختلَق).
String fieldLabel(String fieldId, Map<String, String> fieldNames) {
  if (fieldId.isEmpty) return 'حقل غير محدّد';
  return fieldNames[fieldId] ?? 'حقل $fieldId';
}

/// مرشِّح الحالة في شريط الرقائق.
enum StatusFilter { open, inProgress, done, all }

const Map<StatusFilter, String> kStatusFilterLabelAr = {
  StatusFilter.open: 'المفتوحة',
  StatusFilter.inProgress: 'قيد التنفيذ',
  StatusFilter.done: 'المنجزة',
  StatusFilter.all: 'الكلّ',
};

bool matchesStatus(FieldTask t, StatusFilter f) => switch (f) {
  StatusFilter.open => t.isOpen,
  StatusFilter.inProgress => t.status == TaskStatus.inProgress,
  StatusFilter.done => t.isDone,
  StatusFilter.all => true,
};

/// أيام التأخير (≥1) لمهمّة متأخّرة، وإلّا null.
int? overdueDays(FieldTask t, String todayKey) {
  if (bucketOf(t, todayKey) != TaskBucket.overdue) return null;
  final d = DateTime.tryParse(t.dateKey!);
  final today = DateTime.tryParse(todayKey);
  if (d == null || today == null) return null;
  // تقريب الساعات يتفادى يوماً ناقصاً عند تغيّر التوقيت الصيفيّ.
  return (today.difference(d).inHours / 24).round();
}
