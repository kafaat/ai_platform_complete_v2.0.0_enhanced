/// حلقة تشغيل النماذج الميدانيّة offline-first.
///
/// تفتح مخازن Hive، تبني عميل الـBFF من جلسة المستخدم، تنزّل تعريفات الحقل،
/// وتصرّف طابور الإرسال بترتيب FIFO عند الإقلاع وعودة الاتصال، وبمؤقّت backoff
/// (يحترم Retry-After) بعد فشلٍ مؤقّت ما دام التطبيق متّصلاً.
///
/// حدّ الجلسة: كلّ تصريف يُختَم برقم جيل الجلسة. نهاية الجلسة تزيد الجيل وتلغي
/// المؤقّت، والحلقة تتحقّق قبل كلّ عنصر من الجيل والمستأجِر والمستخدم الحاليّين،
/// فلا يُرسَل عنصرٌ التقطته جلسةٌ سابقة تحت رمز جلسةٍ لاحقة.
library;

import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../../../services/api_service.dart';
import '../../../services/auth_service.dart';
import '../../../services/device_id_service.dart';
import 'field_forms_api.dart';
import 'form_package_store.dart';
import 'submission_queue.dart';
import 'submission_sender.dart';

class FieldFormsCoordinator {
  FieldFormsCoordinator({
    FormPackageStore? packages,
    SubmissionQueue? queue,
    FieldFormsApi? api,
    String? Function()? currentTenantId,
    String? Function()? currentActorId,
    Timer Function(Duration delay, void Function() callback)? timer,
    this.backoffBase = const Duration(seconds: 15),
    this.backoffMax = const Duration(minutes: 30),
  }) : _packages = packages,
       _queue = queue,
       _api = api,
       _currentTenantId =
           currentTenantId ?? (() => AuthService.instance.tenantId),
       _currentActorId = currentActorId ?? (() => AuthService.instance.userId),
       _timer = timer ?? Timer.new;

  /// مصدر المستأجِر الحاليّ (الجلسة افتراضيّاً؛ قابل للحقن في الاختبارات).
  final String? Function() _currentTenantId;
  final String? Function() _currentActorId;
  final Timer Function(Duration delay, void Function() callback) _timer;

  /// أساس backoff الإعادة التلقائيّة وحدّه الأعلى.
  final Duration backoffBase;
  final Duration backoffMax;

  /// يُبلَّغ بعد كلّ تصريف أرسل شيئاً (تحديث قائمة النماذج المفتوحة).
  final ValueNotifier<int> drainTick = ValueNotifier<int>(0);

  static final FieldFormsCoordinator instance = FieldFormsCoordinator();

  static const int maxPoisonAttempts = SubmissionSender.maxRejectedAttempts;

  FormPackageStore? _packages;
  SubmissionQueue? _queue;
  FieldFormsApi? _api;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  bool _draining = false;

  /// جيل الجلسة: يزيد عند نهايتها فتتوقّف أيّ حلقة بدأت قبلها.
  int _epoch = 0;

  /// طُلب تصريف أثناء حلقةٍ جارية.
  bool _rerun = false;
  Timer? _retryTimer;
  int _retryRounds = 0;

  FormPackageStore? get packages => _packages;
  SubmissionQueue? get queue => _queue;
  FieldFormsApi? get api => _api;

  /// للاختبارات: عميل جلسةٍ جديدة (ما يفعله [refreshAuthContext] عند الدخول).
  @visibleForTesting
  set api(FieldFormsApi? value) => _api = value;

  Future<void> init() async {
    try {
      _packages ??= await FormPackageStore.open();
      _queue ??= await SubmissionQueue.open();
      await refreshAuthContext();
      unawaited(drain());

      await _connectivitySubscription?.cancel();
      _connectivitySubscription = Connectivity().onConnectivityChanged.listen((
        results,
      ) {
        if (results.any((result) => result != ConnectivityResult.none)) {
          unawaited(drain());
        }
      });
    } catch (error) {
      debugPrint('FieldFormsCoordinator.init failed (non-fatal): $error');
    }
  }

  Future<void> refreshAuthContext() async {
    final actorId = AuthService.instance.userId;
    if (actorId == null || actorId.isEmpty) {
      _api = null;
      return;
    }
    _api = FieldFormsApi(ApiService.instance.dio);
  }

  Future<void> dispose() async {
    _cancelRetry();
    await _connectivitySubscription?.cancel();
    _connectivitySubscription = null;
  }

  /// نهاية جلسة (خروج صريح): أوقف التصريف وأسقط العميل المرتبط بالتوكن.
  /// زيادة الجيل توقف الحلقة الجارية قبل عنصرها التالي (الطلب الجاري أُرسل
  /// برمز صاحبه نفسه)، فلا تُكمل بقائمةٍ التقطتها الجلسة المنتهية.
  /// عناصر الطابور **لا تُحذف**: هي عمل ميدانيّ لم يُرسَل بعد، وتُصرَّف فقط حين
  /// يعود مستأجِرها (pending(tenantId:)). حذفها هنا كان سيُضيّع بيانات جُمعت
  /// دون اتّصال.
  Future<void> onSessionEnd() async {
    _epoch++;
    await dispose();
    _api = null;
  }

  void _cancelRetry() {
    _retryTimer?.cancel();
    _retryTimer = null;
  }

  Future<void> syncField(String fieldId) async {
    final api = _api;
    final store = _packages;
    final tenantId = AuthService.instance.tenantId;
    final actorId = AuthService.instance.userId;
    if (api == null || store == null || tenantId == null || actorId == null) {
      return;
    }

    try {
      final deviceId = await DeviceIdService.instance.deviceId();
      final download = await api.download(
        fieldId: fieldId,
        actorId: actorId,
        deviceId: deviceId,
      );
      for (final package in download.forms) {
        await store.save(
          tenantId: tenantId,
          fieldId: download.fieldId,
          package: package,
        );
      }
    } catch (error) {
      debugPrint('FieldFormsCoordinator.syncField($fieldId) failed: $error');
    }
  }

  Future<int> drain() async {
    if (_draining) {
      // يُعاد بعد انتهاء الحلقة الجارية إن أوقفها تغيّر الجلسة.
      _rerun = true;
      return 0;
    }
    final api = _api;
    final queue = _queue;
    final tenantId = _currentTenantId();
    // بلا مستأجِر معروف لا نعرف لمن تُنسَب العناصر — لا نُرسل شيئاً.
    if (api == null || queue == null || tenantId == null) return 0;

    _draining = true;
    _rerun = false;
    _cancelRetry();
    final epoch = _epoch;
    final actorId = _currentActorId();
    var settled = 0;
    var touched = false;
    var fenced = false;
    var authRejected = false;
    Duration? retryAfter;
    var retryLater = false;
    try {
      final deviceId = await DeviceIdService.instance.deviceId();
      final server = ApiService.instance.dio.options.baseUrl;
      for (final item in queue.pending(tenantId: tenantId, actorId: actorId)) {
        // الجلسة انتهت أو تبدّل صاحبها منذ بدء التصريف ⇒ توقّف قبل الإرسال.
        if (epoch != _epoch ||
            _currentTenantId() != tenantId ||
            _currentActorId() != actorId) {
          fenced = true;
          break;
        }
        touched = true;
        final outcome = await SubmissionSender.send(
          item: item,
          queue: queue,
          api: api,
          deviceId: deviceId,
          server: server,
        );
        if (outcome.kind == SendOutcomeKind.settled) settled++;
        if (outcome.kind == SendOutcomeKind.retryLater) {
          retryLater = true;
          final after = outcome.retryAfter;
          if (after != null && (retryAfter == null || after > retryAfter)) {
            retryAfter = after;
          }
        }
        if (outcome.kind == SendOutcomeKind.authRejected) {
          authRejected = true;
          break;
        }
      }
      if (epoch != _epoch) fenced = true;
    } finally {
      _draining = false;
      if (touched) drainTick.value++;
    }
    if (fenced) {
      // تصريفٌ طلبته الجلسة الجديدة أثناء إنهاء الحلقة القديمة لا يضيع.
      if (_rerun) unawaited(drain());
    } else if (retryLater && !authRejected) {
      _scheduleRetry(retryAfter);
    } else {
      _retryRounds = 0;
    }
    return settled;
  }

  /// فشل مؤقّت والتطبيق ما زال متّصلاً: لا ننتظر تغيّر الشبكة — نعيد التصريف
  /// بعد backoff أُسّيّ، وليس قبل Retry-After إن أرسله الخادم.
  void _scheduleRetry(Duration? retryAfter) {
    _retryRounds++;
    final exp = _retryRounds <= 1 ? 0 : (_retryRounds - 1).clamp(0, 20);
    final raw = backoffBase * (1 << exp);
    var delay = raw > backoffMax ? backoffMax : raw;
    if (retryAfter != null && retryAfter > delay) delay = retryAfter;
    _retryTimer = _timer(delay, () => unawaited(drain()));
  }

  @visibleForTesting
  bool get hasScheduledRetry => _retryTimer?.isActive ?? false;
}
