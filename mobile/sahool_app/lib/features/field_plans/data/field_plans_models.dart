// SAHOOL — features/field_plans/data/field_plans_models.dart
// نماذج قراءة الوصفات وخطّة العيّنات من شكل الخادم الحقيقيّ. شكل خاطئ ⇒
// FormatException (لا قائمة فارغة مختلَقة). قيمة غائبة تبقى null وتُعرض
// «غير مقيس»، لا صفراً.
import 'package:flutter/foundation.dart';

String? _s(Object? v) {
  final t = v?.toString().trim();
  return (t == null || t.isEmpty) ? null : t;
}

double? _d(Object? v) => v is num ? v.toDouble() : null;

Map<String, dynamic> _map(Object? json, String what) {
  if (json is Map) return Map<String, dynamic>.from(json);
  throw FormatException('شكل $what غير متوقّع من الخادم.');
}

List<Object?> _list(Object? v, String what) {
  if (v is List) return v;
  throw FormatException('شكل $what غير متوقّع من الخادم.');
}

// ── الوصفات (api/routers/prescriptions.py::_row_to_prescription) ──────────

@immutable
class RecipeZone {
  const RecipeZone({this.rate, this.unit});
  final double? rate;
  final String? unit;

  factory RecipeZone.fromJson(Object? json) {
    final m = json is Map ? json : const {};
    return RecipeZone(rate: _d(m['rate']), unit: _s(m['unit']));
  }
}

@immutable
class Recipe {
  const Recipe({
    required this.id,
    required this.name,
    this.productType,
    this.seasonId,
    this.createdAt,
    this.zones = const [],
  });

  final String id;
  final String name;

  /// `seed` | `fertility` كما يحفظه الخادم.
  final String? productType;
  final String? seasonId;
  final DateTime? createdAt;
  final List<RecipeZone> zones;

  String get productLabelAr => switch (productType) {
        'fertility' => 'تسميد',
        'seed' => 'بذار',
        _ => productType ?? 'غير محدّد',
      };

  factory Recipe.fromJson(Object? json) {
    final m = _map(json, 'الوصفة');
    final id = _s(m['prescription_id']);
    if (id == null) throw const FormatException('وصفة بلا معرّف من الخادم.');
    final zones = m['zones'];
    return Recipe(
      id: id,
      name: _s(m['name']) ?? id,
      productType: _s(m['product_type']),
      seasonId: _s(m['season_id']),
      createdAt: DateTime.tryParse('${m['created_at'] ?? ''}'),
      zones: zones is List ? zones.map(RecipeZone.fromJson).toList() : const [],
    );
  }
}

@immutable
class RecipeList {
  const RecipeList({required this.recipes, this.noteAr});
  final List<Recipe> recipes;

  /// سبب صادق يرسله الخادم حين القائمة فارغة لتعطّل القاعدة.
  final String? noteAr;

  factory RecipeList.fromJson(Object? json) {
    final m = _map(json, 'قائمة الوصفات');
    return RecipeList(
      recipes: _list(m['prescriptions'], 'قائمة الوصفات')
          .map(Recipe.fromJson)
          .toList(),
      noteAr: _s(m['note_ar']),
    );
  }
}

// ── خطّة أخذ العيّنات (raster-service soil_zones.compute_soil_sampling_points) ──

@immutable
class SamplePoint {
  const SamplePoint({
    required this.pointId,
    this.zoneId,
    this.lon,
    this.lat,
    this.depthCm,
    this.reasonAr,
    this.tests = const [],
  });

  final String pointId;
  final String? zoneId;
  final double? lon;
  final double? lat;
  final String? depthCm;
  final String? reasonAr;
  final List<String> tests;

  factory SamplePoint.fromJson(Object? json, int index) {
    final f = _map(json, 'نقطة العيّنة');
    final props = f['properties'] is Map ? f['properties'] as Map : const {};
    final geom = f['geometry'] is Map ? f['geometry'] as Map : const {};
    final coords = geom['coordinates'];
    final tests = props['tests'];
    return SamplePoint(
      pointId: _s(props['point_id']) ?? 'نقطة ${index + 1}',
      zoneId: _s(props['zone_id']),
      lon: coords is List && coords.length >= 2 ? _d(coords[0]) : null,
      lat: coords is List && coords.length >= 2 ? _d(coords[1]) : null,
      depthCm: _s(props['depth_cm']),
      reasonAr: _s(props['reason_ar']),
      tests: tests is List
          ? tests.map((t) => '$t').where((t) => t.isNotEmpty).toList()
          : const [],
    );
  }
}

@immutable
class ScanPlan {
  const ScanPlan({
    required this.computed,
    required this.points,
    this.source,
    this.userMessage,
  });

  final bool computed;
  final List<SamplePoint> points;

  /// سبب الخادم حين computed:false (مثل غياب مصدر التربة).
  final String? source;
  final String? userMessage;

  factory ScanPlan.fromJson(Object? json) {
    final m = _map(json, 'خطّة العيّنات');
    final features = _list(m['features'], 'خطّة العيّنات');
    return ScanPlan(
      computed: m['computed'] == true,
      points: [
        for (var i = 0; i < features.length; i++)
          SamplePoint.fromJson(features[i], i),
      ],
      source: _s(m['source']) ?? _s(m['reason']),
      userMessage: _s(m['user_message']),
    );
  }
}

// ── اختيار الحقل ──────────────────────────────────────────────────────────

@immutable
class FieldOption {
  const FieldOption({required this.id, required this.name, this.crop});
  final String id;
  final String name;
  final String? crop;

  static List<FieldOption> listFrom(Object? json) => _list(json, 'قائمة الحقول')
      .map((e) {
        final m = e is Map ? e : const {};
        final id = _s(m['field_id']) ?? _s(m['id']);
        if (id == null) return null;
        return FieldOption(
          id: id,
          name: _s(m['name_ar']) ?? _s(m['name']) ?? id,
          crop: _s(m['crop']),
        );
      })
      .whereType<FieldOption>()
      .toList();
}
