// SAHOOL — features/advisor/advisor_paths.dart
// مسارات المستشار كنصوص (بلا استيراد شاشات) كي تبنيها الشاشات والميزات الأخرى
// دون دورة استيراد مع advisor_routes.dart.

abstract final class AdvisorPaths {
  /// تبويب المحادثة. `?field_id=&field_name=` يربط الحقل.
  static const advisor = '/advisor';

  /// عمود توصيات الحقل + طلب توصية من المحرّك. `?field_id=`.
  static const recommendations = '/advisor/recommendations';

  /// توصية مُخزَّنة وشرحها + التغذية الراجعة. `?rec_id=`.
  static const recommendation = '/advisor/recommendation';

  /// تدفّق تصعيد الآفة (مالك/مهندس). `?field_id=`.
  static const pestEscalation = '/advisor/pest-escalation';

  /// الاستكشاف الميدانيّ (يملكه وكيل scouting) — حيث انتقل تشخيص الآفات بالصورة.
  /// مسار نصّيّ فقط: إن لم يُسجَّل بعد يعرض الموجِّه صفحة «غير موجود» صادقة.
  static const scouting = '/scouting';

  static String chatFor(String fieldId, {String? fieldName}) => Uri(
    path: advisor,
    queryParameters: {
      'field_id': fieldId,
      if (fieldName != null) 'field_name': fieldName,
    },
  ).toString();

  static String recommendationsFor(String? fieldId) => fieldId == null
      ? recommendations
      : Uri(
          path: recommendations,
          queryParameters: {'field_id': fieldId},
        ).toString();

  static String recommendationDetail(String recId) =>
      Uri(path: recommendation, queryParameters: {'rec_id': recId}).toString();

  static String pestEscalationFor(String? fieldId) => fieldId == null
      ? pestEscalation
      : Uri(
          path: pestEscalation,
          queryParameters: {'field_id': fieldId},
        ).toString();
}
