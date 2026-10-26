// SAHOOL — features/alerts/data/alerts_unread.dart
// عدّاد التنبيهات غير المُقَرّة (status=active) المشترك بين الشارة وصندوق
// التنبيهات. «غير مقروء» هنا = نشط لم يُقَرّ: الخادم لا يحفظ حالة قراءة لكلّ
// مستخدم، فلا ندّعيها.
//
// القيمة null ⇒ لم يُقَس بعد (أو تعذّر) — الشارة لا تعرض رقماً عندئذٍ بدل صفرٍ
// مُطمئِن كاذب.
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:sahool_app/services/websocket_service.dart';

import 'alert_live_events.dart';
import 'alert_models.dart';
import 'alerts_api.dart';

class AlertsUnreadCounter extends ChangeNotifier {
  AlertsUnreadCounter({AlertsApi? api, Stream<WsEvent>? events})
    : _api = api ?? AlertsApi.instance,
      _events = events;

  static final AlertsUnreadCounter instance = AlertsUnreadCounter();

  final AlertsApi _api;
  final Stream<WsEvent>? _events;
  StreamSubscription<LiveAlertSignal>? _sub;

  Set<String>? _active;
  bool _capped = false;
  Future<void>? _loading;

  /// عدد التنبيهات النشطة المعروفة؛ null ⇒ غير مقيس.
  int? get count => _active?.length;

  /// true ⇒ الخادم أعاد صفحة ممتلئة فالعدد الحقيقيّ قد يزيد («+»).
  bool get capped => _capped;

  /// نصّ الشارة: null ⇒ لا شارة.
  String? get badgeText {
    final c = count;
    if (c == null || c == 0) return null;
    if (c > 99) return '99+';
    return _capped ? '$c+' : '$c';
  }

  /// يبدأ الاستماع للقناة الحيّة ويحمّل العدد مرّة واحدة لكلّ جلسة.
  void ensureStarted() {
    _sub ??= liveAlertSignals(
      _events ?? defaultAlertEventSource(),
    ).listen(_onSignal, onError: (Object _) {});
    if (_active == null) unawaited(refresh());
  }

  /// يقرأ العدد من الخادم (status=active). فشل ⇒ يبقى العدد السابق كما هو.
  Future<void> refresh() => _loading ??= _doRefresh().whenComplete(() {
    _loading = null;
  });

  Future<void> _doRefresh() async {
    try {
      final list = await _api.listAlerts(
        status: 'active',
        limit: AlertsApi.pageSize,
      );
      _active = list.where((a) => a.isActive).map((a) => a.alertId).toSet();
      _capped = list.length >= AlertsApi.pageSize;
      notifyListeners();
    } catch (_) {
      // لا نخترع عدداً؛ الشارة تبقى على آخر قيمة مقيسة أو بلا رقم.
    }
  }

  /// مزامنة من قائمة الصندوق. [complete]=false ⇒ القائمة صفحة جزئيّة فلا تحلّ
  /// محلّ العدد (قد تُسقط تنبيهات أقدم نشطة).
  void syncFromInbox(List<AlertItem> all, {required bool complete}) {
    if (!complete) return;
    _active = all.where((a) => a.isActive).map((a) => a.alertId).toSet();
    _capped = false;
    notifyListeners();
  }

  void markAcknowledged(String alertId) {
    if (_active?.remove(alertId) ?? false) notifyListeners();
  }

  void _onSignal(LiveAlertSignal s) {
    switch (s.kind) {
      case LiveAlertKind.created:
        final item = s.item!;
        if (!item.isActive) return;
        (_active ??= <String>{}).add(item.alertId);
        notifyListeners();
      case LiveAlertKind.acknowledged:
        markAcknowledged(s.alertId!);
      case LiveAlertKind.refresh:
        unawaited(refresh());
    }
  }

  /// تنظيف الجلسة: لا يرى المستخدم التالي عدد السابق.
  Future<void> reset() async {
    await _sub?.cancel();
    _sub = null;
    _active = null;
    _capped = false;
    notifyListeners();
  }
}
