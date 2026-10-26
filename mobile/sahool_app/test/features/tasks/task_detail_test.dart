// تفاصيل المهمّة وصور الجهاز.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/tasks/data/task_photo_store.dart';
import 'package:sahool_app/features/tasks/presentation/tasks_screen.dart';

import 'tasks_fakes.dart';

void main() {
  test(
    'photos are copied to a tenant/user folder and listed per task',
    () async {
      final tmp = await Directory.systemTemp.createTemp('task_photos_test');
      addTearDown(() => tmp.delete(recursive: true));
      final src = File('${tmp.path}/cam.jpg')..writeAsBytesSync([1, 2, 3]);
      var now = 1000;
      final store = TaskPhotoStore(
        baseDir: () async => tmp,
        tenantId: () => 'ten/1',
        userId: () => 'u1',
        clock: () => DateTime.fromMillisecondsSinceEpoch(now++),
      );
      final saved = await store.save('t:1', src.path);
      await store.save('t:1', src.path);
      await store.save('other', src.path);
      expect(saved.path, contains('/task_photos/ten_1/u1/t_1__1000.jpg'));
      expect(await store.photosFor('t:1'), hasLength(2));
      expect(await store.photosFor('missing'), isEmpty);
    },
  );

  testWidgets('detail shows honest values and adds a note without status', (
    t,
  ) async {
    t.view.physicalSize = const Size(900, 3200);
    t.view.devicePixelRatio = 1;
    addTearDown(t.view.reset);
    final tmp = Directory.systemTemp.createTempSync('task_detail_test');
    addTearDown(() => tmp.deleteSync(recursive: true));
    final server = FakeTasksServer([
      taskJson('t1', notes: 'رشّ صباحاً', date: '2026-10-26'),
    ]);
    final cubit = server.cubit();
    await t.runAsync(cubit.load);
    await t.pumpWidget(
      MaterialApp(
        theme: AppTheme.light,
        locale: const Locale('ar'),
        supportedLocales: const [Locale('ar'), Locale('en')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: TasksScreen(
          cubit: cubit,
          role: 'agronomist',
          photos: TaskPhotoTools(
            store: TaskPhotoStore(baseDir: () async => tmp),
          ),
        ),
      ),
    );
    await t.pump();
    await t.tap(find.text('رشّ صباحاً'));
    await t.pumpAndSettle();
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await t.pump();

    expect(find.text('تفاصيل المهمّة'), findsOneWidget);
    // الكلفة غائبة على الخادم ⇒ «غير مقيس»، لا صفر.
    expect(find.text('غير مقيس'), findsOneWidget);
    expect(find.text('غير مُسندة'), findsOneWidget);
    expect(find.text(TaskPhotoStore.notice), findsOneWidget);
    expect(find.text('لا صور على هذا الجهاز لهذه المهمّة.'), findsOneWidget);

    await t.tap(find.text('إضافة ملاحظة'));
    await t.pumpAndSettle();
    await t.tap(find.text('حفظ الملاحظة'));
    await t.pump();
    expect(find.text('اكتب الملاحظة أوّلاً'), findsOneWidget);
    expect(server.patches, isEmpty);

    await t.enterText(find.byType(TextFormField), 'الضخّ ضعيف');
    await t.tap(find.text('حفظ الملاحظة'));
    await t.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 20)),
    );
    await t.pumpAndSettle();
    expect(server.patches.single.data, {
      'notes': 'رشّ صباحاً\n\nملاحظة ميدانيّة: الضخّ ضعيف',
    });
    expect(find.text('حُفظت الملاحظة.'), findsOneWidget);
  });
}
