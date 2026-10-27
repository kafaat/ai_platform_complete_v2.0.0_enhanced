// R02 (جدول الريّ) + OD-2 على مستوى الشاشة: خادم HTTP محلّيّ حقيقيّ (dart:io) يلتزم
// بالجدول ثمّ يُسقط الردّ؛ الورقة تُغلق والشاشة تُفكَّك، ثمّ يُعاد فتح التخزين (نسخة
// مخزن جديدة فوق «القرص» نفسه) والشاشة من جديد. المطلوب: جدول واحد، مفتاح واحد،
// الحمولة الأصليّة وحدها تُرسَل، والتعديل يُعرض بعد الاستعادة. و409 يعرض صياغة
// الاستعادة بلا زرّ إنشاء.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/features/irrigation/data/irrigation_api.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_screen.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../offline_sync/operation_test_support.dart';
import 'irrigation_test_helpers.dart';

const _schedules = '/api/v1/irrigation/schedules';

Future<LocalCommitServer> _server(WidgetTester t) async {
  final s = (await t.runAsync(
    () => LocalCommitServer.start(
      createPath: _schedules,
      make: (n, body) => {
        'schedule_id': 'sch_$n',
        'name': body['name'],
        'message_ar': 'أُنشئ جدول الريّ',
      },
    ),
  ))!;
  s.getResponses['/api/v1/irrigation/valves'] = [
    {'valve_id': 'v1', 'name': 'صمّام الشمال', 'field_id': 'f1', 'status': 'closed'},
  ];
  s.getResponses[_schedules] = const <Object>[];
  return s;
}

/// يترك الإدخال/الإخراج الحقيقيّ يتقدّم ثمّ يرسم.
/// (لا pumpAndSettle: مؤشّر التحميل يرسم إطارات بلا نهاية أثناء الطلب.)
Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 25; i++) {
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pump(const Duration(milliseconds: 50));
  }
}

Future<void> _openSheet(WidgetTester t) async {
  await t.tap(find.text('الجداول'));
  await t.pumpAndSettle();
  await t.tap(find.byType(FloatingActionButton));
  await _settle(t);
}

Future<void> _fill(WidgetTester t, String name) async {
  final inputs = find.byType(TextField);
  await t.enterText(inputs.at(0), name);
  await t.enterText(inputs.at(1), '06:30');
  await t.enterText(inputs.at(2), '30');
}

void main() {
  setUp(() => HttpOverrides.global = null); // flutter_test يردّ 400 لكلّ HttpClient

  testWidgets('R02 schedule: commit + dropped response, edit, close the sheet '
      'and the screen, reopen storage → one schedule, one key, original '
      'recovered, edit shown', (t) async {
    final server = await _server(t);
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final ApiClient client = realClient(server, tokens);
      final api = IrrigationApi(client);
      final disk = <String, String>{};
      server.plan.add(const CommitThenDrop());

      await t.pumpWidget(
        host(
          IrrigationOpsScreen(
            api: api,
            role: 'owner',
            ledger: ledgerFor(tokens, MemoryOperationStore(disk), client: client),
          ),
        ),
      );
      await _settle(t);
      await _openSheet(t);
      await _fill(t, 'ريّ الفجر');
      await t.tap(find.text('إنشاء الجدول'));
      await _settle(t);

      expect(server.resources, hasLength(1), reason: 'الخادم التزم');
      expect(find.text(kOperationUnknownAr), findsOneWidget);
      expect(find.text(kRecoverActionAr), findsOneWidget);
      expect(find.text('إنشاء الجدول'), findsNothing, reason: 'لا إعادة إنشاء');
      final key = server.creates.single.key;

      // يعدّل الاسم ثمّ يغلق الورقة ويغادر الشاشة.
      await t.enterText(find.byType(TextField).at(0), 'ريّ الضحى');
      await t.tapAt(const Offset(10, 10)); // الحاجز ⇒ إغلاق الورقة
      await _settle(t);
      await t.pumpWidget(const SizedBox());
      await _settle(t);
      expect(server.creates, hasLength(1), reason: 'الإغلاق لا يرسل شيئاً');

      // إعادة فتح: مخزن جديد فوق القرص نفسه، شاشة جديدة.
      final reopened = MemoryOperationStore(disk);
      final rec = reopened.records.single;
      expect(rec.operationId, key);
      expect(rec.payload['name'], 'ريّ الفجر');
      expect(rec.draft?['name'], 'ريّ الضحى', reason: 'التعديل محفوظ');
      await t.pumpWidget(
        host(
          IrrigationOpsScreen(
            api: api,
            role: 'owner',
            ledger: ledgerFor(tokens, reopened, client: client),
          ),
        ),
      );
      await _settle(t);
      await _openSheet(t);
      expect(find.text(kOperationUnknownAr), findsOneWidget);
      expect(find.text('الاسم: ريّ الفجر ← ريّ الضحى'), findsOneWidget);
      expect(find.text('إنشاء الجدول'), findsNothing);

      await t.tap(find.text(kRecoverActionAr));
      await _settle(t);
      expect(find.byKey(const ValueKey('pending-op-recovered')), findsOneWidget);
      expect(find.text('الاسم: ريّ الفجر ← ريّ الضحى'), findsOneWidget);
      await t.tap(find.text('تمّ'));
      await _settle(t);
      expect(find.text('أُنشئ جدول الريّ.'), findsOneWidget);

      expect(server.resources, hasLength(1), reason: 'جدول واحد');
      expect(server.creates.map((c) => c.key).toSet(), {key});
      expect(server.creates.every((c) => c.body!['name'] == 'ريّ الفجر'), isTrue);
      expect(reopened.records, isEmpty);
    } finally {
      // يُفرغ مؤقّتات الإطار (الشريط، مهل Dio) قبل نهاية الاختبار.
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });

  testWidgets('OD-2 schedule: a 409 shows the recover wording and no create '
      'button; recovery reuses the key', (t) async {
    final server = await _server(t);
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final client = realClient(server, tokens);
      server.plan.add(const Status(409, {'detail': 'تعارض'}));
      await t.pumpWidget(
        host(
          IrrigationOpsScreen(
            api: IrrigationApi(client),
            role: 'owner',
            ledger: ledgerFor(tokens, MemoryOperationStore(), client: client),
          ),
        ),
      );
      await _settle(t);
      await _openSheet(t);
      await _fill(t, 'ريّ الفجر');
      await t.tap(find.text('إنشاء الجدول'));
      await _settle(t);

      expect(find.text(kOperationConflictAr), findsOneWidget);
      expect(find.text(kRecoverActionAr), findsOneWidget);
      expect(find.text('إنشاء الجدول'), findsNothing);
      expect(find.byKey(const ValueKey('pending-op-dismiss')), findsNothing);

      // تعديل ثمّ استعادة: نفس المفتاح والحمولة الأصليّة.
      await t.enterText(find.byType(TextField).at(0), 'ريّ آخر');
      await t.tap(find.text(kRecoverActionAr));
      await _settle(t);
      expect(server.creates, hasLength(2));
      expect(server.creates.map((c) => c.key).toSet(), hasLength(1));
      expect(server.creates.last.body!['name'], 'ريّ الفجر');
    } finally {
      // يُفرغ مؤقّتات الإطار (الشريط، مهل Dio) قبل نهاية الاختبار.
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });

  testWidgets('OD-2 schedule: in_progress says "still being processed" and '
      'offers to check again', (t) async {
    final server = await _server(t);
    try {
      final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
      final client = realClient(server, tokens);
      server.plan.add(
        const Status(409, {
          'detail': {'reason': 'in_progress'},
        }),
      );
      await t.pumpWidget(
        host(
          IrrigationOpsScreen(
            api: IrrigationApi(client),
            role: 'owner',
            ledger: ledgerFor(tokens, MemoryOperationStore(), client: client),
          ),
        ),
      );
      await _settle(t);
      await _openSheet(t);
      await _fill(t, 'ريّ الفجر');
      await t.tap(find.text('إنشاء الجدول'));
      await _settle(t);
      expect(find.text(kOperationInProgressAr), findsOneWidget);
      expect(find.text(kCheckAgainActionAr), findsOneWidget);
      expect(find.text('إنشاء الجدول'), findsNothing);
    } finally {
      // يُفرغ مؤقّتات الإطار (الشريط، مهل Dio) قبل نهاية الاختبار.
      await t.pumpWidget(const SizedBox());
      await t.pump(const Duration(seconds: 31));
      await t.runAsync(server.close);
    }
  });
}
