/// تخزين حزم النماذج المنزَّلة Offline-first (GAP-FIELD-FORMS-01 §8.7).
///
/// تُحفظ الحزمة كما نزّلت تمامًا (assignment_id, revision, form_version_id,
/// version_number, schema_json, logic_json, schema_hash, definition_sync_token)
/// في Hive — فتح النموذج وتوليده يعملان بلا اتصال.
library;

import 'package:hive_flutter/hive_flutter.dart';

import 'field_forms_api.dart';

class FormPackageStore {
  static const String boxName = 'field_forms_packages';

  final Box<dynamic> _box;

  FormPackageStore(this._box);

  static Future<FormPackageStore> open() async =>
      FormPackageStore(await Hive.openBox<dynamic>(boxName));

  /// مفتاح التخزين: tenant + field + assignment (كلّ إسناد حزمة مستقلّة).
  static String storageKey({
    required String tenantId,
    required String fieldId,
    required String assignmentId,
  }) =>
      '$tenantId|$fieldId|$assignmentId';

  Future<void> save({
    required String tenantId,
    required String fieldId,
    required DownloadedFormPackage package,
  }) async {
    await _box.put(
      storageKey(
          tenantId: tenantId, fieldId: fieldId, assignmentId: package.assignmentId),
      package.toJson(),
    );
  }

  /// يعيد كلّ الحزم المحفوظة لحقلٍ ما (للمستأجر الحاليّ).
  List<DownloadedFormPackage> packagesForField({
    required String tenantId,
    required String fieldId,
  }) {
    final prefix = '$tenantId|$fieldId|';
    final result = <DownloadedFormPackage>[];
    for (final key in _box.keys) {
      if (key is String && key.startsWith(prefix)) {
        final raw = _box.get(key);
        if (raw is Map) {
          result.add(DownloadedFormPackage.fromJson(
              Map<String, Object?>.from(raw)));
        }
      }
    }
    return result;
  }

  DownloadedFormPackage? package({
    required String tenantId,
    required String fieldId,
    required String assignmentId,
  }) {
    final raw = _box.get(storageKey(
        tenantId: tenantId, fieldId: fieldId, assignmentId: assignmentId));
    if (raw is! Map) return null;
    return DownloadedFormPackage.fromJson(Map<String, Object?>.from(raw));
  }

  Future<void> clearAll() => _box.clear();
}
