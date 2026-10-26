// عيّنات حدود حقيقيّة الشكل حول صنعاء (lon≈44.2، lat≈15.35) — للاختبارات فقط.
import 'dart:convert';

/// مربّع ~100×100 م (lon,lat).
const square = [
  [44.2000, 15.3500],
  [44.2010, 15.3500],
  [44.2010, 15.3510],
  [44.2000, 15.3510],
  [44.2000, 15.3500],
];

/// ثقب داخل [square].
const hole = [
  [44.2003, 15.3503],
  [44.2003, 15.3506],
  [44.2006, 15.3506],
  [44.2006, 15.3503],
  [44.2003, 15.3503],
];

/// مربّع ثانٍ بجوار الأوّل.
const square2 = [
  [44.2020, 15.3500],
  [44.2030, 15.3500],
  [44.2030, 15.3510],
  [44.2020, 15.3510],
  [44.2020, 15.3500],
];

/// فراشة (bow-tie): تتقاطع أضلاعها.
const bowtie = [
  [44.2000, 15.3500],
  [44.2010, 15.3510],
  [44.2010, 15.3500],
  [44.2000, 15.3510],
  [44.2000, 15.3500],
];

String polygonJson(List<List<List<double>>> rings) =>
    jsonEncode({'type': 'Polygon', 'coordinates': rings});

String featureCollection() => jsonEncode({
  'type': 'FeatureCollection',
  'features': [
    {
      'type': 'Feature',
      'properties': {'name': 'حقل البنّ'},
      'geometry': {
        'type': 'Polygon',
        'coordinates': [square, hole],
      },
    },
    {
      'type': 'Feature',
      'properties': {'name': 'المدرّجات'},
      'geometry': {
        'type': 'MultiPolygon',
        'coordinates': [
          [square2],
          [
            [
              [44.2040, 15.3500],
              [44.2050, 15.3500],
              [44.2050, 15.3510],
              [44.2040, 15.3500],
            ],
          ],
        ],
      },
    },
    {
      'type': 'Feature',
      'properties': {'name': 'البئر'},
      'geometry': {
        'type': 'Point',
        'coordinates': [44.2, 15.35],
      },
    },
  ],
});

String coords(List<List<double>> ring) =>
    ring.map((c) => '${c[0]},${c[1]},0').join(' ');

String kmlDoc({String prefix = ''}) =>
    '''<?xml version="1.0" encoding="UTF-8"?>
<${prefix}kml xmlns${prefix.isEmpty ? '' : ':${prefix.substring(0, prefix.length - 1)}'}="http://www.opengis.net/kml/2.2">
<${prefix}Document>
  <!-- <Placemark><name>معلَّق</name></Placemark> -->
  <${prefix}Placemark>
    <${prefix}name><![CDATA[حقل البنّ & الذرة]]></${prefix}name>
    <${prefix}Polygon>
      <${prefix}outerBoundaryIs><${prefix}LinearRing><${prefix}coordinates>
        ${coords(square)}
      </${prefix}coordinates></${prefix}LinearRing></${prefix}outerBoundaryIs>
      <${prefix}innerBoundaryIs><${prefix}LinearRing><${prefix}coordinates>${coords(hole)}</${prefix}coordinates></${prefix}LinearRing></${prefix}innerBoundaryIs>
    </${prefix}Polygon>
  </${prefix}Placemark>
  <${prefix}Placemark>
    <${prefix}name>المدرّجات</${prefix}name>
    <${prefix}MultiGeometry>
      <${prefix}Polygon><${prefix}outerBoundaryIs><${prefix}LinearRing><${prefix}coordinates>${coords(square2)}</${prefix}coordinates></${prefix}LinearRing></${prefix}outerBoundaryIs></${prefix}Polygon>
      <${prefix}Polygon><${prefix}outerBoundaryIs><${prefix}LinearRing><${prefix}coordinates>44.2040, 15.3500 44.2050, 15.3500 44.2050, 15.3510 44.2040, 15.3500</${prefix}coordinates></${prefix}LinearRing></${prefix}outerBoundaryIs></${prefix}Polygon>
      <${prefix}Point><${prefix}coordinates>44.2,15.35</${prefix}coordinates></${prefix}Point>
    </${prefix}MultiGeometry>
  </${prefix}Placemark>
</${prefix}Document>
</${prefix}kml>''';
