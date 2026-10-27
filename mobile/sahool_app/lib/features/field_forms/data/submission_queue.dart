/// طابور الإرسال Offline-first (GAP-FIELD-FORMS-01 §8.7/§15).
///
/// كلّ عنصر يحمل instance_id ثابتًا يُولَّد مرّة واحدة عند الإدراج؛
/// retry لا يُنشئ instance_id جديدًا أبدًا (idempotency أمام الخادم).
library;

import 'dart:math';

import 'package:hive_flutter/hive_flutter.dart';

String _newInstanceId() {
  final rand = Random.secure();
  final suffix = List.generate(
    16,
    (_) => rand.nextInt(256),
  ).map((b) => b.toRadixString(16).padLeft(2, '0')).join();
  return 'ff-${DateTime.now().toUtc().microsecondsSinceEpoch}-$suffix';
}

/// المزوِّد الثابت في envelope.provider لكلّ ما يرسله هذا التطبيق.
const String kFieldFormsProvider = 'sahool-flutter';

/// عنصر طابور إرسال: الإجابات + هويّة النسخة + definition_sync_token، و**جسم
/// الإرسال مجمَّداً**: الخادم يجزّئ الجسم كاملاً (ومنه `submitted_at` و`server`)
/// ليقرّر الإعادة؛ جسمٌ يتغيّر بين المحاولات يُحجَر «مختلفاً» بدل أن يُعاد
/// (dedup_resolution.quarantine_divergent). لذلك تُحفظ هذه القيم مرّة عند الإدراج.
class QueuedSubmission {
  final String instanceId; // ثابت عبر كلّ retries
  final String tenantId;
  final String fieldId;
  final String assignmentId;
  final int assignmentRevision;
  final String formVersionId;
  final String schemaHash;
  final String? definitionSyncToken;
  final Map<String, Object?> answers;
  final DateTime localCreatedAt;
  final int attempts;

  /// وقت الإرسال المجمَّد عند الإدراج. null لعنصرٍ أُدرج قبل التجميد ⇒ يُستعمل
  /// [localCreatedAt] (ثابت أيضاً) فلا يتغيّر الجسم بين المحاولات.
  final DateTime? submittedAt;
  final String? provider;
  final String? server;

  /// المستخدم الذي جمع الإجابات. الخادم ينسب الإرسال لفاعل الـJWT، فلا يُرسَل
  /// عنصر مستخدمٍ تحت جلسة مستخدم آخر.
  final String? actorId;

  /// سبب التوقّف بعد رفضٍ متكرّر من الخادم (4xx). عنصر فاشل لا يُصرَّف تلقائيّاً
  /// ولا يُحذف بصمت: يُعرض للمستخدم ليعيد المحاولة أو يتخلّص منه صراحةً.
  final String? failedReason;

  /// لا تصريف تلقائيّ قبله (backoff + jitter). محفوظ في الصفّ فلا تمحوه إعادة
  /// التشغيل ولا عودة الشبكة.
  final DateTime? nextAttemptAt;

  /// موعد فرضه الخادم (Retry-After بثوانٍ أو بتاريخ HTTP) — لا إرسال قبله
  /// إطلاقاً، ولا من الشاشة.
  final DateTime? notBefore;

  /// محاولة ربّما نفّذها الخادم ولم يصل تأكيدها (مهلة استقبال، قطع بعد الإرسال،
  /// 5xx، تبدّل الجلسة أثناء الطلب). يبقى حتى يؤكّده الخادم بإعادة نفس الجسم.
  final bool outcomeUnknown;

  /// آخر فشل كان تعذّر الوصول إلى الخادم أصلاً — عودة الشبكة تتخطّى backoff هذا
  /// وحده (لا Retry-After ولا backoff سببه ردّ الخادم).
  final bool lastUnreachable;

  const QueuedSubmission({
    required this.instanceId,
    required this.tenantId,
    required this.fieldId,
    required this.assignmentId,
    required this.assignmentRevision,
    required this.formVersionId,
    required this.schemaHash,
    this.definitionSyncToken,
    required this.answers,
    required this.localCreatedAt,
    this.attempts = 0,
    this.submittedAt,
    this.provider,
    this.server,
    this.actorId,
    this.failedReason,
    this.nextAttemptAt,
    this.notBefore,
    this.outcomeUnknown = false,
    this.lastUnreachable = false,
  });

  bool get isFailed => failedReason != null;

  /// مستحقّ للتصريف التلقائيّ الآن؟ [afterReconnect]: عودة الشبكة تتخطّى backoff
  /// فشلٍ كان انقطاعاً فقط. Retry-After لا يتخطّاه شيء.
  bool isDue(DateTime now, {bool afterReconnect = false}) {
    final nb = notBefore;
    if (nb != null && nb.isAfter(now)) return false;
    final next = nextAttemptAt;
    if (next == null || !next.isAfter(now)) return true;
    return afterReconnect && lastUnreachable;
  }

  /// أقرب موعد تلقائيّ (الأبعد بين backoff وRetry-After).
  DateTime? get dueAt {
    final a = nextAttemptAt;
    final b = notBefore;
    if (a == null) return b;
    if (b == null) return a;
    return a.isAfter(b) ? a : b;
  }

  QueuedSubmission _copy({
    int? attempts,
    String? failedReason,
    bool clearFailure = false,
    DateTime? nextAttemptAt,
    DateTime? notBefore,
    bool clearSchedule = false,
    bool? outcomeUnknown,
    bool? lastUnreachable,
  }) => QueuedSubmission(
    instanceId: instanceId, // لا يتغيّر أبدًا
    tenantId: tenantId,
    fieldId: fieldId,
    assignmentId: assignmentId,
    assignmentRevision: assignmentRevision,
    formVersionId: formVersionId,
    schemaHash: schemaHash,
    definitionSyncToken: definitionSyncToken,
    answers: answers,
    localCreatedAt: localCreatedAt,
    attempts: attempts ?? this.attempts,
    submittedAt: submittedAt,
    provider: provider,
    server: server,
    actorId: actorId,
    failedReason: clearFailure ? null : (failedReason ?? this.failedReason),
    nextAttemptAt: clearSchedule
        ? nextAttemptAt
        : (nextAttemptAt ?? this.nextAttemptAt),
    notBefore: clearSchedule ? notBefore : (notBefore ?? this.notBefore),
    outcomeUnknown: outcomeUnknown ?? this.outcomeUnknown,
    lastUnreachable: lastUnreachable ?? this.lastUnreachable,
  );

  QueuedSubmission copyWithAttempts(int attempts) => _copy(attempts: attempts);

  Map<String, Object?> toJson() => {
    'instance_id': instanceId,
    'tenant_id': tenantId,
    'field_id': fieldId,
    'assignment_id': assignmentId,
    'assignment_revision': assignmentRevision,
    'form_version_id': formVersionId,
    'schema_hash': schemaHash,
    'definition_sync_token': definitionSyncToken,
    'answers': answers,
    'local_created_at': localCreatedAt.toUtc().toIso8601String(),
    'attempts': attempts,
    'submitted_at': submittedAt?.toUtc().toIso8601String(),
    'provider': provider,
    'server': server,
    'actor_id': actorId,
    'failed_reason': failedReason,
    'next_attempt_at': nextAttemptAt?.toUtc().toIso8601String(),
    'not_before': notBefore?.toUtc().toIso8601String(),
    'outcome_unknown': outcomeUnknown,
    'last_unreachable': lastUnreachable,
  };

  factory QueuedSubmission.fromJson(Map<String, Object?> json) {
    final submitted = json['submitted_at'];
    return QueuedSubmission(
      instanceId: json['instance_id']! as String,
      tenantId: json['tenant_id']! as String,
      fieldId: json['field_id']! as String,
      assignmentId: json['assignment_id']! as String,
      assignmentRevision: (json['assignment_revision']! as num).toInt(),
      formVersionId: json['form_version_id']! as String,
      schemaHash: json['schema_hash']! as String,
      definitionSyncToken: json['definition_sync_token'] as String?,
      answers: Map<String, Object?>.from(json['answers'] as Map? ?? {}),
      localCreatedAt: DateTime.parse(json['local_created_at']! as String),
      attempts: (json['attempts'] as num? ?? 0).toInt(),
      submittedAt: submitted is String ? DateTime.parse(submitted) : null,
      provider: json['provider'] as String?,
      server: json['server'] as String?,
      actorId: json['actor_id'] as String?,
      failedReason: json['failed_reason'] as String?,
      nextAttemptAt: _date(json['next_attempt_at']),
      notBefore: _date(json['not_before']),
      outcomeUnknown: json['outcome_unknown'] == true,
      lastUnreachable: json['last_unreachable'] == true,
    );
  }

  static DateTime? _date(Object? v) =>
      v is String ? DateTime.tryParse(v) : null;

  /// envelope الإرسال الكامل (§8/دفعة العقود) — هويّة النسخة تُعاد كما هي.
  ///
  /// القيم المجمَّدة في العنصر تغلب دائماً؛ [provider]/[server]/[submittedAt]
  /// احتياط لعناصر أُدرجت قبل التجميد فقط. النتيجة متطابقة بايتاً بين المحاولات.
  Map<String, Object?> buildEnvelope({
    String? provider,
    String? server,
    DateTime? submittedAt,
  }) => {
    'provider': this.provider ?? provider ?? kFieldFormsProvider,
    'server': this.server ?? server ?? '',
    'instance_id': instanceId,
    'submitted_at': (this.submittedAt ?? submittedAt ?? localCreatedAt)
        .toUtc()
        .toIso8601String(),
    'local_created_at': localCreatedAt.toUtc().toIso8601String(),
    'field_id': fieldId,
    'form_version_id': formVersionId,
    'schema_hash': schemaHash,
    'assignment_revision': assignmentRevision,
    'definition_sync_token': definitionSyncToken,
    'answers': answers,
  };
}

class SubmissionQueue {
  static const String boxName = 'field_forms_queue';

  final Box<dynamic> _box;

  SubmissionQueue(this._box);

  static Future<SubmissionQueue> open() async =>
      SubmissionQueue(await Hive.openBox<dynamic>(boxName));

  /// إدراج جديد — يولّد instance_id ويجمّد جسم الإرسال هنا فقط، مرّة واحدة.
  Future<QueuedSubmission> enqueue({
    required String tenantId,
    required String fieldId,
    required String assignmentId,
    required int assignmentRevision,
    required String formVersionId,
    required String schemaHash,
    String? definitionSyncToken,
    required Map<String, Object?> answers,
    String? server,
    String provider = kFieldFormsProvider,
    String? actorId,
    DateTime? now,
  }) async {
    final at = (now ?? DateTime.now()).toUtc();
    final item = QueuedSubmission(
      instanceId: _newInstanceId(),
      tenantId: tenantId,
      fieldId: fieldId,
      assignmentId: assignmentId,
      assignmentRevision: assignmentRevision,
      formVersionId: formVersionId,
      schemaHash: schemaHash,
      definitionSyncToken: definitionSyncToken,
      answers: Map<String, Object?>.from(answers),
      localCreatedAt: at,
      submittedAt: at,
      provider: provider,
      server: (server == null || server.isEmpty) ? null : server,
      actorId: actorId,
    );
    await _box.put(item.instanceId, item.toJson());
    return item;
  }

  /// تسجيل محاولة فاشلة: يزيد العدّاد ولا يمسّ instance_id ولا الجسم، ويحفظ
  /// موعد المحاولة التالية (و[notBefore] من Retry-After) في الصفّ نفسه.
  /// [outcomeUnknown] يُضاف ولا يُمحى: محاولة سابقة غير مؤكَّدة تبقى كذلك.
  Future<QueuedSubmission> markRetry(
    QueuedSubmission item, {
    DateTime? nextAttemptAt,
    DateTime? notBefore,
    bool outcomeUnknown = false,
    bool unreachable = false,
  }) async {
    final updated = item._copy(
      attempts: item.attempts + 1,
      clearSchedule: true,
      nextAttemptAt: nextAttemptAt,
      notBefore: notBefore,
      outcomeUnknown: item.outcomeUnknown || outcomeUnknown,
      lastUnreachable: unreachable,
    );
    await _box.put(updated.instanceId, updated.toJson());
    return updated;
  }

  /// ردٌّ وصل (أو أُلغي الطلب) بعد تبدّل الجلسة: لا حذف — يبقى بجسمه ومعرّفه
  /// «نتيجته غير مؤكَّدة» ويُطابَق حين يعود صاحبه (الخادم يعيد نتيجته المخزّنة).
  Future<QueuedSubmission> markOutcomeUnknown(QueuedSubmission item) async {
    final updated = item._copy(
      attempts: item.attempts + 1,
      clearSchedule: true,
      notBefore: item.notBefore,
      outcomeUnknown: true,
      lastUnreachable: false,
    );
    await _box.put(updated.instanceId, updated.toJson());
    return updated;
  }

  /// العنصر كما هو محفوظ الآن (null ⇒ أُزيل أو تعذّر فكّه).
  QueuedSubmission? byId(String instanceId) => _decode(_box.get(instanceId));

  /// يوقف التصريف التلقائيّ لعنصر رفضه الخادم مراراً — يبقى محفوظاً ومرئيّاً.
  Future<QueuedSubmission> markFailed(
    QueuedSubmission item,
    String reason,
  ) async {
    final updated = item._copy(failedReason: reason);
    await _box.put(updated.instanceId, updated.toJson());
    return updated;
  }

  /// يعيد عنصراً فاشلاً إلى الطابور (بطلب صريح من المستخدم) بالجسم نفسه.
  /// يمحو backoff لا Retry-After.
  Future<QueuedSubmission> requeue(QueuedSubmission item) async {
    final updated = item._copy(
      attempts: 0,
      clearFailure: true,
      clearSchedule: true,
      notBefore: item.notBefore,
    );
    await _box.put(updated.instanceId, updated.toJson());
    return updated;
  }

  Future<void> remove(String instanceId) => _box.delete(instanceId);

  /// كلّ العناصر (معلّقة وفاشلة)، الأقدم أوّلاً، مرشّحةً بالمستأجِر/المستخدم.
  ///
  /// مع [tenantId] تُعاد عناصر ذلك المستأجِر فقط: الخادم يأخذ المستأجِر من
  /// الـJWT، فإرسال عنصرٍ لمستأجِر آخر يُسقطه في حجر مستأجِرٍ خاطئ. ومع
  /// [actorId] تُستثنى عناصر مستخدمٍ آخر (عناصر قديمة بلا فاعل تبقى ظاهرة).
  List<QueuedSubmission> _all({String? tenantId, String? actorId}) {
    final result = <QueuedSubmission>[];
    for (final key in _box.keys) {
      final item = _decode(_box.get(key));
      // صفّ لا يُفكّ لا يُسقط القائمة كلّها؛ يبقى على القرص ويُعَدّ في
      // [unreadableCount] فلا يختفي من العرض كأنّه أُرسل.
      if (item == null) continue;
      if (tenantId != null && item.tenantId != tenantId) continue;
      if (actorId != null && item.actorId != null && item.actorId != actorId) {
        continue;
      }
      result.add(item);
    }
    result.sort((a, b) => a.localCreatedAt.compareTo(b.localCreatedAt));
    return result;
  }

  static QueuedSubmission? _decode(Object? raw) {
    if (raw is! Map) return null;
    try {
      return QueuedSubmission.fromJson(Map<String, Object?>.from(raw));
    } catch (_) {
      return null;
    }
  }

  /// صفوف محفوظة تعذّر فكّها (تالفة أو من إصدار أحدث). لا تُحذف ولا تُرسَل؛
  /// تُعرض عدداً كي لا يُقال «لا شيء بانتظار الإرسال» وهي على الجهاز.
  int unreadableCount() =>
      _box.keys.where((key) => _decode(_box.get(key)) == null).length;

  /// العناصر المعلّقة القابلة للتصريف، الأقدم أوّلاً (بلا الفاشلة).
  List<QueuedSubmission> pending({String? tenantId, String? actorId}) => _all(
    tenantId: tenantId,
    actorId: actorId,
  ).where((i) => !i.isFailed).toList();

  /// العناصر التي توقّف إرسالها بعد رفضٍ متكرّر — تُعرض ولا تُحذف بصمت.
  List<QueuedSubmission> failed({String? tenantId, String? actorId}) => _all(
    tenantId: tenantId,
    actorId: actorId,
  ).where((i) => i.isFailed).toList();

  Future<void> clearAll() => _box.clear();
}
