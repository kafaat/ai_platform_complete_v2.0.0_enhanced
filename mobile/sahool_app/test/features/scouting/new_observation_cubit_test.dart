// تدفّق «مشاهدة جديدة»: التحقّق، مسار رفض GPS ومركز الحقل، والإرسال/الإيداع
// دون اتّصال مع احترام إيصال صندوق الإرسال.
import 'dart:async';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' as crypto;
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/scouting/data/device_sources.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';
import 'package:sahool_app/features/scouting/data/scouting_models.dart';
import 'package:sahool_app/features/scouting/presentation/new_observation_cubit.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

void main() {
  late FakeOutbox outbox;
  late MemoryPhotoStore store;

  setUp(() {
    outbox = FakeOutbox();
    store = MemoryPhotoStore();
  });

  NewObservationCubit make(
    FakeHandler handler, {
    GpsResult gps = const GpsFix(lat: 15.36, lng: 44.21, accuracyM: 8),
    bool online = true,
    ScoutingField field = sanaaField,
    PhotoCapturer? photos,
  }) {
    final (api, _) = fakeApi(handler);
    return NewObservationCubit(
      field: field,
      api: api,
      location: FakeLocation(gps),
      photos: photos ?? FakePhotos(photo: jpegPhoto()),
      photoStore: store,
      outbox: outbox,
      connectivity: connectivity(online: online),
      idempotencyKey: const IdempotencyKey('key-1'),
      photoIdempotencyKey: const IdempotencyKey('photo-key-1'),
    );
  }

  Future<FakeReply> taxonomyOr(
    RequestOptions o,
    Future<FakeReply> Function() other,
  ) async {
    if (o.path == '/api/v1/scouting/taxonomy') {
      return const FakeReply(200, {'crop': 'wheat', 'issues': []});
    }
    return other();
  }

  /// إيصال scout-ingest الصحيح لطلب صورة [o] (بصمته من ترويسته).
  FakeReply photoReceipt(RequestOptions o, {String pinId = 'key-1'}) =>
      FakeReply(200, {
        'evidence_id': 'e1',
        'field_id': 'f1',
        'pin_id': pinId,
        'sha256': o.headers['X-Content-SHA256'],
        'persisted': true,
        'verification_state': 'bytes_verified',
        'review_state': 'unreviewed',
      });

  final photoPath = scoutingPhotoPath('f1', 'key-1');

  group('validation', () {
    test(
      'requires location, category and severity and sends nothing',
      () async {
        var posts = 0;
        final c = make(
          (o) async => taxonomyOr(o, () async {
            posts++;
            return const FakeReply(200, {});
          }),
          gps: const GpsFailure(GpsFailureReason.denied),
        );
        await c.start();
        await c.submit();
        expect(c.state.errors.keys, {
          ObservationField.location,
          ObservationField.category,
          ObservationField.severity,
        });
        expect(posts, 0);
        expect(outbox.ops, isEmpty);
      },
    );

    test(
      'a location outside Yemen is rejected before it is queued forever',
      () async {
        final c = make(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
          gps: const GpsFix(lat: 48.85, lng: 2.35, accuracyM: 5),
          online: false,
        );
        await c.start();
        c
          ..selectCategory(IssueCategory.pest)
          ..selectSeverity(PinSeverity.high);
        await c.submit();
        expect(
          c.state.errors[ObservationField.location],
          contains('خارج حدود اليمن'),
        );
        expect(outbox.ops, isEmpty);
      },
    );
  });

  group('GPS', () {
    test(
      'denied permission is reported honestly and leaves no coordinates',
      () async {
        final c = make(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
          gps: const GpsFailure(GpsFailureReason.denied),
        );
        await c.start();
        expect(c.state.locationMode, LocationMode.failed);
        expect(c.state.hasLocation, isFalse);
        expect(c.state.gpsFailure!.messageAr, contains('مرفوض'));
      },
    );

    test('field centre fallback is explicit and carries no accuracy', () async {
      final c = make(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
        gps: const GpsFailure(GpsFailureReason.timeout),
      );
      await c.start();
      c.useFieldCentre();
      expect(c.state.locationMode, LocationMode.fieldCentre);
      expect(c.state.lat, sanaaField.centerLat);
      expect(c.state.lng, sanaaField.centerLng);
      expect(c.state.accuracyM, isNull);
    });

    test('a field without a centre offers no fallback coordinates', () async {
      final c = make(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
        gps: const GpsFailure(GpsFailureReason.denied),
        field: noCentreField,
      );
      await c.start();
      c.useFieldCentre();
      expect(c.state.hasLocation, isFalse);
    });

    test('a failed re-locate keeps the previous good fix', () async {
      final (api, _) = fakeApi(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
      );
      final loc = FakeLocation(
        const GpsFix(lat: 15.3, lng: 44.2, accuracyM: 4),
      );
      final c = NewObservationCubit(
        field: sanaaField,
        api: api,
        location: loc,
        photos: FakePhotos(),
        photoStore: store,
        outbox: outbox,
        connectivity: connectivity(online: true),
      );
      await c.start();
      loc.result = const GpsFailure(GpsFailureReason.timeout);
      await c.locate();
      expect(c.state.locationMode, LocationMode.gps);
      expect(c.state.lat, 15.3);
      expect(c.state.gpsFailure, isNotNull);
    });
  });

  Future<NewObservationCubit> ready(
    FakeHandler handler, {
    bool online = true,
  }) async {
    final c = make(handler, online: online);
    await c.start();
    c
      ..selectCategory(IssueCategory.disease)
      ..selectSeverity(PinSeverity.medium)
      ..setNote('  بقع صفراء  ');
    return c;
  }

  group('submit', () {
    test(
      'online success posts the PinCreateRequest body with pin_id == key',
      () async {
        Map<String, dynamic>? body;
        String? key;
        final c = await ready(
          (o) async => taxonomyOr(o, () async {
            if (o.path == photoPath) return photoReceipt(o);
            body = Map<String, dynamic>.from(o.data as Map);
            key = o.headers['Idempotency-Key'] as String?;
            return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
          }),
        );
        await c.capturePhoto();
        await c.submit();
        expect(c.state.outcome, SubmitOutcome.sent);
        expect(key, 'key-1');
        expect(body, {
          'pin_id': 'key-1',
          'field_id': 'f1',
          'lat': 15.36,
          'lng': 44.21,
          'issue_category': 'disease',
          'severity': 'medium',
          'status': 'new',
          'persistence': 'seasonal',
          'crop': 'wheat',
          'note_ar': 'بقع صفراء',
          'location_source': 'gps',
          'accuracy_m': 8.0,
        });
        // لا مسار ملفّ محلّيّ في photo_uri ولا صورة في جسم الدبّوس: للصورة إيصالها
        // المستقلّ من scout-ingest (v260).
        expect(body!.containsKey('photo_uri'), isFalse);
        expect(body!.containsKey('photo'), isFalse);
        expect(c.state.photoUpload, PhotoUpload.uploaded);
        expect(outbox.ops, isEmpty);
      },
    );

    test(
      'offline: enqueues observation_create and reports queued only on receipt.queued',
      () async {
        var posts = 0;
        final c = await ready(
          (o) async => taxonomyOr(o, () async {
            posts++;
            return const FakeReply(200, {});
          }),
          online: false,
        );
        await c.submit();
        expect(posts, 0);
        expect(c.state.outcome, SubmitOutcome.queued);
        expect(c.state.outcomeMessage, contains('محفوظ للإرسال'));
        final op = outbox.ops.single;
        expect(op.kind, 'observation_create');
        expect(op.method, 'POST');
        expect(op.path, '/api/v1/fields/f1/pins');
        expect(op.idempotencyKey, 'key-1');
        expect(op.body['pin_id'], 'key-1');
        expect(op.fieldId, 'f1');
      },
    );

    test(
      'offline with an unavailable outbox is an honest failure, never "saved"',
      () async {
        outbox.receipt = const OutboxReceipt.notQueued(
          'offline_queue_unavailable',
        );
        final c = await ready(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
          online: false,
        );
        await c.submit();
        expect(c.state.outcome, SubmitOutcome.failed);
        expect(c.state.outcomeMessage, isNot(contains('محفوظ للإرسال')));
        expect(c.state.outcomeMessage, contains('لم تُحفظ'));
        // يمكن إعادة المحاولة (ليست ملتزَمة).
        expect(c.state.submitting, isFalse);
      },
    );

    test('a transient network failure falls back to the outbox', () async {
      final c = await ready(
        (o) async => taxonomyOr(o, () async => connectionFailure),
      );
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.queued);
      expect(outbox.ops, hasLength(1));
    });

    test('503 after retries falls back to the outbox', () async {
      final c = await ready(
        (o) async => taxonomyOr(o, () async => unavailable('db down')),
      );
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.queued);
    });

    test(
      'server validated but did not persist (persisted=false) ⇒ queued for retry',
      () async {
        final c = await ready(
          (o) async => taxonomyOr(
            o,
            () async =>
                FakeReply(200, {...pinJson('key-1'), 'persisted': false}),
          ),
        );
        await c.submit();
        expect(c.state.outcome, SubmitOutcome.queued);
        expect(c.state.outcomeMessage, contains('لم يحفظها'));
        expect(outbox.ops.single.idempotencyKey, 'key-1');
      },
    );

    test('422 is shown with the server text and is never queued', () async {
      final c = await ready(
        (o) async => taxonomyOr(
          o,
          () async => const FakeReply(422, {'detail': 'الشدّة غير صالحة: x'}),
        ),
      );
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.failed);
      expect(c.state.outcomeMessage, 'الشدّة غير صالحة: x');
      expect(outbox.ops, isEmpty);
    });

    test('double submit sends once', () async {
      var posts = 0;
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          posts++;
          await Future<void>.delayed(const Duration(milliseconds: 10));
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await Future.wait([c.submit(), c.submit()]);
      await c.submit();
      expect(posts, 1);
    });
  });

  group('photo', () {
    test(
      'kept on device under the pin id; discarded if the form is abandoned',
      () async {
        final c = make(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
        );
        await c.capturePhoto();
        expect(c.state.photoPath, '/local/key-1.jpg');
        await c.close();
        expect(store.discarded, ['/local/key-1.jpg']);
      },
    );

    test('camera permission denial is shown, not swallowed', () async {
      final c = make(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
        photos: FakePhotos(
          error: const PhotoCaptureException('إذن الكاميرا مرفوض'),
        ),
      );
      await c.capturePhoto();
      expect(c.state.photoError, 'إذن الكاميرا مرفوض');
      expect(c.state.photoPath, isNull);
    });
  });

  group('location source (v257)', () {
    test('field centre is sent as field_centroid with no accuracy', () async {
      Map<String, dynamic>? body;
      final c = make(
        (o) async => taxonomyOr(o, () async {
          body = Map<String, dynamic>.from(o.data as Map);
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.start();
      c
        ..useFieldCentre()
        ..selectCategory(IssueCategory.pest)
        ..selectSeverity(PinSeverity.low);
      await c.submit();
      expect(body!['location_source'], 'field_centroid');
      expect(body!.containsKey('accuracy_m'), isFalse);
      expect(body!['lat'], sanaaField.centerLat);
    });

    test(
      'a GPS reply that arrives after the manual choice does not overwrite it',
      () async {
        final gps = Completer<GpsResult>();
        final (api, _) = fakeApi(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
        );
        final c = NewObservationCubit(
          field: sanaaField,
          api: api,
          location: _PendingLocation(gps.future),
          photos: FakePhotos(),
          photoStore: store,
          outbox: outbox,
          connectivity: connectivity(online: false),
          idempotencyKey: const IdempotencyKey('key-1'),
        );
        final started = c.start();
        await Future<void>.delayed(Duration.zero);
        expect(c.state.locationMode, LocationMode.locating);
        c.useFieldCentre();
        gps.complete(const GpsFix(lat: 15.9, lng: 44.9, accuracyM: 3));
        await started;
        expect(c.state.locationMode, LocationMode.fieldCentre);
        expect(c.state.lat, sanaaField.centerLat);
        expect(c.state.lng, sanaaField.centerLng);
        expect(c.state.accuracyM, isNull);
        c
          ..selectCategory(IssueCategory.pest)
          ..selectSeverity(PinSeverity.low);
        await c.submit();
        final body = outbox.ops.single.body;
        expect(body['location_source'], 'field_centroid');
        expect(body['lat'], sanaaField.centerLat);
        expect(body.containsKey('accuracy_m'), isFalse);
      },
    );

    test('a late GPS failure does not clear the manual choice', () async {
      final gps = Completer<GpsResult>();
      final (api, _) = fakeApi(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
      );
      final c = NewObservationCubit(
        field: sanaaField,
        api: api,
        location: _PendingLocation(gps.future),
        photos: FakePhotos(),
        photoStore: store,
        outbox: outbox,
        connectivity: connectivity(online: true),
      );
      final started = c.start();
      await Future<void>.delayed(Duration.zero);
      c.useFieldCentre();
      gps.complete(const GpsFailure(GpsFailureReason.timeout));
      await started;
      expect(c.state.locationMode, LocationMode.fieldCentre);
      expect(c.state.gpsFailure, isNull);
    });

    test('pressing GPS again after the manual choice is honoured', () async {
      final loc = FakeLocation(const GpsFailure(GpsFailureReason.timeout));
      final (api, _) = fakeApi(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
      );
      final c = NewObservationCubit(
        field: sanaaField,
        api: api,
        location: loc,
        photos: FakePhotos(),
        photoStore: store,
        outbox: outbox,
        connectivity: connectivity(online: true),
      );
      await c.start();
      c.useFieldCentre();
      loc.result = const GpsFix(lat: 15.4, lng: 44.3, accuracyM: 6);
      await c.locate();
      expect(c.state.locationMode, LocationMode.gps);
      expect(c.state.accuracyM, 6);
      c
        ..selectCategory(IssueCategory.weed)
        ..selectSeverity(PinSeverity.low);
      expect(c.buildBody()['location_source'], 'gps');
      expect(c.buildBody()['accuracy_m'], 6);
    });
  });

  group('photo evidence upload (v260, scout-ingest)', () {
    test(
      'online: the photo follows the pin with its own key, raw bytes and digest',
      () async {
        final posts = <RequestOptions>[];
        final c = await ready(
          (o) async => taxonomyOr(o, () async {
            posts.add(o);
            if (o.path == photoPath) return photoReceipt(o);
            return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
          }),
        );
        await c.capturePhoto();
        await c.submit();
        expect(posts, hasLength(2));
        expect(posts[0].path, scoutingPinCreatePath('f1'));
        expect(posts[0].headers['Idempotency-Key'], 'key-1');
        expect(posts[1].path, photoPath);
        expect(posts[1].headers['Idempotency-Key'], 'photo-key-1');
        expect(posts[1].data, store.bytes);
        expect(
          posts[1].headers['X-Content-SHA256'],
          crypto.sha256.convert(store.bytes).toString(),
        );
        expect((posts[0].data as Map).containsKey('photo'), isFalse);
        expect(c.state.photoUpload, PhotoUpload.uploaded);
        expect(c.state.outcome, SubmitOutcome.sent);
        expect(c.state.outcomeMessage, contains('رُفعت الصورة'));
        expect(outbox.ops, isEmpty);
      },
    );

    test(
      'offline: pin op then photo op for the same field; the photo op holds the digest, not bytes',
      () async {
        final c = await ready(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
          online: false,
        );
        await c.capturePhoto();
        await c.submit();
        expect(c.state.outcome, SubmitOutcome.queued);
        expect(outbox.ops.map((o) => o.kind), [
          'observation_create',
          kObservationPhotoKind,
        ]);
        final pin = outbox.ops[0];
        final photo = outbox.ops[1];
        expect(photo.kind, 'observation_photo_upload');
        expect(photo.idempotencyKey, 'photo-key-1');
        expect(photo.path, photoPath);
        expect(photo.fieldId, pin.fieldId);
        expect(photo.body, {
          'field_id': 'f1',
          'pin_id': 'key-1',
          'sha256': crypto.sha256.convert(store.bytes).toString(),
        });
        expect(c.state.photoUpload, PhotoUpload.queued);
        expect(c.state.outcomeMessage, contains('بانتظار الرفع'));
        // الدبّوس ملتزَم: إغلاق النموذج لا يحذف الصورة المنتظرة.
        await c.close();
        expect(store.discarded, isEmpty);
      },
    );

    test('a transient failure of the photo request queues only the photo', () async {
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          if (o.path == photoPath) return connectionFailure;
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.sent);
      expect(c.state.photoUpload, PhotoUpload.queued);
      expect(outbox.ops.single.kind, kObservationPhotoKind);
      expect(outbox.ops.single.idempotencyKey, 'photo-key-1');
      expect(store.discarded, isEmpty);
    });

    test('a 2xx that does not match these bytes is not an upload: it is queued', () async {
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          if (o.path == photoPath) return photoReceipt(o, pinId: 'someone-else');
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.photoUpload, PhotoUpload.queued);
      expect(outbox.ops.single.kind, kObservationPhotoKind);
    });

    test('a server refusal of the photo is shown and never queued', () async {
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          if (o.path == photoPath) {
            return const FakeReply(415, {'detail': 'photo_decode_failed'});
          }
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.sent);
      expect(c.state.photoUpload, PhotoUpload.failed);
      expect(c.state.outcomeMessage, contains('لم تُرفع الصورة'));
      expect(outbox.ops, isEmpty);
    });

    test('after a refused photo, submit retries the photo only, never the pin', () async {
      var photoCalls = 0;
      var pinCalls = 0;
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          if (o.path == photoPath) {
            photoCalls++;
            return photoCalls == 1
                ? const FakeReply(404, {'detail': 'scout_media_disabled'})
                : photoReceipt(o);
          }
          pinCalls++;
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.photoUpload, PhotoUpload.failed);
      await c.submit();
      expect(pinCalls, 1);
      expect(photoCalls, 2);
      expect(c.state.photoUpload, PhotoUpload.uploaded);
    });

    test('if the photo upload and its queueing both fail, the pin stays acknowledged', () async {
      outbox.receipt = const OutboxReceipt.notQueued('store_failed');
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          if (o.path == photoPath) {
            return const FakeReply(503, {'detail': 'scout_photo_store_unavailable'});
          }
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.sent);
      expect(c.state.photoUpload, PhotoUpload.failed);
      expect(store.discarded, isEmpty);
      await c.close();
      expect(store.discarded, isEmpty);
    });

    test('the photo is frozen once the pin is committed', () async {
      final c = await ready(
        (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
        online: false,
      );
      await c.capturePhoto();
      await c.submit();
      final kept = c.state.photoPath;
      await c.removePhoto();
      await c.capturePhoto();
      expect(c.state.photoPath, kept);
      expect(store.discarded, isEmpty);
    });

    test('a photo over the server limit is not sent', () async {
      var posts = 0;
      store.bytes = Uint8List(kMaxPinPhotoBytes + 1);
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          posts++;
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(posts, 1, reason: 'only the pin');
      expect(c.state.photoUpload, PhotoUpload.failed);
      expect(outbox.ops, isEmpty);
    });

    test('no photo ⇒ no second request and no upload state', () async {
      var posts = 0;
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          posts++;
          return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
        }),
      );
      await c.submit();
      expect(posts, 1);
      expect(c.state.photoUpload, PhotoUpload.none);
    });
  });

  test('taxonomy issues are offered only for the chosen category', () async {
    final (api, _) = fakeApi(
      (o) async => const FakeReply(200, {
        'crop': 'wheat',
        'issues': [
          {'code': 'wheat.rust', 'category': 'disease', 'name_ar': 'صدأ القمح'},
          {'code': 'wheat.aphid', 'category': 'pest', 'name_ar': 'منّ القمح'},
        ],
      }),
    );
    final c = NewObservationCubit(
      field: sanaaField,
      api: api,
      location: FakeLocation(const GpsFix(lat: 15.3, lng: 44.2)),
      photos: FakePhotos(),
      photoStore: store,
      outbox: outbox,
      connectivity: connectivity(online: true),
    );
    await c.start();
    c.selectCategory(IssueCategory.pest);
    expect(c.state.issuesForCategory.map((i) => i.code), ['wheat.aphid']);
    c.selectIssue('wheat.aphid');
    c.selectCategory(IssueCategory.disease);
    expect(c.state.issueCode, isNull, reason: 'changing category clears issue');
  });
}

/// موقع يردّ متى أُكمل المستقبل — لمحاكاة ردّ GPS متأخّر.
class _PendingLocation implements LocationSource {
  _PendingLocation(this._result);
  final Future<GpsResult> _result;

  @override
  Future<GpsResult> current() => _result;

  @override
  Future<void> openSettings(GpsFailureReason reason) async {}
}
