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

  Future<WriteOutcome<FieldActivity>> submit(
    String fieldId,
    Map<String, dynamic> body, {
    String? typeLabelAr,
  }) async {
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
}
