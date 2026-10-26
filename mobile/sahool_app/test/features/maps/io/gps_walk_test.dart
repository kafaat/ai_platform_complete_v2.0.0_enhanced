// مشي الحدود: مرشّح الدقّة/الوهميّ/القفزات، الإيقاف والاستئناف، الإذن والخدمة،
// وحفظ المسار بمفتاح ثابت.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:geolocator/geolocator.dart';
import 'package:latlong2/latlong.dart';
import 'package:sahool_app/features/maps/io/data/maps_io_api.dart';
import 'package:sahool_app/features/maps/io/gps/gps_save_cubit.dart';
import 'package:sahool_app/features/maps/io/gps/gps_walk_cubit.dart';
import 'package:sahool_app/features/maps/io/gps/location_source.dart';

import '../../../core/fake_http.dart';

final _t0 = DateTime.utc(2026, 10, 26, 6);

Position fix(
  double lat,
  double lon, {
  double acc = 4,
  int sec = 0,
  bool mocked = false,
}) => Position(
  latitude: lat,
  longitude: lon,
  timestamp: _t0.add(Duration(seconds: sec)),
  accuracy: acc,
  altitude: 0,
  altitudeAccuracy: 0,
  heading: 0,
  headingAccuracy: 0,
  speed: 0,
  speedAccuracy: 0,
  isMocked: mocked,
);

class FakeLocation implements LocationSource {
  FakeLocation({
    this.enabled = true,
    this.permission = LocationPermission.whileInUse,
  });
  bool enabled;
  LocationPermission permission;
  LocationPermission afterRequest = LocationPermission.whileInUse;
  int subscriptions = 0;
  StreamController<Position>? ctrl;

  void emit(Position p) => ctrl?.add(p);

  @override
  Future<bool> serviceEnabled() async => enabled;
  @override
  Future<LocationPermission> checkPermission() async => permission;
  @override
  Future<LocationPermission> requestPermission() async => afterRequest;
  @override
  Stream<Position> positions() {
    subscriptions++;
    ctrl = StreamController<Position>();
    return ctrl!.stream;
  }

  @override
  Future<bool> openSettings({bool locationService = false}) async => true;
}

Future<void> flush() => Future<void>.delayed(Duration.zero);

void main() {
  group('GpsFixFilter', () {
    const f = GpsFixFilter(maxAccuracyM: 10);
    const last = LatLng(15.35, 44.2);
    final lastAt = _t0;

    test('accuracy worse than the limit is rejected; within it accepted', () {
      expect(f.evaluate(fix(15.3501, 44.2, acc: 25)), FixVerdict.poorAccuracy);
      expect(f.evaluate(fix(15.3501, 44.2, acc: 10)), FixVerdict.accepted);
    });

    test('unknown (0/NaN) accuracy and mocked fixes are rejected', () {
      expect(f.evaluate(fix(15.35, 44.2, acc: 0)), FixVerdict.unknownAccuracy);
      expect(
        f.evaluate(fix(15.35, 44.2, acc: double.nan)),
        FixVerdict.unknownAccuracy,
      );
      expect(f.evaluate(fix(15.35, 44.2, mocked: true)), FixVerdict.mocked);
    });

    test('standing still is ignored, a 300 m jump in 2 s is rejected', () {
      expect(
        f.evaluate(fix(15.350005, 44.2), last: last, lastAt: lastAt),
        FixVerdict.tooClose,
      );
      expect(
        f.evaluate(fix(15.3527, 44.2, sec: 2), last: last, lastAt: lastAt),
        FixVerdict.jump,
      );
      // Same 300 m after 60 s of walking is fine.
      expect(
        f.evaluate(fix(15.3527, 44.2, sec: 60), last: last, lastAt: lastAt),
        FixVerdict.accepted,
      );
    });
  });

  group('GpsWalkCubit', () {
    late FakeLocation loc;
    late GpsWalkCubit cubit;

    setUp(() {
      loc = FakeLocation();
      cubit = GpsWalkCubit(source: loc);
    });
    tearDown(() => cubit.close());

    test(
      'records only fixes that pass the filter; live distance and area',
      () async {
        await cubit.start();
        expect(cubit.state.phase, GpsWalkPhase.recording);
        loc
          ..emit(fix(15.3500, 44.2000, sec: 0))
          ..emit(fix(15.3500, 44.2010, sec: 60))
          ..emit(fix(15.3600, 44.2010, acc: 30, sec: 70)) // poor accuracy
          ..emit(fix(15.3510, 44.2010, sec: 120))
          ..emit(fix(15.3510, 44.2000, sec: 180, mocked: true));
        await flush();
        final s = cubit.state;
        expect(s.track, hasLength(3));
        expect(s.rejected, 2);
        expect(s.distanceM, closeTo(107 + 111, 3));
        expect(s.areaHa, greaterThan(0.5)); // triangle ≈ 0.6 ha
        expect(s.lastVerdict, FixVerdict.mocked);
      },
    );

    test('area is null (not 0) before three points', () async {
      await cubit.start();
      loc.emit(fix(15.35, 44.2));
      await flush();
      expect(cubit.state.areaHa, isNull);
    });

    test('pause cancels the stream; resume resubscribes', () async {
      await cubit.start();
      loc.emit(fix(15.3500, 44.2000));
      await flush();
      cubit.pause();
      expect(cubit.state.phase, GpsWalkPhase.paused);
      loc.emit(fix(15.3500, 44.2010, sec: 60)); // closed stream: never recorded
      await flush();
      expect(cubit.state.track, hasLength(1));
      cubit.resume();
      expect(loc.subscriptions, 2);
      loc.emit(fix(15.3500, 44.2010, sec: 600));
      await flush();
      expect(cubit.state.track, hasLength(2));
      cubit.undoLast();
      expect(cubit.state.track, hasLength(1));
    });

    test('changing the accuracy limit applies to the next fix', () async {
      cubit.setMaxAccuracy(5);
      await cubit.start();
      loc.emit(fix(15.35, 44.2, acc: 8));
      await flush();
      expect(cubit.state.track, isEmpty);
      expect(cubit.state.lastVerdict, FixVerdict.poorAccuracy);
    });

    test(
      'service off and denied permission are honest states, no stream',
      () async {
        loc.enabled = false;
        await cubit.start();
        expect(cubit.state.phase, GpsWalkPhase.serviceDisabled);
        loc
          ..enabled = true
          ..permission = LocationPermission.denied
          ..afterRequest = LocationPermission.deniedForever;
        cubit.reset();
        await cubit.start();
        expect(cubit.state.phase, GpsWalkPhase.permissionDeniedForever);
        expect(loc.subscriptions, 0);
      },
    );

    test('stream errors end recording with a typed state', () async {
      await cubit.start();
      loc.ctrl!.addError(const LocationServiceDisabledException());
      await flush();
      expect(cubit.state.phase, GpsWalkPhase.serviceDisabled);
    });

    test('finish stops recording and exposes a simplified ring', () async {
      await cubit.start();
      // A square walked with a point every ~11 m.
      var sec = 0;
      for (final (lat, lon) in [
        for (var i = 0; i <= 9; i++) (15.35, 44.2 + i * 0.0001),
        for (var i = 1; i <= 9; i++) (15.35 + i * 0.0001, 44.2009),
        for (var i = 1; i <= 9; i++) (15.3509, 44.2009 - i * 0.0001),
        for (var i = 1; i <= 8; i++) (15.3509 - i * 0.0001, 44.2),
      ]) {
        loc.emit(fix(lat, lon, sec: sec += 10));
      }
      await flush();
      cubit.finish();
      expect(cubit.state.phase, GpsWalkPhase.finished);
      expect(cubit.state.track.length, greaterThan(30));
      expect(cubit.state.simplified.length, inInclusiveRange(4, 5));
    });
  });

  group('GpsSaveCubit', () {
    test(
      'retry after a failure reuses the key; a new payload gets a new key',
      () async {
        var n = 0;
        final adapter = FakeAdapter(
          (_) async => n++ == 0
              ? const FakeReply(422, {
                  'detail': {
                    'message_ar': 'حدود الحقل غير قابلة للحفظ',
                    'code': 'field_boundary_save_guard',
                    'issues': ['area_too_small'],
                  },
                })
              : const FakeReply(201, {'field_id': 'fld_gps'}),
        );
        final save = GpsSaveCubit(
          MapsIoApi(
            testClient(
              adapter,
              MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
            ),
          ),
        );
        const ring = [
          LatLng(15.35, 44.2),
          LatLng(15.35, 44.201),
          LatLng(15.351, 44.201),
        ];
        await save.save(
          name: 'أ',
          ring: ring,
          rawVertexCount: 40,
          toleranceM: 3,
        );
        expect(save.state.phase, SavePhase.failed);
        expect(save.state.error, contains('area_too_small'));
        await save.save(
          name: 'أ',
          ring: ring,
          rawVertexCount: 40,
          toleranceM: 3,
        );
        expect(save.state.phase, SavePhase.saved);
        expect(save.state.fieldId, 'fld_gps');
        final keys = adapter.requests
            .map((r) => r.headers['Idempotency-Key'])
            .toList();
        expect(keys[0], keys[1]);
        final body = adapter.requests.first.data as Map;
        expect(body['format'], 'gps');
        expect(body['points'], [
          [44.2, 15.35],
          [44.201, 15.35],
          [44.201, 15.351],
        ]);
        expect(body['boundary_metadata'], {
          'source': 'gps_walk',
          'mode': 'track',
          'post_processing': 'douglas_peucker_3m',
          'vertices_before': 40,
          'vertices_after': 3,
        });
        // A second save after success is a no-op (no duplicate field).
        await save.save(
          name: 'أ',
          ring: ring,
          rawVertexCount: 40,
          toleranceM: 3,
        );
        expect(adapter.requests, hasLength(2));

        save.reset();
        await save.save(
          name: 'ب',
          ring: ring,
          rawVertexCount: 40,
          toleranceM: 3,
        );
        expect(
          adapter.requests.last.headers['Idempotency-Key'],
          isNot(keys[0]),
        );
        await save.close();
      },
    );
  });
}
