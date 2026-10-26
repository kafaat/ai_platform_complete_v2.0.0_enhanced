// SAHOOL — features/fields/presentation/common/field_labels.dart
// قراءات دفاعيّة لمفاتيح الحقل وتسميات عربيّة لقيم الخادم (حالات، أنواع،
// درجات الجودة). مصدر واحد لكلّ شاشات الحقول بدل خرائط مكرّرة.
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/status_chip.dart';

double? wNum(Object? v) =>
    v is num ? v.toDouble() : (v is String ? double.tryParse(v) : null);

String wText(Object? v, [String fallback = '—']) {
  if (v == null) return fallback;
  final s = v.toString().trim();
  return s.isEmpty ? fallback : s;
}

/// اسم الحقل من أيّ شكل يصل (FieldSummary: name_ar · اللوحة: field_name · name).
String fieldNameOf(Map<String, dynamic> f, [String fallback = 'حقل']) =>
    wText(f['name_ar'] ?? f['field_name'] ?? f['name'], fallback);

String fieldIdOf(Map<String, dynamic> f) => wText(f['field_id'] ?? f['id'], '');

/// المحصول، أو null إن غاب (الخادم يرسل "—" حين لا محصول).
String? cropOf(Map<String, dynamic> f) {
  final c = wText(f['crop_ar'] ?? f['crop'], '');
  return (c.isEmpty || c == '—') ? null : c;
}

/// المساحة بالهكتار، أو null إن غابت. الخادم يحوّل المساحة الغائبة إلى 0.0،
/// والصفر ليس مساحة حقل حقيقيّة ⇒ «غير مقيس» لا «0 هـ».
double? areaOf(Map<String, dynamic> f) {
  final a = wNum(f['area_ha'] ?? f['area']);
  return (a == null || a <= 0) ? null : a;
}

/// درجة جودة الحالة الموحّدة (FieldSummary.quality_grade).
const Map<String, String> kQualityGradeAr = {
  'READY': 'جاهز للتوصيات',
  'LIMITED': 'بيانات محدودة',
  'PENDING_LAB': 'بانتظار فحص التربة',
  'BLOCKED': 'محجوب — يحتاج مراجعة',
};

/// ترتيب «الأحوج أوّلاً».
const Map<String, int> kQualityGradeRank = {
  'BLOCKED': 0,
  'PENDING_LAB': 1,
  'LIMITED': 2,
  'READY': 3,
};

StatusTone qualityTone(String? grade) => switch (grade) {
  'READY' => StatusTone.success,
  'LIMITED' => StatusTone.warning,
  'PENDING_LAB' => StatusTone.info,
  'BLOCKED' => StatusTone.danger,
  _ => StatusTone.neutral,
};

const Map<String, String> kSeasonStatusAr = {
  'planned': 'مُخطَّط',
  'active': 'نشط',
  'closed': 'مُغلَق',
};

StatusTone seasonTone(String? s) => switch (s) {
  'active' => StatusTone.success,
  'planned' => StatusTone.info,
  _ => StatusTone.neutral,
};

const Map<String, String> kActivityTypeAr = {
  'planting': 'بذر',
  'sowing': 'بذر',
  'irrigation': 'ريّ',
  'fertilizer': 'تسميد',
  'fertilization': 'تسميد',
  'spraying': 'رشّ',
  'pesticide': 'رشّ مبيد',
  'harvest': 'حصاد',
  'scouting': 'كشف ميدانيّ',
  'tillage': 'حراثة',
  'pruning': 'تقليم',
};

const Map<String, String> kActivityStatusAr = {
  'planned': 'مُخطَّط',
  'done': 'مُنجَز',
  'completed': 'مُنجَز',
};

const Map<String, String> kSeverityAr = {
  'critical': 'حرج',
  'high': 'مرتفع',
  'medium': 'متوسّط',
  'low': 'منخفض',
};

StatusTone severityTone(String? s) => switch (s) {
  'critical' || 'high' => StatusTone.danger,
  'medium' || 'moderate' => StatusTone.warning,
  'low' => StatusTone.info,
  _ => StatusTone.neutral,
};

/// حالة الصحّة كما يصنّفها vegetation (health.status).
StatusTone healthTone(String? status) => switch (status) {
  'excellent' || 'good' => StatusTone.success,
  'fair' => StatusTone.warning,
  'poor' || 'critical' => StatusTone.danger,
  _ => StatusTone.neutral,
};

/// تاريخ من نصّ ISO (null إن تعذّر).
DateTime? parseDate(Object? v) =>
    v == null ? null : DateTime.tryParse(v.toString());

/// تاريخ يوم من نصّ ISO للعرض («12 مارس 2026»)، أو «—».
String fmtDay(Object? v) => fmtIsoDate(v is String ? v : null);
