/// إرسال عنصر طابور واحد — المسار الوحيد الذي يرسل منه التطبيق نموذجاً ميدانيّاً.
///
/// تستدعيه الشاشة (`FieldFormCubit.sync`) وحلقة التصريف
/// (`FieldFormsCoordinator.drain`) معاً. كان كلٌّ منهما يرسل بنفسه، فقد يُرسَل
/// العنصر نفسه مرّتين في اللحظة نفسها. هنا إرسال واحد لكلّ instance_id في أيّ
/// لحظة: الطالب الثاني ينتظر نتيجة الأوّل ولا يرسل ثانيةً، ولا تتضاعف المحاولات.
library;

import 'package:dio/dio.dart';

import 'field_forms_api.dart';
import 'submission_queue.dart';

enum SendOutcomeKind {
  /// ردّ الخادم 201 (مقبول أو محجور) — العنصر أُزيل من الطابور.
  settled,

  /// فشل مؤقّت (شبكة/5xx/408/425/429/ردّ غير مفهوم) — العنصر باقٍ وزاد عدّاده.
  retryLater,

  /// 401/403 — الجلسة لا تسمح الآن؛ أوقف التصريف.
  authRejected,

  /// رفضه الخادم (4xx) مراراً — نُقل إلى قائمة «لم يُقبل» ولا يُحذف.
  failed,
}

class SendOutcome {
  const SendOutcome(
    this.kind, {
    this.result,
    this.error,
    this.item,
    this.retryAfter,
  });

  final SendOutcomeKind kind;

  /// مهلة ترويسة Retry-After (بالثواني) إن أرسلها الخادم مع فشلٍ مؤقّت.
  final Duration? retryAfter;

  /// ردّ الخادم عند [SendOutcomeKind.settled].
  final SubmissionResult? result;
  final Object? error;

  /// العنصر بعد التحديث (العدّاد/الفشل) — null عند التسوية.
  final QueuedSubmission? item;
}

class SubmissionSender {
  SubmissionSender._();

  /// بعد هذا العدد من رفض 4xx يتوقّف التصريف التلقائيّ للعنصر.
  static const int maxRejectedAttempts = 10;

  /// 4xx مؤقّتة بطبيعتها (مهلة/مبكّر جدّاً/تحديد معدّل): الخادم لم يحكم على
  /// الإرسال، فلا تصير «لم يُقبل» مهما تكرّرت — تُعاد لاحقاً كالـ5xx.
  static const Set<int> transientStatuses = {408, 425, 429};

  static final Map<String, Future<SendOutcome>> _inFlight = {};

  /// للاختبارات: هل يُرسَل هذا العنصر الآن؟
  static bool isInFlight(String instanceId) =>
      _inFlight.containsKey(instanceId);

  static Future<SendOutcome> send({
    required QueuedSubmission item,
    required SubmissionQueue queue,
    required FieldFormsApi api,
    required String deviceId,
    String? server,
  }) {
    final running = _inFlight[item.instanceId];
    if (running != null) return running;
    final future = _send(item, queue, api, deviceId, server);
    _inFlight[item.instanceId] = future;
    return future.whenComplete(() => _inFlight.remove(item.instanceId));
  }

  static Future<SendOutcome> _send(
    QueuedSubmission item,
    SubmissionQueue queue,
    FieldFormsApi api,
    String deviceId,
    String? server,
  ) async {
    try {
      final result = await api.submit(
        item.buildEnvelope(server: server),
        deviceId: deviceId,
      );
      // الخادم حسم مصيره (مقبول/محجور) وخزّنه — لا يُعاد إرساله.
      await queue.remove(item.instanceId);
      return SendOutcome(SendOutcomeKind.settled, result: result);
    } on DioException catch (error) {
      final status = error.response?.statusCode ?? 0;
      final updated = await queue.markRetry(item);
      if (status == 401 || status == 403) {
        return SendOutcome(
          SendOutcomeKind.authRejected,
          error: error,
          item: updated,
        );
      }
      if (status >= 400 &&
          status < 500 &&
          !transientStatuses.contains(status) &&
          updated.attempts >= maxRejectedAttempts) {
        final failed = await queue.markFailed(updated, _reasonOf(error));
        return SendOutcome(SendOutcomeKind.failed, error: error, item: failed);
      }
      return SendOutcome(
        SendOutcomeKind.retryLater,
        error: error,
        item: updated,
        retryAfter: _retryAfterOf(error),
      );
    } catch (error) {
      final updated = await queue.markRetry(item);
      return SendOutcome(
        SendOutcomeKind.retryLater,
        error: error,
        item: updated,
      );
    }
  }

  /// Retry-After بصيغة الثواني فقط؛ صيغة التاريخ تُترك لـbackoff المنسّق.
  static Duration? _retryAfterOf(DioException error) {
    final raw = error.response?.headers.value('retry-after');
    final seconds = raw == null ? null : int.tryParse(raw.trim());
    return seconds == null || seconds < 0 ? null : Duration(seconds: seconds);
  }

  static String _reasonOf(DioException error) {
    final status = error.response?.statusCode;
    final data = error.response?.data;
    final detail = data is Map ? data['detail'] : null;
    return detail is String && detail.isNotEmpty
        ? 'HTTP $status: $detail'
        : 'HTTP $status';
  }
}
