// عقد نقاط المستشار مع الخادم: أسماء الحقول من AdvisorQuery وOutcomeRecordRequest
// والترويسات (Idempotency-Key) كما يقرؤها المعالج، عبر ApiClient الحقيقيّ.
import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/advisor/data/advisor_api.dart';

import '../../core/fake_http.dart';
import 'advisor_test_helpers.dart';

void main() {
  group('askAgent → POST /api/ai-agronomist/chat', () {
    test('sends `question` (+field_id) and never message/query', () async {
      Duration? receiveTimeout;
      final adapter = FakeAdapter((o) async {
        receiveTimeout = o.receiveTimeout;
        return FakeReply(200, chatReply(fieldId: 'f-1'));
      });
      await fakeAdvisorApi(adapter).askAgent('متى أروي؟', fieldId: 'f-1');

      final req = adapter.to('/api/ai-agronomist/chat').single;
      expect(req.method, 'POST');
      final body = jsonBody(req.data);
      expect(body['question'], 'متى أروي؟');
      expect(body['field_id'], 'f-1');
      expect(body['language'], 'ar');
      expect(body.containsKey('message'), isFalse);
      expect(body.containsKey('query'), isFalse);
      expect(
        body.containsKey('tenant_id'),
        isFalse,
        reason: 'tenant comes from the gateway-injected X-Tenant-Id',
      );
      expect(receiveTimeout, kAdvisorTimeout);
      expect(kAdvisorTimeout, const Duration(seconds: 120));
    });

    test('a general question sends no field_id', () async {
      final adapter = FakeAdapter((_) async => FakeReply(200, chatReply()));
      await fakeAdvisorApi(adapter).askAgent('سؤال عامّ');
      final body = jsonBody(adapter.requests.single.data);
      expect(body.containsKey('field_id'), isFalse);
    });

    test(
      'a 422 surfaces as a typed validation error, not a fake answer',
      () async {
        final adapter = FakeAdapter((_) async => FakeReply(422, fastApi422()));
        await expectLater(
          fakeAdvisorApi(adapter).askAgent('x'),
          throwsA(
            isA<ApiException>()
                .having((e) => e.kind, 'kind', ApiErrorKind.validation)
                .having(
                  (e) => e.messageAr,
                  'message',
                  contains('Field required'),
                ),
          ),
        );
        expect(
          adapter.requests,
          hasLength(1),
          reason: 'chat is never auto-retried',
        );
      },
    );

    test('a 503 on chat is not retried (no idempotency key)', () async {
      final adapter = FakeAdapter(
        (_) async => const FakeReply(503, {'detail': 'down'}),
      );
      await expectLater(
        fakeAdvisorApi(adapter).askAgent('x'),
        throwsA(isA<ApiException>()),
      );
      expect(adapter.requests, hasLength(1));
      expect(adapter.requests.single.headers[kIdempotencyHeader], isNull);
    });
  });

  group('recommendation outcomes (feedback)', () {
    test(
      'body matches OutcomeRecordRequest and carries the intent key',
      () async {
        final adapter = FakeAdapter(
          (_) async =>
              const FakeReply(201, {'outcome_id': 7, 'recorded': true}),
        );
        final key = IdempotencyKey.generate();
        await fakeAdvisorApi(adapter).recordRecommendationOutcome(
          crop: 'قمح صلب',
          fieldId: 'f-1',
          farmId: 'farm-1',
          recommendationId: 'rec-9',
          accepted: false,
          idempotencyKey: key,
        );
        final req = adapter.to('/api/v1/recommendations/outcomes').single;
        expect(req.headers[kIdempotencyHeader], key.value);
        final body = jsonBody(req.data);
        expect(body, {
          'crop': 'قمح صلب',
          'field_id': 'f-1',
          'farm_id': 'farm-1',
          'recommendation_id': 'rec-9',
          'accepted': false,
          'matured_within_lag': false,
        });
      },
    );

    test(
      'a lost response is retried with the SAME key (server dedups)',
      () async {
        var calls = 0;
        final adapter = FakeAdapter(
          (_) async => ++calls == 1
              ? const FakeReply(503, {'detail': 'busy'})
              : const FakeReply(201, {'outcome_id': 7, 'recorded': true}),
        );
        final key = IdempotencyKey.generate();
        await fakeAdvisorApi(adapter).recordRecommendationOutcome(
          crop: 'شعير',
          fieldId: 'f-1',
          accepted: true,
          idempotencyKey: key,
        );
        final keys = adapter.requests.map((r) => r.headers[kIdempotencyHeader]);
        expect(keys, [key.value, key.value]);
      },
    );
  });

  group('recommendation for a field', () {
    test(
      'a blocked engine result (422 delivered=false) is returned, not thrown',
      () async {
        final adapter = FakeAdapter(
          (_) async => const FakeReply(422, {
            'delivered': false,
            'reason_ar': 'أدخل تحليل التربة لتفعيل التوصية',
            'rec_id': 'rec-1',
          }),
        );
        final r = await fakeAdvisorApi(
          adapter,
        ).requestRecommendationForField(fieldId: 'f-1', crop: 'شعير');
        expect(r['delivered'], isFalse);
        expect(r['reason_ar'], contains('تحليل التربة'));
        final body = jsonBody(adapter.requests.single.data);
        expect(body, {'field_id': 'f-1', 'farm_id': '', 'crop': 'شعير'});
        expect(
          adapter.requests.single.headers[kIdempotencyHeader],
          isNull,
          reason: 'for-field does not honour Idempotency-Key',
        );
      },
    );

    test('a 429 keeps the engine\'s Arabic reason', () async {
      final adapter = FakeAdapter(
        (_) async => const FakeReply(429, {
          'error': 'rate_limit_exceeded',
          'ar': 'تجاوزت حدّ التوصيات',
        }),
      );
      await expectLater(
        fakeAdvisorApi(
          adapter,
        ).requestRecommendationForField(fieldId: 'f', crop: 'c'),
        throwsA(
          isA<ApiException>().having(
            (e) => e.messageAr,
            'messageAr',
            'تجاوزت حدّ التوصيات',
          ),
        ),
      );
    });
  });

  test('field recommendations path encodes the id', () async {
    final adapter = FakeAdapter(
      (_) async =>
          const FakeReply(200, {'field_id': 'a b', 'recommendations': []}),
    );
    await fakeAdvisorApi(adapter).getFieldRecommendations('a b');
    expect(
      adapter.requests.single.path,
      '/api/v1/fields/a%20b/recommendations',
    );
  });

  test('pest escalation keys the request by workflow and step', () async {
    final adapter = FakeAdapter(
      (RequestOptions o) async => const FakeReply(200, {
        'workflow': {'workflow_id': 'pest-1', 'status': 'suspended'},
        'context': {},
      }),
    );
    final api = fakeAdvisorApi(adapter);
    await api.runPestEscalation(
      workflowId: 'pest-1',
      fieldId: 'f',
      pestType: 'المنّ',
      severity: 0.5,
    );
    await api.runPestEscalation(
      workflowId: 'pest-1',
      approvalStatus: 'rejected',
    );
    expect(adapter.requests.map((r) => r.headers[kIdempotencyHeader]), [
      'pest-1:start',
      'pest-1:rejected',
    ]);
    expect(jsonBody(adapter.requests.last.data), {
      'workflow_id': 'pest-1',
      'approval_status': 'rejected',
    });
  });
}
