/// مدخل FieldFormScreen من مساحة عمل الحقل
/// (MOBILE-FIELD-FORM-SCREEN-UNREACHABLE-FROM-NAVIGATION-01): الزرّ يفتح قائمة
/// النماذج المنزَّلة للحقل، والضغط على نموذج يبلغ FieldFormScreen جاهزاً.
library;

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/features/field_forms/data/draft_store.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_api.dart';
import 'package:sahool_app/features/field_forms/data/form_package_store.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';
import 'package:sahool_app/features/field_forms/presentation/field_form_screen.dart';
import 'package:sahool_app/features/field_forms/presentation/field_forms_list_screen.dart';
import 'package:sahool_app/screens/field_workspace_screen.dart';

const _tenant = 'tenant-1';
const _field = 'field-9';

const _package = DownloadedFormPackage(
  assignmentId: 'assign-7',
  revision: 1,
  formVersionId: 'v1',
  versionNumber: 3,
  schemaJson: {
    'title': 'استكشاف الآفات',
    'fields': [
      {'key': 'notes', 'field_type': 'text'},
    ],
  },
  schemaHash: 'hash-v1',
);

void main() {
  late Directory tempDir;
  late FormPackageStore packages;
  late SubmissionQueue queue;
  late DraftStore drafts;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('field_forms_nav_test');
    Hive.init(tempDir.path);
    packages = await FormPackageStore.open();
    queue = await SubmissionQueue.open();
    drafts = await DraftStore.open();
  });

  setUp(() async {
    await packages.clearAll();
    await drafts.clearAll();
  });

  tearDownAll(() async {
    await Hive.close();
    await tempDir.delete(recursive: true);
  });

  Widget listScreen() => FieldFormsListScreen(
    fieldId: _field,
    packages: packages,
    queue: queue,
    tenantId: _tenant,
    server: 'https://example.invalid',
    openDraftStore: () async => drafts,
  );

  Widget workspaceShell() => MaterialApp(
    home: Scaffold(
      appBar: AppBar(
        actions: [
          FieldFormsEntryButton(
            fieldId: _field,
            listBuilder: (_) => listScreen(),
          ),
        ],
      ),
    ),
  );

  testWidgets('الزرّ ← القائمة ← FieldFormScreen جاهز', (tester) async {
    await tester.runAsync(
      () =>
          packages.save(tenantId: _tenant, fieldId: _field, package: _package),
    );

    await tester.pumpWidget(workspaceShell());
    await tester.tap(find.byKey(const ValueKey('open_field_forms')));
    await tester.pumpAndSettle();

    final tile = find.byKey(const ValueKey('field_form_assign-7'));
    expect(tile, findsOneWidget);
    expect(find.text('استكشاف الآفات'), findsOneWidget);

    await tester.tap(tile);
    await tester.pumpAndSettle();

    expect(find.byType(FieldFormScreen), findsOneWidget);
    expect(find.byKey(const ValueKey('status_ready')), findsOneWidget);
    expect(find.byKey(const ValueKey('field_notes')), findsOneWidget);
  });

  testWidgets('لا حزم للحقل ⇒ رسالة صادقة لا قائمة فارغة صامتة', (
    tester,
  ) async {
    await tester.pumpWidget(MaterialApp(home: listScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('field_forms_empty')), findsOneWidget);
    expect(find.byType(ListTile), findsNothing);
  });

  testWidgets('حزم حقلٍ آخر لا تظهر', (tester) async {
    await tester.runAsync(
      () => packages.save(
        tenantId: _tenant,
        fieldId: 'other-field',
        package: _package,
      ),
    );
    await tester.pumpWidget(MaterialApp(home: listScreen()));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('field_forms_empty')), findsOneWidget);
  });

  testWidgets('المخازن غير مهيّأة ⇒ «غير جاهز» بلا انهيار', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: FieldFormsListScreen(fieldId: _field)),
    );
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('field_forms_store_unavailable')),
      findsOneWidget,
    );
  });

  testWidgets('مساحة عمل الحقل الحقيقيّة تحمل زرّ النماذج', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: FieldWorkspaceScreen(field: {'field_id': _field, 'name': 'حقل'}),
      ),
    );
    await tester.pump();
    final button = find.byKey(const ValueKey('open_field_forms'));
    expect(button, findsOneWidget);
    expect(
      tester
          .widget<FieldFormsEntryButton>(find.byType(FieldFormsEntryButton))
          .fieldId,
      _field,
    );
    // أقسام المساحة تبدأ جلباً شبكيّاً بمؤقّتات؛ نفكّ الشجرة ونقدّم الوقت
    // الوهميّ حتّى تنتهي، فلا يبقى مؤقّت معلّق.
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump(const Duration(minutes: 5));
  });
}
