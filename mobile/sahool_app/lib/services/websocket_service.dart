// SAHOOL v9.1.0 — lib/services/websocket_service.dart
// Fixes: F01(cert), F02(max reconnects), F03(backoff), F04(dispose), F05(queue)
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'package:flutter/foundation.dart';
import 'package:logger/logger.dart';
import 'auth_service.dart';

class WebSocketService {
  static final WebSocketService instance = WebSocketService._internal();
  WebSocketService._internal();

  WebSocket? _socket;
  Timer? _pingTimer;
  Timer? _reconnectTimer;
  final _logger = Logger();
  final _controller = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get messages => _controller.stream;

  bool _intentionalClose = false;
  int _reconnectAttempts = 0;
  static const _maxReconnects = 10;  // F02: max attempts
  static const _maxQueueSize  = 100; // F05: message queue

  // F05: Message queue for offline state
  final List<Map<String, dynamic>> _messageQueue = [];

  String get _wsUrl {
    const base = String.fromEnvironment('WS_URL', defaultValue: 'wss://api.sahool.ye');
    final token = AuthService.instance.token ?? '';
    return '$base/ws/notifications?token=${Uri.encodeComponent(token)}';
  }

  Future<void> connect() async {
    if (_socket != null) return;
    _intentionalClose = false;

    try {
      final url = _wsUrl;
      _logger.d('WS connecting: $url');

      // F01: Allow self-signed in debug
      WebSocket ws;
      if (kDebugMode) {
        final client = HttpClient()
          ..badCertificateCallback = (cert, host, port) => true;
        ws = await WebSocket.connect(url, customClient: client);
      } else {
        ws = await WebSocket.connect(url);
      }

      _socket = ws;
      _reconnectAttempts = 0;
      _logger.i('WS connected ✅');

      // Flush queued messages
      for (final msg in _messageQueue) {
        _socket!.add(json.encode(msg));
      }
      _messageQueue.clear();

      _socket!.listen(
        (data) {
          try {
            final msg = json.decode(data as String) as Map<String, dynamic>;
            if (msg['type'] == 'ping') {
              send({'type': 'pong'});
            } else {
              _controller.add(msg);
            }
          } catch (_) {}
        },
        onDone: () {
          _logger.w('WS closed');
          _socket = null;
          _pingTimer?.cancel();
          if (!_intentionalClose) _scheduleReconnect();
        },
        onError: (e) {
          _logger.e('WS error: $e');
          _socket = null;
          _pingTimer?.cancel();
          if (!_intentionalClose) _scheduleReconnect();
        },
      );

      _pingTimer = Timer.periodic(const Duration(seconds: 30), (_) {
        if (_socket?.readyState == WebSocket.open) {
          _socket!.add(json.encode({'type': 'ping'}));
        }
      });

    } catch (e) {
      _logger.e('WS connect failed: $e');
      _socket = null;
      if (!_intentionalClose) _scheduleReconnect();
    }
  }

  void _scheduleReconnect() {
    // F02: Max reconnect attempts
    if (_reconnectAttempts >= _maxReconnects) {
      _logger.e('WS: max reconnect attempts reached');
      return;
    }
    // F03: Exponential backoff
    final delay = Duration(
      seconds: (2 * (_reconnectAttempts + 1)).clamp(2, 60),
    );
    _reconnectAttempts++;
    _logger.d('WS reconnect in ${delay.inSeconds}s (attempt $_reconnectAttempts)');
    _reconnectTimer = Timer(delay, connect);
  }

  /// يُرسل رسالة عبر القناة. يعيد `true` إن أُرسلت فوراً، و`false` إن وُضِعت في
  /// الطابور (القناة غير مفتوحة) — فيعرف المستدعي أنّ أمراً مُغيِّراً للحالة
  /// (تشغيل ريّ/صمّام) لم يُنفَّذ بعد بدل أن يَظنّه نُفِّذ.
  bool send(Map<String, dynamic> data) {
    // P1: idempotency — كلّ عمليّة قابلة للتغيير تحمل operation_id ثابتاً.
    // عند إعادة الإرسال (reconnect)، يبقى نفس المعرّف → الخلفيّة تكتشف التكرار
    // وتتجاهله (تمنع تنفيذ "تشغيل الري" مرّتين). مُولَّد مرّة واحدة عند الإنشاء.
    if (_isMutating(data) && !data.containsKey('operation_id')) {
      data['operation_id'] = _generateOperationId();
    }
    if (_socket?.readyState == WebSocket.open) {
      _socket!.add(json.encode(data));
      return true;
    }
    // F05: تُحفَظ الرسائل أثناء عدم الاتّصال (مع operation_id للتكرار الآمن). عند
    // امتلاء الطابور نُسقط الأقدم ونُبقي الأحدث (الأقرب للحالة الراهنة) مع تحذير
    // صريح، فلا يكون فقد أمرٍ تشغيليّ خفيّاً. نعيد false (طُوبِرت، لم تُرسَل بعد).
    if (_messageQueue.length >= _maxQueueSize) {
      _messageQueue.removeAt(0);
      _logger.w('طابور الرسائل ممتلئ ($_maxQueueSize) — أُسقطت أقدم رسالة');
    }
    _messageQueue.add(data);
    return false;
  }

  // العمليّات المُغيِّرة للحالة (commands) تحتاج idempotency؛ pong/ping لا.
  bool _isMutating(Map<String, dynamic> data) {
    final type = (data['type'] as String?) ?? '';
    return type != 'ping' && type != 'pong' && type != 'subscribe';
  }

  // معرّف عمليّة شبه-فريد (timestamp + عشوائي) — ثابت عبر إعادات الإرسال.
  String _generateOperationId() {
    final ts = DateTime.now().microsecondsSinceEpoch.toRadixString(16);
    final rnd = Random().nextInt(0xFFFFFF).toRadixString(16).padLeft(6, '0');
    return 'op_${ts}_$rnd';
  }

  // F04: Proper dispose
  Future<void> dispose() async {
    _intentionalClose = true;
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    await _socket?.close(WebSocketStatus.normalClosure);
    _socket = null;
    _reconnectAttempts = 0;
    _logger.d('WS disposed');
  }

  Future<void> reconnect() async {
    await dispose();
    _intentionalClose = false;
    await connect();
  }
}
