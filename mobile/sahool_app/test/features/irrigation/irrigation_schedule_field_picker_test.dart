// D5/OD-1: منتقي الحقل في ورقة جدول الريّ اختياريّ. الصمّام المرتبط بحقل يحدّد الحقل
// ويُقفل المنتقي؛ تركه فارغاً بلا صمّام يُرسل بلا field_id ويُعرَض الجدول في القائمة
// «جدول غير مرتبط بحقل». الحقل لا يُفرَض: الإرسال ينجح بلا حقل ولا صمّام.
//
// الخادم هنا مزيّف لكنّه ذو حالة: POST يحفظ الجدول بالحقل المُرسَل (أو حقل الصمّام)،
// وGET يُعيد ما حُفظ — فما تعرضه القائمة بعد الإنشاء هو ما خزّنه «الخادم» لا ما تتوقّعه
// الورقة. ApiClient الحقيقيّ نفسه (interceptors) عبر محوّل HTTP مزيّف.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/irrigation/presentation/irrigation_ops_screen.dart';

import '../offline_sync/operation_test_support.dart';
import 'irrigation_test_helpers.dart';

const _schedPath = '/api/v1/irrigation/schedules';

/// النصّ المطلوب حرفيّاً (OD-1) — لا الثابت من الشاشة، كي يقيس الاختبار ما يراه المستخدم.
const _unlinked = 'جدول غير مرتبط بحقل';

class _ScheduleServer {
  final List<Map<String, dynamic>> schedules = [];
  int seq = 0;

  static const valves = [
    {
      'valve_id': 'v1',
      'name': 'صمّام الشمال',
      'field_id': 'f1',
      'valve_type': 'solenoid',
      'status': 'closed',
    },
    {
      'valve_id': 'v9',
      'name': 'صمّام متنقّل',
      'field_id': null,
      'valve_type': 'manual',
      'status': 'closed',
    },
  ];

  static const fields = [
    {'field_id': 'f1', 'name': 'حقل الشمال', 'area_ha': 2.5},
    {'field_id': 'f2', 'name': 'حقل الجنوب', 'area_ha': 1.0},
  ];

  Future<FakeReply> handle(RequestOptions o) async {
    if (o.method == 'GET' && o.path == '/api/v1/irrigation/valves') {
      return const FakeReply(200, valves);
    }
    if (o.method == 'GET' && o.path == '/api/v1/fields') {
      return const FakeReply(200, fields);
    }
    if (o.method == 'GET' && o.path == _schedPath) {
      return FakeReply(200, List<Map<String, dynamic>>.from(schedules));
    }
    if (o.method == 'POST' && o.path == _schedPath) {
      final body = Map<String, dynamic>.from(o.data as Map);
      String? fieldId = body['field_id'] as String?;
      final valveId = body['valve_id'] as String?;
      for (final v in valves) {
        if (v['valve_id'] == valveId && v['field_id'] != null) {
          fieldId = v['field_id'];
        }
      }
      final id = 'sch_${++seq}';
      schedules.add({
        'schedule_id': id,
        'name': body['name'],
        'field_id': fieldId,
        'valve_id': valveId,
        'start_time': '${body['start_time']}:00',
        'duration_min': body['duration_min'],
        'enabled': true,
      });
      return FakeReply(201, {
        'schedule_id': id,
        'name': body['name'],
        'message_ar': 'أُنشئ جدول الريّ',
      });
    }
    return const FakeReply(404);
  }
}

Future<IrrigationHarness> _open(WidgetTester t, _ScheduleServer srv) async {
  final h = IrrigationHarness(srv.handle);
  // إنشاء الجدول عمليّةٌ مسجَّلة (D1): سجلّ عمليّات في الذاكرة لمالك جلسة الاختبار.
  await t.pumpWidget(
    host(
      IrrigationOpsScreen(
        api: h.api,
        role: 'owner',
        ledger: ledgerFor(h.tokens, MemoryOperationStore()),
      ),
    ),
  );
  await t.pumpAndSettle();
  await t.tap(find.text('الجداول'));
  await t.pumpAndSettle();
  await t.tap(find.byType(FloatingActionButton));
  await t.pumpAndSettle();
  final inputs = find.byType(TextField);
  await t.enterText(inputs.at(0), 'ريّ الفجر');
  await t.enterText(inputs.at(1), '06:30');
  await t.enterText(inputs.at(2), '30');
  return h;
}

Finder _freeFieldPicker() =>
    find.byKey(const ValueKey('schedule-field-picker:'));

Future<void> _choose(WidgetTester t, Finder picker, String label) async {
  await t.ensureVisible(picker);
  await t.tap(picker);
  await t.pumpAndSettle();
  await t.tap(find.text(label).last);
  await t.pumpAndSettle();
}

Future<Map<String, dynamic>> _submit(
  WidgetTester t,
  IrrigationHarness h,
) async {
  await t.tap(find.text('إنشاء الجدول'));
  await t.pumpAndSettle();
  final sent = h.posts(_schedPath);
  expect(sent, hasLength(1));
  expect(sent.single.headers[kIdempotencyHeader], isNotNull);
  return bodyOf(sent.single);
}

void main() {
  testWidgets(
    'the field picker is optional: left empty with no valve, the schedule is '
    'created without field_id and listed as «جدول غير مرتبط بحقل»',
    (t) async {
      final srv = _ScheduleServer();
      final h = await _open(t, srv);
      expect(_freeFieldPicker(), findsOneWidget);
      expect(find.text(_unlinked), findsOneWidget); // الخيار الافتراضيّ
      final body = await _submit(t, h);
      expect(body.containsKey('field_id'), isFalse);
      expect(body.containsKey('valve_id'), isFalse);
      expect(srv.schedules.single['field_id'], isNull);
      // الورقة أُغلقت والقائمة أُعيدت قراءتها من الخادم.
      expect(find.text('إنشاء الجدول'), findsNothing);
      expect(find.text(_unlinked), findsOneWidget);
    },
  );

  testWidgets(
    'picking a field without a valve sends that field_id and the list names it',
    (t) async {
      final srv = _ScheduleServer();
      final h = await _open(t, srv);
      await _choose(t, _freeFieldPicker(), 'حقل الجنوب');
      final body = await _submit(t, h);
      expect(body['field_id'], 'f2');
      expect(body.containsKey('valve_id'), isFalse);
      expect(find.text('الحقل: حقل الجنوب'), findsOneWidget);
      expect(find.text(_unlinked), findsNothing);
    },
  );

  testWidgets(
    'a valve attached to a field decides the field and locks the picker',
    (t) async {
      final srv = _ScheduleServer();
      final h = await _open(t, srv);
      await _choose(t, _freeFieldPicker(), 'حقل الجنوب');
      await _choose(
        t,
        find.byKey(const ValueKey('schedule-valve-picker')),
        'صمّام الشمال',
      );
      final locked = find.byKey(const ValueKey('schedule-field-picker:f1'));
      expect(locked, findsOneWidget);
      expect(t.widget<AppDropdown<String>>(locked).onChanged, isNull);
      expect(find.text('الحقل (يحدّده الصمّام المختار)'), findsOneWidget);
      final body = await _submit(t, h);
      expect(body['valve_id'], 'v1');
      expect(body['field_id'], 'f1'); // لا تعارض مُرسَل مع حقل الصمّام
      expect(find.text('الحقل: حقل الشمال'), findsOneWidget);
    },
  );

  testWidgets(
    'a valve without a field keeps the picker free and the chosen field is sent',
    (t) async {
      final srv = _ScheduleServer();
      final h = await _open(t, srv);
      await _choose(
        t,
        find.byKey(const ValueKey('schedule-valve-picker')),
        'صمّام متنقّل',
      );
      expect(_freeFieldPicker(), findsOneWidget);
      await _choose(t, _freeFieldPicker(), 'حقل الشمال');
      final body = await _submit(t, h);
      expect(body['valve_id'], 'v9');
      expect(body['field_id'], 'f1');
    },
  );

  testWidgets(
    'closing the sheet sends nothing; reopening starts unlinked again',
    (t) async {
      final srv = _ScheduleServer();
      final h = await _open(t, srv);
      await _choose(t, _freeFieldPicker(), 'حقل الجنوب');
      await t.tapAt(const Offset(20, 20)); // خارج الورقة ⇒ إغلاق بلا إرسال
      await t.pumpAndSettle();
      expect(find.text('إنشاء الجدول'), findsNothing);
      expect(h.posts(_schedPath), isEmpty);
      await t.tap(find.byType(FloatingActionButton));
      await t.pumpAndSettle();
      expect(_freeFieldPicker(), findsOneWidget);
      expect(find.text(_unlinked), findsOneWidget);
      expect(find.text('حقل الجنوب'), findsNothing);
    },
  );

  testWidgets(
    'a server schedule without field_id is labelled unlinked in the list',
    (t) async {
      final srv = _ScheduleServer()
        ..schedules.addAll([
          {
            'schedule_id': 'old',
            'name': 'جدول قديم',
            'field_id': null,
            'start_time': '05:00:00',
            'duration_min': 20,
            'enabled': true,
          },
          {
            'schedule_id': 'linked',
            'name': 'جدول الشمال',
            'field_id': 'f1',
            'start_time': '07:00:00',
            'duration_min': 20,
            'enabled': true,
          },
        ]);
      final h = IrrigationHarness(srv.handle);
      await t.pumpWidget(host(IrrigationOpsScreen(api: h.api, role: 'worker')));
      await t.pumpAndSettle();
      await t.tap(find.text('الجداول'));
      await t.pumpAndSettle();
      expect(find.text(_unlinked), findsOneWidget);
      expect(find.text('الحقل: حقل الشمال'), findsOneWidget);
    },
  );
}
