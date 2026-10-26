// توصيات الحقل: العمود الموحَّد، السبب الصادق عند 503، الحجب بسببه، وتغذية
// راجعة بمفتاح منع تكرار واحد لكلّ نيّة.
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/idempotency.dart';
import 'package:sahool_app/features/advisor/presentation/pest_escalation_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/recommendations_cubit.dart';
import 'package:sahool_app/features/advisor/presentation/recommendations_screen.dart';
import 'package:sahool_app/features/advisor/presentation/widgets/recommendation_widgets.dart';

import '../../core/fake_http.dart';
import 'advisor_test_helpers.dart';

const _columnBody = {
  'field_id': 'f-1',
  'crop': 'قمح صلب',
  'weather_available': false,
  'requires_review': true,
  'field_state': {
    'validity': 'partial',
    'execution_mode': 'review',
    'confidence_level': 'low',
    'reasons_ar': ['لا قراءة رطوبة حديثة'],
  },
  'recommendations': [
    {
      'category': 'fertilizer',
      'priority': 'high',
      'title_ar': 'سمّد بالنيتروجين',
      'detail_ar': 'الدفعة الثانية عند الإشطاء',
      'source': 'fao-heuristic',
      'safety': false,
    },
  ],
};

Future<List<Map<String, dynamic>>> _fields() async => [
  {
    'field_id': 'f-1',
    'farm_id': 'farm-1',
    'name_ar': 'الحقل الشماليّ',
    'crop': 'قمح صلب',
  },
];

Future<void> pumpRecs(
  WidgetTester tester,
  FakeAdapter adapter, {
  String role = 'agronomist',
}) async {
  await tester.pumpWidget(
    hostApp(
      RecommendationsScreen(
        fieldId: 'f-1',
        api: fakeAdvisorApi(adapter),
        fieldLoader: _fields,
        role: role,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('shows the unified column with server text and honest gaps', (
    tester,
  ) async {
    final adapter = FakeAdapter((_) async => const FakeReply(200, _columnBody));
    await pumpRecs(tester, adapter);
    expect(find.text('الحقل الشماليّ'), findsOneWidget);
    expect(find.text('سمّد بالنيتروجين'), findsOneWidget);
    expect(find.text('الدفعة الثانية عند الإشطاء'), findsOneWidget);
    expect(find.text('الطقس غير متاح'), findsOneWidget);
    expect(find.text('تحتاج مراجعة قبل التنفيذ'), findsOneWidget);
    expect(adapter.requests.single.path, '/api/v1/fields/f-1/recommendations');
  });

  testWidgets('503 shows the contract wording plus the server reason', (
    tester,
  ) async {
    final adapter = FakeAdapter(
      (_) async => const FakeReply(503, {
        'detail':
            'تعذّر توليد توصيات (لا طقس ولا سياق موسم كافٍ). حدّد موقع الحقل وموسمه.',
      }),
    );
    await pumpRecs(tester, adapter);
    expect(find.textContaining('الخدمة غير متاحة حاليّاً'), findsOneWidget);
    expect(find.textContaining('حدّد موقع الحقل وموسمه'), findsOneWidget);
    expect(find.text('أعد المحاولة'), findsOneWidget);
  });

  testWidgets('worker sees the column but not the engine request', (
    tester,
  ) async {
    final adapter = FakeAdapter((_) async => const FakeReply(200, _columnBody));
    await pumpRecs(tester, adapter, role: 'worker');
    expect(find.text('اطلب توصية'), findsNothing);
    expect(
      find.textContaining('متاحان للمالك والمدير والمهندس'),
      findsOneWidget,
    );
  });

  testWidgets('a blocked engine result shows its reason and no feedback', (
    tester,
  ) async {
    final adapter = FakeAdapter(
      (o) async => o.path.endsWith('/for-field')
          ? const FakeReply(422, {
              'delivered': false,
              'reason_ar': 'أدخل تحليل التربة لتفعيل التوصية',
              'rec_id': 'rec-1',
            })
          : const FakeReply(200, _columnBody),
    );
    await pumpRecs(tester, adapter);
    await tester.ensureVisible(find.text('اطلب توصية'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('اطلب توصية'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('أدخل تحليل التربة لتفعيل التوصية'));
    expect(find.text('توصية محجوبة'), findsOneWidget);
    expect(find.text('قبول'), findsNothing);
    final body = jsonBody(
      adapter.to('/api/v1/recommendations/for-field').single.data,
    );
    expect(body, {'field_id': 'f-1', 'farm_id': 'farm-1', 'crop': 'قمح صلب'});
  });

  testWidgets('delivered result: reject records an outcome with a key', (
    tester,
  ) async {
    final adapter = FakeAdapter((o) async {
      if (o.path.endsWith('/for-field')) {
        return const FakeReply(200, {
          'delivered': true,
          'rec_id': 'rec-7',
          'recommendation': {
            'headline': 'اروِ ٣٥ مم غداً',
            'confidence': 'medium',
            'quality_grade': 'LIMITED',
          },
          'cross_reference_note_ar': '',
        });
      }
      if (o.path.endsWith('/outcomes')) {
        return const FakeReply(201, {'outcome_id': 1, 'recorded': true});
      }
      return const FakeReply(200, _columnBody);
    });
    await pumpRecs(tester, adapter);
    await tester.ensureVisible(find.text('اطلب توصية'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('اطلب توصية'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('رفض'));
    await tester.pumpAndSettle();
    expect(find.text('اروِ ٣٥ مم غداً'), findsOneWidget);
    expect(find.textContaining(kYieldNotCalibrated), findsOneWidget);

    await tester.tap(find.text('رفض'));
    await tester.pumpAndSettle();
    expect(find.text('تأكيد رفض التوصية'), findsOneWidget);
    await tester.tap(find.text('سجّل الرفض'));
    await tester.pumpAndSettle();

    final req = adapter.to('/api/v1/recommendations/outcomes').single;
    expect(req.headers[kIdempotencyHeader], isNotNull);
    final body = jsonBody(req.data);
    expect(body['accepted'], isFalse);
    expect(body['recommendation_id'], 'rec-7');
    expect(body['crop'], 'قمح صلب');
    expect(body.containsKey('reason'), isFalse);
    expect(find.text('سُجِّل رفض التوصية.'), findsOneWidget);
  });

  group('OutcomeFeedbackCubit', () {
    test(
      'one intent keeps one key across user retries; recorded is final',
      () async {
        var calls = 0;
        final adapter = FakeAdapter(
          (_) async => ++calls == 1
              ? const FakeReply(409, {'detail': 'conflict'})
              : const FakeReply(201, {'outcome_id': 1, 'recorded': true}),
        );
        final cubit = OutcomeFeedbackCubit(
          fakeAdvisorApi(adapter),
          accepted: true,
          crop: 'شعير',
          fieldId: 'f',
        );
        await cubit.submit();
        expect(cubit.state.phase, FeedbackPhase.failed);
        await cubit.submit();
        expect(cubit.state.phase, FeedbackPhase.recorded);
        await cubit.submit(); // لا تسجيل ثالث بعد النجاح
        final keys = adapter.requests
            .map((r) => r.headers[kIdempotencyHeader])
            .toList();
        expect(keys, hasLength(2));
        expect(keys.toSet(), {cubit.idempotencyKey.value});
      },
    );

    test('a new intent gets a new key', () {
      final api = fakeAdvisorApi(
        FakeAdapter((_) async => const FakeReply(201)),
      );
      final a = OutcomeFeedbackCubit(
        api,
        accepted: true,
        crop: 'c',
        fieldId: 'f',
      );
      final b = OutcomeFeedbackCubit(
        api,
        accepted: true,
        crop: 'c',
        fieldId: 'f',
      );
      expect(a.idempotencyKey.value, isNot(b.idempotencyKey.value));
    });
  });

  group('PestEscalationCubit', () {
    const suspended = {
      'workflow': {
        'workflow_id': 'pest-A',
        'status': 'suspended',
        'completed_steps': ['detect', 'confirm', 'recommend'],
        'current_step': 'await_approval',
      },
      'context': {'recommendation_ar': 'رشّ موضعيّ'},
    };

    test('a retry after a failure resumes the same workflow id', () async {
      var calls = 0;
      final adapter = FakeAdapter(
        (_) async => ++calls == 1
            ? const FakeReply(500, {'detail': 'x'})
            : const FakeReply(200, suspended),
      );
      var n = 0;
      final cubit = PestEscalationCubit(
        fakeAdvisorApi(adapter),
        newId: () => 'pest-${++n}',
      );
      await cubit.start(fieldId: 'f', pestType: 'المنّ', severity: 0.5);
      expect(cubit.state.error, isNotNull);
      await cubit.start(fieldId: 'f', pestType: 'المنّ', severity: 0.5);
      final ids = adapter.requests
          .map((r) => jsonBody(r.data)['workflow_id'])
          .toList();
      expect(ids, ['pest-1', 'pest-1']);
      expect(cubit.state.workflow!.suspended, isTrue);

      await cubit.reject();
      expect(jsonBody(adapter.requests.last.data), {
        'workflow_id': 'pest-A',
        'approval_status': 'rejected',
      });
    });
  });
}
