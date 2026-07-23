/// حلقة تشغيل النماذج الميدانيّة offline-first.
///
/// تفتح مخازن Hive، تبني عميل الـBFF من جلسة المستخدم، تنزّل تعريفات الحقل،
/// وتصرّف طابور الإرسال بترتيب FIFO عند الإقلاع وعودة الاتصال.
library;

import 'dart:async';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../../../services/api_service.dart';
import '../../../services/auth_service.dart';
import '../../../services/device_id_service.dart';
import 'field_forms_api.dart';
import 'form_package_store.dart';
import 'submission_queue.dart';

class FieldFormsCoordinator {
  FieldFormsCoordinator({
    FormPackageStore? packages,
    SubmissionQueue? queue,
    FieldFormsApi? api,
  })  : _packages = packages,
        _queue = queue,
        _api = api;

  static final FieldFormsCoordinator instance = FieldFormsCoordinator();

  static const int maxPoisonAttempts = 10;

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
      _connectivitySubscription =
          Connectivity().onConnectivityChanged.listen((results) {
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
    if (api == null || queue == null) return 0;

    _draining = true;
    var settled = 0;
    try {
      final deviceId = await DeviceIdService.instance.deviceId();
      for (final item in queue.pending()) {
        try {
          await api.submit(
            item.buildEnvelope(
              provider: 'sahool-flutter',
              server: ApiService.instance.dio.options.baseUrl,
            ),
            deviceId: deviceId,
          );
          await queue.remove(item.instanceId);
          settled++;
        } on DioException catch (error) {
          final statusCode = error.response?.statusCode ?? 0;
          final updated = await queue.markRetry(item);
          if (statusCode == 401 || statusCode == 403) break;
          if (statusCode >= 400 &&
              statusCode < 500 &&
              updated.attempts >= maxPoisonAttempts) {
            await queue.remove(item.instanceId);
          }
        } catch (_) {
          await queue.markRetry(item);
        }
      }
    } finally {
      _draining = false;
    }
    return settled;
  }
}
