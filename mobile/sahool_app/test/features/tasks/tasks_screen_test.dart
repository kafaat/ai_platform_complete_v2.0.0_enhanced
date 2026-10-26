// شاشة المهام: المجموعات، الأدوار، الحالات الفارغة، ورقة الإنجاز (لا إرسال
// مزدوج، الخطأ داخل الورقة)، السحب مع التراجع، ولا فيض بخطّ كبير.
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/tasks/data/task_photo_store.dart';
import 'package:sahool_app/features/tasks/presentation/tasks_cubit.dart';
import 'package:sahool_app/features/tasks/presentation/tasks_screen.dart';

import '../../core/fake_http.dart';
import 'tasks_fakes.dart';

TaskPhotoTools noPhotos() => TaskPhotoTools(
  store: TaskPhotoStore(baseDir: () async => Directory.systemTemp),
);

Widget host(TasksCubit cubit, {String role = 'worker'}) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: TasksScreen(cubit: cubit, role: role, photos: noPhotos()),
);

Future<TasksCubit> pumpTasks(
  WidgetTester t,
  FakeTasksServer server, {
  String role = 'worker',
  FakeOutbox? outbox,
  bool online = true,
  bool tall = true,
  Duration undoWindow = const Duration(seconds: 5),
}) async {
  if (tall) {
    // كلّ البطاقات داخل الشاشة (ListView يبني الظاهر فقط).
    t.view.physicalSize = const Size(900, 3200);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
  }
  final cubit = server.cubit(
    outbox: outbox,
    online: online,
    undoWindow: undoWindow,
  );
  await t.runAsync(cubit.load);
  await t.pumpWidget(host(cubit, role: role));
  await t.pump();
  return cubit;
}

/// يترك طلبات Dio المزيّفة تكتمل ثمّ يعيد البناء.
Future<void> settle(WidgetTester t) async {
  await t.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 20)),
  );
  await t.pump();
  await t.pump(const Duration(milliseconds: 400));
}

List<Map<String, dynamic>> sample() => [
  taskJson('t1', date: '2026-10-20', type: 'spraying'),
  taskJson('t2', date: '2026-10-26'),
  taskJson('t3', status: 'completed', field: 'f2'),
];

void main() {
  testWidgets('groups by when, done collapsed, no create button', (t) async {
    await pumpTasks(t, FakeTasksServer(sample()));
    // المرشِّح الافتراضيّ «المفتوحة».
    expect(find.text('متأخّرة (1)'), findsOneWidget);
    expect(find.text('اليوم (1)'), findsOneWidget);
    expect(find.text('متأخّرة 6 يوم'), findsOneWidget);
    expect(find.text('حقل الوادي'), findsNWidgets(2));
    expect(find.byType(FloatingActionButton), findsNothing);
    expect(find.text('إنجاز'), findsNWidgets(2));

    await t.tap(find.text('الكلّ (3)'));
    await t.pump();
    expect(find.text('المنجزة والملغاة (1)'), findsOneWidget);
    expect(find.text('حقل البنّ'), findsNothing, reason: 'done is collapsed');
    await t.tap(find.text('المنجزة والملغاة (1)'));
    await t.pump();
    expect(find.text('حقل البنّ'), findsOneWidget);
  });

  testWidgets('group by field shows field names as headers', (t) async {
    await pumpTasks(t, FakeTasksServer(sample()));
    await t.tap(find.text('حسب الحقل'));
    await t.pump();
    expect(find.text('حقل الوادي (2)'), findsOneWidget);
  });

  testWidgets('viewer sees tasks but no write actions', (t) async {
    await pumpTasks(t, FakeTasksServer(sample()), role: 'viewer');
    expect(find.text('اليوم (1)'), findsOneWidget);
    expect(find.text('إنجاز'), findsNothing);
    expect(find.text('بدء'), findsNothing);
  });

  testWidgets('empty list says where tasks come from', (t) async {
    await pumpTasks(t, FakeTasksServer([]));
    expect(find.text('لا توجد مهام حاليّاً'), findsOneWidget);
    expect(find.text(kTasksOriginAr), findsOneWidget);
  });

  testWidgets('a filter with zero matches is not a blank screen', (t) async {
    await pumpTasks(t, FakeTasksServer(sample()));
    await t.tap(find.text('قيد التنفيذ (0)'));
    await t.pump();
    expect(find.text('لا مهام تطابق هذا المرشِّح'), findsOneWidget);
    await t.tap(find.text('عرض كلّ المهام'));
    await t.pump();
    expect(find.text('اليوم (1)'), findsOneWidget);
  });

  testWidgets('load failure shows the typed error with retry', (t) async {
    final server = FakeTasksServer([])
      ..listReply = const FakeReply(503, {'detail': 'db'});
    await pumpTasks(t, server);
    expect(
      find.text('الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).'),
      findsOneWidget,
    );
    expect(find.text('إعادة المحاولة'), findsOneWidget);
  });

  testWidgets('complete via sheet: one PATCH, list updated in place', (
    t,
  ) async {
    final server = FakeTasksServer(sample());
    await pumpTasks(t, server);
    await t.tap(find.text('إنجاز').first);
    await t.pumpAndSettle();
    expect(find.text('إنجاز المهمّة'), findsOneWidget);
    expect(
      find.text(TaskPhotoStore.notice),
      findsNothing,
      reason: 'no picker injected ⇒ no photo row',
    );
    await t.enterText(find.byType(TextFormField), 'تمّ الرشّ');
    await t.tap(find.text('تأكيد الإنجاز'));
    await settle(t);
    await t.pumpAndSettle();

    expect(server.patches, hasLength(1));
    expect(server.patches.single.data, {
      'status': 'completed',
      'notes': 'تمّ الرشّ',
    });
    expect(find.text('إنجاز المهمّة'), findsNothing, reason: 'sheet closed');
    expect(find.text('أُنجزت المهمّة.'), findsOneWidget);
    expect(server.taskGets, hasLength(1), reason: 'no full reload');
    expect(find.text('متأخّرة (1)'), findsNothing);
  });

  testWidgets('sheet blocks a double submit while the PATCH is in flight', (
    t,
  ) async {
    final server = FakeTasksServer(sample());
    final gate = Completer<void>();
    server.patchGate = gate.future;
    await pumpTasks(t, server);
    await t.tap(find.text('إنجاز').first);
    await t.pumpAndSettle();
    await t.tap(find.text('تأكيد الإنجاز'));
    await settle(t);
    expect(find.text('تأكيد الإنجاز'), findsNothing, reason: 'loading');
    await t.tap(find.byType(FilledButton).last, warnIfMissed: false);
    await settle(t);
    expect(server.patches, hasLength(1));
    gate.complete();
    await settle(t);
    await t.pumpAndSettle();
    expect(server.patches, hasLength(1));
    expect(find.text('أُنجزت المهمّة.'), findsOneWidget);
  });

  testWidgets('offline without a durable queue: error inside the sheet', (
    t,
  ) async {
    final server = FakeTasksServer(sample());
    await pumpTasks(
      t,
      server,
      online: false,
      outbox: FakeOutbox(accept: false),
    );
    await t.tap(find.text('إنجاز').first);
    await t.pumpAndSettle();
    await t.tap(find.text('تأكيد الإنجاز'));
    await settle(t);
    expect(find.text('إنجاز المهمّة'), findsOneWidget, reason: 'sheet stays');
    expect(find.textContaining('لم يُحفظ شيء'), findsOneWidget);
    expect(server.patches, isEmpty);
  });

  testWidgets('offline with the outbox: card shows pending sync', (t) async {
    final server = FakeTasksServer(sample());
    final outbox = FakeOutbox();
    await pumpTasks(t, server, online: false, outbox: outbox);
    await t.tap(find.text('إنجاز').first);
    await t.pumpAndSettle();
    await t.tap(find.text('تأكيد الإنجاز'));
    await settle(t);
    await t.pumpAndSettle();
    expect(outbox.ops.single.kind, 'task_update');
    await t.tap(find.text('الكلّ (3)'));
    await t.pump();
    await t.tap(find.text('المنجزة والملغاة (2)'));
    await t.pump();
    expect(find.text('بانتظار المزامنة'), findsOneWidget);
  });

  testWidgets('swipe to complete, then undo: nothing is sent', (t) async {
    final server = FakeTasksServer(sample());
    await pumpTasks(t, server);
    await t.drag(find.byKey(const ValueKey('task-t2')), const Offset(-600, 0));
    await t.pump();
    await t.pump(const Duration(milliseconds: 500));
    expect(find.text('ستُنجَز خلال ثوانٍ…'), findsOneWidget);
    await t.tap(
      find.descendant(
        of: find.byKey(const ValueKey('task-t2')),
        matching: find.text('تراجع'),
      ),
    );
    await t.pump();
    await t.pump(const Duration(seconds: 6));
    expect(find.text('ستُنجَز خلال ثوانٍ…'), findsNothing);
    expect(server.patches, isEmpty);
  });

  testWidgets('swipe to complete without undo sends one PATCH', (t) async {
    final server = FakeTasksServer(sample());
    await pumpTasks(t, server, undoWindow: const Duration(seconds: 1));
    await t.drag(find.byKey(const ValueKey('task-t2')), const Offset(-600, 0));
    await t.pump();
    await t.pump(const Duration(milliseconds: 300));
    expect(find.text('ستُنجَز المهمّة خلال ثوانٍ.'), findsOneWidget);
    await t.pump(const Duration(seconds: 2));
    await settle(t);
    expect(server.patches.single.data, {'status': 'completed'});
    await t.pumpAndSettle();
  });

  testWidgets('no overflow on a narrow phone with large text', (t) async {
    t.view.physicalSize = const Size(320, 640);
    t.view.devicePixelRatio = 1;
    t.platformDispatcher.textScaleFactorTestValue = 2;
    addTearDown(t.view.reset);
    addTearDown(t.platformDispatcher.clearTextScaleFactorTestValue);
    final server =
        FakeTasksServer([
            taskJson(
              't1',
              date: '2026-10-20',
              notes: 'ملاحظة طويلة جدّاً ' * 10,
            ),
          ])
          ..fields = [
            {'field_id': 'f1', 'name': 'حقل الوادي الكبير شرق القرية ' * 4},
          ];
    await pumpTasks(t, server, tall: false);
    expect(t.takeException(), isNull);
    expect(find.text('متأخّرة (1)'), findsOneWidget);
  });

  testWidgets('a failed refresh keeps the list under a stale banner', (
    t,
  ) async {
    final server = FakeTasksServer(sample());
    final cubit = await pumpTasks(t, server);
    server.listReply = const FakeReply.fail(DioExceptionType.connectionError);
    await t.runAsync(cubit.load);
    await t.pump();
    expect(find.textContaining('تعذّر التحديث'), findsOneWidget);
    expect(find.text('اليوم (1)'), findsOneWidget);
  });
}
