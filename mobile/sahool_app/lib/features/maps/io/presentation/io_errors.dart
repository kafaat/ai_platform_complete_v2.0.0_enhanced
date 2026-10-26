// SAHOOL — features/maps/io/presentation/io_errors.dart
// نصّ خطأ صادق لشاشات io/. يحترم صياغة ApiException العقديّة (503/401/403)،
// ويُظهر سبب الخادم المحدَّد حين يرسله كـ`detail.message_ar` (تداخل الحدود، تكرار
// الاسم، هندسة غير صالحة) بدل «تعارض» عامّ أو تفريغ Map خام.
import 'package:sahool_app/core/network/api_exception.dart';

String ioErrorText(Object error) {
  final e = ApiException.from(error);
  final d = e.detail;
  final contractual =
      e.statusCode == 503 || e.statusCode == 401 || e.statusCode == 403;
  if (!contractual && d is Map) {
    final msg = d['message_ar'];
    if (msg is String && msg.trim().isNotEmpty) {
      final issues = d['issues'];
      if (issues is List && issues.isNotEmpty) {
        return '$msg (${issues.join('، ')})';
      }
      return msg;
    }
    final code = d['code'];
    if (code is String && code.isNotEmpty) return '${e.messageAr} ($code)';
  }
  return e.messageAr;
}

/// معاينة الدمج/التقسيم خلف FEATURE_GIS_KERNEL: 404 تعني «غير مفعّلة» لا «غير موجود».
bool isGisKernelDisabled(Object error) =>
    ApiException.from(error).kind == ApiErrorKind.notFound;

const String kGisPreviewDisabledAr =
    'معاينة الدمج والتقسيم غير مفعّلة في الخادم بعد (FEATURE_GIS_KERNEL). '
    'لا يمكن حساب الهندسة على الجهاز، لذا لا يُحفظ دمج أو تقسيم دون معاينة.';
