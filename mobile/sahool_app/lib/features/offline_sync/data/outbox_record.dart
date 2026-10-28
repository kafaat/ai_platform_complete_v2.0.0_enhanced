// SAHOOL — features/offline_sync/data/outbox_record.dart
// سجلّ عمليّة مؤجَّلة كما تُحفَظ في الصندوق المشفّر: العمليّة نفسها + مالكها
// (المستخدم والمستأجِر من JWT لحظة الإيداع) + حالة الإرسال. المالك جزء من السجلّ
// لا من اسم الصندوق، فتبقى عمليّات مستخدمٍ خرج محفوظةً ومقفلةً عليه: لا تُرسَل إلّا
// حين يكون هو صاحب الجلسة.
import 'dart:convert';

import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

/// هويّة الجلسة التي تملك العمليّة. تُقرأ من رمز الوصول نفسه الذي يرسله ApiClient
/// (`sub` و`tenant_id` — services/auth/main.py:create_access_token).
class OutboxOwner {
  const OutboxOwner({required this.userId, required this.tenantId});

  final String userId;

  /// '' حين لا يحمل الرمز مستأجِراً (حساب بلا مستأجِر).
  final String tenantId;

  String get key => '$tenantId|$userId';

  /// يقرأ الهويّة من حمولة JWT. لا يتحقّق من الانتهاء: رمز منتهٍ ما زال يسمّي
  /// صاحبه، وApiClient يجدّده لنفس المستخدم قبل الإرسال. بلا `sub` ⇒ null.
  static OutboxOwner? fromAccessToken(String? token) {
    if (token == null || token.isEmpty) return null;
    try {
      final parts = token.split('.');
      if (parts.length != 3) return null;
      final payload = json.decode(
        utf8.decode(base64Url.decode(base64Url.normalize(parts[1]))),
      );
      if (payload is! Map) return null;
      final sub = payload['sub'];
      if (sub == null || sub.toString().isEmpty) return null;
      final tenant = payload['tenant_id'];
      return OutboxOwner(
        userId: sub.toString(),
        tenantId: tenant == null ? '' : tenant.toString(),
      );
    } catch (_) {
      return null;
    }
  }

  @override
  bool operator ==(Object other) => other is OutboxOwner && other.key == key;

  @override
  int get hashCode => key.hashCode;

  @override
  String toString() => 'OutboxOwner($key)';
}

/// حالة العمليّة كما تُعرَض للمستخدم (مشتقّة من السجلّ المحفوظ، لا تخمين):
enum OutboxDeliveryState {
  /// محفوظة على الجهاز ولم تُرسَل بعد.
  savedLocally,

  /// أُرسلت وأجاب الخادم بأنّه لم ينفّذها بعد (429/503/…) أو تعذّر الاتّصال قبل
  /// خروج الطلب ⇒ بانتظار المحاولة التالية بنفس المفتاح.
  pending,

  /// ربّما نفّذها الخادم ولم يصلنا تأكيده (مهلة، قطع بعد الإرسال، 5xx، تبدّل
  /// الجلسة أثناء الطلب) ⇒ تُطابَق بإعادة نفس المفتاح والحمولة في سياق مالكها.
  outcomeUnknown,

  /// أكّدها الخادم (2xx أو إعادة idempotent) ⇒ تُحذف من الصندوق.
  confirmed,

  /// تحتاج قرار المستخدم: رفضها الخادم، أو تعارض مفتاحها مع حمولة أخرى.
  needsAttention,
}

enum OutboxRecordState {
  /// بانتظار الإرسال (أو بانتظار انقضاء مهلة إعادة المحاولة).
  pending,

  /// رفضها الخادم بخطأ 4xx نهائيّ. تبقى ظاهرة للمستخدم برسالة الخادم حتى
  /// يعيدها أو يتجاهلها بنفسه — لا حذف صامت.
  rejected,
}

class OutboxRecord {
  const OutboxRecord({
    required this.id,
    required this.seq,
    required this.owner,
    required this.op,
    required this.createdAt,
    this.state = OutboxRecordState.pending,
    this.attempts = 0,
    this.lastAttemptAt,
    this.nextAttemptAt,
    this.lastErrorAr,
    this.rejectedStatus,
    this.rejectedMessageAr,
    this.rejectedAt,
    this.notBefore,
    this.outcomeUnknown = false,
    this.lastOutcome,
    this.conflictReason,
  });

  /// معرّف محلّيّ (UUIDv7) — مفتاح السجلّ في الصندوق.
  final String id;

  /// ترتيب الإيداع (FIFO). يزيد دائماً داخل الصندوق.
  final int seq;
  final OutboxOwner owner;
  final OutboxOp op;
  final DateTime createdAt;
  final OutboxRecordState state;
  final int attempts;
  final DateTime? lastAttemptAt;

  /// لا يُعاد الإرسال تلقائيّاً قبله (backoff). null ⇒ جاهز الآن.
  final DateTime? nextAttemptAt;

  /// سبب آخر فشل مؤقّت (انقطاع، 5xx) كما يُعرَض للمستخدم.
  final String? lastErrorAr;
  final int? rejectedStatus;
  final String? rejectedMessageAr;
  final DateTime? rejectedAt;

  /// موعد فرضه الخادم (Retry-After): لا إرسال قبله، لا تلقائيّاً ولا يدويّاً ولا
  /// عند عودة الشبكة. [nextAttemptAt] ≥ هذا دائماً.
  final DateTime? notBefore;

  /// محاولة سابقة ربّما نُفّذت ولم يصل تأكيدها — تبقى حتى يؤكّدها الخادم.
  final bool outcomeUnknown;

  /// اسم [OutboxOutcomeKind] لآخر محاولة (offline/retryLater/…).
  final String? lastOutcome;

  /// سبب 409 تعارض المفتاح (payload_mismatch) لعمليّة تحتاج تدخّلاً.
  final String? conflictReason;

  bool get isPending => state == OutboxRecordState.pending;
  bool get isRejected => state == OutboxRecordState.rejected;

  /// المفتاح محجوز على الخادم لحمولة أخرى — إعادة الحمولة نفسها عمياء.
  bool get isPayloadMismatch => conflictReason == 'payload_mismatch';

  OutboxDeliveryState get deliveryState {
    if (isRejected) return OutboxDeliveryState.needsAttention;
    if (outcomeUnknown) return OutboxDeliveryState.outcomeUnknown;
    if (attempts == 0) return OutboxDeliveryState.savedLocally;
    return OutboxDeliveryState.pending;
  }

  /// أقرب موعد تلقائيّ (الأبعد بين backoff وRetry-After). null ⇒ الآن.
  DateTime? get dueAt {
    final a = nextAttemptAt;
    final b = notBefore;
    if (a == null) return b;
    if (b == null) return a;
    return a.isAfter(b) ? a : b;
  }

  OutboxRecord copyWith({
    OutboxRecordState? state,
    int? attempts,
    DateTime? lastAttemptAt,
    DateTime? nextAttemptAt,
    bool clearNextAttempt = false,
    String? lastErrorAr,
    bool clearLastError = false,
    int? rejectedStatus,
    String? rejectedMessageAr,
    DateTime? rejectedAt,
    bool clearRejection = false,
    DateTime? notBefore,
    bool clearNotBefore = false,
    bool? outcomeUnknown,
    String? lastOutcome,
    String? conflictReason,
  }) => OutboxRecord(
    id: id,
    seq: seq,
    owner: owner,
    op: op,
    createdAt: createdAt,
    state: state ?? this.state,
    attempts: attempts ?? this.attempts,
    lastAttemptAt: lastAttemptAt ?? this.lastAttemptAt,
    nextAttemptAt: clearNextAttempt
        ? null
        : (nextAttemptAt ?? this.nextAttemptAt),
    lastErrorAr: clearLastError ? null : (lastErrorAr ?? this.lastErrorAr),
    rejectedStatus: clearRejection
        ? null
        : (rejectedStatus ?? this.rejectedStatus),
    rejectedMessageAr: clearRejection
        ? null
        : (rejectedMessageAr ?? this.rejectedMessageAr),
    rejectedAt: clearRejection ? null : (rejectedAt ?? this.rejectedAt),
    notBefore: clearNotBefore ? null : (notBefore ?? this.notBefore),
    outcomeUnknown: outcomeUnknown ?? this.outcomeUnknown,
    lastOutcome: lastOutcome ?? this.lastOutcome,
    conflictReason: clearRejection
        ? null
        : (conflictReason ?? this.conflictReason),
  );

  Map<String, dynamic> toJson() => {
    'v': 1,
    'id': id,
    'seq': seq,
    'user_id': owner.userId,
    'tenant_id': owner.tenantId,
    'kind': op.kind,
    'method': op.method,
    'path': op.path,
    'body': op.body,
    'idempotency_key': op.idempotencyKey,
    'field_id': op.fieldId,
    'label_ar': op.labelAr,
    'created_at': createdAt.toUtc().toIso8601String(),
    'state': state.name,
    'attempts': attempts,
    'last_attempt_at': lastAttemptAt?.toUtc().toIso8601String(),
    'next_attempt_at': nextAttemptAt?.toUtc().toIso8601String(),
    'last_error_ar': lastErrorAr,
    'rejected_status': rejectedStatus,
    'rejected_message_ar': rejectedMessageAr,
    'rejected_at': rejectedAt?.toUtc().toIso8601String(),
    'not_before': notBefore?.toUtc().toIso8601String(),
    'outcome_unknown': outcomeUnknown,
    'last_outcome': lastOutcome,
    'conflict_reason': conflictReason,
  };

  static DateTime? _date(Object? v) =>
      v is String ? DateTime.tryParse(v) : null;

  factory OutboxRecord.fromJson(Map<String, dynamic> j) {
    final body = j['body'];
    return OutboxRecord(
      id: j['id'] as String,
      seq: (j['seq'] as num).toInt(),
      owner: OutboxOwner(
        userId: j['user_id'] as String,
        tenantId: (j['tenant_id'] as String?) ?? '',
      ),
      op: OutboxOp(
        kind: j['kind'] as String,
        method: j['method'] as String,
        path: j['path'] as String,
        body: body is Map ? Map<String, dynamic>.from(body) : const {},
        idempotencyKey: j['idempotency_key'] as String,
        fieldId: j['field_id'] as String?,
        labelAr: j['label_ar'] as String?,
      ),
      createdAt: _date(j['created_at']) ?? DateTime.now().toUtc(),
      state: j['state'] == OutboxRecordState.rejected.name
          ? OutboxRecordState.rejected
          : OutboxRecordState.pending,
      attempts: (j['attempts'] as num?)?.toInt() ?? 0,
      lastAttemptAt: _date(j['last_attempt_at']),
      nextAttemptAt: _date(j['next_attempt_at']),
      lastErrorAr: j['last_error_ar'] as String?,
      rejectedStatus: (j['rejected_status'] as num?)?.toInt(),
      rejectedMessageAr: j['rejected_message_ar'] as String?,
      rejectedAt: _date(j['rejected_at']),
      notBefore: _date(j['not_before']),
      outcomeUnknown: j['outcome_unknown'] == true,
      lastOutcome: j['last_outcome'] as String?,
      conflictReason: j['conflict_reason'] as String?,
    );
  }

  String encode() => jsonEncode(toJson());

  static OutboxRecord decode(String raw) =>
      OutboxRecord.fromJson(jsonDecode(raw) as Map<String, dynamic>);
}
