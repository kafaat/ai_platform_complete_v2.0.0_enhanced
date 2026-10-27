// خادم HTTP محلّيّ حقيقيّ (dart:io HttpServer) بدلالة `_idempotent` في الخادم: أوّل
// طلب بمفتاحٍ يُنفَّذ ويُلتزَم (يُسجَّل المورد)، والإعادة بالمفتاح نفسه تعيد النتيجة
// المخزّنة؛ و«التزام ثمّ إسقاط الردّ» يُغلق المقبس دون أيّ بايت ردّ بعد تسجيل الالتزام
// — لا mock يرمي قبل الإرسال. لا يعتمد على سجلّ العمليّات (يعمل على شجرة الأساس
// أيضاً لاختبارات التكذيب).
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:sahool_app/core/network/api_client.dart';

/// سلوك الخادم لطلب إنشاءٍ واحد.
sealed class Serve {
  const Serve();
}

/// نفّذ (أو أعِد المخزَّن) وردّ 201.
class Reply extends Serve {
  const Reply();
}

/// نفّذ والتزم، ثمّ أغلق المقبس دون ردّ.
class CommitThenDrop extends Serve {
  const CommitThenDrop();
}

/// نفّذ والتزم، ثمّ لا تردّ أبداً (قتل التطبيق قبل حفظ الردّ).
class CommitThenHang extends Serve {
  const CommitThenHang();
}

/// ردّ بحالة وجسم معيّنين دون تنفيذ (ارتداد).
class Status extends Serve {
  const Status(this.code, this.body);
  final int code;
  final Object body;
}

class ServedRequest {
  ServedRequest(this.method, this.path, this.key, this.body, this.auth);
  final String method;
  final String path;
  final String? key;
  final Map<String, dynamic>? body;
  final String? auth;
}

class LocalCommitServer {
  LocalCommitServer._(this._server, this.createPath, this.make) {
    _server.listen(_handle);
  }

  /// [make] يبني المورد الجديد من رقمه وجسم الطلب.
  static Future<LocalCommitServer> start({
    required String createPath,
    required Map<String, dynamic> Function(int n, Map<String, dynamic> body)
    make,
  }) async => LocalCommitServer._(
    await HttpServer.bind(InternetAddress.loopbackIPv4, 0),
    createPath,
    make,
  );

  final HttpServer _server;
  final String createPath;
  final Map<String, dynamic> Function(int n, Map<String, dynamic> body) make;

  final List<ServedRequest> requests = [];

  /// المفتاح ⇒ النتيجة المُلتزَمة (جدول commands).
  final Map<String, Map<String, dynamic>> committed = {};

  /// الموارد المُنشأة فعلاً (صفوف الجدول).
  final List<Map<String, dynamic>> resources = [];

  /// خطّة سلوك طلبات الإنشاء بالترتيب؛ فارغة ⇒ [Reply].
  final List<Serve> plan = [];

  /// ردود GET ثابتة لمسارات أخرى (قوائم الشاشة).
  final Map<String, Object> getResponses = {};

  /// ردود PATCH ثابتة (تحديثٌ مستقلّ بعد الاستعادة).
  final Map<String, Object> patchResponses = {};

  final _hung = <HttpRequest>[];
  final _arrived = StreamController<ServedRequest>.broadcast();

  String get baseUrl => 'http://${_server.address.host}:${_server.port}';

  List<ServedRequest> get creates =>
      requests.where((r) => r.method == 'POST' && r.path == createPath).toList();

  /// يكتمل عند وصول طلب الإنشاء رقم [n] (من 1).
  Future<void> createArrived(int n) async {
    if (creates.length >= n) return;
    await _arrived.stream.firstWhere((_) => creates.length >= n);
  }

  Future<void> _handle(HttpRequest req) async {
    final raw = await utf8.decoder.bind(req).join();
    final body = raw.isEmpty
        ? null
        : Map<String, dynamic>.from(jsonDecode(raw) as Map);
    final served = ServedRequest(
      req.method,
      req.uri.path,
      req.headers.value('Idempotency-Key'),
      body,
      req.headers.value('Authorization'),
    );
    requests.add(served);
    _arrived.add(served);
    final cmd = RegExp(r'^/api/v1/commands/(.+)$').firstMatch(req.uri.path);
    if (req.method == 'GET' && cmd != null) {
      final id = Uri.decodeComponent(cmd.group(1)!);
      return committed.containsKey(id)
          ? _json(req, 200, {'command_id': id, 'found': true})
          : _json(req, 404, {'detail': 'الأمر غير موجود'});
    }
    final fixed = getResponses[req.uri.path];
    if (req.method == 'GET' && fixed != null) return _json(req, 200, fixed);
    final patched = patchResponses[req.uri.path];
    if (req.method == 'PATCH' && patched != null) {
      return _json(req, 200, patched);
    }
    if (req.method != 'POST' || req.uri.path != createPath) {
      return _json(req, 404, {'detail': 'غير موجود'});
    }
    final serve = plan.isEmpty ? const Reply() : plan.removeAt(0);
    switch (serve) {
      case Status(:final code, :final body):
        return _json(req, code, body);
      case Reply():
        return _json(req, 201, _execute(served));
      case CommitThenDrop():
        _execute(served);
        final socket = await req.response.detachSocket(writeHeaders: false);
        socket.destroy();
      case CommitThenHang():
        _execute(served);
        _hung.add(req);
    }
  }

  /// دلالة `_idempotent`: مفتاح معروف ⇒ النتيجة المخزّنة بلا تنفيذ.
  Map<String, dynamic> _execute(ServedRequest r) {
    final key = r.key;
    if (key != null && committed.containsKey(key)) return committed[key]!;
    final created = make(resources.length + 1, r.body ?? const {});
    resources.add(created);
    if (key != null) committed[key] = created;
    return created;
  }

  Future<void> _json(HttpRequest req, int code, Object body) async {
    req.response
      ..statusCode = code
      ..headers.contentType = ContentType.json
      ..write(jsonEncode(body));
    await req.response.close();
  }

  Future<void> close() async {
    for (final r in _hung) {
      try {
        final s = await r.response.detachSocket(writeHeaders: false);
        s.destroy();
      } catch (_) {}
    }
    await _arrived.close();
    await _server.close(force: true);
  }
}

/// ApiClient حقيقيّ (interceptors نفسها، IOHttpClientAdapter) نحو الخادم المحلّيّ.
ApiClient realClient(LocalCommitServer server, TokenStore tokens) => ApiClient(
  baseUrl: server.baseUrl,
  tokens: tokens,
  retryBaseDelay: const Duration(milliseconds: 1),
  retryJitterMs: 0,
);
