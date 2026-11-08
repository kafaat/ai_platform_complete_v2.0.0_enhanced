// SAHOOL — features/activities/data/activity_writer.dart
// تسجيل نشاط يعمل بلا اتّصال: يرسل الآن بمفتاح Idempotency-Key ثابت للنيّة، أو
// يودعه صندوق الإرسال (OfflineOutbox) إن انقطعت الشبكة. النسخة المُودَعة تُعرَض
// بشارة «بانتظار المزامنة» من [PendingActivities] حتى يظهر النشاط من الخادم.
import 'package:flutter/foundation.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/tasks/data/offline_write.dart';

import 'activities_api.dart';
import 'field_activity.dart';

/// أنشطة أودِعت صندوق الإرسال في هذه الجلسة (ذاكرة فقط؛ الصندوق نفسه هو
/// المخزن الدائم). تُمسَح عند الخروج.
class PendingActivities extends ValueNotifier<List<FieldActivity>> {
  PendingActivities() : super(const []);
  static final PendingActivities instance = PendingActivities();

  void add(FieldActivity a) => value = [...value, a];

  List<FieldActivity> forField(String fieldId) =>
      value.where((a) => a.fieldId == fieldId).toList();

  /// يُسقط النسخ المحلّيّة التي ظهرت في قائمة الخادم [server] للحقل.
  void reconcile(String fieldId, List<FieldActivity> server) {
    final next = value
        .where((p) => p.fieldId != fieldId || !server.any((s) => s.sameAs(p)))
        .toList();
    if (next.length != value.length) value = next;
  }

  void clear() => value = const [];
}

class ActivityWriter {
  ActivityWriter({
    ActivitiesApi? api,
    OfflineOutbox? outbox,
    bool Function()? isOnline,
    IntentKeys? keys,
    PendingActivities? pending,
    DateTime Function()? clock,
  }) : _api = api ?? ActivitiesApi.instance,
       _outbox = outbox,
       _isOnline = isOnline ?? (() => ConnectivityStatus.instance.isOnline),
       _keys = keys ?? IntentKeys(),
       _pending = pending ?? PendingActivities.instance,
       _clock = clock ?? DateTime.now;

  final ActivitiesApi _api;
  final OfflineOutbox? _outbox;
  final bool Function() _isOnline;
  final IntentKeys _keys;
  final PendingActivities _pending;
  final DateTime Function() _clock;

  /// نوع عمليّة الصندوق: نشاط مُنفَّذ = `activity_complete` (اسم العمليّة في
  /// core/offline_first.py)، ونشاط مُجدوَل = `activity_create`.
  static String outboxKind(Map<String, dynamic> body) =>
      body['performed_on'] != null ? 'activity_complete' : 'activity_create';

  /// جسم انتقال الإنجاز من جسم الإنشاء: التاريخ + القيم الفعليّة من details
  /// (المفاتيح التي يقرؤها دفتر المدخلات على الخادم).
  static Map<String, dynamic> completionBody(Map<String, dynamic> body) {
    final details = body['details'];
    final d = details is Map ? details : const {};
    final product = d['product_name'] ?? d['product'];
    final unit = d['unit'];
    return {
      'status': 'done',
      'performed_on': body['performed_on'],
      if (d['quantity'] is num) 'actual_quantity': d['quantity'],
      if (unit is String && unit.isNotEmpty) 'actual_unit': unit,
      if (product is String && product.isNotEmpty) 'actual_product': product,
      if (d['cost'] is num) 'actual_cost': d['cost'],
    };
  }

  /// يسجّل نشاطاً. [activityId] معروف ونشاط مُنفَّذ ⇒ إنجاز الصفّ المُخطَّط القائم
  /// (PATCH) بدل صفّ جديد مكرّر يُبقي المُخطَّط «مُجدوَلاً» للأبد؛ وإلّا POST
  /// (عمل مُنفَّذ عارض أو نشاط مُجدوَل جديد).
  Future<WriteOutcome<FieldActivity>> submit(
    String fieldId,
    Map<String, dynamic> body, {
    String? typeLabelAr,
    String? activityId,
  }) async {
    if (activityId != null && body['performed_on'] != null) {
      return transition(
        fieldId,
        activityId,
        completionBody(body),
        typeLabelAr: typeLabelAr ?? body['activity_type']?.toString(),
      );
    }
    final intent = 'activity:$fieldId';
    final key = _keys.keyFor(intent, body);
    final outcome = await writeOrQueue<FieldActivity>(
      key: key,
      online: _isOnline(),
      outbox: _outbox ?? OfflineOutbox.instance,
      send: (k) => _api.createActivity(fieldId, body, idempotencyKey: k),
      op: (k) => OutboxOp(
        kind: outboxKind(body),
        method: 'POST',
        path: ActivitiesApi.activitiesPath(fieldId),
        body: body,
        idempotencyKey: k.value,
        fieldId: fieldId,
        labelAr: 'تسجيل نشاط: ${typeLabelAr ?? body['activity_type']}',
      ),
    );
    if (outcome.isQueued) {
      _pending.add(
        FieldActivity.pending('local:${key.value}', fieldId, body, _clock()),
      );
    }
    if (!outcome.isFailed) _keys.settle(intent);
    return outcome;
  }

  /// ينقل نشاطاً قائماً: [body] = {status: done|skipped, performed_on?, actual_*?}.
  /// بلا اتّصال يُودَع `activity_complete`/`activity_skip` (PATCH) بمفتاح ثابت للنيّة؛
  /// لا نسخة «بانتظار المزامنة» — الصفّ نفسه موجود في القائمة أصلاً.
  Future<WriteOutcome<FieldActivity>> transition(
    String fieldId,
    String activityId,
    Map<String, dynamic> body, {
    String? typeLabelAr,
  }) async {
    final intent = 'activity:$fieldId:$activityId';
    final key = _keys.keyFor(intent, body);
    final skip = body['status'] == 'skipped';
    final verb = skip ? 'تخطّي' : 'إنجاز';
    final outcome = await writeOrQueue<FieldActivity>(
      key: key,
      online: _isOnline(),
      outbox: _outbox ?? OfflineOutbox.instance,
      send: (k) => _api.transitionActivity(
        fieldId,
        activityId,
        body,
        idempotencyKey: k,
      ),
      op: (k) => OutboxOp(
        kind: skip ? 'activity_skip' : 'activity_complete',
        method: 'PATCH',
        path: ActivitiesApi.activityPath(fieldId, activityId),
        body: body,
        idempotencyKey: k.value,
        fieldId: fieldId,
        labelAr: '$verb نشاط: ${typeLabelAr ?? activityId}',
      ),
    );
    if (!outcome.isFailed) _keys.settle(intent);
    return outcome;
  }
}
