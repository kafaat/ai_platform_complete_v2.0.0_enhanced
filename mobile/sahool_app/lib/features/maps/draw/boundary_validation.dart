// SAHOOL — features/maps/draw/boundary_validation.dart
// تحقّق حاجب قبل الحفظ يطابق قواعد الخادم، وأشدّ منها حيث يتساهل الخادم.
//
// لماذا يحجب العميل ما «يقبله» الخادم؟ قِيس في التدقيق:
//   • المضلّع المتقاطع ذاتيّاً (ربطة العنق) يُصلحه الخادم بصمت (shapely
//     make_valid) إلى MultiPolygon بمساحةٍ مختلفة، أو يرفضه حارس الحفظ — وفي
//     الحالتين لا يحصل المزارع على ما رسم.
//   • `outside_yemen_bbox` و`area_too_small` مجرّد تحذيرات خادميّة، فإحداثيّات
//     مقلوبة (lat/lon) تُحفَظ حقلاً في مكانٍ آخر من العالم.
// القواعد ومصادرها:
//   geospatial_integrity.py: ≥4 رؤوس مع الإغلاق، self_intersection، نطاق
//     الإحداثيّات، مربّع اليمن، area_too_large (>10,000 هـ)، area_too_small (<0.01 هـ تحذير).
//   field_geometry_save_guard.py: ≤2,000 رأس، ≥0.001 هـ.
//   routers/fields.py: تداخلٌ مع حقول المستأجر يتجاوز 25 م² ⇒ 409.
import 'package:latlong2/latlong.dart';

import 'geo_measure.dart';

/// مربّع اليمن كما في `geospatial_integrity.YEMEN_BBOX`.
abstract final class YemenBBox {
  static const double minLat = 11.5;
  static const double maxLat = 19.5;
  static const double minLng = 41.0;
  static const double maxLng = 55.0;

  static bool containsLatLng(double lat, double lng) =>
      lat >= minLat && lat <= maxLat && lng >= minLng && lng <= maxLng;
}

/// حدود الخادم (انظر رأس الملفّ).
abstract final class BoundaryLimits {
  static const int maxVertices = 2000; // save guard (مع رأس الإغلاق)
  static const double minAreaHa = 0.001; // save guard: رفض
  static const double smallAreaWarnHa = 0.01; // integrity: تحذير
  static const double maxAreaHa = 10000; // integrity: رفض
  static const double overlapRejectM2 = 25; // _MIN_FIELD_OVERLAP_M2
}

enum IssueSeverity { block, warn }

class BoundaryIssue {
  const BoundaryIssue(this.code, this.severity, this.messageAr);
  final String code;
  final IssueSeverity severity;
  final String messageAr;
  bool get blocking => severity == IssueSeverity.block;

  @override
  String toString() => '$code(${severity.name})';
}

/// حقل قائم للمقارنة (التداخل والالتقاط). [rings]: حلقات خارجيّة (MultiPolygon).
class ExistingField {
  const ExistingField({
    required this.id,
    required this.name,
    required this.rings,
  });
  final String id;
  final String name;
  final List<List<LatLng>> rings;

  /// من عنصر `GET /api/v1/fields` (FieldSummary): Polygon أو MultiPolygon.
  /// null إن غابت الهندسة أو لم تكن مضلّعيّة — لا نخترع حدّاً.
  static ExistingField? fromSummary(Map<String, dynamic> m) {
    final g = m['geometry'];
    if (g is! Map) return null;
    final rings = <List<LatLng>>[];
    List<LatLng>? ring(Object? r) {
      if (r is! List) return null;
      final out = <LatLng>[];
      for (final c in r) {
        if (c is List && c.length >= 2 && c[0] is num && c[1] is num) {
          out.add(LatLng((c[1] as num).toDouble(), (c[0] as num).toDouble()));
        }
      }
      return out.length >= 3 ? out : null;
    }

    final coords = g['coordinates'];
    if (coords is! List) return null;
    if (g['type'] == 'Polygon' && coords.isNotEmpty) {
      final r = ring(coords.first);
      if (r != null) rings.add(r);
    } else if (g['type'] == 'MultiPolygon') {
      for (final poly in coords) {
        if (poly is List && poly.isNotEmpty) {
          final r = ring(poly.first);
          if (r != null) rings.add(r);
        }
      }
    }
    if (rings.isEmpty) return null;
    return ExistingField(
      id: (m['field_id'] ?? m['id'] ?? '').toString(),
      name: (m['name_ar'] ?? m['name'] ?? '').toString(),
      rings: rings,
    );
  }
}

class BoundaryValidation {
  const BoundaryValidation({
    required this.issues,
    required this.vertexCount,
    required this.storedAreaHa,
    required this.guardAreaHa,
    required this.overlapping,
  });

  final List<BoundaryIssue> issues;

  /// عدد رؤوس الحلقة كما يعدّها حارس الحفظ (مع رأس الإغلاق).
  final int vertexCount;

  /// المساحة التي سيخزّنها الخادم (منزلتان) — null إن لم تكن مضلّعاً.
  final double? storedAreaHa;

  /// مساحة الحارس بأربع منازل (تُستعمل لحدود الحفظ).
  final double? guardAreaHa;

  /// الحقول القائمة التي يتقاطع معها الحدّ.
  final List<ExistingField> overlapping;

  bool get canSave => !issues.any((i) => i.blocking);
  List<BoundaryIssue> get blocking => issues.where((i) => i.blocking).toList();
  List<BoundaryIssue> get warnings => issues.where((i) => !i.blocking).toList();
  bool has(String code) => issues.any((i) => i.code == code);
}

bool _ccw(List<double> a, List<double> b, List<double> c) =>
    (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0]);

bool _same(List<double> a, List<double> b) => a[0] == b[0] && a[1] == b[1];

/// `segments_intersect` من الخادم حرفيّاً (لا تُعدّ النقاط المشتركة).
bool segmentsIntersect(
  List<double> p1,
  List<double> p2,
  List<double> p3,
  List<double> p4,
) {
  if (_same(p1, p3) || _same(p1, p4) || _same(p2, p3) || _same(p2, p4)) {
    return false;
  }
  return _ccw(p1, p3, p4) != _ccw(p2, p3, p4) &&
      _ccw(p1, p2, p3) != _ccw(p1, p2, p4);
}

/// `has_self_intersection` من الخادم حرفيّاً. [coords]: حلقة مغلقة [lon,lat].
bool hasSelfIntersection(List<List<double>> coords) {
  final n = coords.length;
  if (n < 4) return false;
  for (var i = 0; i < n - 1; i++) {
    for (var j = i + 2; j < n - 1; j++) {
      if (i == 0 && j == n - 2) continue;
      if (segmentsIntersect(
        coords[i],
        coords[i + 1],
        coords[j],
        coords[j + 1],
      )) {
        return true;
      }
    }
  }
  return false;
}

bool _pointInRing(LatLng p, List<LatLng> ring) {
  var inside = false;
  for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    final a = ring[i], b = ring[j];
    if ((a.latitude > p.latitude) != (b.latitude > p.latitude) &&
        p.longitude <
            (b.longitude - a.longitude) *
                    (p.latitude - a.latitude) /
                    (b.latitude - a.latitude) +
                a.longitude) {
      inside = !inside;
    }
  }
  return inside;
}

List<double> _ll(LatLng p) => [p.longitude, p.latitude];

/// هل تتقاطع حلقتان (عبور أضلاع أو احتواء)؟ تصفيةٌ أوّليّة بالمربّع المحيط.
bool ringsOverlap(List<LatLng> a, List<LatLng> b) {
  if (a.length < 3 || b.length < 3) return false;
  double minLat(List<LatLng> r) =>
      r.map((p) => p.latitude).reduce((x, y) => x < y ? x : y);
  double maxLat(List<LatLng> r) =>
      r.map((p) => p.latitude).reduce((x, y) => x > y ? x : y);
  double minLng(List<LatLng> r) =>
      r.map((p) => p.longitude).reduce((x, y) => x < y ? x : y);
  double maxLng(List<LatLng> r) =>
      r.map((p) => p.longitude).reduce((x, y) => x > y ? x : y);
  if (maxLat(a) < minLat(b) ||
      maxLat(b) < minLat(a) ||
      maxLng(a) < minLng(b) ||
      maxLng(b) < minLng(a)) {
    return false;
  }
  for (var i = 0; i < a.length; i++) {
    final a1 = _ll(a[i]), a2 = _ll(a[(i + 1) % a.length]);
    for (var j = 0; j < b.length; j++) {
      if (segmentsIntersect(a1, a2, _ll(b[j]), _ll(b[(j + 1) % b.length]))) {
        return true;
      }
    }
  }
  return _pointInRing(a.first, b) || _pointInRing(b.first, a);
}

String _ha(double v) => v < 0.01
    ? '${(v * 10000).toStringAsFixed(0)} م²'
    : '${v.toStringAsFixed(2)} هـ';

/// يتحقّق من حدّ [ring] (حلقة مفتوحة) قبل الحفظ. [existing]: حقول المستأجر.
BoundaryValidation validateBoundary(
  List<LatLng> ring, {
  List<ExistingField> existing = const [],
}) {
  final issues = <BoundaryIssue>[];
  final coords = serverNormalizedRing(ring);
  final vertexCount = coords.length;
  BoundaryValidation done({
    double? guard,
    List<ExistingField> ovl = const [],
  }) => BoundaryValidation(
    issues: issues,
    vertexCount: vertexCount,
    guardAreaHa: guard,
    storedAreaHa: guard == null ? null : pyRound(guard, 2),
    overlapping: ovl,
  );

  if (vertexCount < 4) {
    issues.add(
      const BoundaryIssue(
        'too_few_vertices',
        IssueSeverity.block,
        'الحدّ يحتاج 3 نقاط مختلفة على الأقلّ ليُغلَق مضلّعاً.',
      ),
    );
    return done();
  }
  if (vertexCount > BoundaryLimits.maxVertices) {
    issues.add(
      BoundaryIssue(
        'too_many_vertices',
        IssueSeverity.block,
        'الحدّ فيه $vertexCount رأساً؛ يقبل الخادم ${BoundaryLimits.maxVertices} '
            'على الأكثر. بسّط الحدّ أو احذف رؤوساً.',
      ),
    );
  }

  final outOfRange = coords.any(
    (c) => c[0] < -180 || c[0] > 180 || c[1] < -90 || c[1] > 90,
  );
  if (outOfRange) {
    issues.add(
      const BoundaryIssue(
        'coordinate_out_of_range',
        IssueSeverity.block,
        'إحداثيّات خارج النطاق الممكن؛ غالباً رُتِّبت (خطّ العرض، خطّ الطول) '
            'بدل (خطّ الطول، خطّ العرض).',
      ),
    );
    return done();
  }

  final inside = coords.every((c) => YemenBBox.containsLatLng(c[1], c[0]));
  if (!inside) {
    final swappedInside = coords.every(
      (c) => YemenBBox.containsLatLng(c[0], c[1]),
    );
    issues.add(
      swappedInside
          ? const BoundaryIssue(
              'swapped_lat_lon',
              IssueSeverity.block,
              'يبدو أنّ خطّ العرض وخطّ الطول مقلوبان: الحدّ يقع خارج اليمن، '
                  'ويقع داخلها لو بُدِّل الترتيب. GeoJSON يرتّب [خطّ الطول، خطّ العرض]. '
                  'صحّح الملفّ ثمّ أعد الاستيراد.',
            )
          : const BoundaryIssue(
              'outside_yemen',
              IssueSeverity.block,
              'الحدّ يقع خارج اليمن (خطّ العرض 11.5–19.5، خطّ الطول 41–55). '
                  'الخادم يحفظه مع تحذير فقط، فيظهر الحقل في مكانٍ خاطئ. '
                  'تحقّق من الإحداثيّات أو من موقع الرسم.',
            ),
    );
  }

  if (hasSelfIntersection(coords)) {
    issues.add(
      const BoundaryIssue(
        'self_intersection',
        IssueSeverity.block,
        'الحدّ يتقاطع مع نفسه (شكل ربطة عنق). لن يحفظه الخادم كما رسمته: '
            'يقسمه إلى أجزاء بمساحةٍ مختلفة أو يرفضه. اسحب الرؤوس حتّى لا تتقاطع الأضلاع.',
      ),
    );
  }

  final guard = pyRound(serverPolygonAreaM2(coords) / 10000.0, 4);
  if (guard < BoundaryLimits.minAreaHa) {
    issues.add(
      BoundaryIssue(
        'area_too_small',
        IssueSeverity.block,
        'المساحة ${_ha(guard)} أصغر من الحدّ الأدنى للحفظ (10 م²).',
      ),
    );
  } else if (guard < BoundaryLimits.smallAreaWarnHa) {
    issues.add(
      BoundaryIssue(
        'area_small',
        IssueSeverity.warn,
        'المساحة صغيرة جدّاً (${_ha(guard)}). تأكّد أنّ هذا حدّ الحقل كاملاً.',
      ),
    );
  }
  if (guard > BoundaryLimits.maxAreaHa) {
    issues.add(
      BoundaryIssue(
        'area_too_large',
        IssueSeverity.block,
        'المساحة ${guard.toStringAsFixed(0)} هـ تتجاوز الحدّ الأقصى '
            '(${BoundaryLimits.maxAreaHa.toStringAsFixed(0)} هـ).',
      ),
    );
  }

  final open = [
    for (final c in coords.take(coords.length - 1)) LatLng(c[1], c[0]),
  ];
  final ovl = <ExistingField>[
    for (final f in existing)
      if (f.rings.any((r) => ringsOverlap(open, r))) f,
  ];
  if (ovl.isNotEmpty) {
    final names = ovl.map((f) => '«${f.name}»').join('، ');
    issues.add(
      BoundaryIssue(
        'overlap',
        IssueSeverity.warn,
        'الحدّ يتداخل مع $names. يرفض الخادم الحفظ إن تجاوز التداخل '
            '${BoundaryLimits.overlapRejectM2.toStringAsFixed(0)} م²؛ فعِّل الالتقاط '
            'لإلصاق الحدّ بحدود الحقل المجاور.',
      ),
    );
  }
  return done(guard: guard, ovl: ovl);
}
