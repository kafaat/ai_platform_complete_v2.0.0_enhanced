// التحقّق الحاجب قبل الحفظ. ربطة العنق أدناه هي حالة التدقيق نفسها: الخادم
// يُصلحها بصمت إلى MultiPolygon بمساحة 59.61 هـ (قِيس بتشغيل guard_field_geometry)
// بينما كان المعالج يعرض 0.00 هـ ويسمح بالحفظ.
import 'package:flutter_test/flutter_test.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/draw/boundary_validation.dart';

List<LatLng> ring(List<List<double>> lonLat) => [
  for (final c in lonLat) LatLng(c[1], c[0]),
];

final square = ring([
  [44.20, 15.35],
  [44.2093, 15.35],
  [44.2093, 15.359],
  [44.20, 15.359],
]);

void main() {
  test('a valid square passes and reports the stored area', () {
    final v = validateBoundary(square);
    expect(v.canSave, isTrue);
    expect(v.issues, isEmpty);
    expect(v.storedAreaHa, 99.8);
    expect(v.vertexCount, 5); // مع رأس الإغلاق، كما يعدّه حارس الحفظ
  });

  test('bow-tie is rejected (self-intersection blocks save)', () {
    final bowTie = ring([
      [44.20, 15.35],
      [44.21, 15.36],
      [44.21, 15.35],
      [44.20, 15.36],
    ]);
    final v = validateBoundary(bowTie);
    expect(v.canSave, isFalse);
    expect(v.has('self_intersection'), isTrue);
    expect(v.blocking.map((i) => i.code), contains('self_intersection'));
  });

  test(
    'segment intersection is the server port (shared points do not count)',
    () {
      expect(segmentsIntersect([0, 0], [1, 1], [0, 1], [1, 0]), isTrue);
      expect(segmentsIntersect([0, 0], [1, 1], [1, 1], [2, 0]), isFalse);
    },
  );

  test('too few distinct points blocks', () {
    final v = validateBoundary(
      ring([
        [44.2, 15.35],
        [44.21, 15.35],
      ]),
    );
    expect(v.canSave, isFalse);
    expect(v.has('too_few_vertices'), isTrue);
    expect(v.storedAreaHa, isNull);
  });

  test(
    'area below the save-guard minimum (10 m²) blocks; below 0.01 ha warns',
    () {
      final tiny = ring([
        [44.2, 15.35],
        [44.20001, 15.35],
        [44.20001, 15.35001],
        [44.2, 15.35001],
      ]);
      final v = validateBoundary(tiny);
      expect(v.has('area_too_small'), isTrue);
      expect(v.canSave, isFalse);

      final small = ring([
        [44.2, 15.35],
        [44.20007, 15.35],
        [44.20007, 15.35007],
        [44.2, 15.35007],
      ]);
      final w = validateBoundary(small);
      expect(w.has('area_small'), isTrue);
      expect(w.canSave, isTrue);
    },
  );

  test('area above 10,000 ha blocks', () {
    final v = validateBoundary(
      ring([
        [47.0, 15.5],
        [47.3, 15.5],
        [47.3, 15.8],
        [47.0, 15.8],
      ]),
    );
    expect(v.has('area_too_large'), isTrue);
    expect(v.canSave, isFalse);
  });

  test(
    'swapped lat/lon is blocked with an explanation (server only warns)',
    () {
      // [lat, lon] بدل [lon, lat]: يقع في الصحراء الكبرى لا في اليمن.
      final swapped = ring([
        [15.35, 44.20],
        [15.35, 44.2093],
        [15.359, 44.2093],
        [15.359, 44.20],
      ]);
      final v = validateBoundary(swapped);
      expect(v.canSave, isFalse);
      expect(v.has('swapped_lat_lon'), isTrue);
      expect(v.blocking.first.messageAr, contains('مقلوبان'));
    },
  );

  test('outside Yemen (not a swap) is blocked', () {
    final v = validateBoundary(
      ring([
        [10.0, 50.0],
        [10.01, 50.0],
        [10.01, 50.01],
      ]),
    );
    expect(v.has('outside_yemen'), isTrue);
    expect(v.canSave, isFalse);
  });

  test('more than 2,000 vertices blocks', () {
    final many = [
      for (var i = 0; i < 2100; i++)
        LatLng(15.35 + 0.01 * (i / 2100), 44.2 + (i.isEven ? 0 : 0.0001)),
    ];
    // حلقة مسنّنة طويلة: يكفي أن يتجاوز العدد.
    final v = validateBoundary(many);
    expect(v.has('too_many_vertices'), isTrue);
  });

  test('overlap with an existing field warns and names it', () {
    final neighbour = ExistingField(
      id: 'f1',
      name: 'الحقل الغربيّ',
      rings: [
        ring([
          [44.205, 15.355],
          [44.215, 15.355],
          [44.215, 15.365],
          [44.205, 15.365],
        ]),
      ],
    );
    final far = ExistingField(
      id: 'f2',
      name: 'بعيد',
      rings: [
        ring([
          [45.0, 15.0],
          [45.01, 15.0],
          [45.01, 15.01],
        ]),
      ],
    );
    final v = validateBoundary(square, existing: [neighbour, far]);
    expect(v.has('overlap'), isTrue);
    expect(v.canSave, isTrue, reason: 'التداخل تحذير؛ الخادم يقرّر بـ25 م²');
    expect(v.overlapping.map((f) => f.id), ['f1']);
    expect(v.warnings.single.messageAr, contains('الحقل الغربيّ'));
  });

  test('ExistingField reads Polygon and MultiPolygon summaries', () {
    final p = ExistingField.fromSummary({
      'field_id': 'a',
      'name_ar': 'أ',
      'geometry': {
        'type': 'MultiPolygon',
        'coordinates': [
          [
            [
              [44.0, 15.0],
              [44.1, 15.0],
              [44.1, 15.1],
              [44.0, 15.0],
            ],
          ],
          [
            [
              [45.0, 15.0],
              [45.1, 15.0],
              [45.1, 15.1],
              [45.0, 15.0],
            ],
          ],
        ],
      },
    });
    expect(p!.rings, hasLength(2));
    expect(p.rings.first.first, const LatLng(15.0, 44.0));
    expect(ExistingField.fromSummary({'field_id': 'b'}), isNull);
  });
}
