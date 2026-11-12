// تدفّق «مشاهدة جديدة»: التحقّق، مسار رفض GPS ومركز الحقل، والإرسال/الإيداع
// دون اتّصال مع احترام إيصال صندوق الإرسال.
import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/scouting/data/device_sources.dart';
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
            body ??= Map<String, dynamic>.from(o.data as Map);
            key ??= o.headers['Idempotency-Key'] as String?;
            return FakeReply(200, {
              ...pinJson('key-1'),
              'persisted': true,
              'photo': {'document_id': 'pinph_1', 'status': 'stored'},
            });
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
        // لا مسار ملفّ محلّيّ في photo_uri؛ الصورة تُرفع ببايتاتها في طلب ثانٍ.
        expect(body!.containsKey('photo_uri'), isFalse);
        expect(body!.containsKey('photo'), isFalse);
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

  group('photo upload (v257)', () {
    test(
      'online: the photo follows the pin with its own key and is reported uploaded',
      () async {
        final posts = <RequestOptions>[];
        final c = await ready(
          (o) async => taxonomyOr(o, () async {
            posts.add(o);
            final hasPhoto = (o.data as Map).containsKey('photo');
            return FakeReply(200, {
              ...pinJson('key-1'),
              'persisted': true,
              'photo': hasPhoto
                  ? {'document_id': 'pinph_1', 'status': 'stored'}
                  : null,
            });
          }),
        );
        await c.capturePhoto();
        await c.submit();
        expect(posts, hasLength(2));
        expect(posts[0].headers['Idempotency-Key'], 'key-1');
        expect(posts[1].headers['Idempotency-Key'], 'photo-key-1');
        final photoBody = Map<String, dynamic>.from(posts[1].data as Map);
        final pinBody = Map<String, dynamic>.from(posts[0].data as Map);
        expect(
          Map<String, dynamic>.from(photoBody)..remove('photo'),
          pinBody,
          reason: 'the photo request repeats the pin body exactly',
        );
        expect(
          base64Decode((photoBody['photo'] as Map)['content_b64'] as String),
          store.bytes,
        );
        expect(c.state.photoUpload, PhotoUpload.uploaded);
        expect(c.state.outcome, SubmitOutcome.sent);
        expect(c.state.outcomeMessage, contains('رُفعت الصورة'));
        expect(outbox.ops, isEmpty);
      },
    );

    test(
      'offline: pin op then photo op for the same field, both kept on the device',
      () async {
        final c = await ready(
          (o) async => taxonomyOr(o, () async => const FakeReply(200, {})),
          online: false,
        );
        await c.capturePhoto();
        await c.submit();
        expect(outbox.ops.map((o) => o.kind), [
          'observation_create',
          'observation_photo',
        ]);
        final pin = outbox.ops[0];
        final photo = outbox.ops[1];
        expect(photo.idempotencyKey, 'photo-key-1');
        expect(photo.path, pin.path);
        expect(photo.fieldId, pin.fieldId);
        expect(
          Map<String, dynamic>.from(photo.body)..remove('photo'),
          pin.body,
        );
        expect((photo.body['photo'] as Map)['content_b64'], isNotEmpty);
        expect(c.state.photoUpload, PhotoUpload.queued);
        expect(c.state.outcomeMessage, contains('بانتظار الرفع'));
        // الدبّوس ملتزَم: إغلاق النموذج لا يحذف الصورة المنتظرة.
        await c.close();
        expect(store.discarded, isEmpty);
      },
    );

    test('a transient failure of the photo request queues it', () async {
      var n = 0;
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          n++;
          if (n == 1) {
            return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
          }
          return connectionFailure;
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.sent);
      expect(c.state.photoUpload, PhotoUpload.queued);
      expect(outbox.ops.single.kind, 'observation_photo');
      expect(outbox.ops.single.idempotencyKey, 'photo-key-1');
    });

    test('a server refusal of the photo is shown and never queued', () async {
      var n = 0;
      final c = await ready(
        (o) async => taxonomyOr(o, () async {
          n++;
          if (n == 1) {
            return FakeReply(200, {...pinJson('key-1'), 'persisted': true});
          }
          return const FakeReply(415, {'detail': 'pin_photo_unsupported_type'});
        }),
      );
      await c.capturePhoto();
      await c.submit();
      expect(c.state.outcome, SubmitOutcome.sent);
      expect(c.state.photoUpload, PhotoUpload.failed);
      expect(c.state.outcomeMessage, contains('لم تُرفع الصورة'));
      expect(outbox.ops, isEmpty);
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
