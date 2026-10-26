// SAHOOL — lib/core/network/api_exception.dart
// أخطاء الشبكة المُنمَّطة. كلّ ما يرميه ApiClient من فشل HTTP يصل إلى الواجهة
// كـ[ApiException] واحد بنوعٍ صريح ([ApiErrorKind]) ورسالة عربيّة صادقة، بدل
// DioException خامّ يفحص كلّ شاشة رمزه بنفسها.
//
// الدلالات تطابق apiErrorMessage القديمة حرفيّاً (503 ⇒ الخدمة/القاعدة معطّلة،
// 403 ⇒ لا صلاحيّة، 401 ⇒ انتهت الجلسة، 404 ⇒ غير موجود، 409 ⇒ تعارض)، فلا
// تتغيّر رسالة يراها المستخدم بانتقال شاشةٍ إلى العميل الجديد.
import 'package:dio/dio.dart';

/// نوع الفشل كما قِيس من الاستجابة، لا كما يُخمَّن.
enum ApiErrorKind {
  /// لا اتّصال/تعذّر الوصول إلى الخادم (DNS، شبكة مقطوعة، رفض اتّصال).
  network,

  /// انتهت مهلة الاتّصال أو الإرسال أو الاستقبال.
  timeout,

  /// أُلغي الطلب من التطبيق (مغادرة الشاشة مثلاً). لا يُعرَض كخطأ.
  cancelled,

  /// 400 — طلب غير صالح.
  badRequest,

  /// 401 — الجلسة منتهية أو غير صالحة.
  unauthorized,

  /// 403 — لا صلاحيّة (RBAC) أو يتطلّب خطوة أمنيّة إضافيّة.
  forbidden,

  /// 404 — المورد غير موجود.
  notFound,

  /// 409 — تعارض (مكرَّر/تداخل/نسخة قديمة).
  conflict,

  /// 422 — فشل التحقّق من الحقول.
  validation,

  /// 429 — تجاوز حدّ المعدّل.
  rateLimited,

  /// 503 — الخدمة أو قاعدة بياناتها غير متاحة.
  unavailable,

  /// أيّ 5xx آخر.
  server,

  /// استجابة لا تطابق الشكل المتوقَّع، أو خطأ لم يُصنَّف.
  unknown,
}

class ApiException implements Exception {
  final ApiErrorKind kind;

  /// رمز HTTP إن وصلت استجابة؛ null عند فشل الشبكة/المهلة/الإلغاء.
  final int? statusCode;

  /// الرسالة العربيّة المعروضة للمستخدم.
  final String messageAr;

  /// قيمة `detail` من الخادم كما هي (نصّ أو قائمة أخطاء تحقّق)، إن وُجدت.
  final Object? detail;

  /// X-Request-ID المُرسَل مع الطلب — لربط شكوى المستخدم بسجلّ الخادم.
  final String? requestId;

  /// الخطأ الأصليّ (DioException عادةً) للتشخيص.
  final Object? cause;

  const ApiException({
    required this.kind,
    required this.messageAr,
    this.statusCode,
    this.detail,
    this.requestId,
    this.cause,
  });

  bool get isUnauthorized => kind == ApiErrorKind.unauthorized;
  bool get isForbidden => kind == ApiErrorKind.forbidden;
  bool get isNotFound => kind == ApiErrorKind.notFound;
  bool get isUnavailable => kind == ApiErrorKind.unavailable;
  bool get isCancelled => kind == ApiErrorKind.cancelled;

  /// فشلٌ مصدره الاتّصال لا الخادم — مفيد لعرض «غير متّصل» بدل «خطأ».
  bool get isConnectivity =>
      kind == ApiErrorKind.network || kind == ApiErrorKind.timeout;

  /// يحوّل أيّ خطأ إلى [ApiException]. [ApiException] يُعاد كما هو.
  static ApiException from(Object error) {
    if (error is ApiException) return error;
    if (error is DioException) return ApiException.fromDio(error);
    if (error is FormatException) {
      return ApiException(
        kind: ApiErrorKind.unknown,
        messageAr: error.message.isNotEmpty
            ? error.message
            : 'استجابة غير متوقّعة من الخادم.',
        cause: error,
      );
    }
    return ApiException(
      kind: ApiErrorKind.unknown,
      messageAr: 'حدث خطأ غير متوقّع.',
      cause: error,
    );
  }

  factory ApiException.fromDio(DioException e) {
    final requestId = e.requestOptions.headers['X-Request-ID']?.toString();
    switch (e.type) {
      case DioExceptionType.cancel:
        return ApiException(
          kind: ApiErrorKind.cancelled,
          messageAr: 'أُلغي الطلب.',
          requestId: requestId,
          cause: e,
        );
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
      case DioExceptionType.transformTimeout:
        return ApiException(
          kind: ApiErrorKind.timeout,
          messageAr: 'انتهت مهلة الاتصال بالخادم — تحقّق من الشبكة.',
          requestId: requestId,
          cause: e,
        );
      case DioExceptionType.connectionError:
      case DioExceptionType.badCertificate:
        return ApiException(
          kind: ApiErrorKind.network,
          messageAr: 'تعذّر الاتصال بالخادم — تحقّق من الشبكة.',
          requestId: requestId,
          cause: e,
        );
      case DioExceptionType.unknown:
        // بلا استجابة ⇒ فشل نقل (مثل SocketException). بها ⇒ صنّف بالرمز.
        if (e.response == null) {
          return ApiException(
            kind: ApiErrorKind.network,
            messageAr: 'تعذّر الاتصال بالخادم — تحقّق من الشبكة.',
            requestId: requestId,
            cause: e,
          );
        }
      case DioExceptionType.badResponse:
        break;
    }
    final code = e.response?.statusCode;
    final detail = _detailOf(e.response?.data);
    return ApiException(
      kind: kindForStatus(code),
      statusCode: code,
      messageAr: messageForStatus(code, detail),
      detail: detail,
      requestId: requestId,
      cause: e,
    );
  }

  static ApiErrorKind kindForStatus(int? code) {
    if (code == null) return ApiErrorKind.unknown;
    switch (code) {
      case 400:
        return ApiErrorKind.badRequest;
      case 401:
        return ApiErrorKind.unauthorized;
      case 403:
        return ApiErrorKind.forbidden;
      case 404:
        return ApiErrorKind.notFound;
      case 409:
        return ApiErrorKind.conflict;
      case 422:
        return ApiErrorKind.validation;
      case 429:
        return ApiErrorKind.rateLimited;
      case 503:
        return ApiErrorKind.unavailable;
    }
    if (code >= 500) return ApiErrorKind.server;
    return ApiErrorKind.unknown;
  }

  /// الرسالة العربيّة لرمزٍ ما. الرموز الخمسة الأولى ثابتة (عقد الحالات الصادقة)؛
  /// غيرها يعرض `detail` الخادم إن وُجد.
  static String messageForStatus(int? code, Object? detail) {
    if (code == 503) {
      return 'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).';
    }
    if (code == 403) return 'لا تملك صلاحيّة الوصول إلى هذا القسم.';
    if (code == 401) return 'انتهت الجلسة — يُرجى تسجيل الدخول من جديد.';
    if (code == 404) return 'العنصر غير موجود.';
    if (code == 409) return 'تعارض: السجلّ موجود مسبقاً.';
    final text = _detailText(detail);
    if (text != null) return text;
    if (code == 429) return 'طلبات كثيرة — انتظر قليلاً ثمّ أعِد المحاولة.';
    return 'حدث خطأ غير متوقّع.';
  }

  static Object? _detailOf(Object? data) {
    if (data is Map && data['detail'] != null) return data['detail'];
    return null;
  }

  /// FastAPI يردّ `detail` نصّاً، أو قائمة أخطاء تحقّق `[{loc, msg, type}]`.
  static String? _detailText(Object? detail) {
    if (detail == null) return null;
    if (detail is String) return detail.isEmpty ? null : detail;
    if (detail is List) {
      final msgs = detail
          .map((e) => e is Map && e['msg'] != null ? e['msg'].toString() : null)
          .whereType<String>()
          .toList();
      if (msgs.isNotEmpty) return msgs.join('\n');
    }
    return detail.toString();
  }

  @override
  String toString() =>
      'ApiException(${kind.name}${statusCode != null ? ' $statusCode' : ''}): $messageAr';
}
