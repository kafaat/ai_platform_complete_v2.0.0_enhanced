// SAHOOL — features/maps/presentation/layers/drawings_layer.dart
// رسومات الخريطة المحفوظة (مناطق إدارة/وصفة/استبعاد، مسارات، قياسات، دبابيس)
// بشكل DrawFeatureOut من routers/drawing_features.py: {id, kind, geometry,
// properties.name}. الهندسة Point/LineString/Polygon/MultiPolygon. عرض فقط؛
// التحرير ملك حزمة الرسم.
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/core/theme/sahool_tokens.dart';
import 'package:sahool_app/core/theme/tokens.dart';

import '../../geo/geo_json.dart';

@immutable
class MapDrawing {
  const MapDrawing({
    required this.id,
    required this.kind,
    this.polygons,
    this.lines = const [],
    this.points = const [],
    this.name,
  });

  /// من عنصر DrawFeatureOut. هندسة تالفة ⇒ null (لا تُرسم ولا تُسقط الطبقة).
  static MapDrawing? fromJson(Map<String, dynamic> j) {
    final geom = j['geometry'];
    if (geom is! Map) return null;
    final props = j['properties'];
    final name = props is Map ? props['name']?.toString() : null;
    final id = (j['id'] ?? '').toString();
    final kind = (j['kind'] ?? '').toString();
    try {
      switch (geom['type']) {
        case 'Polygon' || 'MultiPolygon':
          return MapDrawing(
            id: id,
            kind: kind,
            name: name,
            polygons: FieldGeometry.fromGeoJson(geom),
          );
        case 'LineString':
          return MapDrawing(
            id: id,
            kind: kind,
            name: name,
            lines: [latLngsFromPositions(geom['coordinates'])],
          );
        case 'Point':
          return MapDrawing(
            id: id,
            kind: kind,
            name: name,
            points: [latLngFromPosition(geom['coordinates'])],
          );
      }
    } on FormatException {
      return null;
    }
    return null;
  }

  final String id;

  /// DrawKind في الخادم: management-zone, prescription-zone, exclusion-zone,
  /// pivot, field, path, measurement, scout-pin.
  final String kind;
  final FieldGeometry? polygons;
  final List<List<LatLng>> lines;
  final List<LatLng> points;
  final String? name;
}

/// لون كلّ نوع (مع نمط خطّ مختلف للاستبعاد كي لا يعتمد على اللون وحده).
Color drawingColor(String kind, SahoolTokens t) => switch (kind) {
  'exclusion-zone' => t.danger,
  'prescription-zone' => t.accent,
  'management-zone' => t.info,
  'pivot' || 'field' => t.success,
  _ => t.warning,
};

class DrawingsLayer extends StatelessWidget {
  const DrawingsLayer({super.key, required this.drawings});
  final List<MapDrawing> drawings;

  @override
  Widget build(BuildContext context) {
    final t = context.tokens;
    final polys = <Polygon>[];
    final lines = <Polyline>[];
    final markers = <Marker>[];
    for (final d in drawings) {
      final c = drawingColor(d.kind, t);
      final dashed = d.kind == 'exclusion-zone';
      for (final p in d.polygons?.polygons ?? const <GeoPolygon>[]) {
        polys.add(
          Polygon(
            points: p.outer,
            holePointsList: p.holes.isEmpty ? null : p.holes,
            color: c.withValues(alpha: 0.2),
            borderColor: c,
            borderStrokeWidth: 2,
            pattern: dashed
                ? const StrokePattern.dotted()
                : const StrokePattern.solid(),
            label: d.name,
            labelStyle: TextStyle(
              color: t.ink,
              fontSize: SahoolType.caption,
              fontWeight: SahoolType.semibold,
            ),
          ),
        );
      }
      for (final l in d.lines) {
        lines.add(Polyline(points: l, color: c, strokeWidth: 3));
      }
      for (final pt in d.points) {
        markers.add(
          Marker(
            point: pt,
            width: SahoolSizes.iconLg,
            height: SahoolSizes.iconLg,
            child: Icon(Icons.push_pin, color: c, semanticLabel: d.name),
          ),
        );
      }
    }
    return Stack(
      children: [
        if (polys.isNotEmpty) PolygonLayer(polygons: polys),
        if (lines.isNotEmpty) PolylineLayer(polylines: lines),
        if (markers.isNotEmpty) MarkerLayer(markers: markers),
      ],
    );
  }
}
