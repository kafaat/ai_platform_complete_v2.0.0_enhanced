// SAHOOL — features/satellite/data/satellite_models.dart
// نماذج مُنمَّطة لمؤشّرات الأقمار: خيار مؤشّر من الكتالوج، نقطة سلسلة زمنيّة،
// والسلسلة نفسها، وقراءة لحظيّة من vegetation /v1/analyze. صدق: كلّ قيمة غائبة
// تبقى null (يعرضها الـUI «غير مقيس») — لا صفر ولا تخمين.

double? _num(Object? v) => v is num ? v.toDouble() : null;

/// مؤشّر قابل للاختيار (من GET /api/v1/indicators/catalog).
class IndexOption {
  const IndexOption({required this.id, required this.nameAr, this.category});

  factory IndexOption.fromJson(Map<String, dynamic> j) => IndexOption(
    id: j['id'] as String,
    nameAr: (j['name_ar'] is String && (j['name_ar'] as String).isNotEmpty)
        ? j['name_ar'] as String
        : (j['id'] as String).toUpperCase(),
    category: j['category'] is String ? j['category'] as String : null,
  );

  final String id;
  final String nameAr;
  final String? category;

  @override
  bool operator ==(Object other) => other is IndexOption && other.id == id;

  @override
  int get hashCode => id.hashCode;
}

/// قائمة احتياطيّة حين يتعذّر الكتالوج: معرّفات المؤشّرات التي يخدمها
/// raster-service فعلاً (تطابق FALLBACK_RENDERABLE في الويب). أسماء فقط، لا قيم.
const List<IndexOption> kFallbackIndexOptions = [
  IndexOption(id: 'ndvi', nameAr: 'NDVI', category: 'vegetation'),
  IndexOption(id: 'ndwi', nameAr: 'NDWI', category: 'water'),
  IndexOption(id: 'ndmi', nameAr: 'NDMI (الرطوبة)', category: 'water'),
  IndexOption(id: 'evi', nameAr: 'EVI', category: 'vegetation'),
  IndexOption(id: 'ndre', nameAr: 'NDRE', category: 'vegetation'),
  IndexOption(id: 'savi', nameAr: 'SAVI', category: 'vegetation'),
  IndexOption(id: 'msi', nameAr: 'MSI (الإجهاد المائي)', category: 'water'),
  IndexOption(id: 'salinity', nameAr: 'الملوحة (SI)', category: 'soil'),
];

/// نقطة في السلسلة الزمنيّة لمؤشّر.
class IndexPoint {
  const IndexPoint({required this.date, required this.mean, this.cloudPct});

  final DateTime date;
  final double mean;

  /// نسبة الغيوم إن أرسلها الخادم (null = غير مُبلَّغ).
  final double? cloudPct;
}

/// سلسلة زمنيّة لمؤشّر واحد لحقل واحد.
class IndexSeries {
  const IndexSeries({
    required this.fieldId,
    required this.index,
    required this.available,
    required this.points,
    this.noteAr,
  });

  /// يتجاهل النقاط بلا تاريخ صالح أو بلا متوسّط رقميّ (لا نقاط مختلقة)،
  /// ويرتّبها زمنيّاً.
  factory IndexSeries.fromJson(
    String fieldId,
    String index,
    Map<String, dynamic> j,
  ) {
    final pts = <IndexPoint>[];
    final raw = j['points'];
    if (j['available'] != false && raw is List) {
      for (final e in raw.whereType<Map>()) {
        final d = DateTime.tryParse('${e['datetime'] ?? e['date'] ?? ''}');
        final mean = _num(e['mean']);
        if (d == null || mean == null) continue;
        pts.add(
          IndexPoint(
            date: d,
            mean: mean,
            cloudPct: _num(e['cloud_pct'] ?? e['cloudy_pct']),
          ),
        );
      }
      pts.sort((a, b) => a.date.compareTo(b.date));
    }
    final note = j['note_ar'] ?? j['note'];
    return IndexSeries(
      fieldId: fieldId,
      index: index,
      available: pts.isNotEmpty,
      points: pts,
      noteAr: note is String && note.isNotEmpty ? note : null,
    );
  }

  final String fieldId;
  final String index;
  final bool available;
  final List<IndexPoint> points;
  final String? noteAr;

  IndexPoint? get latest => points.isEmpty ? null : points.last;
}

/// قراءة مؤشّر لحظيّة من vegetation /v1/analyze (indices.{id}).
class IndicatorReading {
  const IndicatorReading({
    required this.id,
    required this.value,
    this.unit,
    this.estimated = false,
  });

  final String id;
  final double? value;

  /// الوحدة المعروضة (null لعديم الأبعاد — لا نعرض "dimensionless").
  final String? unit;

  /// true حين المصدر تقدير لا raster حقيقيّ.
  final bool estimated;
}

/// حالة الصحّة كما يصنّفها الخادم (health.status/label_ar).
class HealthLabel {
  const HealthLabel({required this.status, required this.labelAr});
  final String status; // excellent/good/fair/poor/critical
  final String labelAr;
}

/// لقطة المؤشّرات الحاليّة لحقل.
class IndicatorSnapshot {
  const IndicatorSnapshot({
    required this.fieldId,
    required this.readings,
    this.health,
    this.observedAt,
  });

  /// يقرأ الشكل الفعليّ (indices خريطة {value, unit, source, estimated}) ويتسامح
  /// مع الشكلين القديمين (قائمة indicators أو مفاتيح رقميّة عليا).
  factory IndicatorSnapshot.fromJson(String fieldId, Map<String, dynamic> j) {
    final out = <IndicatorReading>[];
    DateTime? observed;
    final indices = j['indices'];
    if (indices is Map) {
      indices.forEach((k, v) {
        if (v is Map) {
          final unit = v['unit'];
          out.add(
            IndicatorReading(
              id: '$k',
              value: _num(v['value']),
              unit: _displayUnit(unit),
              estimated: v['estimated'] == true,
            ),
          );
          final at = DateTime.tryParse('${v['data_available_at'] ?? ''}');
          if (at != null && (observed == null || at.isAfter(observed!))) {
            observed = at;
          }
        } else if (v is num) {
          out.add(IndicatorReading(id: '$k', value: v.toDouble()));
        }
      });
    } else if (j['indicators'] is List) {
      for (final m in (j['indicators'] as List).whereType<Map>()) {
        out.add(
          IndicatorReading(
            id: '${m['id'] ?? m['name'] ?? ''}',
            value: _num(m['value']),
            unit: _displayUnit(m['unit']),
          ),
        );
      }
    } else {
      j.forEach((k, v) {
        if (v is num) out.add(IndicatorReading(id: k, value: v.toDouble()));
      });
    }
    HealthLabel? health;
    final h = j['health'];
    if (h is Map) {
      final label = h['label_ar'];
      final status = h['status'];
      if (label is String && label.isNotEmpty) {
        health = HealthLabel(
          status: status is String ? status : '',
          labelAr: label,
        );
      }
    }
    return IndicatorSnapshot(
      fieldId: fieldId,
      readings: out,
      health: health,
      observedAt: observed,
    );
  }

  final String fieldId;
  final List<IndicatorReading> readings;
  final HealthLabel? health;
  final DateTime? observedAt;

  IndicatorReading? reading(String id) {
    for (final r in readings) {
      if (r.id == id) return r;
    }
    return null;
  }
}

String? _displayUnit(Object? unit) {
  if (unit is! String || unit.isEmpty) return null;
  if (unit == 'dimensionless') return null;
  if (unit == 'm2/m2') return 'م²/م²';
  return unit;
}
