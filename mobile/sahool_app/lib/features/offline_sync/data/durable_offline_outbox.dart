// SAHOOL — features/offline_sync/data/durable_offline_outbox.dart
// التنفيذ الدائم لعقد [OfflineOutbox].
//
//  • الإيداع: يُختَم السجلّ بمالكه (sub/tenant_id من رمز الوصول الحاليّ) ويُكتب في
//    صندوق Hive المشفّر قبل أن يُقال «حُفظ». لا جلسة/لا صندوق ⇒ notQueued صادق.
//  • التصريف: FIFO بترتيب الإيداع، مسلسل (تصريف واحد في كلّ لحظة)، ولا يُرسل
//    إلّا سجلّات مالكها هو صاحب الجلسة الآن — يُعاد الفحص قبل كلّ طلب. يُطلَق عند
//    عودة الاتّصال، وعند استئناف التطبيق، وعند الدخول، وبعد الإيداع، وبمؤقّت
//    backoff.
//  • التصنيف (offline_sync_api.dart): 2xx أو 409-إعادة ⇒ حذف · 4xx ⇒ «مرفوضة»
//    برسالة الخادم · 5xx/مهلة/انقطاع ⇒ تبقى مع backoff. فشلٌ مؤقّت لعمليّة حقلٍ
//    يُوقف ما بعدها لنفس الحقل فقط (لا تسبق عمليّةٌ لاحقة سابقتَها).
//  • الخروج: لا يحذف شيئاً. يُلغي الطلب الجاري ويوقف التصريف؛ السجلّات تبقى مقفلة
//    على مالكها ولا تُرسَل أبداً برمز مستخدم آخر.
import 'dart:async';
import 'dart:math';

import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/session/auth_state.dart';
import 'package:sahool_app/core/session/session_scope.dart';
import 'package:sahool_app/core/utils/ids.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/services/auth_service.dart';

import 'offline_sync_api.dart';
import 'outbox_record.dart';
import 'outbox_store.dart';

typedef OutboxStoreOpener = Future<OutboxStore> Function();
typedef OutboxOwnerReader = OutboxOwner? Function();
typedef OutboxTimerFactory =
    Timer Function(Duration delay, void Function() callback);

/// أسباب عدم الإيداع (OutboxReceipt.notQueued).
abstract final class OutboxRefusal {
  static const noSession = 'no_session';
  static const storeUnavailable = 'offline_store_unavailable';
  static const writeFailed = 'offline_store_write_failed';
  static const badMethod = 'unsupported_method';
  static const badPath = 'invalid_path';
  static const syncEndpoint = 'sync_endpoint_not_supported';
  static const badKey = 'invalid_idempotency_key';
  static const badBody = 'body_not_json';
}

final _uuid = RegExp(
  r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|[0-9a-fA-F]{32})$',
);

/// يفحص العمليّة قبل حفظها. يُعيد سبب الرفض أو null.
String? validateOutboxOp(OutboxOp op) {
  const methods = {'POST', 'PUT', 'PATCH', 'DELETE'};
  if (!methods.contains(op.method.toUpperCase())) {
    return OutboxRefusal.badMethod;
  }
  final path = Uri.tryParse(op.path)?.path;
  if (path == null || !op.path.startsWith('/') || op.path.startsWith('//')) {
    return OutboxRefusal.badPath;
  }
  // POST /api/v1/sync يسجّل في دفتر فقط (routers/sync.py:91) — كلّ عمليّة إلى نقطتها.
  final norm = path.endsWith('/') ? path.substring(0, path.length - 1) : path;
  if (norm == '/api/v1/sync' || norm.startsWith('/api/v1/sync/')) {
    return OutboxRefusal.syncEndpoint;
  }
  // الخادم يرفض مفتاحاً غير UUID بـ400 (api/main.py:_idem_key).
  if (!_uuid.hasMatch(op.idempotencyKey)) return OutboxRefusal.badKey;
  try {
    OutboxRecord(
      id: 'probe',
      seq: 0,
      owner: const OutboxOwner(userId: 'probe', tenantId: ''),
      op: op,
      createdAt: DateTime.utc(2000),
    ).encode();
  } catch (_) {
    return OutboxRefusal.badBody;
  }
  return null;
}

/// ما تعرضه صفحة الحالة والشارة للمستخدم الحاليّ.
@immutable
class OutboxSnapshot {
  const OutboxSnapshot({
    required this.owner,
    required this.pending,
    required this.rejected,
    required this.heldForOtherAccounts,
    required this.draining,
    this.failure,
    this.opened = true,
  });

  const OutboxSnapshot.opening()
    : owner = null,
      pending = const [],
      rejected = const [],
      heldForOtherAccounts = 0,
      draining = false,
      failure = null,
      opened = false;

  const OutboxSnapshot.unavailable(OutboxStoreException this.failure)
    : owner = null,
      pending = const [],
      rejected = const [],
      heldForOtherAccounts = 0,
      draining = false,
      opened = false;

  final OutboxOwner? owner;
  final List<OutboxRecord> pending;
  final List<OutboxRecord> rejected;

  /// عمليّات محفوظة لحسابات أخرى على هذا الجهاز (عددها فقط — لا محتواها).
  final int heldForOtherAccounts;
  final bool draining;
  final OutboxStoreException? failure;
  final bool opened;

  bool get isUnavailable => failure != null;
}

class DurableOfflineOutbox implements OfflineOutbox {
  DurableOfflineOutbox({
    required OutboxStoreOpener openStore,
    required OutboxOwnerReader currentOwner,
    OfflineSyncApi? api,
    ValueListenable<bool>? connectivity,
    AuthState? authState,
    bool observeLifecycle = false,
    bool drainOnOpen = false,
    DateTime Function()? clock,
    OutboxTimerFactory? timer,
    Random? random,
    Future<void> Function()? deleteUnreadableBox,
    this.backoffBase = const Duration(seconds: 15),
    this.backoffMax = const Duration(minutes: 30),
  }) : _openStore = openStore,
       _currentOwner = currentOwner,
       _api = api ?? OfflineSyncApi.instance,
       _connectivity = connectivity,
       _authState = authState,
       _observeLifecycle = observeLifecycle,
       _drainOnOpen = drainOnOpen,
       _clock = clock ?? DateTime.now,
       _timer = timer ?? Timer.new,
       _random = random ?? Random(),
       _deleteUnreadableBox =
           deleteUnreadableBox ?? HiveOutboxStore.deleteUnreadable;

  /// التنفيذ الإنتاجيّ: صندوق Hive مشفّر، هويّة من رمز الوصول الذي يرسله
  /// ApiClient، ومحفّزات التطبيق (الاتّصال، الدخول، الاستئناف). لا إدخال/إخراج
  /// قبل أوّل استعمال.
  static final DurableOfflineOutbox shared = DurableOfflineOutbox(
    openStore: HiveOutboxStore.openEncrypted,
    currentOwner: () => OutboxOwner.fromAccessToken(AuthService.instance.token),
    connectivity: ConnectivityStatus.instance,
    authState: AuthState.instance,
    observeLifecycle: true,
    drainOnOpen: true,
  );

  final OutboxStoreOpener _openStore;
  final OutboxOwnerReader _currentOwner;
  final OfflineSyncApi _api;
  final ValueListenable<bool>? _connectivity;
  final AuthState? _authState;
  final bool _observeLifecycle;
  final bool _drainOnOpen;
  final DateTime Function() _clock;
  final OutboxTimerFactory _timer;
  final Random _random;
  final Future<void> Function() _deleteUnreadableBox;
  final Duration backoffBase;
  final Duration backoffMax;

  OutboxStore? _store;
  Future<OutboxStore?>? _opening;
  OutboxStoreException? _failure;

  final _changes = StreamController<OutboxSnapshot>.broadcast();

  bool _triggersAttached = false;
  bool _lastOnline = true;
  AppLifecycleListener? _lifecycle;

  Future<void>? _drainRun;
  bool _rerun = false;
  bool _rerunIgnoreBackoff = false;
  bool _draining = false;
  int _epoch = 0;
  CancelToken? _inflight;
  Timer? _retryTimer;
  int _ownerPolls = 0;
  static const _maxOwnerPolls = 12;
  static const _ownerPollDelay = Duration(seconds: 5);

  // ── الفتح ───────────────────────────────────────────────────────────

  /// يفتح الصندوق (مرّة واحدة). null ⇒ تعذّر؛ السبب في [snapshot].failure.
  Future<OutboxStore?> ensureOpen() {
    final s = _store;
    if (s != null) return Future.value(s);
    return _opening ??= _open();
  }

  Future<OutboxStore?> _open() async {
    try {
      final s = await _openStore();
      _store = s;
      _failure = null;
      _attachTriggers();
      _emit();
      if (_drainOnOpen) unawaited(drain(ignoreBackoff: true));
      return s;
    } catch (e) {
      _failure = e is OutboxStoreException
          ? e
          : OutboxStoreException(OutboxStoreFailure.openFailed, e);
      _opening = null; // الاستعمال التالي يعيد المحاولة
      _emit();
      return null;
    }
  }

  /// يبدأ العمل في الخلفيّة (يُستدعى من وحدة الميزة عند الإقلاع).
  Future<void> start() async {
    await ensureOpen();
  }

  /// يحذف صندوقاً مفتاحه مفقود ثمّ يفتح صندوقاً جديداً. قرار صريح من المستخدم.
  Future<void> resetUnreadableStore() async {
    if (_failure?.failure != OutboxStoreFailure.keyMissingForExistingBox) {
      return;
    }
    await _deleteUnreadableBox();
    _failure = null;
    _opening = null;
    await ensureOpen();
  }

  void _attachTriggers() {
    if (_triggersAttached) return;
    _triggersAttached = true;
    final c = _connectivity;
    if (c != null) {
      _lastOnline = c.value;
      c.addListener(_onConnectivity);
    }
    _authState?.addListener(_onAuth);
    if (_observeLifecycle) {
      try {
        _lifecycle = AppLifecycleListener(
          onResume: () => unawaited(drain(ignoreBackoff: true)),
        );
      } catch (_) {
        // بلا WidgetsBinding (اختبار منطق صرف) — بقيّة المحفّزات تكفي.
      }
    }
  }

  void _onConnectivity() {
    final online = _connectivity!.value;
    final cameBack = online && !_lastOnline;
    _lastOnline = online;
    if (cameBack) unawaited(drain(ignoreBackoff: true));
  }

  void _onAuth() {
    switch (_authState!.last) {
      case AuthChange.signedIn:
        _ownerPolls = 0;
        _emit();
        unawaited(drain(ignoreBackoff: true));
      case AuthChange.signedOut:
      case AuthChange.expired:
        _abort();
        _emit();
      case null:
        break;
    }
  }

  bool get _isOffline => _connectivity != null && !_connectivity.value;

  // ── العقد ───────────────────────────────────────────────────────────

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    final problem = validateOutboxOp(op);
    if (problem != null) return OutboxReceipt.notQueued(problem);
    final owner = _currentOwner();
    if (owner == null) {
      return const OutboxReceipt.notQueued(OutboxRefusal.noSession);
    }
    final store = await ensureOpen();
    if (store == null) {
      return const OutboxReceipt.notQueued(OutboxRefusal.storeUnavailable);
    }
    // نفس المفتاح لنفس المالك محفوظ ⇒ نفس النيّة؛ لا سجلّ ثانٍ.
    final dup = store.records.any(
      (r) => r.owner == owner && r.op.idempotencyKey == op.idempotencyKey,
    );
    if (dup) return const OutboxReceipt.queued();
    final record = OutboxRecord(
      id: generateRequestId(),
      seq: store.nextSeq(),
      owner: owner,
      op: OutboxOp(
        kind: op.kind,
        method: op.method.toUpperCase(),
        path: op.path,
        body: op.body,
        idempotencyKey: op.idempotencyKey,
        fieldId: op.fieldId,
        labelAr: op.labelAr,
      ),
      createdAt: _clock().toUtc(),
    );
    try {
      await store.put(record);
    } catch (_) {
      return const OutboxReceipt.notQueued(OutboxRefusal.writeFailed);
    }
    _emit();
    if (!_isOffline) unawaited(drain());
    return const OutboxReceipt.queued();
  }

  @override
  Stream<int> get pendingCount => watch()
      .where((s) => s.opened || s.isUnavailable)
      .map((s) => s.pending.length)
      .distinct();

  /// اللقطة الحاليّة ثمّ كلّ تغيير.
  Stream<OutboxSnapshot> watch() {
    late final StreamController<OutboxSnapshot> c;
    StreamSubscription<OutboxSnapshot>? sub;
    c = StreamController<OutboxSnapshot>(
      onListen: () {
        sub = _changes.stream.listen(c.add);
        c.add(snapshot());
        ensureOpen().then((_) {
          if (!c.isClosed) c.add(snapshot());
        });
      },
      onCancel: () => sub?.cancel(),
    );
    return c.stream;
  }

  OutboxSnapshot snapshot() {
    final failure = _failure;
    if (failure != null) return OutboxSnapshot.unavailable(failure);
    final store = _store;
    if (store == null) return const OutboxSnapshot.opening();
    final owner = _currentOwner();
    final all = store.records;
    final mine = owner == null
        ? const <OutboxRecord>[]
        : all.where((r) => r.owner == owner).toList();
    return OutboxSnapshot(
      owner: owner,
      pending: mine.where((r) => r.isPending).toList(),
      rejected: mine.where((r) => r.isRejected).toList(),
      heldForOtherAccounts: all.length - mine.length,
      draining: _draining,
    );
  }

  void _emit() {
    if (!_changes.isClosed) _changes.add(snapshot());
  }

  // ── أفعال المستخدم ───────────────────────────────────────────────────

  /// يعيد عمليّة (معلّقة أو مرفوضة) إلى الطابور ويرسل الآن بنفس المفتاح.
  Future<void> retry(String id) async {
    final store = await ensureOpen();
    final r = store?.byId(id);
    if (store == null || r == null || r.owner != _currentOwner()) return;
    await store.put(
      r.copyWith(
        state: OutboxRecordState.pending,
        clearNextAttempt: true,
        clearRejection: true,
      ),
    );
    _emit();
    await drain(ignoreBackoff: true);
  }

  /// يحذف عمليّة يملكها المستخدم الحاليّ بطلبه (بعد تأكيد في الواجهة).
  Future<bool> discard(String id) async {
    final store = await ensureOpen();
    final r = store?.byId(id);
    if (store == null || r == null || r.owner != _currentOwner()) return false;
    await store.remove(id);
    _emit();
    return true;
  }

  /// تنظيف الخروج: لا حذف. يوقف التصريف ويلغي الطلب الجاري؛ السجلّات تبقى
  /// مختومة بمالكها فلا تُرسَل تحت جلسة أخرى.
  Future<void> onSessionEnd(SessionEnd end) async {
    _abort();
    final run = _drainRun;
    if (run != null) {
      try {
        await run;
      } catch (_) {}
    }
    _emit();
  }

  void _abort() {
    _epoch++;
    _inflight?.cancel('session_end');
    _inflight = null;
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  // ── التصريف ─────────────────────────────────────────────────────────

  /// يصرّف عمليّات المستخدم الحاليّ بالترتيب. [ignoreBackoff] لعودة الاتّصال
  /// والاستئناف والطلب اليدويّ. نداء أثناء تصريفٍ جارٍ يُضمّ إليه.
  Future<void> drain({bool ignoreBackoff = false}) {
    final running = _drainRun;
    if (running != null) {
      _rerun = true;
      _rerunIgnoreBackoff |= ignoreBackoff;
      return running;
    }
    final done = Completer<void>();
    _drainRun = done.future;
    () async {
      var ignore = ignoreBackoff;
      try {
        do {
          _rerun = false;
          await _drainOnce(ignore);
          ignore = _rerunIgnoreBackoff;
          _rerunIgnoreBackoff = false;
        } while (_rerun);
      } catch (e) {
        debugPrint('offline outbox drain failed: $e');
      } finally {
        // لا await بين آخر فحص لـ_rerun وتحرير القفل ⇒ لا طلب تصريف يضيع.
        _drainRun = null;
        _scheduleNext();
        done.complete();
      }
    }();
    return done.future;
  }

  Future<void> _drainOnce(bool ignoreBackoff) async {
    final store = await ensureOpen();
    if (store == null) return;
    final owner = _currentOwner();
    if (owner == null) return;
    _ownerPolls = 0;
    final epoch = _epoch;
    final queue = store.records
        .where((r) => r.owner == owner && r.isPending)
        .toList();
    if (queue.isEmpty) return;
    _draining = true;
    _emit();
    final blocked = <String>{};
    try {
      for (final queued in queue) {
        if (epoch != _epoch) return;
        // الجلسة تغيّرت منذ بدء التصريف ⇒ توقّف فوراً.
        if (_currentOwner() != queued.owner) return;
        final group = queued.op.fieldId ?? '';
        if (blocked.contains(group)) continue;
        final r = store.byId(queued.id);
        if (r == null || !r.isPending) continue;
        final now = _clock();
        if (!ignoreBackoff &&
            r.nextAttemptAt != null &&
            r.nextAttemptAt!.isAfter(now)) {
          blocked.add(group);
          continue;
        }
        final outcome = await _attempt(r);
        if (epoch != _epoch && outcome.kind == OutboxOutcomeKind.aborted) {
          return;
        }
        final stop = await _apply(store, r, outcome);
        _emit();
        if (stop) return;
        if (outcome.kind == OutboxOutcomeKind.retryLater) blocked.add(group);
      }
    } finally {
      _draining = false;
      _emit();
    }
  }

  Future<OutboxOutcome> _attempt(OutboxRecord r) async {
    final token = CancelToken();
    _inflight = token;
    try {
      await _api.sendOp(r.op, cancelToken: token);
      return const OutboxOutcome(OutboxOutcomeKind.sent);
    } catch (e) {
      return classifyOutboxFailure(ApiException.from(e));
    } finally {
      if (identical(_inflight, token)) _inflight = null;
    }
  }

  /// يطبّق النتيجة على السجلّ. يُعيد true إن وجب إيقاف التصريف.
  Future<bool> _apply(
    OutboxStore store,
    OutboxRecord r,
    OutboxOutcome outcome,
  ) async {
    final now = _clock().toUtc();
    switch (outcome.kind) {
      case OutboxOutcomeKind.sent:
      case OutboxOutcomeKind.alreadyApplied:
        await store.remove(r.id);
        return false;
      case OutboxOutcomeKind.rejected:
        await store.put(
          r.copyWith(
            state: OutboxRecordState.rejected,
            attempts: r.attempts + 1,
            lastAttemptAt: now,
            clearNextAttempt: true,
            clearLastError: true,
            rejectedStatus: outcome.statusCode,
            rejectedMessageAr: outcome.messageAr,
            rejectedAt: now,
          ),
        );
        return false;
      case OutboxOutcomeKind.retryLater:
      case OutboxOutcomeKind.offline:
      case OutboxOutcomeKind.sessionProblem:
        final attempts = r.attempts + 1;
        await store.put(
          r.copyWith(
            attempts: attempts,
            lastAttemptAt: now,
            nextAttemptAt: now.add(backoffFor(attempts)),
            lastErrorAr: outcome.messageAr,
          ),
        );
        return outcome.kind != OutboxOutcomeKind.retryLater;
      case OutboxOutcomeKind.aborted:
        return true;
    }
  }

  /// backoff أُسّيّ: الأساس × 2^(n-1) حتى الحدّ + jitter حتى 20٪.
  Duration backoffFor(int attempts) {
    final exp = attempts <= 1 ? 0 : min(attempts - 1, 20);
    final raw = backoffBase.inMilliseconds * (1 << exp);
    final capped = min(raw, backoffMax.inMilliseconds);
    final jitter = (capped * 0.2 * _random.nextDouble()).round();
    return Duration(milliseconds: capped + jitter);
  }

  void _scheduleNext() {
    _retryTimer?.cancel();
    _retryTimer = null;
    final store = _store;
    if (store == null) return;
    final owner = _currentOwner();
    if (owner == null) {
      // الإقلاع: الجلسة المحفوظة قد لا تكون حُمِّلت بعد. افحص بضع مرّات ما دامت
      // هناك عمليّات معلّقة، ثمّ اعتمد على الدخول/الاستئناف/عودة الاتّصال.
      final any = store.records.any((r) => r.isPending);
      if (any && _ownerPolls < _maxOwnerPolls) {
        _ownerPolls++;
        _retryTimer = _timer(_ownerPollDelay, () => unawaited(drain()));
      }
      return;
    }
    DateTime? earliest;
    for (final r in store.records) {
      if (r.owner != owner || !r.isPending) continue;
      final at = r.nextAttemptAt;
      if (at == null) continue;
      if (earliest == null || at.isBefore(earliest)) earliest = at;
    }
    if (earliest == null) return;
    var delay = earliest.difference(_clock());
    if (delay < const Duration(seconds: 1)) delay = const Duration(seconds: 1);
    _retryTimer = _timer(delay, () => unawaited(drain()));
  }

  @visibleForTesting
  bool get hasScheduledRetry => _retryTimer?.isActive ?? false;

  /// للاختبارات: يفصل المستمعين ويوقف المؤقّت.
  @visibleForTesting
  Future<void> dispose() async {
    _abort();
    _connectivity?.removeListener(_onConnectivity);
    _authState?.removeListener(_onAuth);
    _lifecycle?.dispose();
    await _changes.close();
  }
}
