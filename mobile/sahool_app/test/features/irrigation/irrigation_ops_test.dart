// الريّ التشغيليّ: مفتاح الصمّام يعكس حالة الخادم، يُعطَّل أثناء الطلب، يطلب
// تأكيداً، ولا يُرسل طلبات مكرّرة؛ مفتاح النيّة يُعاد بعد فشل اتّصال؛ رفض الخادم
// يُعرض بنصّه؛ العامل لا يرى أدوات irrigation:manage.
import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_cubit.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_screen.dart';

import 'irrigation_test_helpers.dart';

const valvePath = '/api/v1/irrigation/valves';
const statePath = '/api/v1/irrigation/valves/v1/state';

class ValveServer {
  String status = 'closed';
  Completer<FakeReply>? hold;
  FakeReply? next;
  final List<String?> keys = [];

  Future<FakeReply> handle(RequestOptions o) async {
    if (o.method == 'GET' && o.path == valvePath) {
      return FakeReply(200, [
        {
          'valve_id': 'v1',
          'name': 'صمّام الشمال',
          'field_id': 'f1',
          'valve_type': 'solenoid',
          'status': status,
          'flow_rate_lpm': 40,
          'last_changed_at': null,
        },
      ]);
    }
    if (o.method == 'GET') return const FakeReply(200, []);
    if (o.path == statePath) {
      keys.add(o.headers[kIdempotencyHeader] as String?);
      if (hold != null) return hold!.future;
      final n = next;
      if (n != null) {
        next = null;
        return n;
      }
      status = (o.data as Map)['status'] as String;
      return FakeReply(200, {
        'valve_id': 'v1',
        'status': status,
        'message_ar': 'سُجّلت حالة الصمّام',
      });
    }
    return const FakeReply(404);
  }
}

Switch valveSwitch(WidgetTester t) =>
    t.widget<Switch>(find.byKey(const ValueKey('valve-switch-v1')));

void main() {
  group('cubit', () {
    test(
      'one in-flight request per valve; repeated calls send nothing',
      () async {
        final srv = ValveServer()..hold = Completer();
        final h = IrrigationHarness(srv.handle);
        final c = IrrigationOpsCubit(h.api);
        await c.load();
        final first = c.requestValveState('v1', 'open');
        final again = await c.requestValveState('v1', 'open');
        expect(again.ignored, isTrue);
        expect(c.state.isValvePending('v1'), isTrue);
        // الحالة لا تتحرّك تفاؤليّاً قبل ردّ الخادم.
        expect(c.state.valves.single.isOpen, isFalse);
        srv.hold!.complete(
          const FakeReply(200, {'valve_id': 'v1', 'status': 'open'}),
        );
        srv.hold = null;
        srv.status = 'open';
        expect((await first).ok, isTrue);
        expect(h.posts(statePath), hasLength(1));
        expect(c.state.isValvePending('v1'), isFalse);
        expect(c.state.valves.single.isOpen, isTrue);
        await c.close();
      },
    );

    test(
      'a connection failure keeps the intent key; the retry reuses it',
      () async {
        final srv = ValveServer()..next = connectionDown;
        final h = IrrigationHarness(srv.handle);
        final c = IrrigationOpsCubit(h.api);
        await c.load();
        final failed = await c.requestValveState('v1', 'open');
        expect(failed.error!.isConnectivity, isTrue);
        expect(c.state.valves.single.isClosed, isTrue);
        final ok = await c.requestValveState('v1', 'open');
        expect(ok.ok, isTrue);
        expect(srv.keys, hasLength(2));
        expect(srv.keys[0], isNotNull);
        expect(srv.keys[1], srv.keys[0]);
        // النيّة انتهت ⇒ طلب لاحق نيّة جديدة بمفتاح جديد.
        expect(c.intentKey('v1', 'open'), isNull);
        await c.close();
      },
    );

    test('a server refusal drops the key and is reported verbatim', () async {
      final srv = ValveServer()
        ..next = const FakeReply(409, {'detail': 'أوامر المشغِّلات مجمَّدة'});
      final h = IrrigationHarness(srv.handle);
      final c = IrrigationOpsCubit(h.api);
      await c.load();
      final r = await c.requestValveState('v1', 'open');
      expect(r.error!.statusCode, 409);
      expect(r.error!.messageAr, 'تعارض: السجلّ موجود مسبقاً.');
      expect(c.intentKey('v1', 'open'), isNull);
      expect(c.state.valves.single.isClosed, isTrue);
      await c.close();
    });
  });

  group('screen', () {
    testWidgets(
      'switch shows server state, asks to confirm, disables while pending',
      (t) async {
        final srv = ValveServer();
        final h = IrrigationHarness(srv.handle);
        await t.pumpWidget(
          host(IrrigationOpsScreen(api: h.api, role: 'agronomist')),
        );
        await t.pumpAndSettle();
        expect(find.text(kValveIntentBanner), findsOneWidget);
        expect(valveSwitch(t).value, isFalse);

        // إلغاء التأكيد ⇒ لا طلب.
        await t.tap(find.byKey(const ValueKey('valve-switch-v1')));
        await t.pumpAndSettle();
        expect(find.text('طلب فتح الصمّام'), findsOneWidget);
        await t.tap(find.text('إلغاء'));
        await t.pumpAndSettle();
        expect(h.posts(statePath), isEmpty);
        expect(valveSwitch(t).value, isFalse);

        // تأكيد ⇒ طلب واحد، المفتاح معطَّل ولا يتحرّك حتّى يردّ الخادم.
        srv.hold = Completer();
        await t.tap(find.byKey(const ValueKey('valve-switch-v1')));
        await t.pumpAndSettle();
        await t.tap(find.text('اطلب الفتح'));
        await t.pumpAndSettle();
        expect(valveSwitch(t).onChanged, isNull);
        expect(valveSwitch(t).value, isFalse);
        expect(find.text('جارٍ إرسال الطلب…'), findsOneWidget);
        await t.tap(find.byKey(const ValueKey('valve-switch-v1')));
        await t.pumpAndSettle();
        expect(find.text('طلب فتح الصمّام'), findsNothing);
        expect(h.posts(statePath), hasLength(1));
        expect(
          h.posts(statePath).single.headers[kIdempotencyHeader],
          isNotNull,
        );

        srv.status = 'open';
        srv.hold!.complete(
          const FakeReply(200, {
            'valve_id': 'v1',
            'status': 'open',
            'message_ar': 'سُجّلت حالة الصمّام',
          }),
        );
        srv.hold = null;
        await t.pumpAndSettle();
        expect(valveSwitch(t).value, isTrue);
        expect(valveSwitch(t).onChanged, isNotNull);
        expect(find.text('سُجّلت حالة الصمّام'), findsOneWidget);
      },
    );

    testWidgets(
      'a 403 refusal is shown and the switch stays where the server says',
      (t) async {
        final srv = ValveServer()
          ..next = const FakeReply(403, {'detail': 'forbidden'});
        final h = IrrigationHarness(srv.handle);
        await t.pumpWidget(
          host(IrrigationOpsScreen(api: h.api, role: 'manager')),
        );
        await t.pumpAndSettle();
        await t.tap(find.byKey(const ValueKey('valve-switch-v1')));
        await t.pumpAndSettle();
        await t.tap(find.text('اطلب الفتح'));
        await t.pumpAndSettle();
        expect(
          find.text('لا تملك صلاحيّة الوصول إلى هذا القسم.'),
          findsOneWidget,
        );
        expect(valveSwitch(t).value, isFalse);
      },
    );

    testWidgets(
      'a refusal with an Arabic reason shows the reason, not only "conflict"',
      (t) async {
        final srv = ValveServer()
          ..next = const FakeReply(409, {
            'detail': 'أوامر المشغِّلات مجمَّدة بقرار المالك',
          });
        final h = IrrigationHarness(srv.handle);
        await t.pumpWidget(
          host(IrrigationOpsScreen(api: h.api, role: 'owner')),
        );
        await t.pumpAndSettle();
        await t.tap(find.byKey(const ValueKey('valve-switch-v1')));
        await t.pumpAndSettle();
        await t.tap(find.text('اطلب الفتح'));
        await t.pumpAndSettle();
        expect(
          find.text(
            'تعارض: السجلّ موجود مسبقاً.\nأوامر المشغِّلات مجمَّدة بقرار المالك',
          ),
          findsOneWidget,
        );
        expect(valveSwitch(t).value, isFalse);
      },
    );

    testWidgets('worker sees valves read-only (server would answer 403)', (
      t,
    ) async {
      final srv = ValveServer();
      final h = IrrigationHarness(srv.handle);
      await t.pumpWidget(host(IrrigationOpsScreen(api: h.api, role: 'worker')));
      await t.pumpAndSettle();
      expect(find.text('صمّام الشمال'), findsOneWidget);
      expect(find.byType(Switch), findsNothing);
      expect(find.byType(FloatingActionButton), findsNothing);
    });

    testWidgets(
      'schedule tab renders minutes and clock time through formatters',
      (t) async {
        final h = IrrigationHarness((o) async {
          if (o.path == '/api/v1/irrigation/schedules') {
            return const FakeReply(200, [
              {
                'schedule_id': 's1',
                'name': 'ريّ الفجر',
                'start_time': '05:30:00',
                'duration_min': 45,
                'days_of_week': [0, 3],
                'water_target_mm': 12.5,
                'enabled': true,
              },
            ]);
          }
          return const FakeReply(200, []);
        });
        await t.pumpWidget(
          host(IrrigationOpsScreen(api: h.api, role: 'owner')),
        );
        await t.pumpAndSettle();
        await t.tap(find.text('الجداول'));
        await t.pumpAndSettle();
        expect(find.text('05:30 · 45 دقيقة · الأحد، الأربعاء'), findsOneWidget);
        expect(find.text('الهدف: 12.5 مم'), findsOneWidget);
      },
    );
  });
}
