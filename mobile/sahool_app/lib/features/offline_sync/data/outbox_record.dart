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

  bool get isPending => state == OutboxRecordState.pending;
  bool get isRejected => state == OutboxRecordState.rejected;

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
    );
  }

  String encode() => jsonEncode(toJson());

  static OutboxRecord decode(String raw) =>
      OutboxRecord.fromJson(jsonDecode(raw) as Map<String, dynamic>);
}
