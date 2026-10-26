// SAHOOL — features/alerts/data/alert_models.dart
// نماذج التنبيهات كما يُنتجها الخادم حرفيّاً (api/alert_models.py). لا حقل
// مُخترَع: ما لا يرسله الخادم يبقى null ويُعرَض كذلك.
import 'package:flutter/foundation.dart';

/// درجة الخطورة. الخادم يقبل info|warning|critical فقط؛ أيّ قيمة أخرى (حدث حيّ
/// من مصدر آخر) تُحفَظ نصّاً في [AlertItem.severityRaw] وتُعرَض «غير مصنّفة».
enum AlertSeverity {
  critical('critical', 'حرج'),
  warning('warning', 'تحذير'),
  info('info', 'معلومة'),
  unknown('', 'غير مصنّفة');

  const AlertSeverity(this.wire, this.labelAr);
  final String wire;
  final String labelAr;

  /// الترتيب في الفرز (الأخطر أوّلاً).
  int get rank => switch (this) {
    AlertSeverity.critical => 0,
    AlertSeverity.warning => 1,
    AlertSeverity.info => 2,
    AlertSeverity.unknown => 3,
  };

  static AlertSeverity parse(String? raw) {
    switch ((raw ?? '').toLowerCase()) {
      case 'critical':
      case 'high':
        return AlertSeverity.critical;
      case 'warning':
      case 'medium':
        return AlertSeverity.warning;
      case 'info':
      case 'low':
        return AlertSeverity.info;
    }
    return AlertSeverity.unknown;
  }

  /// قيم المرشِّح التي يقبلها الخادم (`severity=` في GET /api/v1/alerts).
  static const filterable = [critical, warning, info];
}

/// أسماء أنواع التنبيهات بالعربيّة حين لا يرسل الخادم عنواناً (مرآة الويب
/// AlertSystemPage.tsx TYPE_LABELS + _ALERT_TYPES في الخادم).
const Map<String, String> kAlertTypeLabelsAr = {
  'low_moisture': 'رطوبة منخفضة',
  'heavy_rain': 'أمطار غزيرة',
  'disease_risk': 'خطر مرض',
  'heat_stress': 'إجهاد حراريّ',
  'frost_risk': 'خطر صقيع',
  'vegetation_stress': 'إجهاد نباتيّ',
  'salinity_critical': 'ملوحة تربة حرجة',
  'human_review_required': 'يحتاج مراجعة بشريّة',
  'other': 'تنبيه',
};

String alertTypeLabelAr(String? type) {
  if (type == null || type.isEmpty) return 'تنبيه';
  final known = kAlertTypeLabelsAr[type];
  if (known != null) return known;
  if (type.startsWith('weather_')) return 'تنبيه طقس';
  return 'تنبيه';
}

String? _str(Object? v) {
  if (v == null) return null;
  final s = v.toString();
  return s.isEmpty ? null : s;
}

/// تنبيه مخزَّن (AlertSummary).
@immutable
class AlertItem {
  const AlertItem({
    required this.alertId,
    required this.alertType,
    required this.severityRaw,
    required this.status,
    this.fieldId,
    this.titleAr,
    this.messageAr,
    this.createdAt,
  });

  final String alertId;
  final String? fieldId;
  final String alertType;
  final String severityRaw;
  final String? titleAr;

  /// نصّ الخادم — يحمل التوصية (alert_rules.py يكتب الإجراء داخل الرسالة).
  final String? messageAr;

  /// active | acknowledged | resolved
  final String status;
  final DateTime? createdAt;

  AlertSeverity get severity => AlertSeverity.parse(severityRaw);
  bool get isActive => status == 'active';
  bool get isAcknowledged => status == 'acknowledged';
  bool get isResolved => status == 'resolved';

  /// العنوان المعروض: عنوان الخادم، وإلّا اسم النوع.
  String get displayTitle => titleAr ?? alertTypeLabelAr(alertType);

  String get statusLabelAr => switch (status) {
    'active' => 'نشط',
    'acknowledged' => 'مُقَرّ',
    'resolved' => 'محلول',
    _ => status,
  };

  factory AlertItem.fromJson(Map<String, dynamic> j) {
    final id = _str(j['alert_id']);
    if (id == null) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: تنبيه بلا alert_id.',
      );
    }
    final created = _str(j['created_at']);
    return AlertItem(
      alertId: id,
      fieldId: _str(j['field_id']),
      alertType: _str(j['alert_type']) ?? 'other',
      severityRaw: _str(j['severity']) ?? '',
      titleAr: _str(j['title_ar']),
      messageAr: _str(j['message_ar']),
      status: _str(j['status']) ?? 'active',
      createdAt: created == null ? null : DateTime.tryParse(created),
    );
  }

  AlertItem copyWith({String? status}) => AlertItem(
    alertId: alertId,
    fieldId: fieldId,
    alertType: alertType,
    severityRaw: severityRaw,
    titleAr: titleAr,
    messageAr: messageAr,
    status: status ?? this.status,
    createdAt: createdAt,
  );

  @override
  bool operator ==(Object other) =>
      other is AlertItem &&
      other.alertId == alertId &&
      other.status == status &&
      other.severityRaw == severityRaw &&
      other.titleAr == titleAr &&
      other.messageAr == messageAr;

  @override
  int get hashCode => Object.hash(alertId, status, severityRaw, titleAr);
}

/// تنبيه مشتقّ من الحالة القانونيّة للحقل (لا معرّف، لا إقرار).
@immutable
class DerivedAlert {
  const DerivedAlert({
    required this.alertType,
    required this.severityRaw,
    this.titleAr,
    this.messageAr,
    this.source,
  });

  final String alertType;
  final String severityRaw;
  final String? titleAr;
  final String? messageAr;
  final String? source;

  AlertSeverity get severity => AlertSeverity.parse(severityRaw);
  String get displayTitle => titleAr ?? alertTypeLabelAr(alertType);

  factory DerivedAlert.fromJson(Map<String, dynamic> j) => DerivedAlert(
    alertType: _str(j['alert_type']) ?? 'other',
    severityRaw: _str(j['severity']) ?? '',
    titleAr: _str(j['title_ar']),
    messageAr: _str(j['message_ar']),
    source: _str(j['source']),
  );
}

/// ناتج POST /alerts/evaluate.
@immutable
class EvaluateResult {
  const EvaluateResult({required this.created, required this.skippedExisting});
  final List<AlertItem> created;
  final int skippedExisting;

  factory EvaluateResult.fromJson(Map<String, dynamic> j) {
    final created = j['created'];
    if (created is! List) {
      throw const FormatException(
        'استجابة غير متوقّعة من الخادم: نتيجة تقييم بلا created.',
      );
    }
    return EvaluateResult(
      created: created
          .whereType<Map>()
          .map((e) => AlertItem.fromJson(e.cast<String, dynamic>()))
          .toList(),
      skippedExisting: (j['skipped_existing'] as num?)?.toInt() ?? 0,
    );
  }

  String get summaryAr {
    final c = created.length;
    if (c == 0 && skippedExisting == 0) {
      return 'لا تنبيهات جديدة — ظروف الحقل ضمن الحدود الطبيعيّة.';
    }
    final skipped = skippedExisting > 0
        ? ' (مع تجاوز $skippedExisting موجوداً مسبقاً)'
        : '';
    return 'أُنشئ $c تنبيه$skipped.';
  }
}
