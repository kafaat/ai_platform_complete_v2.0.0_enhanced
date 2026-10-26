// SAHOOL — features/alerts/presentation/alerts_cubit.dart
// صندوق التنبيهات: تحميل، ترشيح بالخطورة/الحقل، إقرار بمفتاح ثابت لكلّ تنبيه،
// وإدراج حيّ من قناة الإشعارات (أوّل مشترك فعليّ فيها).
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/services/websocket_service.dart';

import '../data/alert_live_events.dart';
import '../data/alert_models.dart';
import '../data/alerts_api.dart';
import '../data/alerts_unread.dart';

enum AlertsStatus { loading, ready, failed }

@immutable
class AlertsState {
  const AlertsState({
    this.status = AlertsStatus.loading,
    this.alerts = const [],
    this.error,
    this.severity,
    this.showAcknowledged = false,
    this.acking = const {},
    this.message,
    this.messageSeq = 0,
    this.pageFull = false,
    this.refreshing = false,
  });

  final AlertsStatus status;

  /// كلّ ما حُمِّل (الأحدث أوّلاً)، قبل الترشيح.
  final List<AlertItem> alerts;
  final ApiException? error;

  /// null ⇒ كلّ درجات الخطورة.
  final AlertSeverity? severity;
  final bool showAcknowledged;

  /// تنبيهات قيد الإقرار (يمنع الضغط المزدوج).
  final Set<String> acking;

  /// رسالة عابرة (SnackBar) — [messageSeq] يتغيّر مع كلّ رسالة جديدة.
  final String? message;
  final int messageSeq;

  /// الخادم أعاد صفحة ممتلئة — قد توجد تنبيهات أقدم لم تُعرَض.
  final bool pageFull;
  final bool refreshing;

  List<AlertItem> get visible => alerts
      .where((a) => severity == null || a.severity == severity)
      .where((a) => showAcknowledged || a.isActive)
      .toList();

  int activeCount(AlertSeverity s) =>
      alerts.where((a) => a.isActive && a.severity == s).length;

  int get activeTotal => alerts.where((a) => a.isActive).length;

  AlertsState copyWith({
    AlertsStatus? status,
    List<AlertItem>? alerts,
    ApiException? error,
    bool clearError = false,
    AlertSeverity? severity,
    bool clearSeverity = false,
    bool? showAcknowledged,
    Set<String>? acking,
    String? message,
    bool? pageFull,
    bool? refreshing,
  }) => AlertsState(
    status: status ?? this.status,
    alerts: alerts ?? this.alerts,
    error: clearError ? null : (error ?? this.error),
    severity: clearSeverity ? null : (severity ?? this.severity),
    showAcknowledged: showAcknowledged ?? this.showAcknowledged,
    acking: acking ?? this.acking,
    message: message ?? this.message,
    messageSeq: message != null ? messageSeq + 1 : messageSeq,
    pageFull: pageFull ?? this.pageFull,
    refreshing: refreshing ?? this.refreshing,
  );
}

class AlertsCubit extends Cubit<AlertsState> {
  AlertsCubit(
    this._api, {
    this.fieldId,
    Stream<WsEvent>? events,
    AlertsUnreadCounter? counter,
  }) : _counter = counter ?? AlertsUnreadCounter.instance,
       super(const AlertsState()) {
    _sub = liveAlertSignals(
      events ?? defaultAlertEventSource(),
    ).listen(_onLive, onError: (Object _) {});
  }

  final AlertsApi _api;

  /// إن مُرِّر: صندوق حقل واحد (ترشيح محلّيّ — الخادم لا يرشّح بالحقل).
  final String? fieldId;
  final AlertsUnreadCounter _counter;
  StreamSubscription<LiveAlertSignal>? _sub;
  final Map<String, IdempotencyKey> _ackKeys = {};
  Timer? _refreshDebounce;

  bool _mine(AlertItem a) => fieldId == null || a.fieldId == fieldId;

  Future<void> load() async {
    emit(state.copyWith(status: AlertsStatus.loading, clearError: true));
    await _fetch();
  }

  /// سحب للتحديث: تبقى القائمة الحاليّة ظاهرة أثناء الجلب.
  Future<void> refresh() async {
    if (state.status != AlertsStatus.ready) return load();
    emit(state.copyWith(refreshing: true));
    await _fetch();
  }

  Future<void> _fetch() async {
    try {
      final list = await _api.listAlerts(limit: AlertsApi.pageSize);
      if (isClosed) return;
      final full = list.length >= AlertsApi.pageSize;
      if (fieldId == null) {
        _counter.syncFromInbox(list, complete: !full);
      }
      emit(
        state.copyWith(
          status: AlertsStatus.ready,
          alerts: list.where(_mine).toList(),
          pageFull: full,
          refreshing: false,
          clearError: true,
        ),
      );
    } catch (e) {
      if (isClosed) return;
      final err = ApiException.from(e);
      if (state.status == AlertsStatus.ready) {
        // تبقى البيانات السابقة مع رسالة صادقة بأنّ التحديث فشل.
        emit(
          state.copyWith(
            refreshing: false,
            message: 'تعذّر التحديث: ${err.messageAr}',
          ),
        );
      } else {
        emit(state.copyWith(status: AlertsStatus.failed, error: err));
      }
    }
  }

  void setSeverity(AlertSeverity? s) => emit(
    s == null
        ? state.copyWith(clearSeverity: true)
        : state.copyWith(severity: s),
  );

  void setShowAcknowledged(bool v) => emit(state.copyWith(showAcknowledged: v));

  /// يُقِرّ تنبيهاً. المفتاح ثابت لهذا التنبيه حتّى ينجح (إعادة المحاولة بعد
  /// انقطاع لا تُنشئ نيّة جديدة).
  Future<bool> acknowledge(String alertId) async {
    if (state.acking.contains(alertId)) return false;
    final key = _ackKeys[alertId] ??= IdempotencyKey.generate();
    emit(state.copyWith(acking: {...state.acking, alertId}));
    try {
      final updated = await _api.acknowledgeAlert(alertId, idempotencyKey: key);
      _ackKeys.remove(alertId);
      _counter.markAcknowledged(alertId);
      if (isClosed) return true;
      emit(
        state.copyWith(
          alerts: [
            for (final a in state.alerts) a.alertId == alertId ? updated : a,
          ],
          acking: {...state.acking}..remove(alertId),
          message: 'تمّ إقرار التنبيه.',
        ),
      );
      return true;
    } catch (e) {
      if (isClosed) return false;
      final err = ApiException.from(e);
      emit(
        state.copyWith(
          acking: {...state.acking}..remove(alertId),
          message: err.isNotFound
              ? 'التنبيه لم يعد موجوداً — حُدِّثت القائمة.'
              : 'تعذّر الإقرار: ${err.messageAr}',
        ),
      );
      if (err.isNotFound) unawaited(refresh());
      return false;
    }
  }

  void _onLive(LiveAlertSignal s) {
    // قبل أوّل تحميل ناجح لا شيء نُدرج فيه؛ التحميل الجاري سيجلب الحدث نفسه.
    if (isClosed || state.status != AlertsStatus.ready) return;
    switch (s.kind) {
      case LiveAlertKind.created:
        final item = s.item!;
        if (!_mine(item)) return;
        if (state.alerts.any((a) => a.alertId == item.alertId)) return;
        emit(
          state.copyWith(
            alerts: [item, ...state.alerts],
            message: 'تنبيه جديد: ${item.displayTitle}',
          ),
        );
      case LiveAlertKind.acknowledged:
        final id = s.alertId!;
        if (!state.alerts.any((a) => a.alertId == id && a.isActive)) return;
        emit(
          state.copyWith(
            alerts: [
              for (final a in state.alerts)
                a.alertId == id ? a.copyWith(status: 'acknowledged') : a,
            ],
          ),
        );
      case LiveAlertKind.refresh:
        _scheduleRefresh();
    }
  }

  // أحداث بلا معرّف قد تصل دفعةً — طلب واحد بعد هدوئها.
  void _scheduleRefresh() {
    _refreshDebounce?.cancel();
    _refreshDebounce = Timer(const Duration(seconds: 2), () {
      if (!isClosed) unawaited(refresh());
    });
  }

  @override
  Future<void> close() async {
    _refreshDebounce?.cancel();
    await _sub?.cancel();
    return super.close();
  }
}
