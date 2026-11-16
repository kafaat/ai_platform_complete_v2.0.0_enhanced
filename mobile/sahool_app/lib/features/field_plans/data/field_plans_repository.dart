// SAHOOL — features/field_plans/data/field_plans_repository.dart
// قراءات خطط الحقل عبر الكاش المشفَّر (core/offline): الشبكة أوّلاً، وعند تعذّرها
// آخر نسخة محفوظة لهذا المستأجِر+المستخدم مع وقت جلبها. قائمة الحقول تُحفَظ كذلك
// كي يختار المزارع حقله عند فتح التطبيق دون اتّصال.
import 'package:sahool_app/core/offline/cached_loader.dart';

import 'field_plans_api.dart';
import 'field_plans_models.dart';

class FieldPlansRepository {
  FieldPlansRepository({FieldPlansApi? api, CachedLoader? loader})
      : _api = api ?? FieldPlansApi.instance,
        _loader = loader ?? CachedLoader();

  static final FieldPlansRepository instance = FieldPlansRepository();

  final FieldPlansApi _api;
  final CachedLoader _loader;

  static const String fieldsKey = 'field_plans:fields';
  static String recipesKey(String fieldId) => 'field_plans:recipes:$fieldId';
  static String scanPlanKey(String fieldId) => 'field_plans:scan_plan:$fieldId';

  Future<CachedResult<List<FieldOption>>> fields() => _loader.load(
        key: fieldsKey,
        fetch: _api.listFields,
        parse: FieldOption.listFrom,
      );

  Future<CachedResult<RecipeList>> recipes(String fieldId) => _loader.load(
        key: recipesKey(fieldId),
        fetch: () => _api.fetchPrescriptions(fieldId),
        parse: RecipeList.fromJson,
      );

  Future<CachedResult<ScanPlan>> scanPlan(String fieldId) => _loader.load(
        key: scanPlanKey(fieldId),
        fetch: () => _api.fetchSoilSamplingPlan(fieldId),
        parse: ScanPlan.fromJson,
      );
}
