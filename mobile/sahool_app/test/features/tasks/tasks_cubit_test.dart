// قائمة المهام وكتاباتها: الترقيم، الإنجاز متّصلاً/بلا اتّصال، ثبات مفتاح
// Idempotency-Key عبر الإعادة، منع الإرسال المزدوج، والسحب مع التراجع.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/tasks/presentation/task_grouping.dart';
import 'package:sahool_app/features/tasks/presentation/tasks_state.dart';

import '../../core/fake_http.dart';
import 'tasks_fakes.dart';

void main() {
  test('load asks for a bounded page and keeps total/next_cursor', () async {
    final server = FakeTasksServer([taskJson('t1'), taskJson('t2')])
      ..total = 450
      ..nextCursor = '200';
    final cubit = server.cubit();
    await cubit.load();
    expect(cubit.state.load, TasksLoad.loaded);
    expect(server.listQueries.single, {'limit': 200, 'offset': 0});
    expect(cubit.state.total, 450);
    expect(cubit.state.hasMore, isTrue);
    expect(cubit.state.fieldNames['f1'], 'حقل الوادي');

    server.nextCursor = null;
    await cubit.loadMore();
    expect(server.listQueries.last, {'limit': 200, 'offset': 200});
    expect(cubit.state.hasMore, isFalse);
    expect(cubit.state.tasks, hasLength(2), reason: 'duplicates dropped');
    await cubit.close();
  });

  test(
    'a failed first load is an honest failed state with the typed error',
    () async {
      final server = FakeTasksServer([])
        ..listReply = const FakeReply(503, {'detail': 'db'});
      final cubit = server.cubit();
      await cubit.load();
      expect(cubit.state.load, TasksLoad.failed);
      expect(cubit.state.error!.isUnavailable, isTrue);
      await cubit.close();
    },
  );

  test('a failed refresh keeps the last list and records the error', () async {
    final server = FakeTasksServer([taskJson('t1')]);
    final cubit = server.cubit();
    await cubit.load();
    server.listReply = const FakeReply.fail(DioExceptionType.connectionError);
    await cubit.load();
    expect(cubit.state.load, TasksLoad.loaded);
    expect(cubit.state.tasks.single.id, 't1');
    expect(cubit.state.error!.isConnectivity, isTrue);
    await cubit.close();
  });

  group('complete', () {
    test(
      'online: PATCH with key, the task is replaced in place (no reload)',
      () async {
        final server = FakeTasksServer([
          taskJson('t1', notes: 'رشّ صباحاً'),
          taskJson('t2'),
        ]);
        final outbox = FakeOutbox();
        final cubit = server.cubit(outbox: outbox);
        await cubit.load();
        final events = <TaskWriteEvent>[];
        final sub = cubit.events.listen(events.add);

        final r = await cubit.complete('t1', note: 'تمّ');
        expect(r!.isSaved, isTrue);
        final patch = server.patches.single;
        expect(patch.path, '/api/v1/tasks/t1');
        expect(patch.data, {
          'status': 'completed',
          'notes': 'رشّ صباحاً\n\nملاحظة ميدانيّة: تمّ',
        });
        expect(patch.headers[kIdempotencyHeader], isNotNull);
        expect(cubit.state.byId('t1')!.status, 'completed');
        expect(cubit.state.byId('t1')!.completedAt, isNotNull);
        expect(server.taskGets, hasLength(1), reason: 'no full reload');
        expect(outbox.ops, isEmpty);
        await Future<void>.delayed(Duration.zero);
        expect(events.single.messageAr, 'أُنجزت المهمّة.');
        await sub.cancel();
        await cubit.close();
      },
    );

    test(
      'offline: queued in the outbox as task_update, shown as pending sync',
      () async {
        final server = FakeTasksServer([taskJson('t1')]);
        final outbox = FakeOutbox();
        var online = true;
        final cubit = server.cubit(outbox: outbox, isOnline: () => online);
        await cubit.load();
        online = false;

        final r = await cubit.complete('t1');
        expect(r!.isQueued, isTrue);
        expect(server.patches, isEmpty, reason: 'no network attempt offline');
        final op = outbox.ops.single;
        expect(op.kind, 'task_update');
        expect(op.method, 'PATCH');
        expect(op.path, '/api/v1/tasks/t1');
        expect(op.body, {'status': 'completed'});
        expect(op.fieldId, 'f1');
        expect(op.idempotencyKey, isNotEmpty);
        expect(cubit.state.queued.containsKey('t1'), isTrue);
        expect(cubit.state.byId('t1')!.status, 'completed');
        // الخادم ما زال يقول pending: نسخة الخادم لم تُلمَس.
        expect(cubit.state.tasks.single.status, 'pending');
        await cubit.close();
      },
    );

    test('connection error while online falls back to the outbox', () async {
      final server = FakeTasksServer([taskJson('t1')])
        ..patchReply = (_) =>
            const FakeReply.fail(DioExceptionType.connectionError);
      final outbox = FakeOutbox();
      final cubit = server.cubit(outbox: outbox);
      await cubit.load();
      final r = await cubit.complete('t1');
      expect(r!.isQueued, isTrue);
      expect(
        outbox.ops.single.idempotencyKey,
        server.patches.first.headers[kIdempotencyHeader],
        reason: 'the outbox replays the same key the failed send used',
      );
      await cubit.close();
    });

    test(
      'offline with no durable outbox: not saved, nothing shown as done',
      () async {
        final server = FakeTasksServer([taskJson('t1')]);
        final cubit = server.cubit(
          outbox: FakeOutbox(accept: false),
          online: false,
        );
        await cubit.load();
        final r = await cubit.complete('t1');
        expect(r!.isFailed, isTrue);
        expect(r.messageAr, contains('لم يُحفظ'));
        expect(cubit.state.queued, isEmpty);
        expect(cubit.state.byId('t1')!.status, 'pending');
        await cubit.close();
      },
    );

    test('server errors (403) are shown, not hidden in the outbox', () async {
      final server = FakeTasksServer([taskJson('t1')])
        ..patchReply = (_) => const FakeReply(403, {'detail': 'x'});
      final outbox = FakeOutbox();
      final cubit = server.cubit(outbox: outbox);
      await cubit.load();
      final r = await cubit.complete('t1');
      expect(r!.isFailed, isTrue);
      expect(r.messageAr, 'لا تملك صلاحيّة الوصول إلى هذا القسم.');
      expect(outbox.ops, isEmpty);
      await cubit.close();
    });
  });

  test('idempotency key is stable across a retry of the same action', () async {
    final server = FakeTasksServer([taskJson('t1')]);
    var fail = true;
    server.patchReply = (_) =>
        fail ? const FakeReply(500, {'detail': 'boom'}) : null;
    final cubit = server.cubit();
    await cubit.load();

    final first = await cubit.complete('t1');
    expect(first!.isFailed, isTrue);
    fail = false;
    final second = await cubit.complete('t1');
    expect(second!.isSaved, isTrue);

    final keys = server.patches
        .map((r) => r.headers[kIdempotencyHeader])
        .toList();
    expect(keys, hasLength(2));
    expect(keys[0], keys[1]);

    // نيّة جديدة بعد الحسم ⇒ مفتاح جديد.
    await cubit.addNote('t1', 'ملاحظة');
    expect(server.patches.last.headers[kIdempotencyHeader], isNot(keys[0]));
    await cubit.close();
  });

  test(
    'a changed body after a failure gets a new key (server rejects reuse)',
    () async {
      final server = FakeTasksServer([taskJson('t1')])
        ..patchReply = (_) => const FakeReply(500, {'detail': 'boom'});
      final cubit = server.cubit();
      await cubit.load();
      await cubit.complete('t1', note: 'أ');
      await cubit.complete('t1', note: 'ب');
      final keys = server.patches.map((r) => r.headers[kIdempotencyHeader]);
      expect(keys.toSet(), hasLength(2));
      await cubit.close();
    },
  );

  test(
    'double submit: a second tap while the first is in flight is ignored',
    () async {
      final server = FakeTasksServer([taskJson('t1')]);
      final cubit = server.cubit();
      await cubit.load();
      final a = cubit.complete('t1');
      final b = cubit.complete('t1');
      expect(await b, isNull);
      expect((await a)!.isSaved, isTrue);
      expect(server.patches, hasLength(1));
      await cubit.close();
    },
  );

  test('swipe: undo inside the window sends nothing', () async {
    final server = FakeTasksServer([taskJson('t1')]);
    final cubit = server.cubit(undoWindow: const Duration(milliseconds: 30));
    await cubit.load();
    expect(cubit.swipeComplete('t1'), isTrue);
    expect(cubit.state.undoable, contains('t1'));
    cubit.undoSwipe('t1');
    await Future<void>.delayed(const Duration(milliseconds: 60));
    expect(server.patches, isEmpty);
    expect(cubit.state.undoable, isEmpty);
    expect(cubit.state.byId('t1')!.status, 'pending');
    await cubit.close();
  });

  test('swipe: after the window the completion is sent once', () async {
    final server = FakeTasksServer([taskJson('t1')]);
    final cubit = server.cubit(undoWindow: const Duration(milliseconds: 10));
    await cubit.load();
    cubit.swipeComplete('t1');
    expect(cubit.swipeComplete('t1'), isFalse, reason: 'no double swipe');
    await Future<void>.delayed(const Duration(milliseconds: 80));
    expect(server.patches.single.data, {'status': 'completed'});
    expect(cubit.state.byId('t1')!.status, 'completed');
    await cubit.close();
  });

  test('start sets in_progress; filters and "mine" narrow the list', () async {
    final server = FakeTasksServer([
      taskJson('t1', assignedTo: 'u1'),
      taskJson('t2', field: 'f2'),
      taskJson('t3', status: 'completed'),
    ]);
    final cubit = server.cubit(userId: 'u1');
    await cubit.load();
    await cubit.start('t2');
    expect(server.patches.single.data, {'status': 'in_progress'});
    expect(cubit.state.byId('t2')!.status, 'in_progress');

    expect(cubit.state.visible('u1').map((t) => t.id), ['t1', 't2']);
    cubit.setFieldFilter('f2');
    expect(cubit.state.visible('u1').map((t) => t.id), ['t2']);
    cubit
      ..setFieldFilter(null)
      ..setMineOnly(true);
    expect(cubit.state.visible('u1').map((t) => t.id), ['t1']);
    cubit
      ..setMineOnly(false)
      ..setStatusFilter(StatusFilter.done);
    expect(cubit.state.visible('u1').map((t) => t.id), ['t3']);
    expect(cubit.state.countFor(StatusFilter.open), 2);
    await cubit.close();
  });
}
