// SAHOOL — features/weather/presentation/weather_format.dart
// تسميات الطقس ووحداته فوق core/utils/formatters.dart (الأرقام نفسها، والوحدات
// °م/مم/٪ من هناك). ما ليس في core بعدُ (كم/س، ساعات، أسماء الأيّام) يُعرَّف هنا
// بالأسلوب نفسه — مرشّح للنقل إلى formatters.dart.
import 'package:sahool_app/core/utils/formatters.dart';
import 'package:sahool_app/core/widgets/widgets.dart';

/// DateTime.weekday: 1=الاثنين … 7=الأحد.
const _weekdaysAr = [
  'الاثنين',
  'الثلاثاء',
  'الأربعاء',
  'الخميس',
  'الجمعة',
  'السبت',
  'الأحد',
];

String arabicWeekday(DateTime d) => _weekdaysAr[d.weekday - 1];

/// «اليوم» / «غداً» / اسم اليوم. null ⇒ «—».
String fmtDayName(DateTime? d, {DateTime? now}) {
  if (d == null) return '—';
  final n = now ?? DateTime.now();
  final today = DateTime(n.year, n.month, n.day);
  final day = DateTime(d.year, d.month, d.day);
  final diff = day.difference(today).inDays;
  if (diff == 0) return 'اليوم';
  if (diff == 1) return 'غداً';
  return arabicWeekday(d);
}

/// سرعة رياح: «12 كم/س».
String fmtKmh(num? kmh) =>
    kmh == null ? kNotMeasured : '${fmtNumber(kmh, decimals: 0)} كم/س';

/// مدّة بالساعات: «6 س».
String fmtHoursShort(num? h) =>
    h == null ? kNotMeasured : '${fmtNumber(h, decimals: 0)} س';

/// موعد نافذة: طابع زمنيّ حقيقيّ إن وُجد، وإلّا الإزاحة بالساعات.
String fmtWindowStart(DateTime? at, int? offsetHours) {
  if (at != null) return fmtDateTime(at);
  if (offsetHours == null) return 'الموعد غير متاح';
  if (offsetHours == 0) return 'الآن';
  return 'بعد ${fmtHoursShort(offsetHours)}';
}

const Map<String, String> kOperationLabelsAr = {
  'spraying': 'الرشّ',
  'irrigation': 'الريّ',
  'harvesting': 'الحصاد',
  'sowing': 'الزراعة',
  'fertilizing': 'التسميد',
};

String operationLabelAr(String op) => kOperationLabelsAr[op] ?? op;

String suitabilityLabelAr(String s) => switch (s) {
  'optimal' => 'مثاليّة',
  'acceptable' => 'مقبولة',
  'poor' => 'ضعيفة',
  'unsafe' => 'غير آمنة',
  _ => kNotMeasured,
};

StatusTone suitabilityTone(String s) => switch (s) {
  'optimal' => StatusTone.success,
  'acceptable' => StatusTone.info,
  'poor' => StatusTone.warning,
  'unsafe' => StatusTone.danger,
  _ => StatusTone.neutral,
};

const Map<String, String> _limitingAr = {
  'wind_speed_high': 'رياح قويّة',
  'wind_gust_high': 'هبّات رياح',
  'wind_high': 'رياح قويّة',
  'temperature_outside_spray_window': 'حرارة خارج نافذة الرشّ',
  'humidity_high': 'رطوبة عالية',
  'precipitation_present': 'هطول',
  'soil_too_wet': 'تربة مشبعة',
  'soil_temperature_unsuitable': 'حرارة تربة غير ملائمة',
  'soil_moisture_low': 'رطوبة تربة منخفضة',
  'heavy_rain_risk': 'خطر مطر غزير',
  'high_vpd_irrigation_need': 'جفاف هواء مرتفع (VPD)',
  'rain_reduces_irrigation_need': 'المطر يقلّل الحاجة',
  'extreme_daytime_heat': 'حرّ نهاريّ شديد',
  'cold_night_stress': 'برد ليليّ',
  'frost_risk': 'خطر صقيع',
  'large_diurnal_swing': 'فارق حرارة كبير بين الليل والنهار',
  'sensitive_reproductive_stage': 'مرحلة إزهار/عقد حسّاسة',
};

/// رمز عامل مُقيِّد ⇒ نصّ عربيّ؛ رمز غير معروف يُعرَض كما هو (لا تخمين).
String limitingFactorAr(String code) => _limitingAr[code] ?? code;

String urgencyLabelAr(String? u) => switch (u) {
  'none' => 'لا حاجة الآن',
  'low' => 'منخفض',
  'moderate' => 'متوسّط',
  'high' => 'عاجل',
  _ => kNotMeasured,
};

StatusTone urgencyTone(String? u) => switch (u) {
  'none' => StatusTone.success,
  'low' => StatusTone.info,
  'moderate' => StatusTone.warning,
  'high' => StatusTone.danger,
  _ => StatusTone.neutral,
};

String riskLabelAr(String? r) => switch (r) {
  'none' => 'لا خطر',
  'low' => 'منخفض',
  'moderate' => 'متوسّط',
  'high' => 'مرتفع',
  _ => kNotMeasured,
};

StatusTone riskTone(String? r) => switch (r) {
  'none' || 'low' => StatusTone.success,
  'moderate' => StatusTone.warning,
  'high' => StatusTone.danger,
  _ => StatusTone.neutral,
};

const Map<String, String> kCropStressProductsAr = {
  'lodging_risk': 'خطر الرقاد',
  'pollination_weather_risk': 'خطر الطقس على التلقيح',
  'chill_accumulation': 'تراكم البرودة',
};

/// رمز طقس WMO (Open-Meteo) ⇒ وصف عربيّ.
String weatherCodeAr(int? code) {
  if (code == null) return 'الحالة غير متاحة';
  if (code == 0) return 'صحو';
  if (code <= 2) return 'غائم جزئيّاً';
  if (code == 3) return 'غائم';
  if (code == 45 || code == 48) return 'ضباب';
  if (code >= 51 && code <= 57) return 'رذاذ';
  if (code >= 61 && code <= 67) return 'مطر';
  if (code >= 71 && code <= 77) return 'ثلج';
  if (code >= 80 && code <= 82) return 'زخّات مطر';
  if (code >= 85 && code <= 86) return 'زخّات ثلج';
  if (code >= 95) return 'عاصفة رعديّة';
  return 'الحالة غير متاحة';
}
