// دمج الطلبات المتطابقة المتزامنة: نداءان بالمفتاح نفسه أثناء طلبٍ جارٍ يشتركان في
// Future واحد، ولا تُخزَّن النتيجة بعد اكتماله — نجاحاً كان أو فشلاً.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/in_flight.dart';

void main() {
  test('concurrent calls with the same key share one request', () async {
    final inFlight = InFlight<int>();
    final gate = Completer<int>();
    var calls = 0;
    Future<int> body() {
      calls++;
      return gate.future;
    }

    final a = inFlight.run('dashboard', body);
    final b = inFlight.run('dashboard', body);
    expect(identical(a, b), isTrue);
    expect(calls, 1);
    expect(inFlight.pendingCount, 1);

    gate.complete(7);
    expect(await Future.wait([a, b]), [7, 7]);
  });

  test('different keys are not coalesced', () async {
    final inFlight = InFlight<String>();
    var calls = 0;
    final a = inFlight.run('a', () async => '${++calls}');
    final b = inFlight.run('b', () async => '${++calls}');
    expect(inFlight.pendingCount, 2);
    expect(await a, '1');
    expect(await b, '2');
  });

  test('the result is not cached once the request completes', () async {
    final inFlight = InFlight<int>();
    var calls = 0;
    expect(await inFlight.run('k', () async => ++calls), 1);
    await pumpEventQueue();
    expect(inFlight.pendingCount, 0);
    expect(await inFlight.run('k', () async => ++calls), 2);
  });

  test('a failure reaches every waiter and does not poison the key', () async {
    final inFlight = InFlight<int>();
    final gate = Completer<int>();
    final a = inFlight.run('k', () => gate.future);
    final b = inFlight.run('k', () => gate.future);
    gate.completeError(StateError('offline'));
    await expectLater(a, throwsStateError);
    await expectLater(b, throwsStateError);
    await pumpEventQueue();
    expect(inFlight.pendingCount, 0);
    expect(await inFlight.run('k', () async => 5), 5);
  });
}
