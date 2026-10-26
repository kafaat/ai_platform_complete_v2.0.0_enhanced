// منطق عيّنات المختبر: انتقالات الحالة مرآة soil_lab_workflow.py، الأزرار التي
// يقبلها الخادم فعلاً، تحقّق النموذج، وإيصال صندوق الإرسال دون اتّصال.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/lab_sampling/data/lab_models.dart';
import 'package:sahool_app/features/lab_sampling/data/lab_sampling_api.dart';
import 'package:sahool_app/features/lab_sampling/presentation/protocol_screen.dart';
import 'package:sahool_app/features/lab_sampling/presentation/sample_create_cubit.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';

import '../../core/fake_http.dart';
import 'fake_outbox.dart';

LabSample sample(String status, {String kind = 'soil'}) => LabSample.fromJson({
  'sample_id': 's-1',
  'field_id': 'f1',
  'kind': kind,
  'status': status,
});

List<String> labels(LabSample s) =>
    labActionsFor(s).map((a) => a.labelAr).toList();

LabSamplingApi apiFor(FakeAdapter a) => LabSamplingApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

const validSoil = SampleDraft(
  fieldId: 'f1',
  latitudeText: '١٥٫٣٥٤٢',
  longitudeText: '44.2067',
  accuracyM: 4,
  depthFromText: '٠',
  depthToText: '٣٠',
);

const savedRow = {
  'sample_id': 's-abc',
  'field_id': 'f1',
  'kind': 'soil',
  'status': 'sampled',
  'latitude': 15.3542,
  'longitude': 44.2067,
};

void main() {
  group('sample status transitions mirror soil_lab_workflow.py', () {
    test('legal targets per status; published and cancelled are final', () {
      expect(LabSampleStatus.sampled.allowedTargets, {
        LabSampleStatus.inLab,
        LabSampleStatus.cancelled,
      });
      expect(LabSampleStatus.inLab.allowedTargets, {
        LabSampleStatus.resultReceived,
        LabSampleStatus.cancelled,
      });
      expect(LabSampleStatus.resultReceived.allowedTargets, {
        LabSampleStatus.approved,
        LabSampleStatus.rejected,
      });
      expect(LabSampleStatus.approved.allowedTargets, {
        LabSampleStatus.published,
      });
      expect(LabSampleStatus.published.isFinal, isTrue);
      expect(LabSampleStatus.cancelled.isFinal, isTrue);
      expect(
        LabSampleStatus.parse('collected'),
        isNull,
        reason: 'collected is a create-time alias the server maps to sampled',
      );
    });

    test('collected → sent → (result entered by the lab) → approve/publish', () {
      expect(labels(sample('sampled')), ['أُرسلت للمختبر', 'إلغاء العيّنة']);
      // «وصلت النتيجة» يضعها إدخال النتيجة، لا زرّ انتقال (سيرفضه الخادم بلا نتيجة).
      expect(labels(sample('in_lab')), ['إلغاء العيّنة']);
      expect(labels(sample('result_received')), [
        'اعتماد النتيجة',
        'رفض النتيجة',
      ]);
      expect(labels(sample('approved')), ['نشر النتيجة']);
      expect(labels(sample('rejected')), [
        'إعادة الإرسال للمختبر',
        'إلغاء العيّنة',
      ]);
      expect(labels(sample('published')), isEmpty);
      expect(labels(sample('mystery')), isEmpty);
    });

    test(
      'water samples cannot be approved or published (server needs a soil result)',
      () {
        expect(labels(sample('result_received', kind: 'water')), [
          'رفض النتيجة',
        ]);
        expect(labels(sample('approved', kind: 'water')), isEmpty);
      },
    );
  });

  group('validateSampleDraft / buildSampleBody', () {
    test('a GPS point is required and must be in range', () {
      expect(
        validateSampleDraft(
          const SampleDraft(fieldId: 'f1', kind: 'water'),
        )[SampleField.location],
        isNotNull,
      );
      expect(
        validateSampleDraft(
          const SampleDraft(
            fieldId: 'f1',
            kind: 'water',
            latitudeText: '95',
            longitudeText: '44',
          ),
        )[SampleField.location],
        'إحداثيّات خارج النطاق',
      );
    });

    test('soil needs an integer depth range with to > from', () {
      final e = validateSampleDraft(
        const SampleDraft(
          fieldId: 'f1',
          latitudeText: '15',
          longitudeText: '44',
        ),
      );
      expect(e[SampleField.depthFrom], 'عمق البداية مطلوب لعيّنة التربة');
      expect(e[SampleField.depthTo], 'عمق النهاية مطلوب لعيّنة التربة');
      expect(
        validateSampleDraft(
          const SampleDraft(
            fieldId: 'f1',
            latitudeText: '15',
            longitudeText: '44',
            depthFromText: '30',
            depthToText: '15',
          ),
        )[SampleField.depthTo],
        'عمق النهاية يجب أن يكون أكبر من البداية',
      );
      expect(
        validateSampleDraft(
          const SampleDraft(
            fieldId: 'f1',
            latitudeText: '15',
            longitudeText: '44',
            depthFromText: '0',
            depthToText: '15.5',
          ),
        )[SampleField.depthTo],
        'أدخل عمقاً بعدد صحيح من السنتيمترات',
      );
    });

    test('Arabic-Indic digits are parsed; body matches LabSampleIn', () {
      expect(validateSampleDraft(validSoil), isEmpty);
      final b = buildSampleBody(
        SampleDraft(
          fieldId: validSoil.fieldId,
          latitudeText: validSoil.latitudeText,
          longitudeText: validSoil.longitudeText,
          accuracyM: 4,
          depthFromText: validSoil.depthFromText,
          depthToText: validSoil.depthToText,
          sampledOn: DateTime(2026, 10, 26),
        ),
      );
      expect(b, {
        'field_id': 'f1',
        'kind': 'soil',
        'latitude': 15.3542,
        'longitude': 44.2067,
        'sampled_on': '2026-10-26',
        'depth_cm_from': 0,
        'depth_cm_to': 30,
        'gps_accuracy_m': 4.0,
        'status': 'collected',
      });
    });

    test(
      'server protocol depth text yields a quick-fill range only when explicit',
      () {
        expect(parseDepthRangeCm('15-30 سم'), (15, 30));
        expect(parseDepthRangeCm('15-30 سم داخل منطقة الترطيب'), (15, 30));
        expect(parseDepthRangeCm('30 سم'), isNull);
        expect(parseDepthRangeCm('متدرّج: 0-5 سم ثمّ 5-15 سم'), isNull);
      },
    );
  });

  group('SampleCreateCubit offline receipts', () {
    test(
      'online: POSTs once with an Idempotency-Key and reports sent',
      () async {
        final a = FakeAdapter((o) async => const FakeReply(200, savedRow));
        final outbox = FakeOutbox();
        final c = SampleCreateCubit(
          apiFor(a),
          outbox: outbox,
          isOnline: () => true,
        );
        await c.submit(validSoil);
        expect(c.state, isA<SampleSent>());
        expect((c.state as SampleSent).sample.sampleId, 's-abc');
        final posts = a.to(LabSamplingApi.samplesPath);
        expect(posts, hasLength(1));
        expect(posts.single.headers['Idempotency-Key'], c.idempotencyKey.value);
        expect(outbox.ops, isEmpty);
        await c.close();
      },
    );

    test(
      'offline: no request; queued in the outbox with the same key',
      () async {
        final a = FakeAdapter((o) async => const FakeReply(200, savedRow));
        final outbox = FakeOutbox();
        final c = SampleCreateCubit(
          apiFor(a),
          outbox: outbox,
          isOnline: () => false,
          fieldLabel: 'حقل البنّ',
        );
        await c.submit(validSoil);
        expect(c.state, isA<SampleQueued>());
        expect(a.requests, isEmpty);
        final op = outbox.ops.single;
        expect(op.method, 'POST');
        expect(op.path, '/api/v1/lab/samples');
        expect(op.kind, 'lab_sample_create');
        expect(op.idempotencyKey, c.idempotencyKey.value);
        expect(op.fieldId, 'f1');
        expect(op.labelAr, 'عيّنة تربة — حقل البنّ');
        expect(op.body['depth_cm_to'], 30);
        await c.close();
      },
    );

    test(
      'network failure mid-send falls back to the outbox with the sent key',
      () async {
        final a = FakeAdapter(
          (o) async => const FakeReply.fail(DioExceptionType.connectionError),
        );
        final outbox = FakeOutbox();
        final c = SampleCreateCubit(
          apiFor(a),
          outbox: outbox,
          isOnline: () => true,
        );
        await c.submit(validSoil);
        expect(c.state, isA<SampleQueued>());
        expect(
          outbox.ops.single.idempotencyKey,
          a.requests.first.headers['Idempotency-Key'],
        );
        await c.close();
      },
    );

    test(
      'unavailable outbox: honest not-saved message and the form stays',
      () async {
        final a = FakeAdapter((o) async => const FakeReply(200, savedRow));
        // التنفيذ الافتراضيّ في الأساس (قبل وكيل offline_sync).
        final c = SampleCreateCubit(
          apiFor(a),
          outbox: OfflineOutbox.instance,
          isOnline: () => false,
        );
        await c.submit(validSoil);
        final s = c.state as SampleEditing;
        expect(s.submitError, notQueuedMessage('offline_queue_unavailable'));
        expect(s.submitError, contains('لم تُحفَظ العيّنة'));
        // يمكن المحاولة مجدّداً (ليست حالة نهائيّة).
        await c.submit(validSoil);
        expect(c.state, isA<SampleEditing>());
        await c.close();
      },
    );

    test('an outbox that throws is reported as not queued', () async {
      final c = SampleCreateCubit(
        apiFor(FakeAdapter((o) async => const FakeReply(200))),
        outbox: FakeOutbox(throws: true),
        isOnline: () => false,
      );
      await c.submit(validSoil);
      expect(
        (c.state as SampleEditing).submitError,
        contains('بياناتها باقية'),
      );
      await c.close();
    });

    test('a server rejection is not queued (it would fail again)', () async {
      final a = FakeAdapter((o) async => const FakeReply(403, {'detail': 'x'}));
      final outbox = FakeOutbox();
      final c = SampleCreateCubit(
        apiFor(a),
        outbox: outbox,
        isOnline: () => true,
      );
      await c.submit(validSoil);
      expect(
        (c.state as SampleEditing).submitError,
        'لا تملك صلاحيّة الوصول إلى هذا القسم.',
      );
      expect(outbox.ops, isEmpty);
      await c.close();
    });

    test('invalid draft makes no request and queues nothing', () async {
      final a = FakeAdapter((o) async => const FakeReply(200, savedRow));
      final outbox = FakeOutbox();
      final c = SampleCreateCubit(
        apiFor(a),
        outbox: outbox,
        isOnline: () => false,
      );
      await c.submit(const SampleDraft(fieldId: 'f1'));
      expect((c.state as SampleEditing).errors, isNotEmpty);
      expect(a.requests, isEmpty);
      expect(outbox.ops, isEmpty);
      await c.close();
    });
  });
}
