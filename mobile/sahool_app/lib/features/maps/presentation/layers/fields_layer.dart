// SAHOOL — features/maps/presentation/layers/fields_layer.dart
// طبقة حقول المستخدم: ملء وحدّ حسب حالة الحقل (أو NDVI إن مُرِّر مقيساً)، تسمية،
// اختيار، واختبار نقر يحترم الثقوب و MultiPolygon.
//
// الخلل الذي يسدّه: شاشة الحقول قرأت `coordinates.first` فقط، فأسقطت كلّ حقل
// MultiPolygon بصمت (الخادم يحوّل المضلّع المتقاطع ذاتيّاً إلى MultiPolygon) وتجاهلت
// الثقوب، وبلا تسميات ولا نقر.
//
// «الحالة» من GET /api/v1/fields: `quality_grade` (READY/LIMITED/PENDING_LAB/
// BLOCKED — field_models.py::field_quality_grade). `health_summary_ar` يُرجعه
// الخادم "—" في القائمة فلا نعرضه صحّةً. NDVI لا يأتي في القائمة؛ إن مرّره
// المستدعي من مصدر مقيس لُوِّن به، وإلّا لا لون صحّة مُختلَق.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import '../../geo/geo_json.dart';

/// رابط مساحة عمل الحقل (مسار ميزة الحقول: `/fields/workspace?field_id=`).
String fieldWorkspaceRoute(String fieldId) =>
    '/fields/workspace?field_id=${Uri.encodeQueryComponent(fieldId)}';

/// حالة الحقل كما يُسقطها الخادم من الحالة القانونيّة.
enum FieldMapStatus {
  ready('READY', 'جاهز للقرار', Icons.check_circle_outline),
  limited('LIMITED', 'بيانات محدودة', Icons.info_outline),
  pendingLab('PENDING_LAB', 'بانتظار تحليل التربة', Icons.science_outlined),
  blocked('BLOCKED', 'محجوب (تعارض/نقص)', Icons.block),
  unknown('', 'غير معروف', Icons.help_outline);

  const FieldMapStatus(this.code, this.labelAr, this.icon);
  final String code;
  final String labelAr;
  final IconData icon;

  static FieldMapStatus parse(Object? code) {
    final c = code?.toString().toUpperCase();
    return FieldMapStatus.values.firstWhere(
      (s) => s.code == c && s != unknown,
      orElse: () => unknown,
    );
  }

  Color color(SahoolTokens t) => switch (this) {
    ready => t.success,
    limited => t.warning,
    pendingLab => t.info,
    blocked => t.danger,
    unknown => t.muted,
  };
}

/// حقل على الخريطة.
@immutable
class MapField {
  const MapField({
    required this.id,
    required this.name,
    this.geometry,
    this.status = FieldMapStatus.unknown,
    this.areaHa,
    this.crop,
    this.ndvi,
  });

  /// من صفّ FieldSummary (GET /api/v1/fields).
  factory MapField.fromSummary(Map<String, dynamic> j) {
    final crop = j['crop']?.toString();
    return MapField(
      id: (j['field_id'] ?? j['id'] ?? '').toString(),
      name: (j['name_ar'] ?? j['name'] ?? '').toString(),
      geometry: FieldGeometry.tryParse(j['geometry']),
      status: FieldMapStatus.parse(j['quality_grade']),
      areaHa: (j['area_ha'] as num?)?.toDouble(),
      crop: (crop == null || crop == '—' || crop.isEmpty) ? null : crop,
    );
  }

  final String id;
  final String name;
  final FieldGeometry? geometry;
  final FieldMapStatus status;

  /// مساحة الخادم المخزّنة (لا تُعاد حسابها هنا).
  final double? areaHa;
  final String? crop;

  /// NDVI مقيس إن توفّر من مصدر حقيقيّ؛ null ⇒ يُلوَّن بالحالة.
  final double? ndvi;

  bool get hasGeometry => geometry != null && !geometry!.isEmpty;

  MapField copyWith({double? ndvi}) => MapField(
    id: id,
    name: name,
    geometry: geometry,
    status: status,
    areaHa: areaHa,
    crop: crop,
    ndvi: ndvi ?? this.ndvi,
  );
}

/// الحقل تحت [point] (الأعلى رسماً أوّلاً)؛ null إن لم يقع داخل أيّ حقل.
MapField? fieldAt(List<MapField> fields, LatLng point) {
  for (final f in fields.reversed) {
    if (f.geometry?.contains(point) ?? false) return f;
  }
  return null;
}

/// إطار كلّ الحقول المرسومة؛ null إن لم يكن لأيّ حقل هندسة.
LatLngBounds? fieldsBounds(List<MapField> fields) {
  final pts = [
    for (final f in fields)
      if (f.hasGeometry) ...f.geometry!.allPoints,
  ];
  return pts.isEmpty ? null : LatLngBounds.fromPoints(pts);
}

/// مضلّعات flutter_map: جزء لكلّ مضلّع (MultiPolygon ⇒ عدّة أجزاء) بثقوبه.
/// التسمية على الجزء الأكبر فقط كي لا تتكرّر.
List<Polygon<String>> buildFieldPolygons(
  List<MapField> fields, {
  required SahoolTokens tokens,
  String? selectedId,
  bool showLabels = true,
  Color? selectedColor,
}) {
  final out = <Polygon<String>>[];
  for (final f in fields) {
    final g = f.geometry;
    if (g == null || g.isEmpty) continue;
    final base = f.ndvi != null ? ndviColor(f.ndvi) : f.status.color(tokens);
    final selected = f.id == selectedId;
    var labelPart = 0;
    var best = -1.0;
    for (var i = 0; i < g.polygons.length; i++) {
      final a = ringSignedArea(g.polygons[i].outer).abs();
      if (a > best) {
        best = a;
        labelPart = i;
      }
    }
    for (var i = 0; i < g.polygons.length; i++) {
      final part = g.polygons[i];
      out.add(
        Polygon<String>(
          points: part.outer,
          holePointsList: part.holes.isEmpty ? null : part.holes,
          color: base.withValues(alpha: selected ? 0.42 : 0.28),
          borderColor: selected ? (selectedColor ?? tokens.accent) : base,
          borderStrokeWidth: selected ? 4 : 2,
          hitValue: f.id,
          label: showLabels && i == labelPart && f.name.isNotEmpty
              ? f.name
              : null,
          labelStyle: TextStyle(
            color: Colors.white,
            fontSize: SahoolType.body,
            fontWeight: SahoolType.semibold,
            shadows: const [Shadow(blurRadius: 3, offset: Offset(0, 1))],
          ),
          labelPlacement: PolygonLabelPlacement.polylabel,
          rotateLabel: true,
        ),
      );
    }
  }
  return out;
}

/// الطبقة الجاهزة. النقر يُعالَج في الشاشة عبر [fieldAt] (يحترم الثقوب).
class FieldsLayer extends StatelessWidget {
  const FieldsLayer({
    super.key,
    required this.fields,
    this.selectedId,
    this.showLabels = true,
  });

  final List<MapField> fields;
  final String? selectedId;
  final bool showLabels;

  @override
  Widget build(BuildContext context) => PolygonLayer<String>(
    polygons: buildFieldPolygons(
      fields,
      tokens: context.tokens,
      selectedId: selectedId,
      showLabels: showLabels,
    ),
    drawLabelsLast: true,
  );
}

/// أسطورة الحالات: لون + أيقونة + نصّ (لا لون وحده).
class FieldStatusLegend extends StatelessWidget {
  const FieldStatusLegend({super.key, this.statuses});

  /// الحالات المعروضة؛ null ⇒ الأربع المعروفة.
  final Iterable<FieldMapStatus>? statuses;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final list =
        (statuses ??
                FieldMapStatus.values.where((s) => s != FieldMapStatus.unknown))
            .toList();
    return Material(
      color: Theme.of(context).colorScheme.surface.withValues(alpha: 0.92),
      borderRadius: SahoolRadius.mdAll,
      child: Padding(
        padding: const EdgeInsetsDirectional.all(SahoolSpacing.sm),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final s in list)
              Padding(
                padding: const EdgeInsetsDirectional.symmetric(
                  vertical: SahoolSpacing.xxs,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(s.icon, size: SahoolSizes.iconSm, color: s.color(t)),
                    const SizedBox(width: SahoolSpacing.xs),
                    Text(
                      s.labelAr,
                      style: TextStyle(
                        fontSize: SahoolType.caption,
                        color: t.ink,
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
