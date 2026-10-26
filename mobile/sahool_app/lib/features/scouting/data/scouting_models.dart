// SAHOOL — features/scouting/data/scouting_models.dart
// نماذج الاستكشاف الميدانيّ مطابقةً لأشكال الخادم المقروءة من الشيفرة لا المُخمَّنة:
//   • الدبّوس: ScoutingPin.to_dict (services/sahool-platform/api/scouting_pins.py)
//     ويقرؤه GET /api/v1/scouting/pins (api/routers/scouting.py:_row_to_pin).
//   • الفئات والشدّة والحالة: IssueCategory/Severity/PinStatus في scouting_pins.py.
//     الخادم يرفض (422) أيّ قيمة خارجها، فالواجهة لا تعرض سلّماً آخر.
//   • كشف الآفات: services/edge-inference/main.py (detect_pest) والكاشف
//     models/pest_detector.py (class_name/arabic_name/confidence/severity).
//
// صدق: قيمة غائبة تبقى null وتُعرض «غير مقيس»/«—»، لا رقماً مُفترَضاً.
import 'package:flutter/material.dart';
import 'package:sahool_app/core/widgets/status_chip.dart';

/// فئات المشكلة كما يقبلها الخادم (IssueCategory في scouting_pins.py).
enum IssueCategory {
  pest('pest', 'آفة حشريّة', Icons.bug_report_outlined),
  disease('disease', 'مرض', Icons.coronavirus_outlined),
  weed('weed', 'أعشاب ضارّة', Icons.grass_outlined),
  nutrient('nutrient', 'نقص عناصر', Icons.science_outlined),
  waterStress('water_stress', 'إجهاد مائيّ', Icons.water_drop_outlined),
  abiotic('abiotic', 'غير حيويّ (ملوحة، حرق، رياح)', Icons.wb_sunny_outlined),
  other('other', 'أخرى', Icons.more_horiz_rounded);

  const IssueCategory(this.wire, this.labelAr, this.icon);
  final String wire;
  final String labelAr;
  final IconData icon;

  static IssueCategory? fromWire(String? v) {
    for (final c in values) {
      if (c.wire == v) return c;
    }
    return null;
  }
}

/// شدّة المشاهدة. الخادم يقبل ثلاث درجات فقط (Severity في scouting_pins.py)؛
/// لا سلّم 1–5 لأنّ أيّ قيمة أخرى تُرفض 422.
enum PinSeverity {
  low('low', 'خفيفة', Icons.signal_cellular_alt_1_bar_rounded, StatusTone.info),
  medium(
    'medium',
    'متوسّطة',
    Icons.signal_cellular_alt_2_bar_rounded,
    StatusTone.warning,
  ),
  high('high', 'شديدة', Icons.signal_cellular_alt_rounded, StatusTone.danger);

  const PinSeverity(this.wire, this.labelAr, this.icon, this.tone);
  final String wire;
  final String labelAr;
  final IconData icon;
  final StatusTone tone;

  static PinSeverity? fromWire(String? v) {
    for (final s in values) {
      if (s.wire == v) return s;
    }
    return null;
  }
}

/// تسمية حالة الدبّوس (PinStatus في scouting_pins.py). قيمة مجهولة تُعرض كما هي.
(String, StatusTone) pinStatusLabel(String? status) => switch (status) {
  'new' => ('جديدة', StatusTone.info),
  'confirmed' => ('مؤكَّدة', StatusTone.warning),
  'under_treatment' => ('تحت المعالجة', StatusTone.warning),
  'resolved' => ('محلولة', StatusTone.success),
  null || '' => ('—', StatusTone.neutral),
  final other => (other, StatusTone.neutral),
};

/// حقل مختصر لما يحتاجه الاستكشاف من FieldSummary (GET /api/v1/fields،
/// api/field_models.py): المعرّف والاسم والمحصول والمركز (lat/lon اختياريّان).
@immutable
class ScoutingField {
  const ScoutingField({
    required this.id,
    required this.nameAr,
    this.crop,
    this.centerLat,
    this.centerLng,
  });

  final String id;
  final String nameAr;
  final String? crop;
  final double? centerLat;
  final double? centerLng;

  bool get hasCenter => centerLat != null && centerLng != null;

  static ScoutingField? fromSummary(Map<String, dynamic> j) {
    final id = j['field_id']?.toString();
    if (id == null || id.isEmpty) return null;
    final name = j['name_ar']?.toString();
    final crop = j['crop']?.toString();
    return ScoutingField(
      id: id,
      nameAr: (name == null || name.isEmpty) ? id : name,
      crop: (crop == null || crop.isEmpty) ? null : crop,
      centerLat: (j['lat'] as num?)?.toDouble(),
      centerLng: (j['lon'] as num?)?.toDouble(),
    );
  }
}

/// دبّوس مشاهدة مُخزَّن على الخادم.
@immutable
class ScoutingPin {
  const ScoutingPin({
    required this.pinId,
    required this.fieldId,
    required this.lat,
    required this.lng,
    required this.categoryWire,
    required this.severityWire,
    this.status,
    this.persistence,
    this.crop,
    this.issueCode,
    this.noteAr,
    this.photoUri,
    this.createdBy,
    this.createdAt,
  });

  final String pinId;
  final String fieldId;
  final double lat;
  final double lng;

  /// القيمة الخام من الخادم (قد تكون فئة لا تعرفها هذه النسخة).
  final String categoryWire;
  final String severityWire;
  final String? status;
  final String? persistence;
  final String? crop;
  final String? issueCode;
  final String? noteAr;
  final String? photoUri;
  final String? createdBy;
  final DateTime? createdAt;

  IssueCategory? get category => IssueCategory.fromWire(categoryWire);
  PinSeverity? get severity => PinSeverity.fromWire(severityWire);

  /// حارس شكل: معرّف أو إحداثيّات غائبة ⇒ FormatException (لا دبّوس في 0,0).
  factory ScoutingPin.fromJson(Map<String, dynamic> j) {
    final id = j['pin_id']?.toString();
    final lat = j['lat'];
    final lng = j['lng'];
    if (id == null || id.isEmpty || lat is! num || lng is! num) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: دبّوس بلا معرّف أو إحداثيّات.',
      );
    }
    String? s(String k) {
      final v = j[k]?.toString();
      return (v == null || v.isEmpty) ? null : v;
    }

    final created = s('created_at');
    return ScoutingPin(
      pinId: id,
      fieldId: s('field_id') ?? '',
      lat: lat.toDouble(),
      lng: lng.toDouble(),
      categoryWire: s('issue_category') ?? '',
      severityWire: s('severity') ?? '',
      status: s('status'),
      persistence: s('persistence'),
      crop: s('crop'),
      issueCode: s('issue_code'),
      noteAr: s('note_ar'),
      photoUri: s('photo_uri'),
      createdBy: s('created_by'),
      createdAt: created == null ? null : DateTime.tryParse(created),
    );
  }
}

/// استجابة GET /api/v1/scouting/pins: {field_id, pins, total, note_ar?}.
/// note_ar موجودة حين القاعدة غير مفعّلة — قائمة فارغة «بسبب» لا «لا مشاهدات».
@immutable
class ScoutingPinsPage {
  const ScoutingPinsPage({required this.pins, this.noteAr});
  final List<ScoutingPin> pins;
  final String? noteAr;
}

/// مشكلة من تصنيف المحصول (GET /api/v1/scouting/taxonomy?crop=).
@immutable
class TaxonomyIssue {
  const TaxonomyIssue({
    required this.code,
    required this.categoryWire,
    required this.nameAr,
  });
  final String code;
  final String categoryWire;
  final String nameAr;

  static TaxonomyIssue? fromJson(Map<String, dynamic> j) {
    final code = j['code']?.toString();
    final name = j['name_ar']?.toString();
    if (code == null || code.isEmpty || name == null || name.isEmpty) {
      return null;
    }
    return TaxonomyIssue(
      code: code,
      categoryWire: j['category']?.toString() ?? '',
      nameAr: name,
    );
  }
}

/// كشف واحد من نموذج الآفات على الحافّة.
@immutable
class PestDetection {
  const PestDetection({
    required this.className,
    this.arabicName,
    this.confidence,
    this.severity,
  });
  final String className;
  final String? arabicName;

  /// 0..1 كما يردّها الخادم؛ null ⇒ «غير مقيس».
  final double? confidence;
  final String? severity;

  String get labelAr =>
      (arabicName == null || arabicName!.isEmpty) ? className : arabicName!;
}

/// نتيجة POST /api/edge/v1/inference/pest-detect.
@immutable
class PestDetectResult {
  const PestDetectResult({
    required this.detections,
    this.alertAr,
    this.modelVersion,
    this.syncStatus,
    this.inferenceMs,
  });

  final List<PestDetection> detections;
  final String? alertAr;
  final String? modelVersion;
  final String? syncStatus;
  final double? inferenceMs;

  /// حارس شكل: detections يجب أن تكون قائمة (غيابها خطأ لا «لا آفات»).
  factory PestDetectResult.fromJson(Map<String, dynamic> j) {
    final raw = j['detections'];
    if (raw is! List) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: لا قائمة كشوف.',
      );
    }
    final dets = <PestDetection>[];
    for (final d in raw) {
      if (d is! Map) continue;
      final name = d['class_name']?.toString();
      if (name == null || name.isEmpty) continue;
      dets.add(
        PestDetection(
          className: name,
          arabicName: d['arabic_name']?.toString(),
          confidence: (d['confidence'] as num?)?.toDouble(),
          severity: d['severity']?.toString(),
        ),
      );
    }
    final alert = j['alert_ar']?.toString();
    return PestDetectResult(
      detections: dets,
      alertAr: (alert == null || alert.trim().isEmpty) ? null : alert,
      modelVersion: j['model_version']?.toString(),
      syncStatus: j['sync_status']?.toString(),
      inferenceMs: (j['inference_time_ms'] as num?)?.toDouble(),
    );
  }
}
