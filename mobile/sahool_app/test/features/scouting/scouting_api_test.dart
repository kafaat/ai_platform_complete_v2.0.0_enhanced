// ScoutingApi مقابل ApiClient الحقيقيّ والمحوّل المزيّف: المسارات، الأشكال،
// مفتاح Idempotency-Key، وحقل field_id في multipart كشف الآفات.
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

void main() {
  group('listPins', () {
    test(
      'reads {pins, note_ar} from GET /api/v1/scouting/pins?field_id',
      () async {
        final (api, adapter) = fakeApi(
          (o) async => FakeReply(200, {
            'field_id': 'f1',
            'pins': [pinJson('p1', note: 'منّ على الأوراق')],
            'total': 1,
          }),
        );
        final page = await api.listPins('f1');
        expect(adapter.requests.single.path, '/api/v1/scouting/pins');
        final uri = adapter.requests.single;
        expect(uri.method, 'GET');
        expect(page.pins.single.pinId, 'p1');
        expect(page.pins.single.noteAr, 'منّ على الأوراق');
        expect(page.pins.single.severity?.wire, 'high');
        expect(page.noteAr, isNull);
      },
    );

    test('passes field_id as a query parameter', () async {
      RequestOptions? seen;
      final (api, _) = fakeApi((o) async {
        seen = o;
        return const FakeReply(200, {'pins': [], 'total': 0});
      });
      await api.listPins('f 1');
      expect(seen!.queryParameters, {'field_id': 'f 1'});
    });

    test('keeps the server note when the database is not enabled', () async {
      final (api, _) = fakeApi(
        (o) async => const FakeReply(200, {
          'field_id': 'f1',
          'pins': [],
          'total': 0,
          'note_ar': 'القاعدة غير مفعّلة (DATABASE_URL) — لا دبابيس مُخزَّنة',
        }),
      );
      final page = await api.listPins('f1');
      expect(page.pins, isEmpty);
      expect(page.noteAr, contains('القاعدة غير مفعّلة'));
    });

    test(
      'a pin without coordinates is a shape error, not a pin at 0,0',
      () async {
        final (api, _) = fakeApi(
          (o) async => const FakeReply(200, {
            'pins': [
              {'pin_id': 'p1', 'issue_category': 'pest'},
            ],
          }),
        );
        expect(api.listPins('f1'), throwsA(isA<FormatException>()));
      },
    );

    test('pins not a list is a shape error', () async {
      final (api, _) = fakeApi(
        (o) async => const FakeReply(200, {'pins': 'nope'}),
      );
      expect(api.listPins('f1'), throwsA(isA<FormatException>()));
    });
  });

  test('cropIssues reads issues for one crop', () async {
    RequestOptions? seen;
    final (api, _) = fakeApi((o) async {
      seen = o;
      return const FakeReply(200, {
        'crop': 'wheat',
        'issues': [
          {'code': 'wheat.rust', 'category': 'disease', 'name_ar': 'صدأ القمح'},
          {'code': 'wheat.aphid', 'category': 'pest', 'name_ar': 'منّ القمح'},
        ],
      });
    });
    final issues = await api.cropIssues('wheat');
    expect(seen!.path, '/api/v1/scouting/taxonomy');
    expect(seen!.queryParameters, {'crop': 'wheat'});
    expect(issues.map((i) => i.code), ['wheat.rust', 'wheat.aphid']);
  });

  test(
    'createPin posts to /fields/{id}/pins with the idempotency key',
    () async {
      final (api, adapter) = fakeApi(
        (o) async => FakeReply(200, {...pinJson('k1'), 'persisted': true}),
      );
      final r = await api.createPin('f1', {
        'pin_id': 'k1',
        'field_id': 'f1',
      }, idempotencyKey: const IdempotencyKey('k1'));
      final req = adapter.requests.single;
      expect(req.method, 'POST');
      expect(req.path, '/api/v1/fields/f1/pins');
      expect(req.headers['Idempotency-Key'], 'k1');
      expect(r['persisted'], isTrue);
    },
  );

  group('detectPest', () {
    test('sends field_id as a multipart form field (422 without it)', () async {
      final (api, adapter) = fakeApi(
        (o) async => const FakeReply(200, {
          'field_id': 'f1',
          'detections': [],
          'sync_status': 'synced',
        }),
      );
      await api.detectPest(
        fieldId: 'f1',
        bytes: Uint8List.fromList([1, 2, 3]),
        filename: 'leaf.jpg',
        crop: 'wheat',
      );
      final req = adapter.requests.single;
      expect(req.path, '/api/edge/v1/inference/pest-detect');
      expect(req.method, 'POST');
      final form = req.data! as FormData;
      final fields = {for (final e in form.fields) e.key: e.value};
      expect(fields['field_id'], 'f1');
      expect(fields['crop'], 'wheat');
      final file = form.files.single;
      expect(file.key, 'file');
      expect(file.value.filename, 'leaf.jpg');
      // الحافّة ترفض 415 ما لا يبدأ بـimage/.
      expect(file.value.contentType?.mimeType, 'image/jpeg');
    });

    test('refuses to send without a field', () {
      final (api, adapter) = fakeApi((o) async => const FakeReply(200, {}));
      expect(
        () =>
            api.detectPest(fieldId: '', bytes: Uint8List(1), filename: 'a.jpg'),
        throwsArgumentError,
      );
      expect(adapter.requests, isEmpty);
    });

    test(
      'parses labels and confidence exactly as the server sent them',
      () async {
        final (api, _) = fakeApi(
          (o) async => const FakeReply(200, {
            'detections': [
              {
                'class_name': 'aphid',
                'arabic_name': 'منّ',
                'confidence': 0.91,
                'severity': 'medium',
              },
            ],
            'alert_ar': 'تنبيه',
            'model_version': 'v1',
            'sync_status': 'queued',
          }),
        );
        final r = await api.detectPest(
          fieldId: 'f1',
          bytes: Uint8List(1),
          filename: 'a.png',
        );
        expect(r.detections.single.labelAr, 'منّ');
        expect(r.detections.single.confidence, 0.91);
        expect(r.alertAr, 'تنبيه');
        expect(r.syncStatus, 'queued');
      },
    );

    test(
      '503 (model not provisioned) surfaces as ApiException with detail',
      () async {
        final (api, _) = fakeApi(
          (o) async =>
              unavailable('نموذج كشف الآفات غير مُجهَّز على هذه الحافة'),
        );
        await expectLater(
          api.detectPest(fieldId: 'f1', bytes: Uint8List(1), filename: 'a.jpg'),
          throwsA(
            isA<ApiException>()
                .having((e) => e.statusCode, 'status', 503)
                .having((e) => e.detail, 'detail', contains('غير مُجهَّز')),
          ),
        );
      },
    );

    test('missing detections list is a shape error, not "no pests"', () async {
      final (api, _) = fakeApi((o) async => const FakeReply(200, {'x': 1}));
      expect(
        api.detectPest(fieldId: 'f1', bytes: Uint8List(1), filename: 'a.jpg'),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
