// SAHOOL — features/maps/io/geo/boundary_writer.dart
// كتابة حدود الحقول كـGeoJSON (RFC 7946) أو KML 2.2 للتصدير. تحفظ كلّ الأجزاء
// والثقوب كما أعادها الخادم (لا تُختصَر إلى الحلقة الأولى).
import 'dart:convert';

import 'import_model.dart';
import 'io_geometry.dart';

/// حقل واحد للتصدير.
class ExportBoundary {
  const ExportBoundary({
    required this.fieldId,
    required this.name,
    required this.polygons,
    this.areaHa,
    this.crop,
  });

  final String fieldId;
  final String name;
  final List<IoPolygon> polygons;

  /// مساحة الخادم (area_ha) إن وُجدت — لا تُحسب بديلاً عنها هنا.
  final num? areaHa;
  final String? crop;

  /// من صفّ FieldSummary (GET /api/v1/fields). بلا هندسة صالحة ⇒ null.
  static ExportBoundary? fromField(Map<String, dynamic> f) {
    final polys = polygonsFromGeoJson(f['geometry']);
    if (polys.isEmpty) return null;
    final id = (f['field_id'] ?? f['id'] ?? '').toString();
    final name = (f['name'] ?? '').toString().trim();
    return ExportBoundary(
      fieldId: id,
      name: name.isEmpty ? id : name,
      polygons: polys,
      areaHa: f['area_ha'] is num ? f['area_ha'] as num : null,
      crop: f['crop'] is String ? f['crop'] as String : null,
    );
  }

  Map<String, dynamic> geometryJson() => polygons.length == 1
      ? polygonToGeoJson(polygons.single)
      : {
          'type': 'MultiPolygon',
          'coordinates': [for (final p in polygons) polygonCoordinates(p)],
        };
}

String boundariesToGeoJson(List<ExportBoundary> items) =>
    const JsonEncoder.withIndent('  ').convert({
      'type': 'FeatureCollection',
      'features': [
        for (final b in items)
          {
            'type': 'Feature',
            'id': b.fieldId,
            'properties': {
              'field_id': b.fieldId,
              'name': b.name,
              if (b.areaHa != null) 'area_ha': b.areaHa,
              if (b.crop != null) 'crop': b.crop,
            },
            'geometry': b.geometryJson(),
          },
      ],
    });

String _esc(String s) => s
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');

String _kmlRing(List<List<double>> ring) =>
    ring.map((c) => '${c[0]},${c[1]},0').join(' ');

String _kmlPolygon(IoPolygon p) {
  final coords = polygonCoordinates(p);
  final b = StringBuffer('<Polygon><outerBoundaryIs><LinearRing><coordinates>')
    ..write(_kmlRing(coords.first))
    ..write('</coordinates></LinearRing></outerBoundaryIs>');
  for (final h in coords.skip(1)) {
    b
      ..write('<innerBoundaryIs><LinearRing><coordinates>')
      ..write(_kmlRing(h))
      ..write('</coordinates></LinearRing></innerBoundaryIs>');
  }
  b.write('</Polygon>');
  return b.toString();
}

String boundariesToKml(
  List<ExportBoundary> items, {
  String docName = 'SAHOOL',
}) {
  final b = StringBuffer()
    ..writeln('<?xml version="1.0" encoding="UTF-8"?>')
    ..writeln('<kml xmlns="http://www.opengis.net/kml/2.2">')
    ..writeln('<Document><name>${_esc(docName)}</name>');
  for (final f in items) {
    b
      ..write('<Placemark id="${_esc(f.fieldId)}"><name>${_esc(f.name)}</name>')
      ..write(
        '<ExtendedData><Data name="field_id"><value>${_esc(f.fieldId)}</value></Data>',
      );
    if (f.areaHa != null) {
      b.write('<Data name="area_ha"><value>${f.areaHa}</value></Data>');
    }
    b.write('</ExtendedData>');
    if (f.polygons.length == 1) {
      b.write(_kmlPolygon(f.polygons.single));
    } else {
      b.write('<MultiGeometry>');
      for (final p in f.polygons) {
        b.write(_kmlPolygon(p));
      }
      b.write('</MultiGeometry>');
    }
    b.writeln('</Placemark>');
  }
  b
    ..writeln('</Document>')
    ..writeln('</kml>');
  return b.toString();
}

/// الملفّ الجاهز للمشاركة.
class ExportFile {
  const ExportFile(this.fileName, this.mimeType, this.content);
  final String fileName;
  final String mimeType;
  final String content;
}

ExportFile buildExport(
  List<ExportBoundary> items,
  BoundaryFormat format, {
  required String baseName,
}) {
  final safe = baseName
      .replaceAll(RegExp(r'[\\/:*?"<>|\s]+'), '_')
      .replaceAll(RegExp(r'_+'), '_');
  final stem = safe.isEmpty ? 'sahool_fields' : safe;
  return format == BoundaryFormat.geojson
      ? ExportFile(
          '$stem.geojson',
          'application/geo+json',
          boundariesToGeoJson(items),
        )
      : ExportFile(
          '$stem.kml',
          'application/vnd.google-earth.kml+xml',
          boundariesToKml(items, docName: baseName),
        );
}
