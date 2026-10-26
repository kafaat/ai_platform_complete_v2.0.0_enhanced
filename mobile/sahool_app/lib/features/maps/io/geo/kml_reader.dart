// SAHOOL — features/maps/io/geo/kml_reader.dart
// محلّل KML أدنى (Dart نقيّ، بلا تبعيّة): يستخرج <Placemark> ← <Polygon> (ومنها ما
// داخل <MultiGeometry>) ← outerBoundaryIs/innerBoundaryIs ← <coordinates>.
//
// لماذا لا package:xml: موجود في pubspec.lock **عابراً** فقط؛ استيراده دون إعلانه
// مباشرةً يخالف depend_on_referenced_packages ويتعلّق بتبعيّة قد تختفي. وتعديل
// pubspec خارج ملكيّة هذه الحزمة (طُلب ترقيته في التقرير). المحلّل هنا لا يوسّع
// أيّ كيانات، ويرفض DTD/ENTITY صراحةً كما يفعل الخادم (defusedxml).
import 'package:latlong2/latlong.dart';

import 'import_model.dart';
import 'io_geometry.dart';

const _ns = r'(?:[A-Za-z_][\w.-]*:)?';

RegExp _block(String tag) =>
    RegExp('<$_ns$tag(?:\\s[^>]*)?>(.*?)</$_ns$tag\\s*>', dotAll: true);

final _comment = RegExp(r'<!--.*?-->', dotAll: true);
final _cdata = RegExp(r'<!\[CDATA\[(.*?)\]\]>', dotAll: true);
final _placemark = _block('Placemark');
final _polygon = _block('Polygon');
final _outer = _block('outerBoundaryIs');
final _inner = _block('innerBoundaryIs');
final _coordinates = _block('coordinates');
final _name = _block('name');
final _nonPolygon = RegExp(
  '<$_ns(Point|LineString|Track|MultiTrack)(?:\\s[^>]*)?>',
);

ParsedImport parseKmlText(String text) {
  if (RegExp(r'<!(DOCTYPE|ENTITY)', caseSensitive: false).hasMatch(text)) {
    throw const FormatException(
      'KML غير آمن: يحوي تعريفات DTD/كيانات XML غير مسموح بها.',
    );
  }
  final doc = text.replaceAll(_comment, '');
  if (!RegExp(
    '<${_ns}kml[\\s>]|<${_ns}Placemark[\\s>]|<${_ns}Polygon[\\s>]',
  ).hasMatch(doc)) {
    throw const FormatException(
      'ليس ملفّ KML — لا يوجد وسم <kml> أو <Placemark>.',
    );
  }
  final shapes = <ImportedShape>[];
  final warnings = <String>[];
  final placemarks = _placemark
      .allMatches(doc)
      .map((m) => m.group(1)!)
      .toList();
  // ملفّ بلا Placemark (Polygon مباشرة) يُعامَل كمعلم واحد بلا اسم.
  final containers = placemarks.isEmpty ? [doc] : placemarks;
  var skippedOther = 0;

  for (var i = 0; i < containers.length; i++) {
    final body = containers[i];
    final name = _textOf(_name.firstMatch(body)?.group(1));
    final polys = _polygon.allMatches(body).toList();
    skippedOther += _nonPolygon.allMatches(body).length;
    for (var p = 0; p < polys.length; p++) {
      final where =
          'المعلم ${i + 1}${polys.length > 1 ? ' (جزء ${p + 1})' : ''}';
      final pb = polys[p].group(1)!;
      final outerSrc = _outer.firstMatch(pb)?.group(1) ?? pb;
      final outerCoords = _coordinates.firstMatch(outerSrc)?.group(1);
      final List<LatLng>? outer;
      try {
        outer = outerCoords == null ? null : _parseCoords(outerCoords);
      } on FormatException catch (e) {
        warnings.add('تُجوهِل مضلّع $where: ${e.message}');
        continue;
      }
      if (outer == null || outer.length < 3) {
        warnings.add('تُجوهِل مضلّع $where: الحلقة الخارجيّة أقلّ من 3 نقاط.');
        continue;
      }
      final rings = [outer];
      for (final im in _inner.allMatches(pb)) {
        final c = _coordinates.firstMatch(im.group(1)!)?.group(1);
        try {
          final hole = c == null ? null : _parseCoords(c);
          if (hole != null && hole.length >= 3) {
            rings.add(hole);
          } else {
            warnings.add('أُهمل ثقب تالف في $where.');
          }
        } on FormatException {
          warnings.add('أُهمل ثقب تالف في $where.');
        }
      }
      shapes.add(
        ImportedShape(
          polygon: IoPolygon(rings),
          name: name,
          featureIndex: i,
          partIndex: polys.length > 1 ? p : null,
        ),
      );
    }
  }
  if (skippedOther > 0) {
    warnings.add('تُجوهِل $skippedOther عنصراً ليس مضلّعاً (نقطة/خطّ/مسار).');
  }
  if (shapes.isEmpty) {
    throw FormatException(
      ['لا يوجد <Polygon> صالح في ملفّ KML.', ...warnings].join(' '),
    );
  }
  return ParsedImport(
    format: BoundaryFormat.kml,
    shapes: shapes,
    warnings: warnings,
  );
}

/// «lon,lat[,alt]» مفصولة بمسافات/أسطر ⇒ حلقة مفتوحة.
List<LatLng> _parseCoords(String raw) {
  final cleaned = _textOf(raw) ?? '';
  // بعض المصدِّرين يضعون مسافة بعد الفاصلة: «44.1, 15.2».
  final tokens = cleaned
      .replaceAll(RegExp(r'\s*,\s*'), ',')
      .split(RegExp(r'\s+'))
      .where((t) => t.isNotEmpty);
  final pts = <LatLng>[];
  for (final t in tokens) {
    final parts = t.split(',');
    if (parts.length < 2) {
      throw FormatException('إحداثيّة غير صالحة «$t» (المتوقَّع lon,lat).');
    }
    final lon = double.tryParse(parts[0]);
    final lat = double.tryParse(parts[1]);
    if (lon == null ||
        lat == null ||
        !lon.isFinite ||
        !lat.isFinite ||
        lat.abs() > 90 ||
        lon.abs() > 180) {
      throw FormatException('إحداثيّة غير صالحة «$t».');
    }
    pts.add(LatLng(lat, lon));
  }
  return openRing(pts);
}

/// نصّ عنصر: يفكّ CDATA وكيانات XML الأساسيّة (لا كيانات مخصّصة).
String? _textOf(String? raw) {
  if (raw == null) return null;
  var s = raw.replaceAllMapped(_cdata, (m) => m.group(1)!);
  s = s
      .replaceAll('&lt;', '<')
      .replaceAll('&gt;', '>')
      .replaceAll('&quot;', '"')
      .replaceAll('&apos;', "'")
      .replaceAll('&amp;', '&')
      .trim();
  return s.isEmpty ? null : s;
}
