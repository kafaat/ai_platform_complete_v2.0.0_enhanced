import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_api.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_coordinator.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';

class _FakeAdapter implements HttpClientAdapter {
  _FakeAdapter(this.outcomes);

  final List<Object> outcomes;
  int calls = 0;
  String? lastDeviceId;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    lastDeviceId = options.headers['X-Device-Id']?.toString();
    final outcome = outcomes[calls++];
    if (outcome is DioException) throw outcome;
    return ResponseBody.fromString(
      jsonEncode({'status': 'accepted', 'submission_id': 'ff-x'}),
      outcome as int,
      headers: {
        Headers.contentTypeHeader: ['application/json'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

Future<SubmissionQueue> _openQueue(String name) async =>
    SubmissionQueue(await Hive.openBox<dynamic>(name));

void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('ff_coord_test');
    Hive.init(directory.path);
  });

  tearDown(() async {
    await Hive.close();
    await directory.delete(recursive: true);
  });

  FieldFormsCoordinator coordinator(
    SubmissionQueue queue,
    _FakeAdapter adapter,
  ) {
    final dio = Dio(BaseOptions(baseUrl: 'http://test.invalid'));
    dio.httpClientAdapter = adapter;
    return FieldFormsCoordinator(queue: queue, api: FieldFormsApi(dio));
  }

  test('201 settles FIFO item and sends device identity header', () async {
    final queue = await _openQueue('q1');
    await queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: 'a',
      assignmentRevision: 1,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: const {'x': 1},
    );
    final adapter = _FakeAdapter([201]);
    expect(await coordinator(queue, adapter).drain(), 1);
    expect(queue.pending(), isEmpty);
    expect(adapter.lastDeviceId, startsWith('dev-'));
  });

  test('network error increments attempts and preserves instance id', () async {
    final queue = await _openQueue('q2');
    final item = await queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: 'a',
      assignmentRevision: 1,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: const {},
    );
    final adapter = _FakeAdapter([
      DioException(
        requestOptions: RequestOptions(),
        type: DioExceptionType.connectionError,
      ),
    ]);
    expect(await coordinator(queue, adapter).drain(), 0);
    final kept = queue.pending().single;
    expect(kept.instanceId, item.instanceId);
    expect(kept.attempts, 1);
  });

  test('401 increments first item and stops before second', () async {
    final queue = await _openQueue('q3');
    final first = await queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: 'a',
      assignmentRevision: 1,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: const {'n': 1},
    );
    await Future<void>.delayed(const Duration(milliseconds: 2));
    final second = await queue.enqueue(
      tenantId: 't',
      fieldId: 'f',
      assignmentId: 'a2',
      assignmentRevision: 1,
      formVersionId: 'v',
      schemaHash: 'h',
      answers: const {'n': 2},
    );
    final adapter = _FakeAdapter([401]);
    expect(await coordinator(queue, adapter).drain(), 0);
    expect(adapter.calls, 1);
    final pending = queue.pending();
    expect(pending[0].instanceId, first.instanceId);
    expect(pending[0].attempts, 1);
    expect(pending[1].instanceId, second.instanceId);
    expect(pending[1].attempts, 0);
  });
}
