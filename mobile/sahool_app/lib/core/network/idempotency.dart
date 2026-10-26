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
