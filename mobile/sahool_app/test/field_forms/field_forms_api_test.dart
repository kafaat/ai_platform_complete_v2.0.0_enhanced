/// اختبار تكامل على مستوى HTTP interception (§15.3): يتحقّق أنّ الطلبات
/// تُبنى على مساري BFF الصحيحين وبالحمولة الصحيحة — عبر HttpClientAdapter
/// وهميّ يعترض dio (لا شبكة حقيقيّة).
library;

import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_api.dart';

class _RecordedRequest {
  final String method;
  final String path;
  final Map<String, dynamic> query;
  final Object? body;
  final Map<String, dynamic> headers;
  const _RecordedRequest(
      this.method, this.path, this.query, this.body, this.headers);
}

/// MockAdapter: يسجّل الطلب ويعيد ردًّا مبرمجًا.
class _MockAdapter implements HttpClientAdapter {
  final List<_RecordedRequest> requests = [];
  Object? downloadResponse;
  Object? submitResponse;
  int submitStatus = 201;

  @override
  Future<ResponseBody> fetch(RequestOptions options,
      Stream<List<int>>? requestStream, Future<void>? cancelFuture) async {
    Object? body;
    if (requestStream != null) {
      final bytes =
          await requestStream.fold<List<int>>([], (acc, c) => acc..addAll(c));
      body = jsonDecode(utf8.decode(bytes));
    }
    requests.add(_RecordedRequest(
      options.method,
      options.path,
      options.queryParameters,
      body,
      Map<String, dynamic>.from(options.headers),
    ));

    if (options.path == '/api/field-forms/submissions') {
      return ResponseBody.fromString(
        jsonEncode(submitResponse),
        submitStatus,
        headers: {
          Headers.contentTypeHeader: [Headers.jsonContentType],
        },
      );
    }
    return ResponseBody.fromString(
      jsonEncode(downloadResponse),
      200,
      headers: {
        Headers.contentTypeHeader: [Headers.jsonContentType],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  late Dio dio;
  late _MockAdapter adapter;
  late FieldFormsApi api;

  setUp(() {
    adapter = _MockAdapter();
    dio = Dio(BaseOptions(baseUrl: 'https://api.example.test'))
      ..httpClientAdapter = adapter;
    api = FieldFormsApi(dio);
  });

  test('GET /api/field-forms/download بالمعاملات الثلاثة', () async {
    adapter.downloadResponse = {
      'field_id': 'field-9',
      'count': 1,
      'forms': [
        {
          'assignment_id': 'assign-7',
          'revision': 3,
          'form_version_id': 'v1',
          'version_number': 1,
          'schema_json': {
            'fields': [
              {'key': 'notes', 'field_type': 'text'},
            ],
          },
          'logic_json': null,
          'schema_hash': 'hash-v1',
          'definition_sync_token': 'sync-token-abc',
        },
      ],
    };

    final result = await api.download(
        fieldId: 'field-9', actorId: 'actor-1', deviceId: 'device-1');

    final request = adapter.requests.single;
    expect(request.method, 'GET');
    expect(request.path, '/api/field-forms/download');
    expect(request.query, {
      'field_id': 'field-9',
      'actor_id': 'actor-1',
      'device_id': 'device-1',
    });
    expect(result.fieldId, 'field-9');
    expect(result.forms.single.assignmentId, 'assign-7');
    expect(result.forms.single.revision, 3);
    expect(result.forms.single.schemaHash, 'hash-v1');
    expect(result.forms.single.definitionSyncToken, 'sync-token-abc');
  });

  test('POST /api/field-forms/submissions بالـenvelope الكامل', () async {
    adapter.submitResponse = {
      'status': 'accepted',
      'submission_id': 'srv-1',
      'version_resolution_status': 'current',
      'form_validation_status': 'valid',
    };

    final envelope = {
      'provider': 'sahool-flutter',
      'server': 'https://api.example.test',
      'instance_id': 'ff-123-abc',
      'submitted_at': '2025-01-15T12:00:00.000Z',
      'local_created_at': '2025-01-15T11:55:00.000Z',
      'field_id': 'field-9',
      'form_version_id': 'v1',
      'schema_hash': 'hash-v1',
      'assignment_revision': 3,
      'definition_sync_token': 'sync-token-abc',
      'answers': {'crop': 'wheat', 'severity': 3},
    };
    final result = await api.submit(envelope, deviceId: 'device-1');

    final request = adapter.requests.single;
    expect(request.method, 'POST');
    expect(request.path, '/api/field-forms/submissions');
    expect(request.body, envelope);
    expect(request.headers['X-Device-Id'], 'device-1');

    expect(result.status, 'accepted');
    expect(result.versionResolutionStatus, 'current');
    expect(result.formValidationStatus, 'valid');
  });

  test('استجابة quarantined تُعرض كما هي (لا نجاح كاذب)', () async {
    adapter.submitResponse = {
      'status': 'quarantined',
      'version_resolution_status': 'stale_proven',
      'form_validation_status': 'valid',
    };
    final result = await api.submit(
      const {'answers': {}},
      deviceId: 'device-1',
    );
    expect(result.status, 'quarantined');
    expect(result.versionResolutionStatus, 'stale_proven');
  });
}
