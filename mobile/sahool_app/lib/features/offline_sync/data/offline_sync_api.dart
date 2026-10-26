// SAHOOL — features/offline_sync/data/offline_sync_api.dart
// إرسال عمليّة مؤجَّلة إلى نقطتها الخاصّة، وتصنيف النتيجة.
//
// لا نمرّ عبر POST /api/v1/sync (routers/sync.py:91): يسجّل معظم أنواع العمليّات
// في دفتر فقط ولا يطبّقها، فإرسال مهمّة/ملاحظة عبره «ينجح» دون أن يتغيّر شيء.
// كلّ عمليّة تذهب إلى مسارها (PATCH /api/v1/tasks/{id}، POST …/activities، …)
// بترويسة Idempotency-Key الثابتة نفسها في كلّ محاولة، والخادم يعيد النتيجة
// المخزّنة عند الإعادة (api/main.py:_idempotent).
import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

class OfflineSyncApi {
  OfflineSyncApi([this._client]);

  static final OfflineSyncApi instance = OfflineSyncApi();

  final ApiClient? _client;
  ApiClient get _c => _client ?? ApiClient.instance;

  /// يرسل [op] كما هي: الطريقة والمسار والجسم والمفتاح الثابت. يرمي
  /// [ApiException] عند الفشل.
  Future<dynamic> sendOp(OutboxOp op, {CancelToken? cancelToken}) {
    final method = op.method.toUpperCase();
    return _c.send(
      method,
      op.path,
      data: (method == 'DELETE' && op.body.isEmpty) ? null : op.body,
      idempotencyKey: IdempotencyKey(op.idempotencyKey),
      cancelToken: cancelToken,
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

  /// أُلغي الطلب (انتهت الجلسة أثناءه) ⇒ تبقى كما هي.
  aborted,
}

class OutboxOutcome {
  const OutboxOutcome(this.kind, {this.statusCode, this.messageAr});
  final OutboxOutcomeKind kind;
  final int? statusCode;
  final String? messageAr;
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

/// 409 «الأمر قيد المعالجة — أعد المحاولة لاحقاً» (api/main.py:_idempotent):
/// الطلب الأصليّ لم يكتمل بعد؛ ليس رفضاً.
bool isCommandInProgress(ApiException e) =>
    e.statusCode == 409 &&
    e.detail is String &&
    (e.detail as String).contains('قيد المعالجة');

OutboxOutcome classifyOutboxFailure(ApiException e) {
  if (e.isCancelled) return const OutboxOutcome(OutboxOutcomeKind.aborted);
  if (e.isConnectivity) {
    return OutboxOutcome(OutboxOutcomeKind.offline, messageAr: e.messageAr);
  }
  final code = e.statusCode;
  if (code == null) {
    return OutboxOutcome(OutboxOutcomeKind.retryLater, messageAr: e.messageAr);
  }
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
    if (isCommandInProgress(e)) {
      return OutboxOutcome(
        OutboxOutcomeKind.retryLater,
        statusCode: code,
        messageAr: serverMessageOf(e),
      );
    }
  }
  if (code == 408 || code == 425 || code == 429 || code >= 500) {
    return OutboxOutcome(
      OutboxOutcomeKind.retryLater,
      statusCode: code,
      messageAr: e.messageAr,
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
