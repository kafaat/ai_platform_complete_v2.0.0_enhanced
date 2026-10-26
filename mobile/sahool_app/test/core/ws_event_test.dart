// WsEvent.fromJson يقرأ النوع من `event_type` كما يبثّه وكيل الإشعارات
// (agents/notification/agent.py dispatch: {event_type, title, message, data,
// tenant_id}) وغلاف ناقل الأحداث في الخادم (event_bus.py)، ثمّ `type` لإطارات
// التحكّم (auth_ok/subscribed/pong). كان يقرأ type/event فقط فلا يطابق
// on('alert') أيّ تنبيه حقيقيّ.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/services/websocket_service.dart';

void main() {
  test('reads the producer event_type key', () {
    final e = WsEvent.fromJson({
      'event_type': 'alert',
      'title': 'صقيع',
      'tenant_id': 't1',
    });
    expect(e.type, 'alert');
    expect(e.data['title'], 'صقيع');
  });

  test('event_type wins over type when both are present', () {
    expect(
      WsEvent.fromJson({'event_type': 'alert.created', 'type': 'x'}).type,
      'alert.created',
    );
  });

  test('control frames keep using type, then event', () {
    expect(WsEvent.fromJson({'type': 'auth_ok'}).type, 'auth_ok');
    expect(WsEvent.fromJson({'event': 'legacy'}).type, 'legacy');
    expect(WsEvent.fromJson({}).type, '');
  });
}
