import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/realtime/realtime_api.dart';

class FixtureAdapter implements HttpClientAdapter {
  final requests = <RequestOptions>[];
  Map<String, dynamic> response = {
    'session_id': 'session-1', 'field_id': 'field-1', 'status': 'ACTIVE',
    'url': 'wss://media.example.invalid', 'participant_token': 'ephemeral-fixture-token',
    'expires_at': 1250, 'token_expires_at': 1050,
  };
  @override
  Future<ResponseBody> fetch(RequestOptions options, Stream<Uint8List>? requestStream,
      Future<void>? cancelFuture) async {
    requests.add(options);
    return ResponseBody.fromString(jsonEncode(response), 200,
      headers: {Headers.contentTypeHeader: ['application/json']},
    );
  }
  @override
  void close({bool force = false}) {}
}

void main() {
  late Dio dio;
  late FixtureAdapter adapter;
  late RealtimeApi api;
  setUp(() {
    dio = Dio(BaseOptions(baseUrl: 'https://api.example.invalid',
      headers: {'Authorization': 'Bearer authenticated-test-user'},
    ));
    adapter = FixtureAdapter();
    dio.httpClientAdapter = adapter;
    api = RealtimeApi(dio, now: () => DateTime.fromMillisecondsSinceEpoch(1000000, isUtc: true));
  });
  tearDown(() { dio.close(); });

  test('fixed session endpoint carries explicit field and both consents', () async {
    final grant = await api.create('field-1');
    expect(adapter.requests.single.path, '/api/v1/realtime/sessions');
    expect(adapter.requests.single.data, {
      'field_id': 'field-1', 'consent': true, 'voice_consent': true,
    });
    expect(adapter.requests.single.headers['Authorization'], 'Bearer authenticated-test-user');
    expect(grant.fieldId, 'field-1');
    expect(grant.token, 'ephemeral-fixture-token');
  });

  test('foreign field response fails closed', () async {
    adapter.response['field_id'] = 'field-2';
    await expectLater(api.create('field-1'), throwsStateError);
  });

  test('non-active response is not admitted to media', () async {
    adapter.response['status'] = 'PENDING';
    await expectLater(api.create('field-1'), throwsStateError);
  });

  for (final url in [
    'ws://media.example.invalid',
    'wss://user:password@media.example.invalid',
    'wss://media.example.invalid?access_token=secret',
    'wss://media.example.invalid#secret',
  ]) {
    test('unsafe media origin is rejected: $url', () async {
      adapter.response['url'] = url;
      await expectLater(api.create('field-1'), throwsStateError);
    });
  }

  final invalidLeases = <Map<String, dynamic>>[
    {'expires_at': 999}, {'expires_at': 1306}, {'token_expires_at': 999},
    {'token_expires_at': 1066}, {'token_expires_at': null},
    {'token_expires_at': '1050'}, {'expires_at': 1030, 'token_expires_at': 1040},
    {'session_id': ''}, {'participant_token': ''},
  ];
  for (var index = 0; index < invalidLeases.length; index++) {
    test('malformed or overlong lease is rejected ($index)', () async {
      adapter.response.addAll(invalidLeases[index]);
      await expectLater(api.create('field-1'), throwsStateError);
    });
  }

  test('close encodes the server identifier without adding headers or payload', () async {
    await api.close('session/1');
    expect(adapter.requests.single.method, 'DELETE');
    expect(adapter.requests.single.path, '/api/v1/realtime/sessions/session%2F1');
    expect(adapter.requests.single.data, isNull);
  });
}
