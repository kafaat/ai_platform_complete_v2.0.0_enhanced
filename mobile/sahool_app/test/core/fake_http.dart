// أدوات اختبار مشتركة لطبقة الشبكة: محوّل HTTP مزيّف يسجّل كلّ طلب ويردّ عبر
// دالّة، ومخزن توكنات في الذاكرة، وصانع JWT بانتهاء محدّد. تختبر ApiClient
// الحقيقيّ (interceptors نفسها) لا نسخة مُعاد كتابتها من منطقه.
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:sahool_app/core/network/api_client.dart';

class RecordedRequest {
  final String method;
  final String path;
  final Map<String, dynamic> headers;
  final Object? data;
  final Map<String, dynamic> extra;
  RecordedRequest(RequestOptions o)
      : method = o.method,
        path = o.path,
        headers = Map<String, dynamic>.from(o.headers),
        data = o.data,
        extra = Map<String, dynamic>.from(o.extra);
}

class FakeReply {
  final int status;
  final Object? body;
  final Map<String, List<String>> headers;
  final DioExceptionType? failure;
  const FakeReply(this.status, [this.body, this.headers = const {}])
      : failure = null;
  const FakeReply.fail(DioExceptionType this.failure)
      : status = 0,
        body = null,
        headers = const {};
}

typedef FakeHandler = Future<FakeReply> Function(RequestOptions options);

class FakeAdapter implements HttpClientAdapter {
  FakeAdapter(this.handler);
  final FakeHandler handler;
  final List<RecordedRequest> requests = [];

  List<RecordedRequest> to(String path) =>
      requests.where((r) => r.path == path).toList();

  @override
  Future<ResponseBody> fetch(RequestOptions options,
      Stream<Uint8List>? requestStream, Future<void>? cancelFuture) async {
    requests.add(RecordedRequest(options));
    final reply = await handler(options);
    if (reply.failure != null) {
      throw DioException(
          requestOptions: options, type: reply.failure!, error: 'fake');
    }
    return ResponseBody.fromString(
      reply.body == null ? '' : jsonEncode(reply.body),
      reply.status,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
        ...reply.headers,
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

class MemoryTokenStore implements TokenStore {
  MemoryTokenStore({this.accessToken, this.refreshToken});
  @override
  String? accessToken;
  @override
  String? refreshToken;
  int clears = 0;

  @override
  Future<void> saveTokens(String access, {String? refresh}) async {
    accessToken = access;
    if (refresh != null) refreshToken = refresh;
  }

  @override
  Future<void> clear() async {
    clears++;
    accessToken = null;
    refreshToken = null;
  }
}

/// JWT غير موقَّع بانتهاء [expiresIn] من الآن (سالب ⇒ منتهٍ).
String fakeJwt(Duration expiresIn, {String sub = 'u'}) {
  String b64(Map<String, Object> m) =>
      base64Url.encode(utf8.encode(jsonEncode(m))).replaceAll('=', '');
  final exp = DateTime.now().add(expiresIn).millisecondsSinceEpoch ~/ 1000;
  return '${b64({'alg': 'none'})}.${b64({'sub': sub, 'exp': exp})}.sig';
}

ApiClient testClient(FakeAdapter adapter, TokenStore tokens) => ApiClient(
      baseUrl: 'https://api.test.invalid',
      tokens: tokens,
      adapter: adapter,
      retryBaseDelay: const Duration(milliseconds: 1),
      retryJitterMs: 0,
    );
