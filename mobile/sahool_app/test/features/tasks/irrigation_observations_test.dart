import 'dart:async';
import 'package:flutter/material.dart';
import 'package:sahool_app/core/session/auth_state.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/tasks/data/irrigation_observations_api.dart';
import 'package:sahool_app/features/tasks/presentation/irrigation_observations_screen.dart';
import 'tasks_fakes.dart';

Map<String, dynamic> observation() => {
  'observation_id': '019aaa00-1111-7111-8111-111111111111',
  'execution_id': '019aaa00-2222-7222-8222-222222222222',
  'source': 'farmer_task', 'outcome': 'unknown',
  'occurred_at': '2020-01-01T09:00:00Z',
  'quantity_method': 'unknown', 'interruptions_minutes': 0, 'volume_m3': null,
};

class ObservationsFake extends IrrigationObservationsApi {
  ObservationsFake() : super();
  @override
  Future<List<Map<String, dynamic>>> history(String taskId) async => [];
  @override
  Future<List<Map<String, dynamic>>> executions(String fieldId) async => [{
    'execution_id': '019aaa00-2222-7222-8222-222222222222', 'state': 'approved',
  }];
}

class SlowObservationsFake extends ObservationsFake {
  final pending = Completer<List<Map<String, dynamic>>>();
  int executionReads = 0;
  @override
  Future<List<Map<String, dynamic>>> history(String taskId) => pending.future;
  @override
  Future<List<Map<String, dynamic>>> executions(String fieldId) async {
    executionReads++;
    return super.executions(fieldId);
  }
}

const ownerA = OutboxOwner(userId: 'a', tenantId: 'tenant-a');
const ownerB = OutboxOwner(userId: 'b', tenantId: 'tenant-b');

void main() {
  test('unknown volume remains null and evidence never patches task status', () {
    final value = IrrigationObservation(observation());
    final op = value.toOutbox('task/1', 'f1');
    expect(validateIrrigationObservation(value.body), isNull);
    expect(op.body['task_id'], 'task/1');
    final evidence = op.body['irrigation_observation'] as Map<String, dynamic>;
    expect(evidence['volume_m3'], isNull);
    expect(evidence.containsKey('status'), isFalse);
    expect(op.body.containsKey('status'), isFalse);
    expect(op.path, '/api/v1/observations');
    expect(op.method, 'POST');
    expect(op.idempotencyKey, value.id);
  });

  test('payload is detached from editable draft and cannot rotate on retry', () {
    final draft = observation();
    final value = IrrigationObservation(draft);
    draft['outcome'] = 'irrigated';
    expect(value.body['outcome'], 'unknown');
    expect(() => value.body['outcome'] = 'irrigated', throwsUnsupportedError);
    final first = value.toOutbox('t', 'f');
    final retry = value.toOutbox('t', 'f');
    expect(retry.body, first.body);
    expect(first.body['irrigation_observation'], value.body);
    expect(() => (first.body['irrigation_observation'] as Map<String, dynamic>)['outcome'] = 'irrigated',
        throwsUnsupportedError);
    expect(first.body['task_id'], 't');
    expect(retry.idempotencyKey, first.idempotencyKey);
  });

  test('rejects incomplete meter, nonfinite values and invalid duration', () {
    final body = observation()..['outcome'] = 'irrigated';
    body['quantity_method'] = 'meter';
    body['meter_start_m3'] = 20;
    body['meter_end_m3'] = 10;
    expect(validateIrrigationObservation(body), isNotNull);
    body['meter_end_m3'] = 30;
    expect(validateIrrigationObservation(body), isNull);
    body['meter_end_m3'] = double.infinity;
    expect(validateIrrigationObservation(body), isNotNull);
    body.remove('meter_end_m3'); body.remove('meter_start_m3');
    body['quantity_method'] = 'estimated_flow';
    body['flow_m3_h'] = 100;
    body['duration_minutes'] = 20;
    body['interruptions_minutes'] = 20;
    expect(validateIrrigationObservation(body), isNotNull);
  });

  test('unknown outcome rejects area instead of implying measured irrigation', () {
    final body = observation()..['irrigated_area_ha'] = 2;
    expect(validateIrrigationObservation(body), isNotNull);
  });

  test('rejects missing timezone, future time, source and mixed quantity evidence', () {
    final body = observation();
    final now = DateTime.utc(2026, 10, 27, 9);
    body['occurred_at'] = '2026-10-27T09:00:00Z';
    expect(validateIrrigationObservation(body, now: now), isNull);
    body['occurred_at'] = '2026-10-27T09:00:00';
    expect(validateIrrigationObservation(body, now: now), isNotNull);
    body['occurred_at'] = '2026-10-27T10:00:00Z';
    expect(validateIrrigationObservation(body, now: now), isNotNull);
    body['occurred_at'] = '2026-10-27T09:00:00Z';
    body['source'] = 'automatic';
    expect(validateIrrigationObservation(body, now: now), isNotNull);
    body['source'] = 'field_inspection';
    body['outcome'] = 'irrigated';
    body['quantity_method'] = 'declared_volume';
    body['volume_m3'] = 10;
    body['meter_start_m3'] = 5;
    expect(validateIrrigationObservation(body, now: now), isNotNull);
    body.remove('meter_start_m3');
    body['interruptions_minutes'] = 1;
    expect(validateIrrigationObservation(body, now: now), isNotNull);
  });

  testWidgets('session switch discards stale history before subsequent reads', (tester) async {
    var owner = ownerA;
    final auth = AuthState();
    final api = SlowObservationsFake();
    final outbox = FakeOutbox();
    await tester.pumpWidget(MaterialApp(home: IrrigationObservationsScreen(
      taskId: 't', fieldId: 'f', canEdit: true, api: api, outbox: outbox,
      ownerReader: () => owner, authState: auth,
    )));
    owner = ownerB;
    auth.signedIn();
    api.pending.complete([{'outcome': 'irrigated', 'notes': 'private-owner-a'}]);
    await tester.pumpAndSettle();
    expect(api.executionReads, 0);
    expect(find.textContaining('private-owner-a'), findsNothing);
    expect(outbox.ops, isEmpty);
    final button = tester.widget<FilledButton>(find.byType(FilledButton));
    expect(button.onPressed, isNull);
  });

  testWidgets('queue refusal retries the same observation, then shows local-only success', (tester) async {
    final outbox = FakeOutbox(accept: false);
    await tester.pumpWidget(MaterialApp(home: IrrigationObservationsScreen(
      taskId: 't', fieldId: 'f', canEdit: true,
      api: ObservationsFake(), outbox: outbox,
      ownerReader: () => ownerA, authState: AuthState(),
    )));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.textContaining('019aaa00-2222').last);
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('حفظ الإفادة للمزامنة'));
    await tester.tap(find.text('حفظ الإفادة للمزامنة'));
    await tester.pumpAndSettle();
    expect(outbox.ops, hasLength(1));
    final first = outbox.ops.single;
    outbox.accept = true;
    await tester.ensureVisible(find.text('إعادة حفظ الإفادة نفسها'));
    await tester.tap(find.text('إعادة حفظ الإفادة نفسها'));
    await tester.pumpAndSettle();
    expect(outbox.ops, hasLength(2));
    expect(outbox.ops.last.idempotencyKey, first.idempotencyKey);
    expect(outbox.ops.last.body, first.body);
    expect(find.textContaining('حُفظت الإفادة محلياً'), findsOneWidget);
    expect(find.text('إنجاز المهمّة'), findsNothing);
  });
}
