// SAHOOL — features/maps/draw/boundary_import.dart
// تحليل نصّ GeoJSON أو KML ملصوق إلى حلقة حدٍّ واحدة تُحمَّل في أداة الرسم،
// فتمرّ بالتحقّق الحاجب نفسه وتُعرَض مساحتها كما سيخزّنها الخادم.
//
// صدق: الخادم يحتفظ بالحلقة الخارجيّة للجزء الأوّل فقط (geo_import.py)، ويهمل
// الثقوب في المساحة. فإن حوى الملفّ أجزاءً أو ثقوباً نقول ذلك صراحةً بدل إسقاطها
// بصمت.
import 'dart:convert';

import 'package:latlong2/latlong.dart';

class ImportedBoundary {
  const ImportedBoundary(this.ring, this.notes);
  final List<LatLng> ring;

  /// ملاحظات صادقة عمّا أُهمِل (أجزاء إضافيّة، ثقوب، ارتفاعات).
  final List<String> notes;
}

class BoundaryImportException implements Exception {
  const BoundaryImportException(this.messageAr);
  final String messageAr;
  @override
  String toString() => messageAr;
}

List<LatLng> _ringFromCoords(Object? raw) {
  if (raw is! List) {
    throw const BoundaryImportException('إحداثيّات الحلقة ليست قائمة.');
  }
  final out = <LatLng>[];
  for (final c in raw) {
    if (c is! List || c.length < 2 || c[0] is! num || c[1] is! num) {
      throw const BoundaryImportException(
        'نقطة غير صالحة: المتوقَّع [خطّ الطول، خطّ العرض].',
      );
    }
    final lon = (c[0] as num).toDouble(), lat = (c[1] as num).toDouble();
    if (!lon.isFinite || !lat.isFinite) {
      throw const BoundaryImportException('إحداثيّة غير محدودة في الملفّ.');
    }
    out.add(LatLng(lat, lon));
  }
  return out;
}

/// يجمع مضلّعات GeoJSON (كلّ مضلّع: قائمة حلقات) من أيّ شكل مدعوم.
void _collectPolygons(Object? node, List<List<Object?>> out) {
  if (node is! Map) return;
  switch (node['type']) {
    case 'Polygon':
      final c = node['coordinates'];
      if (c is List && c.isNotEmpty) out.add(c);
    case 'MultiPolygon':
      final c = node['coordinates'];
      if (c is List) {
        for (final p in c) {
          if (p is List && p.isNotEmpty) out.add(p);
        }
      }
    case 'Feature':
      _collectPolygons(node['geometry'], out);
    case 'FeatureCollection':
      final f = node['features'];
      if (f is List) {
        for (final x in f) {
          _collectPolygons(x, out);
        }
      }
  }
}

ImportedBoundary parseGeoJsonBoundary(String text) {
  Object? decoded;
  try {
    decoded = json.decode(text.trim());
  } on FormatException {
    throw const BoundaryImportException('النصّ ليس JSON صالحاً.');
  }
  final polys = <List<Object?>>[];
  _collectPolygons(decoded, polys);
  if (polys.isEmpty) {
    throw const BoundaryImportException(
      'لا يوجد Polygon أو MultiPolygon في GeoJSON.',
    );
  }
  final notes = <String>[];
  if (polys.length > 1) {
    notes.add(
      'الملفّ يحوي ${polys.length} أجزاء؛ استُعمل الجزء الأوّل وحده '
      '(الخادم يحفظ حدّاً واحداً لكلّ حقل). أنشئ بقيّة الأجزاء حقولاً منفصلة.',
    );
  }
  if (polys.first.length > 1) {
    notes.add('أُهمِلت ${polys.first.length - 1} ثقوب داخل الحدّ.');
  }
  return ImportedBoundary(_ringFromCoords(polys.first.first), notes);
}

final _coordsTag = RegExp(
  r'<(?:\w+:)?coordinates[^>]*>([\s\S]*?)</(?:\w+:)?coordinates>',
);
final _outerTag = RegExp(
  r'<(?:\w+:)?outerBoundaryIs[^>]*>([\s\S]*?)</(?:\w+:)?outerBoundaryIs>',
);
final _innerTag = RegExp(r'<(?:\w+:)?innerBoundaryIs');

ImportedBoundary parseKmlBoundary(String text) {
  final outers = _outerTag.allMatches(text).toList();
  if (outers.isEmpty) {
    throw const BoundaryImportException(
      'لا يوجد Polygon (outerBoundaryIs) في KML.',
    );
  }
  final coordsMatch = _coordsTag.firstMatch(outers.first.group(1)!);
  if (coordsMatch == null) {
    throw const BoundaryImportException('حدّ KML بلا إحداثيّات.');
  }
  final ring = <LatLng>[];
  for (final tuple in coordsMatch.group(1)!.trim().split(RegExp(r'\s+'))) {
    if (tuple.isEmpty) continue;
    final parts = tuple.split(',');
    final lon = parts.isNotEmpty ? double.tryParse(parts[0]) : null;
    final lat = parts.length > 1 ? double.tryParse(parts[1]) : null;
    if (lon == null || lat == null || !lon.isFinite || !lat.isFinite) {
      throw BoundaryImportException('إحداثيّة KML غير صالحة: «$tuple».');
    }
    ring.add(LatLng(lat, lon));
  }
  final notes = <String>[];
  if (outers.length > 1) {
    notes.add(
      'الملفّ يحوي ${outers.length} مضلّعات؛ استُعمل الأوّل وحده. '
      'أنشئ البقيّة حقولاً منفصلة.',
    );
  }
  final holes = _innerTag.allMatches(text).length;
  if (holes > 0) notes.add('أُهمِلت $holes ثقوب داخل الحدّ.');
  return ImportedBoundary(ring, notes);
}

/// يكتشف الصيغة من المحتوى: يبدأ بـ`<` ⇒ KML، وإلّا GeoJSON.
ImportedBoundary parseBoundaryText(String text) {
  final t = text.trim();
  if (t.isEmpty) throw const BoundaryImportException('النصّ فارغ.');
  return t.startsWith('<') ? parseKmlBoundary(t) : parseGeoJsonBoundary(t);
}
