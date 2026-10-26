/// حلقة تشغيل النماذج الميدانيّة offline-first.
///
/// تفتح مخازن Hive، تبني عميل الـBFF من جلسة المستخدم، تنزّل تعريفات الحقل،
/// وتصرّف طابور الإرسال بترتيب FIFO عند الإقلاع وعودة الاتصال.
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
  }) : _packages = packages,
       _queue = queue,
       _api = api,
       _currentTenantId =
           currentTenantId ?? (() => AuthService.instance.tenantId),
       _currentActorId = currentActorId ?? (() => AuthService.instance.userId);

  /// مصدر المستأجِر الحاليّ (الجلسة افتراضيّاً؛ قابل للحقن في الاختبارات).
  final String? Function() _currentTenantId;
  final String? Function() _currentActorId;

  /// يُبلَّغ بعد كلّ تصريف أرسل شيئاً (تحديث قائمة النماذج المفتوحة).
  final ValueNotifier<int> drainTick = ValueNotifier<int>(0);

  static final FieldFormsCoordinator instance = FieldFormsCoordinator();

  static const int maxPoisonAttempts = SubmissionSender.maxRejectedAttempts;

  FormPackageStore? _packages;
  SubmissionQueue? _queue;
  FieldFormsApi? _api;
  StreamSubscription<List<ConnectivityResult>>? _connectivitySubscription;
  bool _draining = false;

  FormPackageStore? get packages => _packages;
  SubmissionQueue? get queue => _queue;
  FieldFormsApi? get api => _api;

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
    await _connectivitySubscription?.cancel();
    _connectivitySubscription = null;
  }

  /// نهاية جلسة (خروج صريح): أوقف التصريف وأسقط العميل المرتبط بالتوكن.
  /// عناصر الطابور **لا تُحذف**: هي عمل ميدانيّ لم يُرسَل بعد، وتُصرَّف فقط حين
  /// يعود مستأجِرها (pending(tenantId:)). حذفها هنا كان سيُضيّع بيانات جُمعت
  /// دون اتّصال.
  Future<void> onSessionEnd() async {
    await dispose();
    _api = null;
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
    if (_draining) return 0;
    final api = _api;
    final queue = _queue;
    final tenantId = _currentTenantId();
    // بلا مستأجِر معروف لا نعرف لمن تُنسَب العناصر — لا نُرسل شيئاً.
    if (api == null || queue == null || tenantId == null) return 0;

    _draining = true;
    var settled = 0;
    var touched = false;
    try {
      final deviceId = await DeviceIdService.instance.deviceId();
      final server = ApiService.instance.dio.options.baseUrl;
      for (final item in queue.pending(
        tenantId: tenantId,
        actorId: _currentActorId(),
      )) {
        touched = true;
        final outcome = await SubmissionSender.send(
          item: item,
          queue: queue,
          api: api,
          deviceId: deviceId,
          server: server,
        );
        if (outcome.kind == SendOutcomeKind.settled) settled++;
        if (outcome.kind == SendOutcomeKind.authRejected) break;
      }
    } finally {
      _draining = false;
      if (touched) drainTick.value++;
    }
    return settled;
  }
}
