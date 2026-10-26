// كشف الآفات في الاستكشاف: field_id يُرسل دائماً (كان المستشار يرسله بلا حقل
// فيرفضه الخادم 422)، حالة «يتطلّب اتّصالاً»، وعرض النتيجة/الفشل كما ردّه الخادم.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/scouting/data/device_sources.dart';
import 'package:sahool_app/features/scouting/presentation/pest_detect_cubit.dart';
import 'package:sahool_app/features/scouting/presentation/pest_detect_screen.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

const _detected = FakeReply(200, {
  'field_id': 'f1',
  'crop': 'wheat',
  'detections': [
    {
      'class_id': 0,
      'class_name': 'aphid',
      'arabic_name': 'منّ',
      'confidence': 0.91,
      'severity': 'medium',
      'action_policy': 'observation_only',
    },
  ],
  'alert_ar': '🐛 **تنبيه آفة عالية الثقة!**',
  'model_version': 'pest-v2',
  'sync_status': 'synced',
});

void main() {
  group('PestDetectCubit', () {
    test('sends field_id and the field crop in the multipart form', () async {
      final (api, adapter) = fakeApi((o) async => _detected);
      final c = PestDetectCubit(
        field: sanaaField,
        api: api,
        photos: FakePhotos(photo: jpegPhoto()),
        connectivity: connectivity(online: true),
      );
      await c.captureAndDetect();
      final form = adapter.requests.single.data! as FormData;
      final fields = {for (final e in form.fields) e.key: e.value};
      expect(fields['field_id'], 'f1');
      expect(fields['crop'], 'wheat');
      expect(c.state, isA<PestDetectDone>());
      final done = c.state as PestDetectDone;
      expect(done.result.detections.single.labelAr, 'منّ');
    });

    test('offline: nothing is sent and the state says so', () async {
      final (api, adapter) = fakeApi((o) async => _detected);
      final photos = FakePhotos(photo: jpegPhoto());
      final c = PestDetectCubit(
        field: sanaaField,
        api: api,
        photos: photos,
        connectivity: connectivity(online: false),
      );
      await c.captureAndDetect();
      expect(c.state, isA<PestDetectOffline>());
      expect(adapter.requests, isEmpty);
      expect(photos.calls, 0);
    });

    test('503 keeps the server detail (model not provisioned)', () async {
      final (api, _) = fakeApi(
        (o) async => unavailable('نموذج كشف الآفات غير مُجهَّز على هذه الحافة'),
      );
      final c = PestDetectCubit(
        field: sanaaField,
        api: api,
        photos: FakePhotos(photo: jpegPhoto()),
        connectivity: connectivity(online: true),
      );
      await c.captureAndDetect();
      final s = c.state as PestDetectFailed;
      expect(s.serverDetail, contains('غير مُجهَّز'));
    });

    test('retry re-sends the last photo without a new capture', () async {
      var n = 0;
      final (api, adapter) = fakeApi(
        (o) async =>
            n++ == 0 ? const FakeReply(400, {'detail': 'x'}) : _detected,
      );
      final photos = FakePhotos(photo: jpegPhoto());
      final c = PestDetectCubit(
        field: sanaaField,
        api: api,
        photos: photos,
        connectivity: connectivity(online: true),
      );
      await c.captureAndDetect();
      expect(c.state, isA<PestDetectFailed>());
      await c.retry();
      expect(c.state, isA<PestDetectDone>());
      expect(photos.calls, 1);
      expect(adapter.requests, hasLength(2));
    });

    test('camera denial is reported, nothing sent', () async {
      final (api, adapter) = fakeApi((o) async => _detected);
      final c = PestDetectCubit(
        field: sanaaField,
        api: api,
        photos: FakePhotos(
          error: const PhotoCaptureException('إذن الكاميرا مرفوض'),
        ),
        connectivity: connectivity(online: true),
      );
      await c.captureAndDetect();
      expect((c.state as PestDetectIdle).message, 'إذن الكاميرا مرفوض');
      expect(adapter.requests, isEmpty);
    });
  });

  group('PestDetectScreen', () {
    Future<void> open(WidgetTester t, FakeHandler handler) async {
      t.view.physicalSize = const Size(800, 2400);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      final (api, _) = fakeApi(handler);
      await t.pumpWidget(
        host(
          PestDetectScreen(
            field: sanaaField,
            deps: testDeps(api: api),
          ),
        ),
      );
      await t.tap(find.text('التقاط صورة'));
      await t.pumpAndSettle();
    }

    testWidgets('shows labels and confidence from the server', (t) async {
      await open(t, (o) async => _detected);
      expect(find.text('منّ'), findsOneWidget);
      expect(find.text('الثقة 91٪'), findsOneWidget);
      expect(find.textContaining('تنبيه آفة عالية الثقة'), findsOneWidget);
      expect(find.textContaining('**'), findsNothing);
      expect(find.textContaining('pest-v2'), findsOneWidget);
    });

    testWidgets('no detections is said plainly', (t) async {
      await open(
        t,
        (o) async =>
            const FakeReply(200, {'detections': [], 'sync_status': 'queued'}),
      );
      expect(
        find.textContaining('لم يكتشف النموذج آفات فوق عتبة الثقة'),
        findsOneWidget,
      );
    });

    testWidgets('"اسأل المستشار" opens the advisor route with the field', (
      t,
    ) async {
      await open(t, (o) async => _detected);
      await t.tap(find.text('اسأل المستشار'));
      await t.pumpAndSettle();
      expect(find.textContaining('route:/advisor:'), findsOneWidget);
      expect(find.textContaining('field_id: f1'), findsOneWidget);
    });

    testWidgets('503 shows the typed message and the server detail', (t) async {
      await open(
        t,
        (o) async => unavailable('نموذج كشف الآفات غير مُجهَّز على هذه الحافة'),
      );
      expect(find.text('تعذّر تحليل الصورة'), findsOneWidget);
      expect(
        find.textContaining('ردّ الخادم: نموذج كشف الآفات'),
        findsOneWidget,
      );
    });
  });
}
