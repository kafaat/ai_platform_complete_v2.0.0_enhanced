// SAHOOL — features/offline_sync/offline_outbox.dart
// عقد صندوق الإرسال دون اتّصال. تستدعيه الميزات (المهام، الاستكشاف، الأنشطة …)
// ولا تعرف تنفيذه؛ يملكه وكيل offline_sync وحده ويستبدل [OfflineOutbox.instance]
// بتنفيذٍ دائم (Hive، مقيَّد بالمستخدم والمستأجر، يُفرَّغ عند عودة الاتّصال بمفتاح
// Idempotency-Key ثابت). التنفيذ الافتراضيّ صادق: لا يدّعي الحفظ.
//
// [OfflineOutbox.instance] صار التنفيذ الدائم (data/durable_offline_outbox.dart)،
// يُنشأ كسولاً عند أوّل وصول ولا يفتح شيئاً قبل أوّل استعمال. إن تعذّر فتح
// الصندوق المشفّر أو لا جلسة، يُعيد enqueue «notQueued» بسببٍ صريح كما كان.
import 'data/durable_offline_outbox.dart';

/// عمليّة كتابة مؤجَّلة.
class OutboxOp {
  const OutboxOp({
    required this.kind,
    required this.method,
    required this.path,
    required this.body,
    required this.idempotencyKey,
    this.fieldId,
    this.labelAr,
  });

  /// نوع منطقيّ ثابت، مثل 'task_update' أو 'observation_create'.
  final String kind;

  /// POST / PUT / PATCH / DELETE.
  final String method;

  /// مسار الخادم، مثل '/api/v1/tasks/42'.
  final String path;
  final Map<String, dynamic> body;

  /// ثابت عبر المحاولات لنفس الفعل المنطقيّ.
  final String idempotencyKey;
  final String? fieldId;

  /// وصف قصير يظهر في صفحة حالة المزامنة.
  final String? labelAr;
}

/// نتيجة الإيداع: [queued] صحيحة فقط إن حُفظت العمليّة فعلاً للإرسال لاحقاً.
class OutboxReceipt {
  const OutboxReceipt.queued() : queued = true, reason = null;
  const OutboxReceipt.notQueued(this.reason) : queued = false;
  final bool queued;
  final String? reason;
}

abstract class OfflineOutbox {
  /// التنفيذ الدائم (كسول). قابل للاستبدال في الاختبارات.
  static OfflineOutbox instance = DurableOfflineOutbox.shared;

  /// تنفيذ لا يحفظ شيئاً ويقول ذلك — لاختبارات الميزات الأخرى.
  static const OfflineOutbox unavailable = _UnavailableOutbox();

  Future<OutboxReceipt> enqueue(OutboxOp op);

  /// عدد العمليّات المنتظرة للمستخدم الحاليّ.
  Stream<int> get pendingCount;
}

class _UnavailableOutbox implements OfflineOutbox {
  const _UnavailableOutbox();

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async =>
      const OutboxReceipt.notQueued('offline_queue_unavailable');

  @override
  Stream<int> get pendingCount => Stream<int>.value(0);
}
