/// مسودّة offline: حفظ/استرجاع بالمفتاح الخماسيّ مع هويّة النسخة كاملة،
/// ولا ترحيل بين نسختين (GAP-FIELD-FORMS-01 §8.7/§15.3).
library;

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/features/field_forms/data/draft_store.dart';

void main() {
  late DraftStore store;
  late Directory tempDir;

  setUpAll(() async {
    tempDir = await Directory.systemTemp.createTemp('draft_store_test');
    Hive.init(tempDir.path);
  });

  setUp(() async {
    store = await DraftStore.open();
    await store.clearAll();
  });

  tearDownAll(() async {
    await Hive.close();
    await tempDir.delete(recursive: true);
  });

  FormDraft makeDraft({String version = 'v1', String hash = 'hash-v1'}) =>
      FormDraft(
        tenantId: 'tenant-1',
        fieldId: 'field-9',
        assignmentId: 'assign-7',
        revision: 3,
        formVersionId: version,
        schemaHash: hash,
        definitionSyncToken: 'sync-token-abc',
        answers: const {
          'crop': 'wheat',
          'severity': 3,
          'area': 3.5,
          'tags': ['a', 'b'],
          'location': {'lat': 24.7, 'lng': 46.7},
        },
        savedAt: DateTime.utc(2025, 1, 15, 10, 30),
      );

  test('حفظ ثمّ استرجاع: القيم + هويّة النسخة كاملة', () async {
    await store.save(makeDraft());
    final loaded = store.load(
      tenantId: 'tenant-1',
      fieldId: 'field-9',
      assignmentId: 'assign-7',
      formVersionId: 'v1',
      schemaHash: 'hash-v1',
    );
    expect(loaded, isNotNull);
    expect(loaded!.answers, makeDraft().answers);
    expect(loaded.formVersionId, 'v1');
    expect(loaded.schemaHash, 'hash-v1');
    expect(loaded.assignmentId, 'assign-7');
    expect(loaded.revision, 3);
    expect(loaded.definitionSyncToken, 'sync-token-abc');
    expect(loaded.savedAt, DateTime.utc(2025, 1, 15, 10, 30));
  });

  test('لا ترحيل بين نسختين: v2 بـhash جديد لا ترى مسودّة v1', () async {
    await store.save(makeDraft());
    final migrated = store.load(
      tenantId: 'tenant-1',
      fieldId: 'field-9',
      assignmentId: 'assign-7',
      formVersionId: 'v2',
      schemaHash: 'hash-v2',
    );
    expect(migrated, isNull, reason: 'لا fallback لنسخة أقدم أبدًا');
  });

  test('إغلاق وفتح: المسودّة تبقى بعد إعادة فتح الـbox', () async {
    await store.save(makeDraft());
    await Hive.box(DraftStore.boxName).close();
    final reopened = await DraftStore.open();
    final loaded = reopened.load(
      tenantId: 'tenant-1',
      fieldId: 'field-9',
      assignmentId: 'assign-7',
      formVersionId: 'v1',
      schemaHash: 'hash-v1',
    );
    expect(loaded, isNotNull);
    expect(loaded!.answers['crop'], 'wheat');
  });
}
