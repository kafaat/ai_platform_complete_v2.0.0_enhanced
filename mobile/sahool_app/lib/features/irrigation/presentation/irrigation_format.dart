// SAHOOL — features/irrigation/presentation/irrigation_format.dart
// تنسيق وحدات الريّ (مم · م³ · دقيقة) فوق core/utils/formatters.dart، وتسميات
// عربيّة لرموز الخادم، وصلاحيّات الريّ كما يفرضها الخادم (core/authorization.py).
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/utils/formatters.dart';

export 'package:sahool_app/core/utils/formatters.dart'
    show fmtMm, fmtNumber, fmtPct, fmtDate, fmtDateTime, kNotMeasured;

/// حجم بالمتر المكعّب: «120 م³». null ⇒ «غير مقيس».
String fmtM3(num? m3, {int decimals = 1}) =>
    m3 == null ? kNotMeasured : '${fmtNumber(m3, decimals: decimals)} م³';

/// م³ للهكتار: «450 م³/هـ».
String fmtM3PerHa(num? v) =>
    v == null ? kNotMeasured : '${fmtNumber(v, decimals: 0)} م³/هـ';

/// مدّة بالدقائق: «45 دقيقة».
String fmtMinutes(num? minutes) =>
    minutes == null ? kNotMeasured : '${fmtNumber(minutes, decimals: 0)} دقيقة';

/// 1 مم على 1 هكتار = 10 م³ (تحويل حسابيّ، لا تقدير).
num? mmToM3(num? mm, num? areaHa) =>
    (mm == null || areaHa == null || areaHa <= 0) ? null : mm * areaHa * 10;

num? m3ToMm(num? m3, num? areaHa) =>
    (m3 == null || areaHa == null || areaHa <= 0) ? null : m3 / (areaHa * 10);

/// «06:00:00» ⇒ «06:00». نصّ غير متوقَّع يُعاد كما هو (لا اختلاق).
String fmtClock(String? hhmmss) {
  if (hhmmss == null || hhmmss.isEmpty) return '—';
  final m = RegExp(r'^(\d{1,2}):(\d{2})').firstMatch(hhmmss);
  if (m == null) return hhmmss;
  return '${m.group(1)!.padLeft(2, '0')}:${m.group(2)}';
}

/// تاريخ اليوم المحلّيّ بصيغة YYYY-MM-DD (مفتاح قيد الدفتر).
String isoDay(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

/// أيّام الأسبوع بترتيب الويب (IrrigationOpsPage: 0 = الأحد).
const List<String> kDaysAr = [
  'الأحد',
  'الإثنين',
  'الثلاثاء',
  'الأربعاء',
  'الخميس',
  'الجمعة',
  'السبت',
];

const Map<String, String> kValveTypesAr = {
  'solenoid': 'كهرومغناطيسيّ',
  'manual': 'يدويّ',
  'drip_header': 'رأس تنقيط',
  'gate': 'بوّابة',
};

// ── الصلاحيّات (مطابقة لـ core/authorization.py على الخادم) ──────────────

/// irrigation:manage — المالك والمدير والمهندس الزراعيّ. العامل والمشاهد عرضٌ
/// فقط (كانت الشاشة تعرض أزرار الصمّام للعامل فيردّ الخادم 403).
bool canManageIrrigation(String? role) {
  final r = normalizeRole(role);
  return r == AppRole.owner || r == AppRole.manager || r == AppRole.agronomist;
}

/// field:edit (كتابة دفتر المياه) — المالك والمدير فقط.
bool canWriteWaterLedger(String? role) => canManage(role);

// ── تسميات رموز الخادم ─────────────────────────────────────────────

const Map<String, String> _limitationsAr = {
  'applied_water_unknown_depletion_is_upper_bound':
      'الريّ المضاف غير مسجَّل، فالاستنزاف المحسوب حدٌّ أعلى لا قياس.',
  'growth_stage_unavailable':
      'مرحلة نموّ المحصول غير معروفة (لا موسم نشط بمرحلة).',
  'stale_water_ledger': 'دفتر المياه قديم — آخر قيد لم يُحدَّث مؤخّراً.',
  'taw_uncalibrated': 'سعة الماء المتاح في التربة (TAW) غير معايَرة ميدانيّاً.',
  'missing_depletion_mm': 'لا قيمة استنزاف في دفتر المياه لهذا الحقل.',
  'missing_taw_mm': 'سعة الماء المتاح في التربة غير معروفة.',
  'depletion_exceeds_taw':
      'الاستنزاف المسجَّل يتجاوز سعة التربة — حالة غير متّسقة.',
  'invalid_depletion_or_taw': 'قيم الاستنزاف أو سعة التربة غير صالحة.',
};

/// يحوّل قيداً من `limitations` إلى نصّ عربيّ. الخادم يكتب بعضها «رمز — شرح
/// عربيّ»؛ نعرض الشرح. رمز غير معروف يُعرض كما هو (لا يُخفى).
String limitationAr(String raw) {
  final known = _limitationsAr[raw.trim()];
  if (known != null) return known;
  final i = raw.indexOf(' — ');
  if (i > 0) {
    final tail = raw.substring(i + 3).trim();
    if (RegExp(r'[؀-ۿ]').hasMatch(tail)) return tail;
  }
  return raw;
}

String urgencyAr(String? u) => switch (u) {
  'high' => 'عاجل',
  'moderate' => 'متوسّط',
  'low' => 'منخفض',
  'none' => 'لا إلحاح',
  null => kNotMeasured,
  _ => u,
};

String approvalStateAr(String? s) => switch (s) {
  'not_submitted' => 'مرشَّح — لم يُقدَّم للاعتماد',
  'pending_approval' => 'بانتظار الاعتماد',
  'approved' => 'معتمَد',
  'rejected' => 'مرفوض',
  'submit_unavailable' => 'خدمة القرار غير متاحة — لم يُقدَّم',
  'submit_unproven' => 'لم يُثبَت التقديم',
  null => 'مرشَّح — غير معتمَد',
  _ => s,
};

String appliedWaterAr(bool? known) => switch (known) {
  true => 'مسجَّل',
  false => 'غير مسجَّل',
  null => 'غير معلَن',
};

/// نصّ رفض الخادم: رسالة العقد العربيّة (503/403/401/404/409 ثابتة)، يليها
/// `detail` الخادم إن كان عربيّاً ومختلفاً — فرفضٌ مثل «أوامر المشغِّلات مجمَّدة»
/// يُقرأ بسببه لا كـ«تعارض» عامّ.
String refusalText(ApiException e) {
  final d = e.detail;
  if (d is String &&
      d.trim().isNotEmpty &&
      !e.messageAr.contains(d.trim()) &&
      RegExp(r'[؀-ۿ]').hasMatch(d)) {
    return '${e.messageAr}\n${d.trim()}';
  }
  return e.messageAr;
}
