// ScoutingApi مقابل ApiClient الحقيقيّ والمحوّل المزيّف: المسارات، الأشكال،
// مفتاح Idempotency-Key، وحقل field_id في multipart كشف الآفات.
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';

void main() {
  group('shared photo evidence', () {
    test('bytes sent with digest, and exact receipt required', () async {
      const id = 'p1';
      final bytes = Uint8List.fromList([255, 216, 255, 217]);
      final digest = crypto.sha256.convert(bytes).toString();
      final (api, adapter) = fakeApi((o) async => FakeReply(200, {
        'evidence_id': 'e1', 'field_id': 'f1', 'pin_id': id,
        'sha256': digest, 'persisted': true,
        'verification_state': 'bytes_verified', 'review_state': 'unreviewed',
      }));
      final receipt = await api.uploadPinPhoto(
        fieldId: 'f1', pinId: id, bytes: bytes, filename: 'leaf.jpg');
      expect(receipt['sha256'], digest);
      expect(adapter.requests.single.path, scoutingPhotoPath('f1', id));
      expect(adapter.requests.single.headers['X-Content-SHA256'], digest);
      expect(adapter.requests.single.data, bytes);
    });

    test('an unrelated photo 2xx is not a saved photo', () async {
      final (api, _) = fakeApi((o) async => const FakeReply(200, {
        'evidence_id': 'e1', 'field_id': 'f1', 'pin_id': 'wrong',
        'persisted': true, 'sha256': 'nope',
        'verification_state': 'bytes_verified', 'review_state': 'unreviewed',
      }));
      expect(api.uploadPinPhoto(fieldId: 'f1', pinId: 'p1',
        bytes: Uint8List.fromList([1, 2]), filename: 'a.jpg'),
        throwsA(isA<FormatException>()));
    });

    test('remote viewing requires trusted HTTPS expiring link', () async {
      final (api, _) = fakeApi((o) async => const FakeReply(200, {
        'field_id': 'f1', 'pin_id': 'p1', 'persisted': true,
        'verification_state': 'bytes_verified', 'url': 'http://bad/image',
      }));
      expect(api.photoForPin('f1', 'p1'), throwsA(isA<FormatException>()));
    });
  });

  group('authoritative photo context', () {
    test('requires exact source and keeps pesticide decision unauthorized', () async {
      final (api, adapter) = fakeApi((o) async => const FakeReply(200, {
        'schema': 'sahool.scout-photo-evidence-context/v1',
        'source': {'kind': 'scouting_pin', 'field_id': 'f1', 'pin_id': 'p1'},
        'evidence': {'field_id': 'f1', 'pin_id': 'p1', 'persisted': true,
          'verification_state': 'bytes_verified', 'review_state': 'unreviewed'},
        'object_state': 'present_at_check',
        'inspection': {'state': 'not_linked'},
        'season': {'state': 'explicit_link_required', 'season_id': null},
        'detection': {'state': 'explicit_link_required', 'result_id': null},
        'decision': {'state': 'not_authorized', 'decision_id': null},
        'automatic_pesticide_action_authorized': false,
      }));
      final context = await api.photoEvidenceContext('f1', 'p1');
      expect(context['inspection'], {'state': 'not_linked'});
      expect(adapter.requests.single.path, '${scoutingPhotoPath('f1', 'p1')}/context');
    });

    test('rejects cross-field context and false action authority', () async {
      final (api, _) = fakeApi((o) async => const FakeReply(200, {
        'schema': 'sahool.scout-photo-evidence-context/v1',
        'source': {'kind': 'scouting_pin', 'field_id': 'other', 'pin_id': 'p1'},
        'evidence': {'field_id': 'f1', 'pin_id': 'p1', 'persisted': true,
          'verification_state': 'bytes_verified', 'review_state': 'unreviewed'},
        'object_state': 'present_at_check',
        'inspection': {'state': 'linked', 'task_id': 't1'},
        'season': {'state': 'explicit_link_required', 'season_id': null},
        'decision': {'state': 'authorized'},
        'automatic_pesticide_action_authorized': true,
      }));
      expect(api.photoEvidenceContext('f1', 'p1'), throwsA(isA<FormatException>()));
    });
  });

  group('attested model source links, not diagnostic approval', () {
    test('explicit unreviewed provenance is recognized, never upgraded', () {
      const eventId = 'e587bca2-c39a-453a-b722-d3454292ec77';
      final model = verifyScoutingPhotoDetectionContext({
        'state': 'linked_model_provenance_unreviewed',
        'result_id': 901, 'edge_result_id': 901, 'detection_provenance_id': 55,
        'link_event_id': eventId, 'model_id': 'onnx-model',
        'model_version': 'v1', 'input_sha256': List.filled(64, 'a').join(),
        'link_proof': 'scout_photo_detection_link_events:v261',
        'human_diagnosis_approved': false,
      });
      expect(model['human_diagnosis_approved'], false);
      expect(() => verifyScoutingPhotoDetectionContext({
        ...model, 'human_diagnosis_approved': true,
      }), throwsA(isA<FormatException>()));
      expect(() => verifyScoutingPhotoDetectionContext({
        ...model, 'link_proof': 'same-field-time',
      }), throwsA(isA<FormatException>()));
    });

    test('model-link POST keeps the same event id and forbids pesticide actions', () async {
      const id = 'e587bca2-c39a-453a-b722-d3454292ec77';
      final (api, adapter) = fakeApi((o) async => FakeReply(200, {
        'event_id': id, 'persisted': true, 'idempotent': false,
        'current': {
          'state': 'linked_model_provenance_unreviewed',
          'result_id': 901, 'edge_result_id': 901, 'detection_provenance_id': 55,
          'link_event_id': id, 'model_id': 'onnx-model', 'model_version': 'v1',
          'input_sha256': List.filled(64, 'a').join(),
          'link_proof': 'scout_photo_detection_link_events:v261',
          'human_diagnosis_approved': false,
        },
        'automatic_pesticide_action_authorized': false,
      }));
      final receipt = await api.appendPhotoDetectionLinkEvent(
        fieldId: 'f1', pinId: 'p1', eventId: id, action: 'link',
        detectionProvenanceId: 55,
        idempotencyKey: const IdempotencyKey('model-source-link-intent'),
      );
      expect(receipt['event_id'], id);
      expect(adapter.requests.single.path, '${scoutingPhotoPath('f1','p1')}/detection-link-events');
      expect(adapter.requests.single.data['detection_provenance_id'], 55);
    });
  });

  group('explicit photo-season linkage', () {
    test('recognizes accepted link but keeps it separate from a diagnosis', () {
      final result = verifyScoutingPhotoSeasonContext({
        'state': 'linked_accepted',
        'season_id': '72e29c4b-5ce2-46af-a5dc-502e3d41b8ed',
        'link_event_id': 'e587bca2-c39a-453a-b722-d3454292ec77',
        'link_proof': 'scout_photo_season_link_events:v257',
      });
      expect(result['state'], 'linked_accepted');
      expect(() => verifyScoutingPhotoSeasonContext({
        ...result, 'link_proof': 'time-proximity',
      }), throwsA(isA<FormatException>()));
    });

    test('rejects forged season ids and a revoked link naming a season', () {
      expect(() => verifyScoutingPhotoSeasonContext({
        'state': 'linked_accepted', 'season_id': 'other-field',
        'link_event_id': 'e587bca2-c39a-453a-b722-d3454292ec77',
        'link_proof': 'scout_photo_season_link_events:v257',
      }), throwsA(isA<FormatException>()));
      expect(() => verifyScoutingPhotoSeasonContext({
        'state': 'revoked', 'season_id': '72e29c4b-5ce2-46af-a5dc-502e3d41b8ed',
        'link_event_id': 'e587bca2-c39a-453a-b722-d3454292ec77',
      }), throwsA(isA<FormatException>()));
    });
  });

  group('human photo-season link event POST', () {
    test('requires the same event id and refuses action authority', () async {
      const id = 'e587bca2-c39a-453a-b722-d3454292ec77';
      const seasonId = '72e29c4b-5ce2-46af-a5dc-502e3d41b8ed';
      final (api, adapter) = fakeApi((o) async => const FakeReply(200, {
        'event_id': id, 'persisted': true, 'idempotent': false, 'is_current': true,
        'season': {'state': 'linked_accepted', 'season_id': seasonId,
          'link_event_id': id, 'link_proof': 'scout_photo_season_link_events:v257'},
        'automatic_pesticide_action_authorized': false,
      }));
      final saved = await api.appendPhotoSeasonLinkEvent(
        fieldId: 'f1', pinId: 'p1', eventId: id, action: 'link',
        seasonId: seasonId, idempotencyKey: const IdempotencyKey('same-intent'),
      );
      expect(saved['event_id'], id);
      expect(adapter.requests.single.path, '${scoutingPhotoPath('f1', 'p1')}/season-link-events');
      expect(adapter.requests.single.data['event_id'], id);
    });

    test('rejects unrelated event receipt', () async {
      const id = 'e587bca2-c39a-453a-b722-d3454292ec77';
      final (api, _) = fakeApi((o) async => const FakeReply(200, {
        'event_id': 'wrong-id', 'persisted': true, 'idempotent': false,
        'is_current': true, 'season': {'state': 'explicit_link_required', 'season_id': null},
        'automatic_pesticide_action_authorized': false,
      }));
      expect(api.appendPhotoSeasonLinkEvent(
        fieldId: 'f1', pinId: 'p1', eventId: id, action: 'link',
        seasonId: '72e29c4b-5ce2-46af-a5dc-502e3d41b8ed',
        idempotencyKey: const IdempotencyKey('same-intent'),
      ), throwsA(isA<FormatException>()));
    });
  });

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
            'field_id': 'f1',
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

    for (final response in [
      {'field_id': 'other', 'detections': []},
      {'field_id': 'f1', 'detections': [{}]},
      {'field_id': 'f1', 'detections': [{'class_name': 'rust', 'confidence': 2}]},
    ]) {
      test('refuses an invalid result $response', () async {
        final (api, _) = fakeApi((_) async => FakeReply(200, response));
        await expectLater(
          api.detectPest(fieldId: 'f1', bytes: Uint8List(1), filename: 'a.jpg'),
          throwsA(isA<FormatException>()),
        );
      });
    }

    test('matching provenance binds the result to the uploaded photo bytes', () async {
      final bytes = Uint8List.fromList([1, 2, 3, 4]);
      final digest = crypto.sha256.convert(bytes).toString();
      final (api, _) = fakeApi((_) async => FakeReply(200, {
        'field_id': 'f1',
        'model_version': 'pest-v2',
        'detections': [],
        'provenance': {
          'schema': 'sahool.detection-provenance/v1',
          'model_id': 'pest_detector_int8.onnx',
          'model_version': 'pest-v2',
          'artifact_sha256': 'a'.padRight(64, 'a'),
          'input_sha256': digest,
          'threshold': 0.6,
          'calibrated': false,
        },
      }));
      final result = await api.detectPest(fieldId: 'f1', bytes: bytes, filename: 'leaf.jpg');
      expect(result.imageVerified, isTrue);
    });

    test('rejects provenance from different image bytes', () async {
      final (api, _) = fakeApi((_) async => FakeReply(200, {
        'field_id': 'f1',
        'model_version': 'pest-v2',
        'detections': [{'class_name': 'rust', 'confidence': 0.9}],
        'provenance': {
          'schema': 'sahool.detection-provenance/v1',
          'model_id': 'pest_detector_int8.onnx',
          'model_version': 'pest-v2',
          'artifact_sha256': 'a'.padRight(64, 'a'),
          'input_sha256': 'b'.padRight(64, 'b'),
        },
      }));
      await expectLater(
        api.detectPest(fieldId: 'f1', bytes: Uint8List.fromList([1, 2]), filename: 'leaf.jpg'),
        throwsA(isA<FormatException>()),
      );
    });

    test('inconsistent provenance model version is refused', () async {
      final bytes = Uint8List.fromList([7, 8, 9]);
      final digest = crypto.sha256.convert(bytes).toString();
      final (api, _) = fakeApi((_) async => FakeReply(200, {
        'field_id': 'f1', 'model_version': 'current', 'detections': [],
        'provenance': {
          'schema': 'sahool.detection-provenance/v1',
          'model_id': 'pest_detector_int8.onnx',
          'model_version': 'stale',
          'artifact_sha256': 'a'.padRight(64, 'a'),
          'input_sha256': digest,
          'threshold': 0.7,
          'calibrated': false,
        },
      }));
      await expectLater(
        api.detectPest(fieldId: 'f1', bytes: bytes, filename: 'leaf.jpg'),
        throwsA(isA<FormatException>()),
      );
    });

    test('an invalid inference threshold is not accepted as provenance', () async {
      final bytes = Uint8List.fromList([7, 8, 9]);
      final (api, _) = fakeApi((_) async => FakeReply(200, {
        'field_id': 'f1', 'model_version': 'v1', 'detections': [],
        'provenance': {
          'schema': 'sahool.detection-provenance/v1',
          'model_id': 'pest_detector_int8.onnx',
          'model_version': 'v1',
          'artifact_sha256': 'a'.padRight(64, 'a'),
          'input_sha256': crypto.sha256.convert(bytes).toString(),
          'threshold': 1.5,
          'calibrated': false,
        },
      }));
      await expectLater(
        api.detectPest(fieldId: 'f1', bytes: bytes, filename: 'leaf.jpg'),
        throwsA(isA<FormatException>()),
      );
    });

    test('missing provenance stays explicitly unverified', () async {
      final (api, _) = fakeApi((_) async => const FakeReply(200, {
        'field_id': 'f1', 'model_version': 'v1', 'detections': [],
      }));
      final result = await api.detectPest(fieldId: 'f1', bytes: Uint8List(1), filename: 'leaf.jpg');
      expect(result.imageVerified, isFalse);
    });

    test('malformed model artifact provenance is refused', () async {
      final (api, _) = fakeApi((_) async => const FakeReply(200, {
        'field_id': 'f1', 'model_version': 'v1', 'detections': [],
        'provenance': {'schema': 'sahool.detection-provenance/v1', 'input_sha256': 'bad'},
      }));
      await expectLater(
        api.detectPest(fieldId: 'f1', bytes: Uint8List(1), filename: 'leaf.jpg'),
        throwsA(isA<FormatException>()),
      );
    });

    test('missing detections list is a shape error, not "no pests"', () async {
      final (api, _) = fakeApi((o) async => const FakeReply(200, {'field_id': 'f1'}));
      expect(
        api.detectPest(fieldId: 'f1', bytes: Uint8List(1), filename: 'a.jpg'),
        throwsA(isA<FormatException>()),
      );
    });
  });
}
