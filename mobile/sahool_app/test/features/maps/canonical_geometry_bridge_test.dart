// جسر النموذج الكنسيّ إلى المحوّل الموحّد: Polygon وحده، مساحة وإطار بطريقة الخادم.
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/geo/geo_json.dart';
import 'package:sahool_app/features/maps/geo/geo_measure.dart';
import 'package:sahool_app/models/canonical_field_geometry.dart';

void main() {
  final square = FieldGeometry.polygon(const [
    LatLng(16.20, 44.70),
    LatLng(16.209, 44.70), // مع عقارب الساعة عمداً
    LatLng(16.209, 44.70941),
    LatLng(16.20, 44.70941),
  ]);

  test('fromPolygon: closed CCW ring, server area, literal bbox keys', () {
    final c = CanonicalFieldGeometry.fromPolygon(square);
    expect(c.geometry['type'], 'Polygon');
    final ring = (c.geometry['coordinates'] as List).first as List;
    expect(ring.first, ring.last);
    expect(c.areaHa, closeTo(100.55355735901693, 100.55 * 1e-4));
    expect(c.bbox.toJson(), {
      'min_lng': 44.70,
      'min_lat': 16.20,
      'max_lng': 44.70941,
      'max_lat': 16.209,
    });
    expect(c.source, 'mobile-draw');
    // يعود عبر JSON ويُقرأ بالمحوّل نفسه.
    final back = CanonicalFieldGeometry.fromJson(c.toJson()).parsed!;
    expect(serverAreaHa(back), closeTo(c.areaHa, 1e-9));
  });

  test('MultiPolygon is refused: the Python contract is Polygon-only', () {
    final multi = FieldGeometry([
      ...square.polygons,
      GeoPolygon(const [LatLng(15, 44), LatLng(15, 44.01), LatLng(15.01, 44)]),
    ]);
    expect(
      () => CanonicalFieldGeometry.fromPolygon(multi),
      throwsArgumentError,
    );
    expect(
      () => CanonicalFieldGeometry.fromPolygon(FieldGeometry(const [])),
      throwsArgumentError,
    );
  });
}
