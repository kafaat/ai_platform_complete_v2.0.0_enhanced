// صندوق الإرسال الدائم مع ApiClient الحقيقيّ فوق محوّل HTTP مزيّف: ترتيب التصريف،
// ثبات Idempotency-Key عبر المحاولات، تصنيف 2xx/409/4xx/5xx/انقطاع، والعزل بين
// المستخدمين (عمليّات أ لا تُرسَل أبداً برمز ب).
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/features/activities/data/activities_api.dart';
import 'package:sahool_app/features/activities/data/activity_writer.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/water_ledger_cubit.dart';
import 'package:sahool_app/features/lab_sampling/data/lab_sampling_api.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/offline_sync_api.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';
import 'package:sahool_app/features/tasks/data/tasks_api.dart';

import '../../core/fake_http.dart';
import 'outbox_test_support.dart';

ApiException _e(int code) => ApiException(
  kind: ApiException.kindForStatus(code),
  statusCode: code,
  messageAr: 'm',
);

void main() {
  group('enqueue', () {
    test(
      'stamps the owner from the JWT and persists before saying queued',
      () async {
        final h = Harness();
        final receipt = await h.outbox.enqueue(op('/api/v1/tasks/1'));
        expect(receipt.queued, isTrue);
        final r = h.store.records.single;
        expect(r.owner, const OutboxOwner(userId: 'alice', tenantId: 't1'));
        expect(r.isPending, isTrue);
        expect(
          h.adapter.requests,
          isEmpty,
          reason: 'offline: nothing sent yet',
        );
      },
    );

    test(
      'refuses honestly: no session, sync endpoint, bad key, bad method',
      () async {
        final h = Harness();
        expect(
          (await h.outbox.enqueue(op('/api/v1/sync', method: 'POST'))).reason,
          OutboxRefusal.syncEndpoint,
        );
        expect(
          (await h.outbox.enqueue(op('/api/v1/tasks/1', key: 'abc'))).reason,
          OutboxRefusal.badKey,
        );
        expect(
          (await h.outbox.enqueue(op('/api/v1/tasks/1', method: 'GET'))).reason,
          OutboxRefusal.badMethod,
        );
        h.tokens.accessToken = null;
        final r = await h.outbox.enqueue(op('/api/v1/tasks/1'));
        expect(r.queued, isFalse);
        expect(r.reason, OutboxRefusal.noSession);
        expect(h.store.records, isEmpty);
      },
    );

    test('store that cannot open ⇒ notQueued, never a fake save', () async {
      final outbox = DurableOfflineOutbox(
        openStore: () async =>
            throw const OutboxStoreException(OutboxStoreFailure.keyStorage),
        currentOwner: () => const OutboxOwner(userId: 'a', tenantId: 't'),
      );
      final r = await outbox.enqueue(op('/api/v1/tasks/1'));
      expect(r.queued, isFalse);
      expect(r.reason, OutboxRefusal.storeUnavailable);
      expect(outbox.snapshot().failure?.failure, OutboxStoreFailure.keyStorage);
    });

    test('same idempotency key for the same owner is stored once', () async {
      final h = Harness();
      final o = op('/api/v1/tasks/1');
      await h.outbox.enqueue(o);
      expect((await h.outbox.enqueue(o)).queued, isTrue);
      expect(h.store.records, hasLength(1));
    });
  });

  group('drain', () {
    test('FIFO in enqueue order when connectivity returns, each to its own '
        'endpoint with its own key', () async {
      final h = Harness();
      final ops = [
        op('/api/v1/fields/f1/activities', method: 'POST', fieldId: 'f1'),
        op('/api/v1/tasks/7', fieldId: 'f2'),
        op('/api/v1/observations', method: 'POST'),
      ];
      for (final o in ops) {
        await h.outbox.enqueue(o);
      }
      expect(h.adapter.requests, isEmpty);

      h.connectivity.value = true; // عودة الاتّصال تُطلق التصريف
      await h.settle();

      expect(
        h.adapter.requests.map((r) => r.path).toList(),
        ops.map((o) => o.path).toList(),
      );
      expect(h.adapter.requests.map((r) => r.method).toList(), [
        'POST',
        'PATCH',
        'POST',
      ]);
      for (var i = 0; i < ops.length; i++) {
        expect(
          h.adapter.requests[i].headers[kIdempotencyHeader],
          ops[i].idempotencyKey,
        );
        expect(h.adapter.requests[i].data, ops[i].body);
      }
      expect(h.adapter.to('/api/v1/sync'), isEmpty);
      expect(h.store.records, isEmpty, reason: '2xx ⇒ removed');
    });

    test(
      'every producer kind replays generically over its own method, '
      'path and body; unknown kinds too; nothing goes to /api/v1/sync',
      () async {
        final h = Harness();
        // كلّ نوع يُودِعه منتِج حقيقيّ في التطبيق، بمساره من مساعد ميزته.
        final ops = [
          op(
            scoutingPinCreatePath('f1'),
            method: 'POST',
            kind: 'observation_create',
            body: {'pin_id': 'p1', 'lat': 15.3, 'lon': 44.2},
          ),
          op(TasksApi.taskPath('t1'), kind: 'task_update'),
          op(
            ActivitiesApi.activitiesPath('f1'),
            method: 'POST',
            kind: ActivityWriter.outboxKind({'performed_on': '2026-10-26'}),
            body: {'activity_type': 'irrigation', 'performed_on': '2026-10-26'},
          ),
          op(
            ActivitiesApi.activitiesPath('f2'),
            method: 'POST',
            kind: ActivityWriter.outboxKind({'activity_type': 'sowing'}),
            body: {'activity_type': 'sowing'},
          ),
          op(
            IrrigationApi.waterLedgerPath('f1'),
            method: 'POST',
            kind: kWaterAppliedKind,
            body: {'water_applied_mm': 12.5},
          ),
          op(
            '/api/v1/inventory/items/i1/batches',
            method: 'POST',
            kind: 'inventory_batch_add',
            body: {'quantity': 3},
          ),
          op(
            '/api/v1/equipment/e1/maintenance',
            method: 'POST',
            kind: 'equipment_maintenance_log',
            body: {'note': 'زيت'},
          ),
          op(
            LabSamplingApi.samplesPath,
            method: 'POST',
            kind: 'lab_sample_create',
            body: {'field_id': 'f1'},
          ),
          op(
            '/api/v1/farm-book/entries',
            method: 'POST',
            kind: 'farm_book_entry',
            body: {'amount': 1000},
          ),
          op(
            '/api/v1/some/new/endpoint',
            method: 'PUT',
            kind: 'a_kind_added_after_this_build',
            body: {'x': 1},
          ),
        ];
        expect(ops.map((o) => o.kind).toSet(), {
          'observation_create',
          'task_update',
          'activity_complete',
          'activity_create',
          'water_applied',
          'inventory_batch_add',
          'equipment_maintenance_log',
          'lab_sample_create',
          'farm_book_entry',
          'a_kind_added_after_this_build',
        });
        for (final o in ops) {
          expect(validateOutboxOp(o), isNull, reason: o.kind);
          expect((await h.outbox.enqueue(o)).queued, isTrue, reason: o.kind);
        }
        h.connectivity.value = true;
        await h.settle();

        expect(h.adapter.requests, hasLength(ops.length));
        for (var i = 0; i < ops.length; i++) {
          final r = h.adapter.requests[i];
          expect(r.path, ops[i].path, reason: ops[i].kind);
          expect(r.method, ops[i].method, reason: ops[i].kind);
          expect(r.data, ops[i].body, reason: ops[i].kind);
          expect(r.headers[kIdempotencyHeader], ops[i].idempotencyKey);
        }
        expect(
          h.adapter.requests.where((r) => r.path.startsWith('/api/v1/sync')),
          isEmpty,
        );
        expect(h.store.records, isEmpty, reason: '2xx ⇒ removed');
      },
    );

    test(
      'the same Idempotency-Key is reused on every retry of one op',
      () async {
        var fail = true;
        final h = Harness(
          handler: (_) async => fail
              ? const FakeReply(500, {'detail': 'boom'})
              : const FakeReply(200, {'ok': true}),
        );
        final o = op('/api/v1/tasks/9');
        await h.outbox.enqueue(o);
        await h.outbox.drain(ignoreBackoff: true);
        final kept = h.store.records.single;
        expect(kept.attempts, 1);
        expect(kept.nextAttemptAt, isNotNull);

        await h.outbox.drain(ignoreBackoff: true); // still failing
        expect(h.store.records.single.attempts, 2);

        fail = false;
        h.now = h.store.records.single.nextAttemptAt!.add(
          const Duration(seconds: 1),
        );
        h.timers.last.fire(); // مؤقّت backoff
        await h.settle();

        final sent = h.adapter.to('/api/v1/tasks/9');
        expect(sent, hasLength(3));
        expect(sent.map((r) => r.headers[kIdempotencyHeader]).toSet(), {
          o.idempotencyKey,
        });
        expect(h.store.records, isEmpty);
      },
    );

    test('4xx moves the op to rejected with the server message; later ops '
        'still go', () async {
      final h = Harness(
        handler: (o) async {
          if (o.path == '/api/v1/tasks/1') {
            return const FakeReply(422, {
              'detail': [
                {
                  'loc': ['body', 'status'],
                  'msg': 'الحالة غير صالحة',
                },
              ],
            });
          }
          if (o.path == '/api/v1/tasks/2') {
            return const FakeReply(403, {
              'detail': {'message_ar': 'المهمّة ليست ضمن حقولك.'},
            });
          }
          return const FakeReply(200, {});
        },
      );
      await h.outbox.enqueue(op('/api/v1/tasks/1', fieldId: 'f1'));
      await h.outbox.enqueue(op('/api/v1/tasks/2', fieldId: 'f1'));
      await h.outbox.enqueue(op('/api/v1/tasks/3', fieldId: 'f1'));
      await h.outbox.drain();

      final s = h.outbox.snapshot();
      expect(s.pending, isEmpty);
      expect(s.rejected.map((r) => r.op.path), [
        '/api/v1/tasks/1',
        '/api/v1/tasks/2',
      ]);
      expect(s.rejected[0].rejectedStatus, 422);
      expect(s.rejected[0].rejectedMessageAr, 'الحالة غير صالحة');
      expect(s.rejected[1].rejectedStatus, 403);
      expect(s.rejected[1].rejectedMessageAr, 'المهمّة ليست ضمن حقولك.');
      expect(h.adapter.to('/api/v1/tasks/3'), hasLength(1));

      // لا يُعاد إرسال المرفوض تلقائيّاً.
      await h.outbox.drain(ignoreBackoff: true);
      expect(h.adapter.to('/api/v1/tasks/1'), hasLength(1));
    });

    test('5xx keeps the op with backoff and holds back later ops of the '
        'same field only', () async {
      final h = Harness(
        handler: (o) async => o.path == '/api/v1/tasks/1'
            ? const FakeReply(500, {'detail': 'db down'})
            : const FakeReply(200, {}),
      );
      await h.outbox.enqueue(op('/api/v1/tasks/1', fieldId: 'f1'));
      await h.outbox.enqueue(op('/api/v1/tasks/2', fieldId: 'f1'));
      await h.outbox.enqueue(op('/api/v1/tasks/3', fieldId: 'f2'));
      await h.outbox.drain();

      final pending = h.outbox.snapshot().pending;
      expect(pending.map((r) => r.op.path), [
        '/api/v1/tasks/1',
        '/api/v1/tasks/2',
      ]);
      expect(pending.first.attempts, 1);
      expect(pending.first.nextAttemptAt!.isAfter(h.now), isTrue);
      expect(pending.first.lastErrorAr, isNotNull);
      expect(
        h.adapter.to('/api/v1/tasks/2'),
        isEmpty,
        reason: 'لا تسبق عمليّةٌ لاحقة سابقتَها في الحقل نفسه',
      );
      expect(h.adapter.to('/api/v1/tasks/3'), hasLength(1));
      expect(h.outbox.hasScheduledRetry, isTrue);
      expect(h.timers.last.delay, greaterThanOrEqualTo(h.outbox.backoffBase));

      // قبل انقضاء المهلة لا يُعاد الإرسال تلقائيّاً.
      await h.outbox.drain();
      expect(h.adapter.to('/api/v1/tasks/1'), hasLength(1));
    });

    test('backoff grows and is capped', () {
      final h = Harness();
      final b1 = h.outbox.backoffFor(1);
      final b3 = h.outbox.backoffFor(3);
      expect(b1, greaterThanOrEqualTo(h.outbox.backoffBase));
      expect(b3, greaterThanOrEqualTo(h.outbox.backoffBase * 4));
      expect(
        h.outbox.backoffFor(40),
        lessThanOrEqualTo(h.outbox.backoffMax * 1.2),
      );
    });

    test(
      '409 replay removes; 409 in progress keeps; other 409 rejects',
      () async {
        final h = Harness(
          handler: (o) async => switch (o.path) {
            '/a' => const FakeReply(409, {'idempotent_replay': true}),
            '/b' => const FakeReply(409, {
              'detail': 'الأمر قيد المعالجة — أعد المحاولة لاحقاً',
            }),
            _ => const FakeReply(409, {
              'detail': {
                'message_ar': 'يوجد حقل بالاسم نفسه.',
                'code': 'duplicate_field_name',
              },
            }),
          },
        );
        await h.outbox.enqueue(op('/a', method: 'POST'));
        await h.outbox.enqueue(op('/b', method: 'POST', fieldId: 'x'));
        await h.outbox.enqueue(op('/c', method: 'POST'));
        await h.outbox.drain();
        final s = h.outbox.snapshot();
        expect(s.pending.map((r) => r.op.path), ['/b']);
        expect(s.rejected.map((r) => r.op.path), ['/c']);
        expect(s.rejected.single.rejectedMessageAr, 'يوجد حقل بالاسم نفسه.');
      },
    );

    test('network failure keeps the op and stops the drain', () async {
      final h = Harness(
        handler: (_) async =>
            const FakeReply.fail(DioExceptionType.connectionError),
      );
      await h.outbox.enqueue(op('/api/v1/tasks/1', fieldId: 'f1'));
      await h.outbox.enqueue(op('/api/v1/tasks/2', fieldId: 'f2'));
      await h.outbox.drain();
      expect(h.adapter.requests, hasLength(1));
      expect(h.store.records, hasLength(2));
      expect(h.store.records.first.attempts, 1);
    });

    test(
      'a rejected op can be retried by the user with the same key',
      () async {
        var reject = true;
        final h = Harness(
          handler: (_) async => reject
              ? const FakeReply(400, {'detail': 'bad'})
              : const FakeReply(200, {}),
        );
        final o = op('/api/v1/tasks/1');
        await h.outbox.enqueue(o);
        await h.outbox.drain();
        final id = h.outbox.snapshot().rejected.single.id;
        reject = false;
        await h.outbox.retry(id);
        expect(h.store.records, isEmpty);
        expect(
          h.adapter.requests.map((r) => r.headers[kIdempotencyHeader]).toSet(),
          {o.idempotencyKey},
        );
      },
    );

    test('discard deletes only the current user\'s op', () async {
      final h = Harness();
      await h.outbox.enqueue(op('/api/v1/tasks/1'));
      final id = h.store.records.single.id;
      h.signInAs('bob');
      expect(await h.outbox.discard(id), isFalse);
      expect(h.store.records, hasLength(1));
      h.signInAs('alice');
      expect(await h.outbox.discard(id), isTrue);
      expect(h.store.records, isEmpty);
    });
  });

  group('user isolation', () {
    test('ops of user A are never sent with user B\'s token', () async {
      final h = Harness();
      await h.outbox.enqueue(op('/alice/1'));
      await h.outbox.enqueue(op('/alice/2'));

      // الخروج لا يحذف شيئاً.
      await h.outbox.onSessionEnd(
        const SessionEnd(userId: 'alice', tenantId: 't1'),
      );
      expect(h.store.records, hasLength(2));

      h.signInAs('bob');
      h.connectivity.value = true;
      await h.settle();
      expect(
        h.adapter.requests,
        isEmpty,
        reason: 'bob\'s session must not drain alice\'s ops',
      );
      final bobView = h.outbox.snapshot();
      expect(bobView.pending, isEmpty);
      expect(bobView.heldForOtherAccounts, 2);
      expect(await h.outbox.pendingCount.first, 0);

      await h.outbox.enqueue(op('/bob/1'));
      await h.settle();

      // نفس المستخدم في مستأجِر آخر هويّةٌ أخرى.
      h.signInAs('alice', tenant: 't2');
      await h.outbox.drain(ignoreBackoff: true);

      h.signInAs('alice');
      await h.outbox.drain(ignoreBackoff: true);

      expect(h.adapter.requests.map((r) => r.path).toList(), [
        '/bob/1',
        '/alice/1',
        '/alice/2',
      ]);
      for (final r in h.adapter.requests) {
        expect(subOf(r), r.path.split('/')[1], reason: r.path);
      }
      expect(h.store.records, isEmpty);
    });

    test('a session that ends mid-drain stops before the next op', () async {
      final gate = Completer<void>();
      final h = Harness(
        online: true,
        handler: (o) async {
          if (o.path == '/alice/1') await gate.future;
          return const FakeReply(200, {});
        },
      );
      await h.outbox.enqueue(op('/alice/1'));
      await h.outbox.enqueue(op('/alice/2'));
      for (var i = 0; i < 100 && h.adapter.to('/alice/1').isEmpty; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 1));
      }
      expect(h.adapter.to('/alice/1'), hasLength(1));

      final ended = h.outbox.onSessionEnd(
        const SessionEnd(userId: 'alice', tenantId: 't1'),
      );
      h.signInAs('bob');
      gate.complete();
      await ended;
      await h.settle();

      expect(h.adapter.to('/alice/2'), isEmpty);
      expect(
        h.store.records.map((r) => r.op.path),
        containsAll(['/alice/1', '/alice/2']),
        reason: 'the cancelled request and the next op both stay queued',
      );
    });
  });

  group('classification', () {
    test('validation and status edge cases', () {
      expect(
        validateOutboxOp(op('/api/v1/sync/', method: 'POST')),
        OutboxRefusal.syncEndpoint,
      );
      expect(validateOutboxOp(op('//evil.example/x')), OutboxRefusal.badPath);
      expect(validateOutboxOp(op('/api/v1/tasks/1')), isNull);
      expect(classifyOutboxFailure(_e(429)).kind, OutboxOutcomeKind.retryLater);
      expect(
        classifyOutboxFailure(_e(401)).kind,
        OutboxOutcomeKind.sessionProblem,
      );
      expect(classifyOutboxFailure(_e(404)).kind, OutboxOutcomeKind.rejected);
    });
  });

  test('OfflineOutbox.instance is the durable implementation', () {
    expect(OfflineOutbox.instance, isA<DurableOfflineOutbox>());
  });

  test('records round-trip through JSON', () {
    final r = OutboxRecord(
      id: 'i',
      seq: 3,
      owner: const OutboxOwner(userId: 'u', tenantId: 't'),
      op: op(
        '/x',
        body: {
          'n': 1,
          'nested': {
            'a': [1, 2],
          },
        },
        fieldId: 'f',
      ),
      createdAt: DateTime.utc(2026),
      state: OutboxRecordState.rejected,
      attempts: 2,
      rejectedStatus: 422,
      rejectedMessageAr: 'm',
    );
    final back = OutboxRecord.decode(r.encode());
    expect(back.toJson(), r.toJson());
  });
}
