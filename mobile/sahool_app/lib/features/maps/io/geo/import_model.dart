// SAHOOL — features/maps/io/geo/import_model.dart
// ناتج تحليل ملفّ حدود (GeoJSON/KML) على الجهاز: كلّ مضلّع قابل للاختيار
// منفرداً، مع ما أُهمل وسببه — لا يُسقَط جزء بصمت.
import 'dart:convert';

import 'geojson_reader.dart';
import 'io_geometry.dart';
import 'kml_reader.dart';

enum BoundaryFormat { geojson, kml }

extension BoundaryFormatX on BoundaryFormat {
  String get labelAr => this == BoundaryFormat.geojson ? 'GeoJSON' : 'KML';
}

/// مضلّع واحد مستخرَج من الملفّ.
class ImportedShape {
  const ImportedShape({
    required this.polygon,
    required this.featureIndex,
    this.name,
    this.partIndex,
  });

  final IoPolygon polygon;

  /// اسم من الملفّ (properties.name أو وسم name في KML) إن وُجد.
  final String? name;

  /// ترتيب المعلم في الملفّ (يبدأ من 0).
  final int featureIndex;

  /// رقم الجزء داخل MultiPolygon/MultiGeometry (null ⇒ مضلّع منفرد).
  final int? partIndex;

  /// اسم مقترح للحقل (قابل للتعديل في الواجهة).
  String suggestedName(int ordinal) {
    final base = (name != null && name!.trim().isNotEmpty)
        ? name!.trim()
        : 'حقل مستورَد ${ordinal + 1}';
    return partIndex == null ? base : '$base — جزء ${partIndex! + 1}';
  }
}

class ParsedImport {
  const ParsedImport({
    required this.format,
    required this.shapes,
    this.warnings = const [],
  });

  final BoundaryFormat format;
  final List<ImportedShape> shapes;

  /// ما أُهمل وسببه (نقاط/خطوط، حلقات تالفة، …) — تُعرَض للمستخدم.
  final List<String> warnings;
}

/// يكتشف الصيغة من المحتوى: يبدأ بـ«{» ⇒ GeoJSON، وبـ«<» ⇒ KML.
BoundaryFormat? sniffFormat(String text) {
  final t = text.trimLeft();
  if (t.startsWith('{')) return BoundaryFormat.geojson;
  if (t.startsWith('<')) return BoundaryFormat.kml;
  return null;
}

/// يحلّل نصّ ملفّ حدود. يرمي [FormatException] برسالة عربيّة عند محتوى تالف
/// أو خالٍ من المضلّعات.
ParsedImport parseBoundaryText(String text, {BoundaryFormat? format}) {
  if (text.trim().isEmpty) {
    throw const FormatException('المحتوى فارغ — الصق نصّ ملفّ GeoJSON أو KML.');
  }
  final f = format ?? sniffFormat(text);
  switch (f) {
    case BoundaryFormat.geojson:
      return parseGeoJsonText(text);
    case BoundaryFormat.kml:
      return parseKmlText(text);
    case null:
      throw const FormatException(
        'صيغة غير معروفة — المتوقَّع GeoJSON (يبدأ بـ{) أو KML (يبدأ بـ<).',
      );
  }
}

/// نصّ GeoJSON لمضلّع واحد (ما يُرسَل في content لنقطة الاستيراد).
String polygonGeoJsonText(IoPolygon p) => jsonEncode(polygonToGeoJson(p));
