// دفتر المياه: تحقّق الإدخال (أرقام عربيّة، م³↔مم)، بلاغ الريّ وحده الذي لا يحمل
// ما حسبه الخادم (W0-13)، والإيصال الصادق دون اتّصال (في الطابور / لم يُحفَظ).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_models.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/log_water_sheet.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/water_ledger_cubit.dart';
import 'package:sahool_app/features/irrigation/presentation/ledger/water_ledger_screen.dart';

import 'irrigation_test_helpers.dart';

const ledgerPath = '/api/v1/fields/f1/water-ledger';

/// قيد آليّ ليوم 2026-10-26 بقيم حسبها الخادم.
const Map<String, dynamic> autoRow = {
  'field_id': 'f1',
  'ledger_date': '2026-10-26',
  'et0_mm': 6.1,
  'kc': 1.05,
  'etc_mm': 6.4,
  'rain_mm': 0.0,
  'irrigation_mm': 0.0,
  'soil_moisture_pct': null,
  'depletion_mm': 38.2,
  'deficit_mm': 38.2,
  'stage': 'mid',
  'decision': 'auto:irrigation_unobserved',
  'confidence': 0.4,
  'created_by': 'water-balance-auto',
  'created_at': '2026-10-26T03:00:00+00:00',
};

DateTime fixedNow() => DateTime(2026, 10, 26, 9);

void main() {
  group('validateAppliedWater', () {
    test('required, numeric, non-negative', () {
      expect(validateAppliedWater('').error, 'أدخل كمّيّة الماء');
      expect(validateAppliedWater('abc').error, 'أدخل رقماً صالحاً');
      expect(validateAppliedWater('-3').error, 'لا تكون الكمّيّة سالبة');
      expect(validateAppliedWater('0').mm, 0); // «لم أروِ» قيمة مقيسة لا فراغ
    });

    test('Arabic-Indic digits and decimal separator', () {
      expect(validateAppliedWater('٢٥٫٥').mm, 25.5);
    });

    test('m³ converts with the field area; unknown area refuses m³', () {
      // 100 م³ على 2 هـ = 5 مم.
      expect(validateAppliedWater('100', unit: WaterUnit.m3, areaHa: 2).mm, 5);
      expect(
        validateAppliedWater('100', unit: WaterUnit.m3).error,
        'مساحة الحقل غير معروفة — أدخل الكمّيّة بالمليمتر',
      );
    });

    test('an implausible daily amount is rejected (unit mistake guard)', () {
      expect(validateAppliedWater('900').error, contains('500'));
    });
  });

  test('the body is the irrigation report alone, never a copy of the day', () {
    // W0-13: a copy of the day's columns, replayed from the outbox after the worker
    // rewrote the day, wrote stale values (or NULL) over the computed balance.
    expect(irrigationReportBody('2026-10-26', 20), {
      'ledger_date': '2026-10-26',
      'irrigation_mm': 20,
    });
  });

  test('a reported figure is known though the decision says unobserved', () {
    final unreported = WaterLedgerEntry.fromJson(autoRow);
    expect(unreported.irrigationUnobserved, isTrue);
    expect(unreported.knownIrrigationMm, isNull);
    final reported = WaterLedgerEntry.fromJson({
      ...autoRow,
      'irrigation_mm': 18.0,
      'irrigation_reported_by': 'u-7',
    });
    expect(reported.irrigationReported, isTrue);
    expect(reported.irrigationUnobserved, isFalse);
    expect(reported.knownIrrigationMm, 18.0);
  });

  group('cubit', () {
    test(
      'online: posts the irrigation report alone with the intent key',
      () async {
        final h = IrrigationHarness((o) async {
          if (o.method == 'GET') {
            return const FakeReply(200, {
              'field_id': 'f1',
              'entries': [autoRow],
              'total': 1,
            });
          }
          return const FakeReply(200, {
            'field_id': 'f1',
            'ledger_date': '2026-10-26',
            'persisted': true,
          });
        });
        final outbox = FakeOutbox();
        final c = WaterLedgerCubit(
          h.api,
          'f1',
          isOnline: () => true,
          outbox: () => outbox,
          now: fixedNow,
        );
        await c.load();
        const key = IdempotencyKey('0190f0c8-0000-7000-8000-00000000000a');
        final r = await c.logAppliedWater(
          ledgerDate: '2026-10-26',
          irrigationMm: 20,
          key: key,
        );
        expect(r, isA<WaterLogSaved>());
        final post = h.posts(ledgerPath).single;
        expect(post.headers[kIdempotencyHeader], key.value);
        // No server-computed column rides along, even though the day is loaded.
        expect(bodyOf(post), {
          'ledger_date': '2026-10-26',
          'irrigation_mm': 20,
        });
        expect(outbox.ops, isEmpty);
        await c.close();
      },
    );

    test(
      'offline: enqueues water_applied with the same key and returns queued',
      () async {
        final h = IrrigationHarness(
          (o) async => const FakeReply(200, {
            'field_id': 'f1',
            'entries': [autoRow],
            'total': 1,
          }),
        );
        final outbox = FakeOutbox();
        var online = true;
        final c = WaterLedgerCubit(
          h.api,
          'f1',
          isOnline: () => online,
          outbox: () => outbox,
          now: fixedNow,
        );
        await c.load();
        online = false;
        const key = IdempotencyKey('0190f0c8-0000-7000-8000-00000000000b');
        final r = await c.logAppliedWater(
          ledgerDate: '2026-10-26',
          irrigationMm: 15,
          key: key,
        );
        expect(r, isA<WaterLogQueued>());
        expect(h.posts(ledgerPath), isEmpty);
        final op = outbox.ops.single;
        expect(op.kind, kWaterAppliedKind);
        expect(op.method, 'POST');
        expect(op.path, ledgerPath);
        expect(op.idempotencyKey, key.value);
        expect(op.fieldId, 'f1');
        // The replay carries the report alone: a stale copy of the day would overwrite
        // whatever the worker computes before the phone is back online.
        expect(op.body, {'ledger_date': '2026-10-26', 'irrigation_mm': 15});
        await c.close();
      },
    );

    test(
      'offline with no durable queue: honest not-queued, nothing claimed',
      () async {
        final h = IrrigationHarness(
          (o) async => const FakeReply(200, {'entries': []}),
        );
        final c = WaterLedgerCubit(
          h.api,
          'f1',
          isOnline: () => false,
          outbox: () => FakeOutbox(accept: false),
          now: fixedNow,
        );
        final r = await c.logAppliedWater(
          ledgerDate: '2026-10-26',
          irrigationMm: 15,
          key: IdempotencyKey.generate(),
        );
        expect(r, isA<WaterLogNotQueued>());
        expect((r as WaterLogNotQueued).reason, 'offline_queue_unavailable');
        await c.close();
      },
    );

    test(
      'a dropped POST goes to the queue with the exact body and key',
      () async {
        final h = IrrigationHarness((o) async {
          if (o.method == 'GET') {
            return const FakeReply(200, {
              'entries': [autoRow],
            });
          }
          return connectionDown;
        });
        final outbox = FakeOutbox();
        final c = WaterLedgerCubit(
          h.api,
          'f1',
          isOnline: () => true,
          outbox: () => outbox,
          now: fixedNow,
        );
        const key = IdempotencyKey('0190f0c8-0000-7000-8000-00000000000c');
        final r = await c.logAppliedWater(
          ledgerDate: '2026-10-26',
          irrigationMm: 9,
          key: key,
        );
        expect(r, isA<WaterLogQueued>());
        expect(outbox.ops.single.idempotencyKey, key.value);
        expect(outbox.ops.single.body, bodyOf(h.posts(ledgerPath).single));
        await c.close();
      },
    );

    test('a server rejection is a failure, not a queue entry', () async {
      final h = IrrigationHarness((o) async {
        if (o.method == 'GET') return const FakeReply(200, {'entries': []});
        return const FakeReply(403, {'detail': 'x'});
      });
      final outbox = FakeOutbox();
      final c = WaterLedgerCubit(
        h.api,
        'f1',
        isOnline: () => true,
        outbox: () => outbox,
        now: fixedNow,
      );
      final r = await c.logAppliedWater(
        ledgerDate: '2026-10-26',
        irrigationMm: 9,
        key: IdempotencyKey.generate(),
      );
      expect(r, isA<WaterLogFailed>());
      expect(outbox.ops, isEmpty);
      await c.close();
    });
  });

  group('screen', () {
    Widget ledger(
      IrrigationHarness h, {
      required bool online,
      FakeOutbox? outbox,
      String role = 'owner',
    }) => host(
      WaterLedgerScreen(
        fieldId: 'f1',
        fieldName: 'حقل البُنّ',
        areaHa: 2,
        role: role,
        cubitFactory: () => WaterLedgerCubit(
          h.api,
          'f1',
          isOnline: () => online,
          outbox: () => outbox ?? FakeOutbox(accept: false),
          now: fixedNow,
        ),
      ),
    );

    IrrigationHarness server() => IrrigationHarness(
      (o) async => const FakeReply(200, {
        'field_id': 'f1',
        'entries': [autoRow],
        'total': 1,
      }),
    );

    testWidgets(
      'an auto row with no irrigation record reads "not recorded", never 0 مم',
      (t) async {
        await t.pumpWidget(ledger(server(), online: true));
        await t.pumpAndSettle();
        expect(find.text('آليّ'), findsOneWidget);
        expect(find.text('الريّ: غير مسجَّل'), findsOneWidget);
        expect(find.text('الريّ: 0 مم'), findsNothing);
        expect(
          find.text('المطر: 0 مم · ETc: 6.4 مم · الاستنزاف: 38.2 مم'),
          findsOneWidget,
        );
      },
    );

    testWidgets(
      'a manual row shows its amount and the m³ equivalent for the field',
      (t) async {
        final h = IrrigationHarness(
          (o) async => FakeReply(200, {
            'entries': [
              {
                ...autoRow,
                'irrigation_mm': 12.5,
                'created_by': 'u-7',
                'ledger_date': '2026-10-25',
              },
            ],
          }),
        );
        await t.pumpWidget(ledger(h, online: true));
        await t.pumpAndSettle();
        expect(find.text('يدويّ'), findsOneWidget);
        expect(find.text('الريّ: 12.5 مم (≈ 250 م³)'), findsOneWidget);
      },
    );

    testWidgets('empty amount shows an inline error and sends nothing', (
      t,
    ) async {
      final h = server();
      await t.pumpWidget(ledger(h, online: true));
      await t.pumpAndSettle();
      await t.tap(find.text('سجّل ريّاً'));
      await t.pumpAndSettle();
      await t.tap(find.text('حفظ في الدفتر'));
      await t.pumpAndSettle();
      expect(find.text('أدخل كمّيّة الماء'), findsOneWidget);
      expect(h.posts(ledgerPath), isEmpty);
    });

    testWidgets(
      'offline without a queue keeps the sheet open with the honest receipt',
      (t) async {
        await t.pumpWidget(ledger(server(), online: false));
        await t.pumpAndSettle();
        await t.tap(find.text('سجّل ريّاً'));
        await t.pumpAndSettle();
        // 0 مم آليّ «مجهول» لا يُعرض كقيمة مسجّلة ستُستبدَل.
        expect(find.textContaining('مسجَّل لهذا اليوم'), findsNothing);
        await t.enterText(find.byType(TextField).last, '٢٠');
        await t.tap(find.text('حفظ في الدفتر'));
        await t.pumpAndSettle();
        expect(find.text(kNotQueuedMessage), findsOneWidget);
        expect(
          find.text('سجّل الماء المضاف'),
          findsOneWidget,
        ); // الورقة ما زالت مفتوحة
      },
    );

    testWidgets(
      'offline with the queue closes the sheet and says it is queued',
      (t) async {
        final outbox = FakeOutbox();
        await t.pumpWidget(ledger(server(), online: false, outbox: outbox));
        await t.pumpAndSettle();
        await t.tap(find.text('سجّل ريّاً'));
        await t.pumpAndSettle();
        await t.enterText(find.byType(TextField).last, '20');
        await t.tap(find.text('حفظ في الدفتر'));
        await t.pumpAndSettle();
        expect(find.text(kQueuedMessage), findsOneWidget);
        expect(find.text('سجّل الماء المضاف'), findsNothing);
        expect(outbox.ops.single.body['irrigation_mm'], 20);
      },
    );

    testWidgets('agronomist and worker cannot write the ledger (field:edit)', (
      t,
    ) async {
      await t.pumpWidget(ledger(server(), online: true, role: 'agronomist'));
      await t.pumpAndSettle();
      expect(find.text('سجّل ريّاً'), findsNothing);
      expect(
        find.text('تسجيل الريّ في الدفتر للمالك والمدير فقط.'),
        findsOneWidget,
      );
    });
  });
}
