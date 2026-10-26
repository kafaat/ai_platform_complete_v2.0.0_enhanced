import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/draw/boundary_import.dart';

void main() {
  test('GeoJSON Polygon in a Feature', () {
    final b = parseBoundaryText('''
{"type":"Feature","geometry":{"type":"Polygon","coordinates":
[[[44.2,15.35],[44.21,15.35],[44.21,15.36],[44.2,15.35]]]}}''');
    expect(b.ring.first, const LatLng(15.35, 44.2));
    expect(b.ring, hasLength(4));
    expect(b.notes, isEmpty);
  });

  test('MultiPolygon with a hole says what was dropped', () {
    final b = parseBoundaryText('''
{"type":"MultiPolygon","coordinates":[
 [[[44.2,15.35],[44.21,15.35],[44.21,15.36],[44.2,15.35]],
  [[44.205,15.352],[44.206,15.352],[44.206,15.353],[44.205,15.352]]],
 [[[45.2,15.35],[45.21,15.35],[45.21,15.36],[45.2,15.35]]]]}''');
    expect(b.notes.join(' '), contains('2 أجزاء'));
    expect(b.notes.join(' '), contains('ثقوب'));
  });

  test('KML outer boundary, altitude ignored', () {
    final b = parseBoundaryText('''
<kml><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>
44.2,15.35,0 44.21,15.35,0 44.21,15.36,0 44.2,15.35,0
</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>''');
    expect(b.ring, hasLength(4));
    expect(b.ring[1], const LatLng(15.35, 44.21));
  });

  test('bad input is an honest error, not an empty ring', () {
    expect(
      () => parseBoundaryText('{"type":"Point","coordinates":[1,2]}'),
      throwsA(isA<BoundaryImportException>()),
    );
    expect(
      () => parseBoundaryText('not json'),
      throwsA(isA<BoundaryImportException>()),
    );
  });
}
