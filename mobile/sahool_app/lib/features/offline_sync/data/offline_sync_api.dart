// SAHOOL — features/offline_sync/data/offline_sync_api.dart
// إرسال عمليّة مؤجَّلة إلى نقطتها الخاصّة، وتصنيف النتيجة.
//
// لا نمرّ عبر POST /api/v1/sync (routers/sync.py:91): يسجّل معظم أنواع العمليّات
// في دفتر فقط ولا يطبّقها، فإرسال مهمّة/ملاحظة عبره «ينجح» دون أن يتغيّر شيء.
// كلّ عمليّة تذهب إلى مسارها (PATCH /api/v1/tasks/{id}، POST …/activities، …)
// بترويسة Idempotency-Key الثابتة نفسها في كلّ محاولة، والخادم يعيد النتيجة
// المخزّنة عند الإعادة (api/main.py:_idempotent).
import 'dart:io' show SocketException;

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/network/retry_schedule.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

class OfflineSyncApi {
  OfflineSyncApi([this._client]);

  static final OfflineSyncApi instance = OfflineSyncApi();

  final ApiClient? _client;
  ApiClient get _c => _client ?? ApiClient.instance;

  /// يرسل [op] كما هي: الطريقة والمسار والجسم والمفتاح الثابت. يرمي
  /// [ApiException] عند الفشل.
  ///
  /// [ownerGuard] يُفحَص داخل ApiClient على الرمز الذي سيُرسَل فعلاً (بعد أيّ
  /// تجديد)، فلا يخرج الطلب بهويّة غير مالكه. لا إعادات فوريّة لـ5xx هنا:
  /// الصندوق يعيد بموعدٍ محفوظ يحترم Retry-After.
  Future<dynamic> sendOp(
    OutboxOp op, {
    CancelToken? cancelToken,
    bool Function(String? token)? ownerGuard,
  }) {
    final method = op.method.toUpperCase();
    return _c.send(
      method,
      op.path,
      data: (method == 'DELETE' && op.body.isEmpty) ? null : op.body,
      idempotencyKey: IdempotencyKey(op.idempotencyKey),
      cancelToken: cancelToken,
      extra: {kOwnerGuardExtra: ?ownerGuard, kDurableRetryExtra: true},
    );
  }
}

/// ما يحدث للعمليّة بعد محاولة إرسال.
enum OutboxOutcomeKind {
  /// 2xx ⇒ تُحذف.
  sent,

  /// 409 يقول إنّ نفس المفتاح طُبِّق سابقاً (إعادة idempotent) ⇒ تُحذف.
  alreadyApplied,

  /// 4xx نهائيّ ⇒ قائمة «مرفوضة» برسالة الخادم.
  rejected,

  /// 5xx/429/«قيد المعالجة» ⇒ تبقى مع backoff.
  retryLater,

  /// لا شبكة/مهلة ⇒ تبقى مع backoff ويتوقّف التصريف.
  offline,

  /// 401 بعد فشل التجديد ⇒ تبقى (ليس ذنب العمليّة) ويتوقّف التصريف.
  sessionProblem,

  /// أُلغي الطلب (انتهت الجلسة أثناءه) ⇒ تبقى، ونتيجتها غير مؤكَّدة: الإلغاء
  /// على الجهاز لا يوقف ما وصل الخادم.
  aborted,

  /// لم يغادر الطلب الجهاز: تبدّل صاحب الجلسة قبل الإرسال ⇒ لا تغيير على السجلّ.
  notSent,
}

/// سبب 409 تعارض المفتاح كما يميّزه الخادم (D4). null ⇒ 409 من نوع آخر.
abstract final class IdempotencyConflict {
  /// المفتاح محجوز لحمولة أخرى ⇒ تحتاج تدخّلاً، لا إعادة عمياء.
  static const payloadMismatch = 'payload_mismatch';

  /// الأمر الأصليّ ما زال قيد المعالجة ⇒ يُعاد لاحقاً بنفس المفتاح.
  static const inProgress = 'in_progress';
}

class OutboxOutcome {
  const OutboxOutcome(
    this.kind, {
    this.statusCode,
    this.messageAr,
    this.retryAfter,
    this.maybeCommitted = false,
    this.conflictReason,
  });
  final OutboxOutcomeKind kind;
  final int? statusCode;
  final String? messageAr;

  /// مهلة Retry-After من الخادم (ثوانٍ أو تاريخ HTTP) إن أرسلها.
  final Duration? retryAfter;

  /// قد يكون الخادم نفّذ الطلب ولم يصلنا تأكيده (مهلة استقبال، قطع بعد الإرسال،
  /// 5xx من بوّابة، 409 قيد المعالجة، إلغاء أثناء الطلب).
  final bool maybeCommitted;

  /// [IdempotencyConflict] عند 409 تعارض المفتاح.
  final String? conflictReason;
}

/// رسالة الخادم كما هي إن وُجدت: `detail` نصّاً، أو `{message_ar|message|code}`،
/// أو قائمة أخطاء تحقّق. وإلّا الرسالة العربيّة المُنمَّطة.
String serverMessageOf(ApiException e) {
  final d = e.detail;
  if (d is String && d.trim().isNotEmpty) return d;
  if (d is Map) {
    for (final k in const ['message_ar', 'message', 'detail', 'code']) {
      final v = d[k];
      if (v is String && v.trim().isNotEmpty) return v;
    }
  }
  if (d is List) {
    final msgs = d
        .map((x) => x is Map && x['msg'] != null ? x['msg'].toString() : null)
        .whereType<String>()
        .toList();
    if (msgs.isNotEmpty) return msgs.join('\n');
  }
  return e.messageAr;
}

Object? _responseBody(ApiException e) {
  final c = e.cause;
  return c is DioException ? c.response?.data : null;
}

bool _flag(Object? m, String key) => m is Map && m[key] == true;

/// 409 يحمل علامة إعادة idempotent (`idempotent_replay`/`idempotent` = true) في
/// الجسم أو في `detail`.
bool isIdempotentReplay(ApiException e) {
  if (e.statusCode != 409) return false;
  final body = _responseBody(e);
  for (final m in [body, e.detail]) {
    if (_flag(m, 'idempotent_replay') || _flag(m, 'idempotent')) return true;
  }
  return false;
}

/// سبب 409 تعارض المفتاح: رمز `reason`/`code` الثابت من الخادم أوّلاً (في الجسم
/// أو في `detail`)، ثمّ — ما دام الخادم الحاليّ لا يرسل رمزاً (api/main.py:
/// _idempotent يرسل نصّاً فقط) — نصّ الرسالتين المعروفتين. null ⇒ 409 آخر.
String? idempotencyConflictReason(ApiException e) {
  if (e.statusCode != 409) return null;
  const known = {
    IdempotencyConflict.payloadMismatch,
    IdempotencyConflict.inProgress,
  };
  for (final m in [_responseBody(e), e.detail]) {
    if (m is! Map) continue;
    for (final k in const ['reason', 'code']) {
      final v = m[k];
      if (v is String && known.contains(v)) return v;
    }
    final inner = m['detail'];
    if (inner is Map) {
      for (final k in const ['reason', 'code']) {
        final v = inner[k];
        if (v is String && known.contains(v)) return v;
      }
    }
  }
  final text = e.detail is String ? e.detail as String : '';
  if (text.contains('قيد المعالجة')) return IdempotencyConflict.inProgress;
  if (text.contains('بحمولةٍ مختلفة') || text.contains('بحمولة مختلفة')) {
    return IdempotencyConflict.payloadMismatch;
  }
  return null;
}

/// 409 «الأمر قيد المعالجة — أعد المحاولة لاحقاً» (api/main.py:_idempotent):
/// الطلب الأصليّ لم يكتمل بعد؛ ليس رفضاً.
bool isCommandInProgress(ApiException e) =>
    idempotencyConflictReason(e) == IdempotencyConflict.inProgress;

/// مهلة Retry-After من ترويسة الاستجابة (ثوانٍ أو تاريخ HTTP).
Duration? retryAfterOf(ApiException e, {DateTime? now}) {
  final c = e.cause;
  if (c is! DioException) return null;
  return parseRetryAfter(
    c.response?.headers.value('retry-after'),
    now: now ?? DateTime.now(),
  );
}

/// فشل اتّصال لم يغادر فيه الطلب الجهاز (تعذّر فتح الاتّصال)؟ غير ذلك (مهلة
/// استقبال/إرسال، إغلاق الاتّصال بعد الإرسال) قد يكون الخادم نفّذ الطلب.
bool _neverLeftDevice(ApiException e) {
  final c = e.cause;
  if (c is! DioException) return false;
  if (c.type == DioExceptionType.connectionTimeout) return true;
  if (c.type == DioExceptionType.connectionError) {
    return c.error is SocketException;
  }
  return false;
}

OutboxOutcome classifyOutboxFailure(ApiException e, {DateTime? now}) {
  if (e.isCancelled) {
    final c = e.cause;
    if (c is DioException && c.error == kOwnerChangedBeforeSend) {
      return const OutboxOutcome(OutboxOutcomeKind.notSent);
    }
    return const OutboxOutcome(OutboxOutcomeKind.aborted, maybeCommitted: true);
  }
  if (e.isConnectivity) {
    return OutboxOutcome(
      OutboxOutcomeKind.offline,
      messageAr: e.messageAr,
      maybeCommitted: !_neverLeftDevice(e),
    );
  }
  final code = e.statusCode;
  if (code == null) {
    return OutboxOutcome(
      OutboxOutcomeKind.retryLater,
      messageAr: e.messageAr,
      maybeCommitted: true,
    );
  }
  final retryAfter = retryAfterOf(e, now: now);
  if (code == 401) {
    return OutboxOutcome(
      OutboxOutcomeKind.sessionProblem,
      statusCode: code,
      messageAr: e.messageAr,
    );
  }
  if (code == 409) {
    if (isIdempotentReplay(e)) {
      return const OutboxOutcome(
        OutboxOutcomeKind.alreadyApplied,
        statusCode: 409,
      );
    }
    switch (idempotencyConflictReason(e)) {
      case IdempotencyConflict.inProgress:
        // الأصل ما زال يُعالَج: نتيجته غير معروفة بعد ⇒ نفس المفتاح لاحقاً.
        return OutboxOutcome(
          OutboxOutcomeKind.retryLater,
          statusCode: code,
          messageAr: serverMessageOf(e),
          retryAfter: retryAfter,
          maybeCommitted: true,
          conflictReason: IdempotencyConflict.inProgress,
        );
      case IdempotencyConflict.payloadMismatch:
        // المفتاح محجوز لحمولة أخرى: إعادة الحمولة نفسها لن تُغيّر الجواب.
        return OutboxOutcome(
          OutboxOutcomeKind.rejected,
          statusCode: code,
          messageAr: serverMessageOf(e),
          conflictReason: IdempotencyConflict.payloadMismatch,
        );
    }
  }
  // 408/425/429/503: الخادم لم ينفّذ (تحديد معدّل/غير متاح) ⇒ إعادة بنفس المفتاح
  // بعد Retry-After. بقيّة 5xx: قد يكون نفّذ ⇒ النتيجة غير مؤكَّدة.
  if (code == 408 || code == 425 || code == 429 || code == 503) {
    return OutboxOutcome(
      OutboxOutcomeKind.retryLater,
      statusCode: code,
      messageAr: e.messageAr,
      retryAfter: retryAfter,
    );
  }
  if (code >= 500) {
    return OutboxOutcome(
      OutboxOutcomeKind.retryLater,
      statusCode: code,
      messageAr: e.messageAr,
      retryAfter: retryAfter,
      maybeCommitted: true,
    );
  }
  if (code >= 400) {
    return OutboxOutcome(
      OutboxOutcomeKind.rejected,
      statusCode: code,
      messageAr: serverMessageOf(e),
    );
  }
  // 1xx/3xx غير متوقّع من Dio — لا نحكم برفض.
  return OutboxOutcome(
    OutboxOutcomeKind.retryLater,
    statusCode: code,
    messageAr: e.messageAr,
  );
}
