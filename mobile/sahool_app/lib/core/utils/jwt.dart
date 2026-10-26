// SAHOOL — lib/utils/jwt.dart
// منطق نقيّ (بلا اعتماد على Flutter) لفحص انتهاء JWT — مصدر واحد للحقيقة
// يستخدمه AuthService وApiService معاً، لتفادي انحراف منطق منسوخ (كان يسبّب
// سلوكاً متناقضاً: fail-open في AuthService مقابل fail-closed في ApiService).
//
// السياسة: يفشل-مغلقاً (fail-closed). أيّ توكن مشوّه، أو غير قابل للتحليل، أو
// بلا حقل exp صالح، يُعدّ منتهياً — لا نمنح جلسة بناءً على توكن لا نثق به.
import 'dart:convert';

/// يتحقّق إن كان [token] (JWT مضغوط: header.payload.signature) منتهياً.
///
/// fail-closed: يعيد `true` (منتهٍ) لأيّ من الحالات التالية:
///  - بنية غير صحيحة (ليست ثلاثة أجزاء)،
///  - فشل فكّ/تحليل الـpayload،
///  - غياب حقل `exp` أو كونه بنوع غير عدديّ صحيح.
///
/// [skewSeconds] هامش أمان (ثوانٍ): يُعدّ التوكن منتهياً قبل وقته الفعليّ بهذا
/// القدر، لتفادي حالات الحدّ وفروق الساعة (افتراضيّ 60 ثانية).
bool isJwtExpired(String token, {int skewSeconds = 60}) {
  try {
    final parts = token.split('.');
    if (parts.length != 3) return true;
    final payload = json.decode(
      utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
    );
    if (payload is! Map) return true;
    final exp = payload['exp'];
    // exp يجب أن يكون عدداً صحيحاً (ثوانٍ منذ epoch). أيّ شيء آخر ⇒ fail-closed.
    if (exp is! int) return true;
    final nowSeconds = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    return nowSeconds > exp - skewSeconds;
  } catch (_) {
    return true;
  }
}
