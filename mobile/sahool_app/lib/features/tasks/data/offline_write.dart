// SAHOOL — features/tasks/data/offline_write.dart
// كتابة ميدانيّة «أرسِل الآن أو احفظ للإرسال لاحقاً» مشتركة بين المهام والأنشطة.
//
// القواعد:
//  * مفتاح Idempotency-Key واحد لكلّ نيّة منطقيّة ([IntentKeys]): يُعاد نفسه في
//    كلّ إعادة لنفس النيّة بنفس الجسم، ويُستبدَل إن تغيّر الجسم (الخادم يرفض
//    إعادة مفتاحٍ بحمولةٍ مختلفة بـ409 — api/main.py `_idempotent`)، ويُحرَّر بعد
//    تأكيد الخادم أو بعد إيداعه في صندوق الإرسال (الذي يحمله من ثَمّ).
//  * بلا اتّصال (أو فشل اتّصال/مهلة) ⇒ صندوق الإرسال. نجاح الإيداع وحده
//    ([OutboxReceipt.queued]) يسمح بعرض النتيجة محلّيّاً؛ غير ذلك فشل صريح
//    «لم يُحفظ» لا ادّعاء حفظ.
//  * أخطاء الخادم (403/404/422/503…) لا تُخبَّأ في الصندوق: إعادة إرسالها لاحقاً
//    لن تنجح، والمستخدم يجب أن يرى السبب الآن.
import 'dart:convert';

import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

enum WriteOutcomeKind { saved, queued, failed }

class WriteOutcome<T> {
  const WriteOutcome.saved(T this.value)
    : kind = WriteOutcomeKind.saved,
      error = null,
      notQueuedReason = null;
  const WriteOutcome.queued()
    : kind = WriteOutcomeKind.queued,
      value = null,
      error = null,
      notQueuedReason = null;
  const WriteOutcome.failed(ApiException this.error, {this.notQueuedReason})
    : kind = WriteOutcomeKind.failed,
      value = null;

  final WriteOutcomeKind kind;
  final T? value;
  final ApiException? error;

  /// سبب رفض صندوق الإرسال (إن كان الفشل بلا اتّصال ولم يُحفَظ للإرسال).
  final String? notQueuedReason;

  bool get isSaved => kind == WriteOutcomeKind.saved;
  bool get isQueued => kind == WriteOutcomeKind.queued;
  bool get isFailed => kind == WriteOutcomeKind.failed;

  /// رسالة عربيّة صادقة لحالة الفشل.
  String get messageAr {
    if (!isFailed) return '';
    if (notQueuedReason != null) return notQueuedMessage(notQueuedReason!);
    return error!.messageAr;
  }
}

/// رسالة رفض صندوق الإرسال.
String notQueuedMessage(String reason) => reason == 'offline_queue_unavailable'
    ? 'لا اتّصال بالخادم، والحفظ دون اتّصال غير متاح بعد على هذا الجهاز — لم يُحفظ شيء. أعد المحاولة عند عودة الشبكة.'
    : 'لا اتّصال بالخادم، وتعذّر حفظ العمليّة للإرسال لاحقاً — لم يُحفظ شيء.';

/// مفاتيح النيّات المفتوحة: مفتاح ثابت لكلّ (نيّة، جسم) حتى تُحسَم.
class IntentKeys {
  IntentKeys({IdempotencyKey Function()? generate})
    : _generate = generate ?? IdempotencyKey.generate;

  final IdempotencyKey Function() _generate;
  final Map<String, (String, IdempotencyKey)> _open = {};

  /// المفتاح لنيّة [intent] بالجسم [body]: نفسه ما دام الجسم نفسه.
  IdempotencyKey keyFor(String intent, Map<String, dynamic> body) {
    final digest = jsonEncode(body);
    final open = _open[intent];
    if (open != null && open.$1 == digest) return open.$2;
    final key = _generate();
    _open[intent] = (digest, key);
    return key;
  }

  /// النيّة حُسِمت (أكّدها الخادم أو صار المفتاح ملك صندوق الإرسال).
  void settle(String intent) => _open.remove(intent);

  bool isOpen(String intent) => _open.containsKey(intent);
}

/// يرسل الآن إن أمكن، وإلّا يودع في [outbox].
///
/// [online] قراءة حالة الشبكة (ConnectivityStatus): false ⇒ لا محاولة شبكة.
Future<WriteOutcome<T>> writeOrQueue<T>({
  required IdempotencyKey key,
  required Future<T> Function(IdempotencyKey key) send,
  required OutboxOp Function(IdempotencyKey key) op,
  required OfflineOutbox outbox,
  required bool online,
}) async {
  ApiException? connectivityError;
  if (online) {
    try {
      return WriteOutcome.saved(await send(key));
    } catch (e) {
      final err = ApiException.from(e);
      if (!err.isConnectivity) return WriteOutcome.failed(err);
      connectivityError = err;
    }
  }
  final err =
      connectivityError ??
      const ApiException(
        kind: ApiErrorKind.network,
        messageAr: 'لا اتّصال بالشبكة.',
      );
  OutboxReceipt receipt;
  try {
    receipt = await outbox.enqueue(op(key));
  } catch (_) {
    receipt = const OutboxReceipt.notQueued('outbox_error');
  }
  if (receipt.queued) return const WriteOutcome.queued();
  return WriteOutcome.failed(
    err,
    notQueuedReason: receipt.reason ?? 'outbox_error',
  );
}
