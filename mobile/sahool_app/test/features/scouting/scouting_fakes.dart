// أدوات اختبار ميزة الاستكشاف: موقع/كاميرا/مخزن صور/صندوق إرسال مزيّفة، وعميل
// HTTP مزيّف بالـApiClient الحقيقيّ (test/core/fake_http.dart).
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:sahool_app/core/network/connectivity_status.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/scouting/data/device_sources.dart';
import 'package:sahool_app/features/scouting/data/scouting_api.dart';
import 'package:sahool_app/features/scouting/data/scouting_models.dart';
import 'package:sahool_app/features/scouting/presentation/scouting_deps.dart';

import '../../core/fake_http.dart';

const sanaaField = ScoutingField(
  id: 'f1',
  nameAr: 'حقل القمح',
  crop: 'wheat',
  centerLat: 15.35,
  centerLng: 44.2,
);

const noCentreField = ScoutingField(id: 'f2', nameAr: 'حقل بلا مركز');

Map<String, dynamic> fieldJson(ScoutingField f) => {
  'field_id': f.id,
  'farm_id': 'farm1',
  'name_ar': f.nameAr,
  'crop': f.crop ?? '',
  'area_ha': 1.0,
  'quality_grade': 'READY',
  'health_summary_ar': 'صحّي',
  'lat': f.centerLat,
  'lon': f.centerLng,
};

Map<String, dynamic> pinJson(
  String id, {
  String category = 'pest',
  String severity = 'high',
  String? createdAt,
  String? note,
  double lat = 15.351,
  double lng = 44.201,
}) => {
  'pin_id': id,
  'field_id': 'f1',
  'lat': lat,
  'lng': lng,
  'issue_category': category,
  'severity': severity,
  'status': 'new',
  'persistence': 'seasonal',
  'crop': 'wheat',
  'issue_code': null,
  'note_ar': note,
  'photo_uri': null,
  'color': null,
  'created_by': 'u1',
  'created_at': createdAt ?? DateTime.now().toUtc().toIso8601String(),
};

class FakeLocation implements LocationSource {
  FakeLocation(this.result);
  GpsResult result;
  int calls = 0;
  int settingsOpened = 0;

  @override
  Future<GpsResult> current() async {
    calls++;
    return result;
  }

  @override
  Future<void> openSettings(GpsFailureReason reason) async => settingsOpened++;
}

class FakePhotos implements PhotoCapturer {
  FakePhotos({this.photo, this.error});
  CapturedPhoto? photo;
  PhotoCaptureException? error;
  int calls = 0;

  @override
  Future<CapturedPhoto?> capture({bool fromCamera = true}) async {
    calls++;
    if (error != null) throw error!;
    return photo;
  }
}

CapturedPhoto jpegPhoto([String name = 'leaf.jpg']) => CapturedPhoto(
  path: '/tmp/does-not-exist/$name',
  filename: name,
  readBytes: () async => Uint8List.fromList([0xff, 0xd8, 0xff, 0xe0]),
);

class MemoryPhotoStore implements LocalPhotoStore {
  final Map<String, String> byPin = {};
  final List<String> discarded = [];

  @override
  Future<String> keep(String pinId, CapturedPhoto photo) async {
    final p = '/local/$pinId.jpg';
    byPin[pinId] = p;
    return p;
  }

  @override
  Future<void> discard(String path) async {
    discarded.add(path);
    byPin.removeWhere((_, v) => v == path);
  }

  @override
  Future<String?> find(String pinId) async => byPin[pinId];
}

class FakeOutbox implements OfflineOutbox {
  FakeOutbox([this.receipt = const OutboxReceipt.queued()]);
  OutboxReceipt receipt;
  final List<OutboxOp> ops = [];

  @override
  Future<OutboxReceipt> enqueue(OutboxOp op) async {
    ops.add(op);
    return receipt;
  }

  @override
  Stream<int> get pendingCount => Stream<int>.value(ops.length);
}

ConnectivityStatus connectivity({required bool online}) =>
    ConnectivityStatus()..value = online;

/// عميل حقيقيّ فوق محوّل مزيّف بتوكن صالح.
(ScoutingApi, FakeAdapter) fakeApi(FakeHandler handler) {
  final adapter = FakeAdapter(handler);
  final client = testClient(
    adapter,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  );
  return (ScoutingApi(client), adapter);
}

ScoutingDeps testDeps({
  required ScoutingApi api,
  List<ScoutingField> fields = const [sanaaField],
  Future<List<Map<String, dynamic>>> Function()? fieldsLoader,
  LocationSource? location,
  PhotoCapturer? photos,
  LocalPhotoStore? store,
  OfflineOutbox? outbox,
  ConnectivityStatus? net,
  String role = 'worker',
}) => ScoutingDeps(
  api: api,
  fieldsLoader:
      fieldsLoader ?? () async => [for (final f in fields) fieldJson(f)],
  location:
      location ??
      FakeLocation(const GpsFix(lat: 15.36, lng: 44.21, accuracyM: 8)),
  photos: photos ?? FakePhotos(photo: jpegPhoto()),
  photoStore: store ?? MemoryPhotoStore(),
  outbox: outbox ?? FakeOutbox(),
  connectivity: net ?? connectivity(online: true),
  role: () => role,
  showMapTiles: false,
);

Widget host(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: child,
  onGenerateRoute: (s) => MaterialPageRoute<void>(
    settings: s,
    builder: (_) => Scaffold(body: Text('route:${s.name}:${s.arguments}')),
  ),
);

FakeReply status(int code, [Object? body]) => FakeReply(code, body);

/// خطأ 503 من الخادم بنصّ detail.
FakeReply unavailable(String detail) => FakeReply(503, {'detail': detail});

/// يرمي فشل اتّصال (لا ردّ).
const FakeReply connectionFailure = FakeReply.fail(
  DioExceptionType.connectionError,
);
