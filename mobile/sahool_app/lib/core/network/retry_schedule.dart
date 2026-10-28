// SAHOOL — lib/core/network/retry_schedule.dart
// جدولة إعادة المحاولة المشتركة بين صفّي المزامنة (صندوق الإرسال الدائم وطابور
// النماذج الميدانيّة): backoff أُسّيّ محدود + jitter، وقراءة Retry-After بصيغتيه
// (ثوانٍ أو تاريخ HTTP — RFC 9110 §10.2.3).
//
// الموعد المحسوب يُحفَظ في سجلّ العمليّة نفسه (next_attempt_at / not_before)، فلا
// تمحوه إعادة تشغيل التطبيق ولا عودة الشبكة.
import 'dart:io' show HttpDate;
import 'dart:math';

/// أقصى مهلة نقبلها من Retry-After: قيمة شاذّة (تاريخ بعيد) لا تجمّد الطابور.
const Duration kMaxRetryAfter = Duration(hours: 6);

/// يقرأ ترويسة Retry-After. ثوانٍ غير سالبة أو تاريخ HTTP (IMF-fixdate وما
/// يقبله [HttpDate.parse]). تاريخ مضى ⇒ صفر. قيمة غير مفهومة ⇒ null.
Duration? parseRetryAfter(
  String? raw, {
  required DateTime now,
  Duration max = kMaxRetryAfter,
}) {
  if (raw == null) return null;
  final v = raw.trim();
  if (v.isEmpty) return null;
  Duration? d;
  final seconds = int.tryParse(v);
  if (seconds != null) {
    if (seconds < 0) return null;
    d = Duration(seconds: seconds);
  } else {
    try {
      final at = HttpDate.parse(v);
      final diff = at.difference(now.toUtc());
      d = diff.isNegative ? Duration.zero : diff;
    } catch (_) {
      return null;
    }
  }
  return d > max ? max : d;
}

/// backoff أُسّيّ: الأساس × 2^(n-1) حتى [max]، ثمّ jitter حتى 20٪ فوقه.
Duration retryBackoff(
  int attempts, {
  required Duration base,
  required Duration max,
  required Random random,
}) {
  final exp = attempts <= 1 ? 0 : min(attempts - 1, 20);
  final raw = base.inMilliseconds * (1 << exp);
  final capped = min(raw, max.inMilliseconds);
  final jitter = (capped * 0.2 * random.nextDouble()).round();
  return Duration(milliseconds: capped + jitter);
}

/// تقريب مهلة مؤقّت إلى الثانية التالية (لا يُطلَق المؤقّت قبل الموعد بأجزاء
/// من الثانية فيجد العمليّة «غير مستحقّة» بعد).
Duration ceilToSecond(Duration d) {
  if (d <= Duration.zero) return const Duration(seconds: 1);
  final ms = d.inMilliseconds;
  return Duration(seconds: (ms + 999) ~/ 1000);
}
