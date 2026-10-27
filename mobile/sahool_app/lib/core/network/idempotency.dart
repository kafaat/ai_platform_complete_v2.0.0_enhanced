// SAHOOL — lib/core/network/idempotency.dart
// مفاتيح منع التكرار (Idempotency-Key) للكتابات.
//
// القاعدة: **مفتاح واحد لكلّ نيّة كتابة منطقيّة**، يُولَّد مرّة حين يبدأ المستخدم
// العمليّة (فتح نموذج الإضافة، الضغط الأوّل على «حفظ») ويُعاد استعماله في كلّ
// محاولة لاحقة لنفس العمليّة. ApiClient يعيد الكتابة تلقائيّاً على 502/503/504
// **فقط** إن حملت مفتاحاً — فالخادم عندئذٍ يميّز الإعادة من طلب جديد.
//
// لا نولّد مفتاحاً تلقائيّاً لكلّ POST: مفتاح جديد في كلّ نداء لا يمنع تكراراً
// (ضغطتان ⇒ مفتاحان)، ويُوهم بأمانٍ غير موجود. ولا يكفي المفتاح وحده: الخادم
// يجب أن يحترمه على تلك النقطة؛ هذا عقدٌ خادميّ يُتحقَّق منه لكلّ نقطة.
//
// «النيّة» = المفتاح **والحمولة معاً**: إن عدّل المستخدم النموذج بعد نتيجة مجهولة
// (انقطاع بعد التزام الخادم) ثمّ أعاد الحفظ بالمفتاح نفسه، أعاد الخادم نتيجة
// الطلب القديم نجاحاً للنيّة الجديدة (UI-M3). لذا النماذج القابلة للتعديل تستعمل
// [PayloadIdempotencyKey]: نفس الحمولة ⇒ نفس المفتاح، حمولة معدّلة ⇒ مفتاح جديد.
import 'dart:convert';

import 'package:sahool_app/core/utils/ids.dart';

/// اسم الترويسة كما يقرؤها الخادم والويب.
const String kIdempotencyHeader = 'Idempotency-Key';

/// مفتاح نيّة كتابة واحدة. احتفظ بالكائن طوال عمر النموذج/العمليّة.
class IdempotencyKey {
  final String value;
  const IdempotencyKey(this.value);

  /// UUIDv7 (مرتّب زمنيّاً + 74 بت عشوائيّة) من utils/ids.dart.
  factory IdempotencyKey.generate() => IdempotencyKey(generateRequestId());

  @override
  String toString() => value;
}

/// مفتاح مربوط بحمولة الكتابة: يبقى ثابتاً ما دامت الحمولة نفسها، ويُولَّد من
/// جديد حين تتغيّر (تعديلٌ بعد فشلٍ مجهول النتيجة = نيّة جديدة لا إعادة).
class PayloadIdempotencyKey {
  IdempotencyKey _key = IdempotencyKey.generate();
  String? _fingerprint;

  /// آخر مفتاح سُلِّم (للعرض/الاختبار).
  IdempotencyKey get current => _key;

  /// المفتاح لهذه الحمولة: المحاولة الأولى تأخذ المفتاح الحاليّ، ثمّ يتجدّد عند
  /// أيّ اختلاف في المحتوى (ترتيب مفاتيح الخرائط لا يهمّ).
  IdempotencyKey forPayload(Object? payload) {
    final fp = jsonEncode(_canonical(payload));
    if (_fingerprint != null && _fingerprint != fp) {
      _key = IdempotencyKey.generate();
    }
    _fingerprint = fp;
    return _key;
  }

  static Object? _canonical(Object? v) {
    if (v is Map) {
      final keys = v.keys.map((k) => k.toString()).toList()..sort();
      return {for (final k in keys) k: _canonical(v[k])};
    }
    if (v is Iterable) return [for (final e in v) _canonical(e)];
    if (v is num || v is String || v is bool || v == null) return v;
    return v.toString();
  }
}
