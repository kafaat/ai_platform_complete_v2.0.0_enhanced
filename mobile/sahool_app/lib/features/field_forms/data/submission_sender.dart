/// إرسال عنصر طابور واحد — المسار الوحيد الذي يرسل منه التطبيق نموذجاً ميدانيّاً.
///
/// تستدعيه الشاشة (`FieldFormCubit.sync`) وحلقة التصريف
/// (`FieldFormsCoordinator.drain`) معاً. كان كلٌّ منهما يرسل بنفسه، فقد يُرسَل
/// العنصر نفسه مرّتين في اللحظة نفسها. هنا إرسال واحد لكلّ instance_id في أيّ
/// لحظة: الطالب الثاني ينتظر نتيجة الأوّل ولا يرسل ثانيةً، ولا تتضاعف المحاولات.
///
/// الجدولة دائمة: كلّ فشل مؤقّت يحفظ في الصفّ next_attempt_at (backoff + jitter)
/// وnot_before (Retry-After بثوانٍ أو بتاريخ HTTP). not_before لا يتخطّاه أحد —
/// ولا الشاشة. [isCurrent] يُفحَص قبل الإرسال وبعد ردّ الخادم: ردٌّ وصل بعد تبدّل
/// الجلسة لا يحذف عنصر صاحبها؛ يبقى «نتيجته غير مؤكَّدة» حتى يعود.
library;

import 'dart:io' show SocketException;
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart'
    show kOwnerChangedBeforeSend;
import 'package:sahool_app/core/network/retry_schedule.dart';

import 'field_forms_api.dart';
import 'submission_queue.dart';

enum SendOutcomeKind {
  /// ردّ الخادم 201 (مقبول أو محجور) — العنصر أُزيل من الطابور.
  settled,

  /// فشل مؤقّت (شبكة/5xx/408/425/429/ردّ غير مفهوم) — العنصر باقٍ وزاد عدّاده.
  retryLater,

  /// 401/403 — الجلسة لا تسمح الآن؛ أوقف التصريف.
  authRejected,

  /// رفضه الخادم (4xx) مراراً، أو 409 تعارضٌ لا تحلّه الإعادة — نُقل إلى قائمة
  /// «لم يُقبل» ولا يُحذف.
  failed,

  /// تبدّلت الجلسة قبل الإرسال (لم يُرسَل) أو قبل وصول الردّ/أثناءه (أُلغي أو وصل
  /// متأخّراً) — العنصر باقٍ بجسمه ومعرّفه، ويُطابَق في سياق صاحبه.
  fenced,
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

  /// مهلة ترويسة Retry-After (ثوانٍ أو تاريخ HTTP) إن أرسلها الخادم مع فشلٍ
  /// مؤقّت، أو ما بقي منها إن لم يُرسَل العنصر لأنّ موعده لم يحن.
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

  /// backoff الإعادة التلقائيّة الافتراضيّ (المنسّق يمرّر قيمه).
  static const Duration defaultBackoffBase = Duration(seconds: 15);
  static const Duration defaultBackoffMax = Duration(minutes: 30);

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
    bool Function()? isCurrent,
    CancelToken? cancelToken,
    DateTime Function()? clock,
    Random? random,
    Duration backoffBase = defaultBackoffBase,
    Duration backoffMax = defaultBackoffMax,
  }) {
    final running = _inFlight[item.instanceId];
    if (running != null) return running;
    final future = _send(
      item,
      queue,
      api,
      deviceId,
      server,
      isCurrent: isCurrent,
      cancelToken: cancelToken,
      clock: clock ?? DateTime.now,
      random: random ?? Random(),
      backoffBase: backoffBase,
      backoffMax: backoffMax,
    );
    _inFlight[item.instanceId] = future;
    return future.whenComplete(() => _inFlight.remove(item.instanceId));
  }

  static Future<SendOutcome> _send(
    QueuedSubmission item,
    SubmissionQueue queue,
    FieldFormsApi api,
    String deviceId,
    String? server, {
    required bool Function()? isCurrent,
    required CancelToken? cancelToken,
    required DateTime Function() clock,
    required Random random,
    required Duration backoffBase,
    required Duration backoffMax,
  }) async {
    // النسخة المحفوظة الآن (عدّاد/موعد) — نسخة الشاشة قد تكون أقدم.
    final current = queue.byId(item.instanceId) ?? item;
    final before = clock();
    final notBefore = current.notBefore;
    if (notBefore != null && notBefore.isAfter(before)) {
      // الخادم طلب الانتظار: لا طلب قبل موعده، ولو يدويّاً.
      return SendOutcome(
        SendOutcomeKind.retryLater,
        item: current,
        retryAfter: notBefore.difference(before),
      );
    }
    if (isCurrent != null && !isCurrent()) {
      return SendOutcome(SendOutcomeKind.fenced, item: current);
    }

    Future<QueuedSubmission> retryLater({
      Duration? retryAfter,
      bool outcomeUnknown = false,
      bool unreachable = false,
    }) {
      final now = clock().toUtc();
      var wait = retryBackoff(
        current.attempts + 1,
        base: backoffBase,
        max: backoffMax,
        random: random,
      );
      if (retryAfter != null && retryAfter > wait) wait = retryAfter;
      return queue.markRetry(
        current,
        nextAttemptAt: now.add(wait),
        notBefore: retryAfter == null ? null : now.add(retryAfter),
        outcomeUnknown: outcomeUnknown,
        unreachable: unreachable,
      );
    }

    try {
      final result = await api.submit(
        current.buildEnvelope(server: server),
        deviceId: deviceId,
        cancelToken: cancelToken,
        ownerGuard: isCurrent == null ? null : (_) => isCurrent(),
      );
      if (isCurrent != null && !isCurrent()) {
        // ردّ وصل بعد تبدّل الجلسة: لا يُحذف عنصر صاحبها بسببه.
        final held = await queue.markOutcomeUnknown(current);
        return SendOutcome(SendOutcomeKind.fenced, result: result, item: held);
      }
      // الخادم حسم مصيره (مقبول/محجور) وخزّنه — لا يُعاد إرساله.
      await queue.remove(current.instanceId);
      return SendOutcome(SendOutcomeKind.settled, result: result);
    } on DioException catch (error) {
      if (error.type == DioExceptionType.cancel &&
          error.error == kOwnerChangedBeforeSend) {
        // الحارس أوقفه قبل أن يغادر الجهاز (تبدّلت الجلسة أثناء التجديد).
        return SendOutcome(SendOutcomeKind.fenced, error: error, item: current);
      }
      if (error.type == DioExceptionType.cancel) {
        // الإلغاء على الجهاز لا يوقف ما وصل الخادم.
        final held = await queue.markOutcomeUnknown(current);
        return SendOutcome(SendOutcomeKind.fenced, error: error, item: held);
      }
      final status = error.response?.statusCode ?? 0;
      final retryAfter = parseRetryAfter(
        error.response?.headers.value('retry-after'),
        now: clock(),
      );
      if (status == 0) {
        final neverLeft =
            error.type == DioExceptionType.connectionTimeout ||
            (error.type == DioExceptionType.connectionError &&
                error.error is SocketException);
        final updated = await retryLater(
          outcomeUnknown: !neverLeft,
          unreachable: error.type != DioExceptionType.receiveTimeout,
        );
        return SendOutcome(
          SendOutcomeKind.retryLater,
          error: error,
          item: updated,
        );
      }
      if (status == 401 || status == 403) {
        final updated = await queue.markRetry(current);
        return SendOutcome(
          SendOutcomeKind.authRejected,
          error: error,
          item: updated,
        );
      }
      if (status == 409) {
        if (conflictReasonOf(error) == 'in_progress') {
          // الإرسال الأصليّ ما زال يُعالَج: نفس الجسم لاحقاً.
          final updated = await retryLater(
            retryAfter: retryAfter,
            outcomeUnknown: true,
          );
          return SendOutcome(
            SendOutcomeKind.retryLater,
            error: error,
            item: updated,
            retryAfter: retryAfter,
          );
        }
        // تعارض (اختلاف حمولة/إسناد ملتبس): إعادة الجسم نفسه لن تغيّر الجواب.
        final counted = await queue.markRetry(current);
        final failed = await queue.markFailed(counted, _reasonOf(error));
        return SendOutcome(SendOutcomeKind.failed, error: error, item: failed);
      }
      if (transientStatuses.contains(status) || status == 503) {
        final updated = await retryLater(retryAfter: retryAfter);
        return SendOutcome(
          SendOutcomeKind.retryLater,
          error: error,
          item: updated,
          retryAfter: retryAfter,
        );
      }
      if (status >= 500) {
        // ربّما نفّذ الخادم قبل الخطأ ⇒ النتيجة غير مؤكَّدة حتى يُعاد الجسم نفسه.
        final updated = await retryLater(
          retryAfter: retryAfter,
          outcomeUnknown: true,
        );
        return SendOutcome(
          SendOutcomeKind.retryLater,
          error: error,
          item: updated,
          retryAfter: retryAfter,
        );
      }
      final updated = await retryLater(retryAfter: retryAfter);
      if (status >= 400 && updated.attempts >= maxRejectedAttempts) {
        final failed = await queue.markFailed(updated, _reasonOf(error));
        return SendOutcome(SendOutcomeKind.failed, error: error, item: failed);
      }
      return SendOutcome(
        SendOutcomeKind.retryLater,
        error: error,
        item: updated,
        retryAfter: retryAfter,
      );
    } catch (error) {
      // 2xx بلا حالة مفهومة: ربّما خُزّن ⇒ غير مؤكَّد حتى يُعاد الجسم نفسه.
      final updated = await retryLater(outcomeUnknown: true);
      return SendOutcome(
        SendOutcomeKind.retryLater,
        error: error,
        item: updated,
      );
    }
  }

  /// سبب 409 الثابت إن أرسله الخادم (`reason`/`code` في الجسم أو في `detail`)،
  /// وإلّا نصّ `detail` كما هو. لا يرسل field_forms_api.py رمز in_progress
  /// اليوم (409 عنده ambiguous_active_assignment فقط) — مدعوم لحين يرسله.
  static String? conflictReasonOf(DioException error) {
    final data = error.response?.data;
    if (data is! Map) return null;
    for (final m in [data, data['detail']]) {
      if (m is! Map) continue;
      for (final k in const ['reason', 'code']) {
        final v = m[k];
        if (v is String && v.isNotEmpty) return v;
      }
    }
    final detail = data['detail'];
    if (detail is String) {
      if (detail.contains('قيد المعالجة')) return 'in_progress';
      return detail;
    }
    return null;
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
