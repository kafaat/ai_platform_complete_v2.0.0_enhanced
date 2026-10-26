// SAHOOL — features/maps/draw/field_create_errors.dart
// رسائل صادقة لفشل إنشاء الحقل. رسالة ApiException العامّة لـ409 هي «تعارض:
// السجلّ موجود مسبقاً» ولـ422 تفريغٌ خامّ لكائن `detail`؛ بينما يرسل الخادم
// `detail.code` و`message_ar` (اسم مكرّر، تداخل هندسيّ بقائمة الحقول، هندسة غير
// صالحة، مزرعة غير موجودة). نعرض نصّ الخادم ونقول أين يُصلَح.
import 'package:sahool_app/core/network/api_exception.dart';

/// خطوة المعالج التي يُصلَح فيها الخطأ.
enum FixStep { basics, boundary, none }

class CreateErrorView {
  const CreateErrorView(this.messageAr, this.fixStep, {this.retrySafe = false});
  final String messageAr;
  final FixStep fixStep;

  /// true ⇒ النتيجة مجهولة (شبكة/مهلة/5xx) وإعادة المحاولة بالمفتاح نفسه آمنة.
  final bool retrySafe;
}

CreateErrorView describeCreateError(Object error) {
  final e = ApiException.from(error);
  final d = e.detail;
  final code = d is Map ? d['code']?.toString() : null;
  final serverMsg = d is Map ? d['message_ar']?.toString() : null;

  switch (code) {
    case 'duplicate_field_name':
      return CreateErrorView(
        '${serverMsg ?? 'يوجد حقل بالاسم نفسه.'} غيّر الاسم في الخطوة الأولى.',
        FixStep.basics,
      );
    case 'farm_not_found':
      return CreateErrorView(
        serverMsg ?? 'المزرعة غير موجودة أو ليست لك.',
        FixStep.basics,
      );
    case 'field_geometry_overlap':
      final list = d is Map && d['overlaps'] is List
          ? (d['overlaps'] as List)
                .whereType<Map>()
                .map((o) => '«${o['name']}» (~${o['overlap_m2']} م²)')
                .join('، ')
          : '';
      return CreateErrorView(
        '${serverMsg ?? 'الحدّ يتداخل مع حقل قائم.'}'
        '${list.isEmpty ? '' : '\nالتداخل مع: $list'}',
        FixStep.boundary,
      );
    case 'invalid_field_geometry':
    case 'field_boundary_save_guard':
      final issues = d is Map && d['issues'] is List
          ? (d['issues'] as List).join('، ')
          : '';
      return CreateErrorView(
        '${serverMsg ?? 'هندسة الحقل غير صالحة.'}'
        '${issues.isEmpty ? '' : '\n($issues)'}',
        FixStep.boundary,
      );
  }

  switch (e.kind) {
    case ApiErrorKind.network:
    case ApiErrorKind.timeout:
    case ApiErrorKind.server:
    case ApiErrorKind.unavailable:
      return CreateErrorView(
        '${e.messageAr}\nلم يُؤكَّد الحفظ. إعادة المحاولة آمنة: '
        'لن يُنشأ الحقل مرّتين.',
        FixStep.none,
        retrySafe: true,
      );
    default:
      return CreateErrorView(serverMsg ?? e.messageAr, FixStep.none);
  }
}
