// تجميع المهام حسب الموعد/الحقل، المرشِّحات، ودمج الملاحظات — منطق صرف.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/tasks/data/field_task.dart';
import 'package:sahool_app/features/tasks/presentation/task_grouping.dart';
import 'package:sahool_app/features/tasks/presentation/task_labels.dart';

FieldTask task(
  String id, {
  String status = 'pending',
  String? date,
  String field = 'f1',
  int? priority,
  String type = 'irrigation',
}) => FieldTask.fromJson({
  'task_id': id,
  'field_id': field,
  'task_type': type,
  'status': status,
  'recommended_date': date,
  'priority': priority,
});

void main() {
  const today = '2026-10-26';

  test('status grouping: overdue / today / upcoming / undated / done', () {
    final groups = groupByWhen([
      task('up', date: '2026-10-30'),
      task('late', date: '2026-10-20'),
      task('now', date: today, status: 'in_progress'),
      task('nodate'),
      task('done', date: '2026-10-01', status: 'completed'),
      task('cx', date: '2026-10-29', status: 'cancelled'),
    ], today);
    expect(groups.map((g) => g.key), [
      'overdue',
      'today',
      'upcoming',
      'undated',
      'done',
    ]);
    expect(groups[0].tasks.single.id, 'late');
    expect(groups[1].tasks.single.id, 'now');
    expect(groups[2].tasks.single.id, 'up');
    expect(groups[3].tasks.single.id, 'nodate');
    expect(groups[4].tasks.map((t) => t.id).toSet(), {'done', 'cx'});
  });

  test('empty buckets are dropped, and a done task is never overdue', () {
    final groups = groupByWhen([
      task('old', date: '2020-01-01', status: 'completed'),
    ], today);
    expect(groups.single.key, 'done');
  });

  test('overdue compares the local calendar date, not a UTC instant', () {
    // مهمّة اليوم ليست متأخّرة مهما كانت الساعة.
    expect(bucketOf(task('a', date: today), today), TaskBucket.today);
    expect(
      bucketOf(task('a', date: '2026-10-26T00:00:00'), today),
      TaskBucket.today,
    );
    expect(localDateKey(DateTime(2026, 10, 26, 23, 59)), today);
    expect(overdueDays(task('b', date: '2026-10-23'), today), 3);
    expect(overdueDays(task('c', date: today), today), isNull);
  });

  test('within a bucket: earlier date first, then higher priority', () {
    final g = groupByWhen([
      task('p3', date: '2026-11-02', priority: 3),
      task('p1', date: '2026-11-02', priority: 1),
      task('early', date: '2026-10-28', priority: 5),
    ], today).single;
    expect(g.tasks.map((t) => t.id), ['early', 'p1', 'p3']);
  });

  test('group by field uses names, falls back to the id, open tasks first', () {
    final groups = groupByField(
      [
        task('x', field: 'f2', status: 'completed'),
        task('y', field: 'f2', date: '2026-10-27'),
        task('z', field: 'f9'),
      ],
      {'f2': 'حقل البنّ'},
    );
    expect(groups.map((g) => g.titleAr), ['حقل f9', 'حقل البنّ']);
    expect(groups.last.tasks.map((t) => t.id), ['y', 'x']);
  });

  test('status filter chips', () {
    final open = task('o');
    final prog = task('p', status: 'in_progress');
    final done = task('d', status: 'completed');
    expect(matchesStatus(open, StatusFilter.open), isTrue);
    expect(matchesStatus(prog, StatusFilter.open), isTrue);
    expect(matchesStatus(done, StatusFilter.open), isFalse);
    expect(matchesStatus(open, StatusFilter.inProgress), isFalse);
    expect(matchesStatus(done, StatusFilter.done), isTrue);
    expect(matchesStatus(done, StatusFilter.all), isTrue);
  });

  test('a missing task type is not shown as scouting', () {
    final t = FieldTask.fromJson({'task_id': '1', 'status': 'pending'});
    expect(t.type, isEmpty);
    expect(taskTypeAr(t.type), 'نوع غير محدّد');
    expect(taskTypeAr('mulching'), 'mulching');
  });

  test('a task without an id is a contract error, not a silent row', () {
    expect(
      () => FieldTask.fromJson({'status': 'pending'}),
      throwsFormatException,
    );
  });

  test('cost is labelled in dollars as stored; missing values are honest', () {
    expect(fmtCostUsd(12.5), '12.5 دولار أمريكي');
    expect(fmtCostUsd(null), 'غير مقيس');
    expect(fmtDurationMin(null), 'غير مقيس');
    expect(fmtDurationMin(90), '1 ساعة و30 دقيقة');
  });

  test('completion note is appended to existing task notes', () {
    expect(composeNotes(null, '  '), isNull);
    expect(composeNotes(null, 'تمّ'), 'تمّ');
    expect(
      composeNotes('رشّ صباحاً', 'تمّ بلا رياح'),
      'رشّ صباحاً\n\nملاحظة ميدانيّة: تمّ بلا رياح',
    );
  });
}
