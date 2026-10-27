// SAHOOL — features/offline_sync/data/operation_ledger.dart
// سجلّ عمليّات الإنشاء المعلّقة (UI-M3 / D1): تسوية العمليّة بدل تدوير المفتاح.
//
// المشكلة: إنشاء حقل/موسم/جدول ريّ ثمّ انقطاع الردّ بعد التزام الخادم ⇒ النتيجة
// مجهولة. الإصلاح السابق كان يولّد مفتاحاً جديداً إن عدّل المستخدم النموذج ثمّ أعاد
// الحفظ — فينشئ الخادم سجلّاً ثانياً بجانب الأوّل المُلتزَم (تكرار صامت). والأقدم كان
// يرسل الحمولة المعدّلة بالمفتاح القديم فيعيد الخادم النتيجة القديمة نجاحاً لها.
//
// العقد هنا:
//  • أوّل إرسال يُنشئ **سجلّ عمليّة** ثابتاً: operation_id (= Idempotency-Key)،
//    المالك (tenant_id + user_id من رمز الوصول — لا الرمز نفسه)، نوع العمليّة،
//    الحمولة الأصليّة وبصمتها القانونيّة، والحالة. يُكتب على القرص **قبل** الشبكة؛
//    فشل الكتابة ⇒ لا طلب إطلاقاً (R04).
//  • التخزين: صندوق Hive مشفّر بالآليّة نفسها لصندوق الإرسال
//    (HiveOutboxStore.openEncryptedBox) بصندوقه ومفتاحه — لا طبقة ثالثة.
//  • النموذج يحتفظ بمسودّة منفصلة. مهلة/5xx/انقطاع/إغلاق الشاشة لا تدوّر المفتاح
//    ولا تستبدل الحمولة المرسلة. المسودّة المعدّلة تُحفَظ وتُعرَض فروقها ولا تُرسَل
//    ضمن إعادة الإنشاء.
//  • «استعادة نتيجة المحاولة السابقة» = نفس المفتاح ونفس الحمولة الأصليّة، بعد
//    استعلام مصادَق قائم (GET /api/v1/commands/{id}) إن أمكن. النجاح يربط النموذج
//    بالمعرّف الحقيقيّ؛ أيّ تعديل لاحق عمليّة تحديث مستقلّة بعد تأكيد المستخدم.
//  • 409 لا يقود أبداً إلى مفتاح جديد (OD-2): payload_mismatch ⇒ needs_attention؛
//    in_progress ⇒ تبقى النتيجة مجهولة «تحقّق لاحقاً»؛ 409 بلا سبب ⇒ رسالة الاستعادة.
//  • فشلٌ مثبت قبل التنفيذ (4xx تحقّق/صلاحيّة، أو 409 أعمال برمز `code` يرتدّ معه
//    إدراج الأمر) يعيد السجلّ إلى saved_locally: يجوز تصحيح الحمولة **بالمفتاح نفسه**
//    لأنّ الخادم لم يحفظ شيئاً له. المهلة وقطع الاتّصال ليسا هذا الإثبات.
//  • بعد مدّة الاحتفاظ الموثَّقة لا يُعاد الطلب آليّاً: not_found ⇒
//    needs_reconciliation (R13) — مراجعة بشريّة، لا إنشاء بمفتاح آخر.
//  • إعادة التشغيل تستعيد العمليّات المفتوحة لنفس المالك فقط.
import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/network/api_client.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/core/utils/ids.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'outbox_record.dart' show OutboxOwner;
import 'outbox_store.dart';

// ── نصوص الواجهة ────────────────────────────────────────────────────

/// النتيجة مجهولة (مهلة/انقطاع/5xx بعد الإرسال).
const String kOperationUnknownAr =
    'لم نتأكد من نتيجة الحفظ. احتفظنا بطلبك وتعديلاتك. '
    'تحقّق من نتيجة المحاولة السابقة قبل إنشاء سجل آخر';

/// 409 على إنشاء (OD-2): لا مسار «أنشئ من جديد».
const String kOperationConflictAr =
    'هذه العملية أُرسلت سابقاً بنفس المعرّف. استعِد نتيجة المحاولة السابقة '
    'أولاً، ولا تُنشئ سجلاً جديداً.';

/// 409 بسبب in_progress.
const String kOperationInProgressAr =
    'المحاولة السابقة ما زالت قيد المعالجة على الخادم. تحقّق من نتيجتها مرّة '
    'أخرى بعد قليل، ولا تُنشئ سجلاً جديداً.';

/// انقضت مدّة الاحتفاظ ولم يُعثَر على الأمر (R13).
const String kOperationReconcileAr =
    'تعذّر التأكّد من نتيجة المحاولة السابقة: انقضت مدّة احتفاظ الخادم بها. '
    'راجع القائمة؛ إن وجدت السجلّ فلا تُنشئه مرّة أخرى، وإن لم تجده فأغلق '
    'هذه العمليّة ثمّ أنشئه بقرارك.';

/// زرّ الاستعادة (نفس المفتاح ونفس الحمولة الأصليّة).
const String kRecoverActionAr = 'استعادة نتيجة المحاولة السابقة';
const String kCheckAgainActionAr = 'تحقّق مرّة أخرى';

/// زرّ إغلاق عمليّة بعد مراجعة بشريّة (needs_reconciliation) أو لم تُنفَّذ قطعاً.
const String kDismissReconciledAr = 'راجعتُ القائمة — أغلق هذه العمليّة';

/// مدّة احتفاظ الخادم بنتيجة المفتاح كما يفترضها العميل. الخادم اليوم لا يحذف صفوف
/// `commands` (لا مهمّة تنظيف — command_store.py)، فأيّ قيمة آمنة؛ إن وثّق الخادم
/// مدّةً (D4) وجب أن تكون هذه أقصر منها أو مساوية.
const Duration kServerIdempotencyRetention = Duration(hours: 24);

// ── الحالات والسجلّ ─────────────────────────────────────────────────

enum OperationState {
  /// محفوظة على الجهاز ولم يُنفِّذها الخادم قطعاً (لم تُرسَل، أو رُفضت قبل التنفيذ).
  /// الحالة الوحيدة التي يجوز فيها تصحيح الحمولة — بالمفتاح نفسه.
  savedLocally('saved_locally'),

  /// كُتبت قبل الإرسال ولم يصل ردّ بعد (قتلٌ هنا ⇒ مجهولة عند الاستعادة).
  pending('pending'),

  /// أُرسلت ولا نعرف هل التزم الخادم (مهلة، انقطاع، 5xx، in_progress).
  outcomeUnknown('outcome_unknown'),

  /// أكّد الخادم المورد.
  confirmed('confirmed'),

  /// تعارض مفتاح (409 payload_mismatch أو بلا سبب) — يحتاج استعادة لا إعادة إنشاء.
  needsAttention('needs_attention'),

  /// انقضت مدّة الاحتفاظ دون دليل — مراجعة بشريّة (R13).
  needsReconciliation('needs_reconciliation');

  const OperationState(this.wire);
  final String wire;

  static OperationState? parse(Object? v) {
    for (final s in values) {
      if (s.wire == v) return s;
    }
    return null;
  }
}

/// أسباب 409 الثابتة من الخادم (D4). غيابها مقبول.
abstract final class ConflictReason {
  static const payloadMismatch = 'payload_mismatch';
  static const inProgress = 'in_progress';
}

@immutable
class OperationRecord {
  const OperationRecord({
    required this.operationId,
    required this.owner,
    required this.kind,
    required this.scope,
    required this.method,
    required this.path,
    required this.payload,
    required this.digest,
    required this.state,
    required this.createdAt,
    required this.updatedAt,
    this.attempts = 0,
    this.draft,
    this.context = const {},
    this.resourceId,
    this.lastErrorAr,
    this.lastStatus,
    this.conflictReason,
  });

  /// = Idempotency-Key. لا يتغيّر طوال عمر العمليّة.
  final String operationId;
  final OutboxOwner owner;

  /// نوع ثابت: 'field.create' · 'season.create' · 'irrigation_schedule.create'.
  final String kind;

  /// نطاق داخل النوع (مثل field_id للموسم)؛ '' ⇒ بلا نطاق.
  final String scope;
  final String method;
  final String path;

  /// الحمولة المرسلة (الأصليّة). لا تُستبدَل إلّا في saved_locally.
  final Map<String, dynamic> payload;

  /// بصمة التمثيل القانونيّ للحمولة (ترتيب المفاتيح لا يهمّ).
  final String digest;
  final OperationState state;
  final DateTime createdAt;
  final DateTime updatedAt;
  final int attempts;

  /// آخر مسودّة عدّلها المستخدم بعد الإرسال (لا تُرسَل ضمن الإنشاء).
  final Map<String, dynamic>? draft;

  /// بيانات خاصّة بالمسار ليست جزءاً من الحمولة (مثل محصول الموسم التالي).
  final Map<String, dynamic> context;
  final String? resourceId;
  final String? lastErrorAr;
  final int? lastStatus;
  final String? conflictReason;

  IdempotencyKey get key => IdempotencyKey(operationId);

  /// لم تُحسَم بعد (يجب أن تظهر للمستخدم قبل إنشاء سجلّ آخر).
  bool get isOpen => state != OperationState.confirmed;

  /// قد يكون الخادم نفّذها — لا يُقبل تصحيح الحمولة.
  bool get mayHaveExecuted => state != OperationState.savedLocally;

  /// فروق المسودّة عن الحمولة المرسلة.
  List<PayloadChange> get draftChanges =>
      draft == null ? const [] : payloadDiff(payload, draft!);

  OperationRecord copyWith({
    Map<String, dynamic>? payload,
    String? digest,
    OperationState? state,
    DateTime? updatedAt,
    int? attempts,
    Map<String, dynamic>? draft,
    bool clearDraft = false,
    Map<String, dynamic>? context,
    String? resourceId,
    String? lastErrorAr,
    bool clearError = false,
    int? lastStatus,
    String? conflictReason,
    bool clearConflict = false,
  }) => OperationRecord(
    operationId: operationId,
    owner: owner,
    kind: kind,
    scope: scope,
    method: method,
    path: path,
    payload: payload ?? this.payload,
    digest: digest ?? this.digest,
    state: state ?? this.state,
    createdAt: createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
    attempts: attempts ?? this.attempts,
    draft: clearDraft ? null : (draft ?? this.draft),
    context: context ?? this.context,
    resourceId: resourceId ?? this.resourceId,
    lastErrorAr: clearError ? null : (lastErrorAr ?? this.lastErrorAr),
    lastStatus: clearError ? null : (lastStatus ?? this.lastStatus),
    conflictReason: clearConflict
        ? null
        : (conflictReason ?? this.conflictReason),
  );

  Map<String, dynamic> toJson() => {
    'v': 1,
    'operation_id': operationId,
    'tenant_id': owner.tenantId,
    'actor_id': owner.userId,
    'kind': kind,
    'scope': scope,
    'method': method,
    'path': path,
    'payload': payload,
    'digest': digest,
    'state': state.wire,
    'created_at': createdAt.toUtc().toIso8601String(),
    'updated_at': updatedAt.toUtc().toIso8601String(),
    'attempts': attempts,
    'draft': draft,
    'context': context,
    'resource_id': resourceId,
    'last_error_ar': lastErrorAr,
    'last_status': lastStatus,
    'conflict_reason': conflictReason,
  };

  factory OperationRecord.fromJson(Map<String, dynamic> j) {
    final state = OperationState.parse(j['state']);
    if (state == null) throw FormatException('unknown state ${j['state']}');
    final payload = Map<String, dynamic>.from(j['payload'] as Map);
    final draft = j['draft'];
    final ctx = j['context'];
    return OperationRecord(
      operationId: j['operation_id'] as String,
      owner: OutboxOwner(
        userId: j['actor_id'] as String,
        tenantId: (j['tenant_id'] as String?) ?? '',
      ),
      kind: j['kind'] as String,
      scope: (j['scope'] as String?) ?? '',
      method: j['method'] as String,
      path: j['path'] as String,
      payload: payload,
      digest: (j['digest'] as String?) ?? payloadDigest(payload),
      state: state,
      createdAt: DateTime.parse(j['created_at'] as String),
      updatedAt: DateTime.parse(j['updated_at'] as String),
      attempts: (j['attempts'] as num?)?.toInt() ?? 0,
      draft: draft is Map ? Map<String, dynamic>.from(draft) : null,
      context: ctx is Map ? Map<String, dynamic>.from(ctx) : const {},
      resourceId: j['resource_id'] as String?,
      lastErrorAr: j['last_error_ar'] as String?,
      lastStatus: (j['last_status'] as num?)?.toInt(),
      conflictReason: j['conflict_reason'] as String?,
    );
  }

  String encode() => jsonEncode(toJson());
  static OperationRecord decode(String raw) =>
      OperationRecord.fromJson(jsonDecode(raw) as Map<String, dynamic>);
}

// ── البصمة والفروق ──────────────────────────────────────────────────

Object? _canonical(Object? v) {
  if (v is Map) {
    final keys = v.keys.map((k) => k.toString()).toList()..sort();
    return {for (final k in keys) k: _canonical(v[k])};
  }
  if (v is Iterable) return [for (final e in v) _canonical(e)];
  if (v is num || v is String || v is bool || v == null) return v;
  return v.toString();
}

/// JSON قانونيّ: مفاتيح مرتّبة تكراريّاً.
String canonicalJson(Object? v) => jsonEncode(_canonical(v));

/// بصمة FNV-1a بطول 64 بتّاً للتمثيل القانونيّ (مقارنة محلّيّة، لا أمان).
String payloadDigest(Object? payload) {
  var h = BigInt.parse('cbf29ce484222325', radix: 16);
  final prime = BigInt.parse('100000001b3', radix: 16);
  final mask = (BigInt.one << 64) - BigInt.one;
  for (final b in utf8.encode(canonicalJson(payload))) {
    h = ((h ^ BigInt.from(b)) * prime) & mask;
  }
  return 'fnv1a64:${h.toRadixString(16).padLeft(16, '0')}';
}

@immutable
class PayloadChange {
  const PayloadChange(this.key, this.before, this.after);
  final String key;
  final Object? before;
  final Object? after;
}

/// فروق المفاتيح العليا بين الحمولة المرسلة والمسودّة.
List<PayloadChange> payloadDiff(
  Map<String, dynamic> sent,
  Map<String, dynamic> draft,
) {
  final keys = {...sent.keys, ...draft.keys}.toList()..sort();
  return [
    for (final k in keys)
      if (canonicalJson(sent[k]) != canonicalJson(draft[k]))
        PayloadChange(k, sent[k], draft[k]),
  ];
}

// ── التخزين ─────────────────────────────────────────────────────────

abstract class OperationStore {
  /// كلّ السجلّات (كلّ المالكين).
  List<OperationRecord> get records;
  Future<void> put(OperationRecord record);
  Future<void> remove(String operationId);
}

/// مفتاح تشفير صندوق العمليّات — مفتاح مستقلّ عن مفتاح صندوق الإرسال كي لا يُولَّد
/// مفتاحٌ مشترك جديد فوق صندوقٍ قائم لم يُفحَص وجوده.
class SecureOperationKeyStore implements OutboxKeyStore {
  const SecureOperationKeyStore();

  static const _storage = FlutterSecureStorage(
    aOptions: AndroidOptions(encryptedSharedPreferences: true),
  );
  static const storageKey = 'sahool_pending_operations_key_v1';

  @override
  Future<String?> read() => _storage.read(key: storageKey);

  @override
  Future<void> write(String base64Key) =>
      _storage.write(key: storageKey, value: base64Key);
}

class HiveOperationStore implements OperationStore {
  HiveOperationStore._(this._box) {
    for (final key in _box.keys) {
      final raw = _box.get(key);
      if (raw == null) continue;
      try {
        final r = OperationRecord.decode(raw);
        _records[r.operationId] = r;
      } catch (_) {
        // سجلّ لا يُفكّ يبقى على القرص كما هو (لا حذف صامت).
      }
    }
  }

  static const boxName = 'sahool_pending_operations_v1';

  final Box<String> _box;
  final Map<String, OperationRecord> _records = {};

  /// يفتح الصندوق المشفّر. يرمي [OutboxStoreException] عند التعذّر.
  static Future<HiveOperationStore> openEncrypted({
    OutboxKeyStore keys = const SecureOperationKeyStore(),
    String name = boxName,
  }) async => HiveOperationStore._(
    await HiveOutboxStore.openEncryptedBox(keys: keys, name: name),
  );

  @override
  List<OperationRecord> get records => _records.values.toList();

  @override
  Future<void> put(OperationRecord record) async {
    await _box.put(record.operationId, record.encode());
    _records[record.operationId] = record;
  }

  @override
  Future<void> remove(String operationId) async {
    await _box.delete(operationId);
    _records.remove(operationId);
  }

  Future<void> close() => _box.close();
}

/// استعلام مصادَق قائم عن أمرٍ بمفتاحه: true موجود · false غير موجود · null تعذّر.
typedef CommandLookup = Future<bool?> Function(String operationId);

/// GET /api/v1/commands/{command_id} (routers/commands.py) — RLS المستأجِر.
/// يردّ `{found: true}` أو 404؛ لا يعيد النتيجة نفسها، فالاستعادة تعيد الطلب الأصليّ
/// بنفس المفتاح ليُعيد الخادم النتيجة المخزّنة.
class CommandStatusApi {
  CommandStatusApi([ApiClient? client])
    : _client = client ?? ApiClient.instance;
  final ApiClient _client;

  Future<bool?> exists(String operationId) async {
    try {
      await _client.get('/api/v1/commands/${Uri.encodeComponent(operationId)}');
      return true;
    } on ApiException catch (e) {
      if (e.isNotFound) return false;
      return null;
    }
  }
}

typedef OperationStoreOpener = Future<OperationStore> Function();
typedef OperationOwnerReader = OutboxOwner? Function();

/// فشل الكتابة المحلّيّة قبل الإرسال — لا طلب شبكة.
class OperationStoreUnavailable implements Exception {
  const OperationStoreUnavailable([this.cause]);
  final Object? cause;
  @override
  String toString() => 'OperationStoreUnavailable($cause)';
}

class OperationLedger {
  OperationLedger({
    required OperationStoreOpener openStore,
    required OperationOwnerReader currentOwner,
    this.lookup,
    DateTime Function()? clock,
    this.retention = kServerIdempotencyRetention,
  }) : _openStore = openStore,
       _currentOwner = currentOwner,
       _clock = clock ?? DateTime.now;

  /// الإنتاج: صندوق Hive مشفّر، والمالك من مطالبات رمز الوصول (sub/tenant_id).
  static final OperationLedger shared = OperationLedger(
    openStore: HiveOperationStore.openEncrypted,
    currentOwner: () => OutboxOwner.fromAccessToken(AuthService.instance.token),
    lookup: (id) => CommandStatusApi().exists(id),
  );

  final OperationStoreOpener _openStore;
  final OperationOwnerReader _currentOwner;
  final CommandLookup? lookup;
  final DateTime Function() _clock;
  final Duration retention;

  OperationStore? _store;
  Future<OperationStore>? _opening;

  DateTime now() => _clock().toUtc();
  OutboxOwner? currentOwner() => _currentOwner();

  Future<OperationStore> _ensure() {
    final s = _store;
    if (s != null) return Future.value(s);
    return _opening ??= () async {
      try {
        final opened = await _openStore();
        _store = opened;
        return opened;
      } catch (e) {
        _opening = null; // الاستعمال التالي يعيد المحاولة
        throw OperationStoreUnavailable(e);
      }
    }();
  }

  /// آخر عمليّة مفتوحة للمالك الحاليّ بهذا النوع والنطاق. لا جلسة ⇒ null.
  Future<OperationRecord?> openFor(String kind, {String scope = ''}) async {
    final owner = _currentOwner();
    if (owner == null) return null;
    final OperationStore store;
    try {
      store = await _ensure();
    } on OperationStoreUnavailable {
      return null;
    }
    OperationRecord? latest;
    for (final r in store.records) {
      if (r.owner != owner || r.kind != kind || r.scope != scope) continue;
      if (!r.isOpen) continue;
      if (latest == null || r.createdAt.isAfter(latest.createdAt)) latest = r;
    }
    return latest;
  }

  /// يكتب السجلّ. يرمي [OperationStoreUnavailable] إن تعذّر.
  Future<OperationRecord> put(OperationRecord r) async {
    final store = await _ensure();
    final stamped = r.copyWith(updatedAt: now());
    try {
      await store.put(stamped);
    } catch (e) {
      throw OperationStoreUnavailable(e);
    }
    return stamped;
  }

  Future<void> remove(OperationRecord r) async {
    final store = await _ensure();
    await store.remove(r.operationId);
  }

  bool retentionElapsed(OperationRecord r) =>
      now().difference(r.createdAt.toUtc()) > retention;
}

// ── تسوية مسار إنشاء واحد ───────────────────────────────────────────

/// الإرسال الفعليّ: الحمولة + المفتاح ⇒ ردّ الخادم.
typedef OperationSend =
    Future<Map<String, dynamic>> Function(
      Map<String, dynamic> payload,
      IdempotencyKey key,
    );

sealed class CreateOutcome {
  const CreateOutcome();
}

/// أكّد الخادم المورد. [pendingEdits] فروق المسودّة التي لم تُرسَل (تحديث مستقلّ
/// بعد تأكيد المستخدم).
class CreateConfirmed extends CreateOutcome {
  const CreateConfirmed(this.record, this.result);
  final OperationRecord record;
  final Map<String, dynamic> result;
  List<PayloadChange> get pendingEdits => record.draftChanges;
}

/// النتيجة غير محسومة: outcome_unknown / needs_attention / needs_reconciliation.
class CreateUnconfirmed extends CreateOutcome {
  const CreateUnconfirmed(this.record);
  final OperationRecord record;

  OperationState get state => record.state;
  bool get inProgress => record.conflictReason == ConflictReason.inProgress;
  List<PayloadChange> get draftChanges => record.draftChanges;

  String get messageAr => switch (record.state) {
    OperationState.needsReconciliation => kOperationReconcileAr,
    OperationState.needsAttention => kOperationConflictAr,
    _ when inProgress => kOperationInProgressAr,
    _ => kOperationUnknownAr,
  };

  String get actionLabelAr => inProgress ? kCheckAgainActionAr : kRecoverActionAr;

  /// إغلاق يدويّ متاح فقط بعد انقضاء الاحتفاظ (مراجعة بشريّة).
  bool get canDismiss => record.state == OperationState.needsReconciliation;
}

/// رفضٌ مثبت قبل التنفيذ: يجوز التصحيح، والمفتاح نفسه يبقى للعمليّة.
class CreateRejected extends CreateOutcome {
  const CreateRejected(this.record, this.error);
  final OperationRecord record;
  final ApiException error;
}

/// لم يُحفظ شيء محلّيّاً ⇒ لم يُرسَل شيء.
class CreateNotSaved extends CreateOutcome {
  const CreateNotSaved(this.messageAr);
  final String messageAr;
}

/// نداء أثناء نداء جارٍ — تجاهل.
class CreateBusy extends CreateOutcome {
  const CreateBusy();
}

const String kOperationNotSavedAr =
    'تعذّر حفظ الطلب على الجهاز، فلم يُرسَل شيء. أعد المحاولة.';
const String kOperationNoSessionAr =
    'لا جلسة نشطة لهذا الحساب، فلم يُرسَل شيء. سجّل الدخول ثمّ أعد المحاولة.';

/// يحدّد سبب 409: رمز D4 إن وُجد، وإلّا نصوص `_idempotent` الحاليّة
/// (main.py)، وإلّا null.
String? idempotencyConflictReason(ApiException e) {
  if (e.statusCode != 409) return null;
  String? reason;
  final d = e.detail;
  if (d is Map) reason = (d['reason'] ?? d['code'])?.toString();
  final cause = e.cause;
  if (reason == null && cause is DioException) {
    final body = cause.response?.data;
    if (body is Map) reason = (body['reason'] ?? body['code'])?.toString();
  }
  if (reason == ConflictReason.payloadMismatch ||
      reason == ConflictReason.inProgress) {
    return reason;
  }
  if (reason != null && reason.contains('idempot')) {
    return ConflictReason.payloadMismatch;
  }
  if (d is String) {
    if (d.contains('قيد المعالجة')) return ConflictReason.inProgress;
    if (d.contains('بحمولةٍ مختلفة') || d.contains('بحمولة مختلفة')) {
      return ConflictReason.payloadMismatch;
    }
  }
  return null;
}

/// 409 أعمال برمز (اسم مكرّر، تداخل…): يُرفع داخل عمل الأمر فيرتدّ إدراجه معه.
bool _isBusinessConflict(ApiException e) {
  final d = e.detail;
  return e.statusCode == 409 &&
      d is Map &&
      d['code'] is String &&
      idempotencyConflictReason(e) == null;
}

/// رفضٌ قبل التنفيذ بحكم العقد (تحقّق/صلاحيّة/غير موجود/جلسة).
bool _provenNotExecuted(ApiException e) => switch (e.kind) {
  ApiErrorKind.badRequest ||
  ApiErrorKind.validation ||
  ApiErrorKind.notFound ||
  ApiErrorKind.forbidden ||
  ApiErrorKind.unauthorized => true,
  _ => false,
};

/// تسوية مسار إنشاء واحد (نموذج واحد). يملكه Cubit/حالة الشاشة.
class CreateOperation {
  CreateOperation({
    required this.ledger,
    required this.kind,
    this.scope = '',
    required this.method,
    required this.path,
    required this.send,
  });

  final OperationLedger ledger;
  final String kind;
  final String scope;
  final String method;
  final String path;
  final OperationSend send;

  OperationRecord? _record;
  OperationRecord? get record => _record;
  bool _busy = false;
  bool get busy => _busy;

  /// يستعيد عمليّة مفتوحة للمالك الحاليّ (بعد إعادة التشغيل أو إعادة فتح الشاشة).
  /// saved_locally يُستعاد صامتاً (لم يُنفَّذ — مفتاحه يُعاد للإرسال التالي).
  Future<CreateOutcome?> restore() async {
    final r = await ledger.openFor(kind, scope: scope);
    if (r == null) return null;
    _record = r;
    if (r.state == OperationState.savedLocally) return null;
    if (r.state == OperationState.pending) {
      // كُتبت قبل الإرسال ولم يُحفظ ردّ: مجهولة.
      _record = await _persist(r.copyWith(state: OperationState.outcomeUnknown));
    }
    return CreateUnconfirmed(_record!);
  }

  /// إرسال النموذج. أوّل مرّة ⇒ سجلّ جديد يُكتب قبل الشبكة. عمليّة مفتوحة قد
  /// نُفِّذت ⇒ لا تُرسَل الحمولة المعدّلة أبداً: تُحفَظ مسودّةً وتُعرَض فروقها؛
  /// الحمولة نفسها ⇒ استعادة بنفس المفتاح.
  Future<CreateOutcome> submit(
    Map<String, dynamic> payload, {
    Map<String, dynamic> context = const {},
  }) async {
    if (_busy) return const CreateBusy();
    _busy = true;
    try {
      final owner = ledger.currentOwner();
      if (owner == null) return const CreateNotSaved(kOperationNoSessionAr);
      final current = _record;
      if (current != null && current.owner != owner) {
        return const CreateNotSaved(kOperationNoSessionAr);
      }
      final digest = payloadDigest(payload);
      if (current == null) {
        final t = ledger.now();
        final fresh = OperationRecord(
          operationId: generateRequestId(),
          owner: owner,
          kind: kind,
          scope: scope,
          method: method,
          path: path,
          payload: Map<String, dynamic>.from(payload),
          digest: digest,
          state: OperationState.pending,
          createdAt: t,
          updatedAt: t,
          context: context,
        );
        try {
          _record = await ledger.put(fresh);
        } on OperationStoreUnavailable {
          return const CreateNotSaved(kOperationNotSavedAr); // R04
        }
        return _send();
      }
      if (!current.mayHaveExecuted) {
        // لم يُنفَّذ قطعاً ⇒ تصحيح الحمولة بالمفتاح نفسه.
        try {
          _record = await ledger.put(
            current.copyWith(
              payload: Map<String, dynamic>.from(payload),
              digest: digest,
              state: OperationState.pending,
              context: context,
              clearDraft: true,
              clearError: true,
              clearConflict: true,
            ),
          );
        } on OperationStoreUnavailable {
          return const CreateNotSaved(kOperationNotSavedAr);
        }
        return _send();
      }
      if (digest == current.digest) {
        return _recover(current.copyWith(clearDraft: true));
      }
      // حمولة معدّلة بعد نتيجة مجهولة: مسودّة فقط، صفر طلبات.
      _record = await _persist(
        current.copyWith(draft: Map<String, dynamic>.from(payload)),
      );
      return CreateUnconfirmed(_record!);
    } finally {
      _busy = false;
    }
  }

  /// «استعادة نتيجة المحاولة السابقة»: نفس المفتاح ونفس الحمولة الأصليّة.
  /// [draft] مسودّة النموذج الحاليّة (تُحفَظ لتُعرَض فروقها بعد الاستعادة).
  Future<CreateOutcome?> recover({Map<String, dynamic>? draft}) async {
    final current = _record;
    if (current == null) return null;
    if (_busy) return const CreateBusy();
    if (current.owner != ledger.currentOwner()) {
      return const CreateNotSaved(kOperationNoSessionAr);
    }
    _busy = true;
    try {
      var r = current;
      if (draft != null) {
        r = payloadDigest(draft) == r.digest
            ? r.copyWith(clearDraft: true)
            : r.copyWith(draft: Map<String, dynamic>.from(draft));
      }
      if (!r.mayHaveExecuted) {
        _record = await _persist(r.copyWith(state: OperationState.pending));
        return _send();
      }
      return _recover(r);
    } finally {
      _busy = false;
    }
  }

  /// يحفظ مسودّة النموذج لعمليّة ربّما نُفِّذت (إغلاق الشاشة بعد نتيجة مجهولة)
  /// كي تُعرَض فروقها بعد إعادة الفتح. لا شبكة.
  Future<void> saveDraft(Map<String, dynamic>? draft) async {
    final r = _record;
    if (draft == null || r == null || !r.mayHaveExecuted || !r.isOpen) return;
    final next = payloadDigest(draft) == r.digest
        ? r.copyWith(clearDraft: true)
        : r.copyWith(draft: Map<String, dynamic>.from(draft));
    _record = await _persist(next);
  }

  /// يغلق عمليّة بعد مراجعة بشريّة (needs_reconciliation) أو لم تُنفَّذ قطعاً.
  Future<bool> dismiss() async {
    final r = _record;
    if (r == null) return false;
    if (r.state != OperationState.needsReconciliation && r.mayHaveExecuted) {
      return false;
    }
    try {
      await ledger.remove(r);
    } catch (_) {
      return false;
    }
    _record = null;
    return true;
  }

  Future<CreateOutcome> _recover(OperationRecord r) async {
    final lookup = ledger.lookup;
    final expired = ledger.retentionElapsed(r);
    bool? found;
    if (lookup != null) {
      try {
        found = await lookup(r.operationId);
      } catch (_) {
        found = null;
      }
    }
    if (expired && found != true) {
      // R13: بعد مدّة الاحتفاظ not_found ليس دليلاً على عدم التنفيذ.
      _record = await _persist(
        r.copyWith(
          state: OperationState.needsReconciliation,
          clearConflict: true,
        ),
      );
      return CreateUnconfirmed(_record!);
    }
    _record = await _persist(r);
    return _send(commandAbsent: found == false);
  }

  /// [commandAbsent]: الاستعلام المصادَق قال لا أمر مُلتزَماً بهذا المفتاح، فأيّ 409
  /// بلا سبب مفتاح هو رفض أعمال لهذا التنفيذ لا تعارض مفتاح.
  Future<CreateOutcome> _send({bool commandAbsent = false}) async {
    final r = _record!;
    final attempts = r.attempts + 1;
    try {
      final result = await send(r.payload, r.key);
      final id = _resourceIdOf(result);
      final done = r.copyWith(
        state: OperationState.confirmed,
        attempts: attempts,
        resourceId: id,
        clearError: true,
        clearConflict: true,
      );
      _record = done;
      try {
        await ledger.remove(done);
      } catch (e) {
        debugPrint('operation ledger: remove after confirm failed ($e)');
      }
      return CreateConfirmed(done, result);
    } catch (error) {
      final e = ApiException.from(error);
      final reason = idempotencyConflictReason(e);
      if (reason == ConflictReason.inProgress) {
        _record = await _persist(
          r.copyWith(
            state: OperationState.outcomeUnknown,
            attempts: attempts,
            lastErrorAr: kOperationInProgressAr,
            lastStatus: e.statusCode,
            conflictReason: reason,
          ),
        );
        return CreateUnconfirmed(_record!);
      }
      if (reason == ConflictReason.payloadMismatch ||
          (e.statusCode == 409 &&
              !_isBusinessConflict(e) &&
              !commandAbsent)) {
        _record = await _persist(
          r.copyWith(
            state: OperationState.needsAttention,
            attempts: attempts,
            lastErrorAr: kOperationConflictAr,
            lastStatus: e.statusCode,
            conflictReason: reason,
            clearConflict: reason == null,
          ),
        );
        return CreateUnconfirmed(_record!);
      }
      if (e.statusCode == 409 || _provenNotExecuted(e)) {
        _record = await _persist(
          r.copyWith(
            state: OperationState.savedLocally,
            attempts: attempts,
            lastErrorAr: e.messageAr,
            lastStatus: e.statusCode,
            clearConflict: true,
          ),
        );
        return CreateRejected(_record!, e);
      }
      // مهلة/انقطاع/إلغاء/5xx/429/شكل غير متوقّع ⇒ ربّما التزم الخادم.
      _record = await _persist(
        r.copyWith(
          state: OperationState.outcomeUnknown,
          attempts: attempts,
          lastErrorAr: e.messageAr,
          lastStatus: e.statusCode,
          clearConflict: true,
        ),
      );
      return CreateUnconfirmed(_record!);
    }
  }

  /// كتابة حالة بعد الإرسال: الفشل لا يُسقط السجلّ من الذاكرة.
  Future<OperationRecord> _persist(OperationRecord r) async {
    try {
      return await ledger.put(r);
    } catch (e) {
      debugPrint('operation ledger: state write failed ($e)');
      return r;
    }
  }

  static String? _resourceIdOf(Map<String, dynamic> result) {
    for (final k in const ['field_id', 'season_id', 'schedule_id', 'id']) {
      final v = result[k];
      if (v != null && v.toString().isNotEmpty) return v.toString();
    }
    return null;
  }
}
