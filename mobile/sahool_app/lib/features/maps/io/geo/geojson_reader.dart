// SAHOOL — features/maps/io/geo/geojson_reader.dart
// محلّل GeoJSON على الجهاز (Dart نقيّ): Polygon وMultiPolygon وFeature
// وFeatureCollection وGeometryCollection. بخلاف الخادم (geo_import.parse_geojson
// يأخذ أوّل حلقة فقط) يُعيد كلّ المضلّعات بثقوبها كي يختار المستخدم، ويبلّغ عمّا
// أُهمل (نقاط، خطوط، حلقات تالفة).
import 'dart:convert';

import 'package:latlong2/latlong.dart';

import 'import_model.dart';
import 'io_geometry.dart';

ParsedImport parseGeoJsonText(String text) {
  final Object? data;
  try {
    data = jsonDecode(text);
  } on FormatException catch (e) {
    throw FormatException('GeoJSON غير صالح (JSON تالف): ${e.message}');
  }
  if (data is! Map) {
    throw const FormatException('GeoJSON غير صالح — المتوقَّع كائن JSON.');
  }
  final ctx = _Ctx();
  final type = data['type'];
  if (type == 'FeatureCollection') {
    final features = data['features'];
    if (features is! List) {
      throw const FormatException('FeatureCollection بلا features.');
    }
    for (var i = 0; i < features.length; i++) {
      final f = features[i];
      if (f is! Map || f['type'] != 'Feature') {
        ctx.warn('تُجوهِل عنصر ${i + 1}: ليس Feature.');
        continue;
      }
      ctx.feature(f, i);
    }
  } else if (type == 'Feature') {
    ctx.feature(data, 0);
  } else {
    ctx.geometry(data, 0, null);
  }
  if (ctx.shapes.isEmpty) {
    throw FormatException(
      [
        'لا يوجد مضلّع (Polygon/MultiPolygon) صالح في الملفّ.',
        ...ctx.warnings,
      ].join(' '),
    );
  }
  return ParsedImport(
    format: BoundaryFormat.geojson,
    shapes: ctx.shapes,
    warnings: ctx.warnings,
  );
}

class _Ctx {
  final shapes = <ImportedShape>[];
  final warnings = <String>[];
  final _skipped = <String, int>{};

  void warn(String w) => warnings.add(w);

  void feature(Map<dynamic, dynamic> f, int index) {
    final props = f['properties'];
    String? name;
    if (props is Map) {
      for (final k in const ['name', 'Name', 'NAME', 'name_ar', 'title']) {
        final v = props[k];
        if (v is String && v.trim().isNotEmpty) {
          name = v.trim();
          break;
        }
      }
    }
    final g = f['geometry'];
    if (g is! Map) {
      warn('تُجوهِل المعلم ${index + 1}: بلا هندسة.');
      return;
    }
    geometry(g, index, name);
  }

  void geometry(Map<dynamic, dynamic> g, int index, String? name) {
    final type = g['type'];
    switch (type) {
      case 'Polygon':
        _addPolygon(g['coordinates'], index, name, null);
      case 'MultiPolygon':
        final parts = g['coordinates'];
        if (parts is! List) {
          warn('MultiPolygon في المعلم ${index + 1} بلا إحداثيّات.');
          return;
        }
        for (var p = 0; p < parts.length; p++) {
          _addPolygon(parts[p], index, name, parts.length > 1 ? p : null);
        }
      case 'GeometryCollection':
        final geoms = g['geometries'];
        if (geoms is List) {
          for (final sub in geoms) {
            if (sub is Map) geometry(sub, index, name);
          }
        }
      default:
        final key = '$type';
        _skipped[key] = (_skipped[key] ?? 0) + 1;
        if (_skipped[key] == 1) {
          warn('تُجوهِلت هندسة من نوع $type (ليست مضلّعاً).');
        }
    }
  }

  void _addPolygon(Object? coords, int index, String? name, int? part) {
    final where =
        'المعلم ${index + 1}${part == null ? '' : ' (جزء ${part + 1})'}';
    if (coords is! List || coords.isEmpty) {
      warn('تُجوهِل مضلّع $where: بلا حلقات.');
      return;
    }
    final rings = <List<LatLng>>[];
    for (var r = 0; r < coords.length; r++) {
      final ring = _ring(coords[r]);
      if (ring == null) {
        if (r == 0) {
          warn(
            'تُجوهِل مضلّع $where: الحلقة الخارجيّة تالفة أو أقلّ من 3 نقاط.',
          );
          return;
        }
        warn('أُهمل ثقب تالف في $where.');
        continue;
      }
      rings.add(ring);
    }
    shapes.add(
      ImportedShape(
        polygon: IoPolygon(rings),
        name: name,
        featureIndex: index,
        partIndex: part,
      ),
    );
  }

  List<LatLng>? _ring(Object? raw) {
    if (raw is! List) return null;
    final pts = <LatLng>[];
    for (final p in raw) {
      if (p is! List || p.length < 2 || p[0] is! num || p[1] is! num) {
        return null;
      }
      final lon = (p[0] as num).toDouble();
      final lat = (p[1] as num).toDouble();
      if (!lon.isFinite || !lat.isFinite || lat.abs() > 90 || lon.abs() > 180) {
        return null;
      }
      pts.add(LatLng(lat, lon));
    }
    final open = openRing(pts);
    return open.length >= 3 ? open : null;
  }
}
