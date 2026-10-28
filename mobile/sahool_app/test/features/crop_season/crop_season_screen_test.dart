// شاشة المواسم ضدّ ApiClient حقيقيّ بمحوّل مزيّف: المسارات الحقيقيّة، Idempotency-Key
// ثابت لنيّة الحفظ، إجراءات الطور من الخادم فقط، والأزرار حسب الدور.
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/network/api_exception.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/crop_season/data/crop_season_api.dart';
import 'package:sahool_app/features/crop_season/data/season_models.dart';
import 'package:sahool_app/features/crop_season/presentation/phenology_cards.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_cubit.dart';
import 'package:sahool_app/features/crop_season/presentation/season_form_logic.dart';
import 'package:sahool_app/features/crop_season/presentation/seasons_screen.dart';
import 'package:sahool_app/features/offline_sync/data/operation_ledger.dart';

import '../../core/fake_http.dart';
import '../offline_sync/operation_test_support.dart';

Widget host(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar'), Locale('en')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: child,
);

const _seasons = [
  {
    'season_id': 'ssn_1',
    'field_id': 'f1',
    'crops': ['wheat'],
    'cultivar': 'بكّور',
    'sowing_date': '2026-03-05',
    'season_end': '2026-07-01',
    'status': 'active',
    'stages': [],
  },
];

const _phenology = {
  'available': true,
  'crop': 'wheat',
  'crop_id': 'wheat',
  'sowing_date': '2026-03-05',
  'days_after_sowing': 40,
  'current_stage': {'stage': 'tillering', 'name_ar': 'الإشطاء'},
  'current_stage_kc': 0.7,
  'timeline': [
    {
      'stage': 'tillering',
      'name_ar': 'الإشطاء',
      'start_date': '2026-03-05',
      'end_date': '2026-04-20',
      'status': 'current',
    },
  ],
};

const _actions = {
  'available': true,
  'current_stage': 'tillering',
  'current_stage_name_ar': 'الإشطاء',
  'suggestions': [
    {
      'stage': 'tillering',
      'stage_name_ar': 'الإشطاء',
      'action_ar': 'ريّ تكميليّ خفيف',
    },
  ],
  'note_ar': 'اقتراحات إرشاديّة فقط — لا تُنشَأ مهامّ تلقائيّاً',
};

FakeAdapter fieldAdapter({
  Object actions = _actions,
  List<RecordedRequest>? log,
}) => FakeAdapter((o) async {
  switch ((o.method, o.path)) {
    case ('GET', '/api/v1/fields/f1/seasons'):
      return const FakeReply(200, _seasons);
    case ('GET', '/api/v1/fields/f1/phenology'):
      return const FakeReply(200, _phenology);
    case ('GET', '/api/v1/fields/f1/stage-actions'):
      return FakeReply(200, actions);
    case ('GET', '/api/v1/crop-cards'):
      return const FakeReply(200, {
        'crops': [
          {'crop_id': 'wheat', 'name_ar': 'القمح'},
        ],
      });
    case ('PATCH', '/api/v1/fields/f1/seasons/ssn_1'):
      return FakeReply(200, {..._seasons.first, 'status': 'closed'});
  }
  return const FakeReply(404, {'detail': 'not found'});
});

/// Cubit النموذج بسجلّ عمليّات في الذاكرة ومالكٍ من رمز الجلسة نفسه.
SeasonFormCubit formCubit(FakeAdapter a) {
  final tokens = MemoryTokenStore(accessToken: jwtFor('alice'));
  final client = testClient(a, tokens);
  return SeasonFormCubit(
    CropSeasonApi(client),
    fieldId: 'f1',
    ledger: ledgerFor(tokens, MemoryOperationStore(), client: client),
  );
}

CropSeasonApi apiFor(FakeAdapter a) => CropSeasonApi(
  testClient(
    a,
    MemoryTokenStore(accessToken: fakeJwt(const Duration(hours: 1))),
  ),
);

void bigScreen(WidgetTester t) {
  t.view.physicalSize = const Size(1080, 3200);
  t.view.devicePixelRatio = 1;
  addTearDown(t.view.reset);
}

void main() {
  testWidgets('owner sees phenology, server stage action and Arabic dates', (
    t,
  ) async {
    bigScreen(t);
    final a = fieldAdapter();
    await t.pumpWidget(
      host(CropSeasonScreen(fieldId: 'f1', api: apiFor(a), role: 'owner')),
    );
    await t.pumpAndSettle();

    expect(find.text('الإشطاء'), findsWidgets);
    expect(find.text('ريّ تكميليّ خفيف'), findsOneWidget);
    expect(find.text('5 مارس 2026 – 20 أبريل 2026'), findsOneWidget);
    expect(find.text('1 يوليو 2026'), findsOneWidget); // الحصاد المتوقّع
    expect(find.text('القمح'), findsOneWidget); // اسم المحصول من الفهرس
    expect(find.text('إغلاق الموسم'), findsOneWidget);
    expect(find.text('موسم جديد'), findsOneWidget);
  });

  testWidgets('viewer gets a read-only screen', (t) async {
    bigScreen(t);
    await t.pumpWidget(
      host(
        CropSeasonScreen(
          fieldId: 'f1',
          api: apiFor(fieldAdapter()),
          role: 'viewer',
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('إغلاق الموسم'), findsNothing);
    expect(find.text('تعديل'), findsNothing);
    expect(find.text('موسم جديد'), findsNothing);
  });

  testWidgets('closing a season confirms first and PATCHes status with a key', (
    t,
  ) async {
    bigScreen(t);
    final a = fieldAdapter();
    await t.pumpWidget(
      host(CropSeasonScreen(fieldId: 'f1', api: apiFor(a), role: 'manager')),
    );
    await t.pumpAndSettle();

    await t.tap(find.text('إغلاق الموسم'));
    await t.pumpAndSettle();
    expect(
      find.text('إغلاق الموسم نهائيّ ولا يمكن إعادة فتحه. هل تريد المتابعة؟'),
      findsOneWidget,
    );
    await t.tap(find.widgetWithText(FilledButton, 'إغلاق الموسم'));
    await t.pumpAndSettle();

    final patches = a.requests.where((r) => r.method == 'PATCH').toList();
    expect(patches, hasLength(1));
    expect(patches.single.data, {'status': 'closed'});
    expect(patches.single.headers['Idempotency-Key'], isNotEmpty);
    expect(find.text('أُغلق الموسم'), findsOneWidget);
  });

  testWidgets('stage actions render server data only', (t) async {
    await t.pumpWidget(
      host(
        const Scaffold(
          body: StageActionsCard(
            actions: StageActions(
              available: false,
              reasonAr: 'لا يوجد تاريخ بذار للموسم النشط',
            ),
          ),
        ),
      ),
    );
    expect(find.text('لا يوجد تاريخ بذار للموسم النشط'), findsOneWidget);

    await t.pumpWidget(
      host(
        const Scaffold(
          body: StageActionsCard(
            actions: StageActions(
              available: true,
              currentStageNameAr: 'الإزهار',
            ),
          ),
        ),
      ),
    );
    expect(find.text('لا إجراء مقترح لهذه المرحلة من الخادم'), findsOneWidget);
    expect(find.text('المرحلة: الإزهار'), findsOneWidget);
  });

  testWidgets(
    'stage-actions with a 503 shows the contract message in its card',
    (t) async {
      bigScreen(t);
      final a = FakeAdapter((o) async {
        if (o.path.endsWith('/stage-actions')) {
          return const FakeReply(503, {'detail': 'db'});
        }
        return (await fieldAdapter().handler(o));
      });
      await t.pumpWidget(
        host(CropSeasonScreen(fieldId: 'f1', api: apiFor(a), role: 'owner')),
      );
      await t.pumpAndSettle();
      expect(
        find.text(
          'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
        ),
        findsOneWidget,
      );
      // بقيّة الشاشة لا تسقط.
      expect(find.text('5 مارس 2026 – 20 أبريل 2026'), findsOneWidget);
    },
  );

  testWidgets('new season form validates inline before any request', (t) async {
    bigScreen(t);
    final a = fieldAdapter();
    await t.pumpWidget(
      host(CropSeasonScreen(fieldId: 'f1', api: apiFor(a), role: 'owner')),
    );
    await t.pumpAndSettle();
    await t.tap(find.text('موسم جديد'));
    await t.pumpAndSettle();
    expect(
      find.text('حفظ موسم جديد يُغلق الموسم النشط الحاليّ.'),
      findsOneWidget,
    );

    await t.tap(find.text('حفظ الموسم'));
    await t.pumpAndSettle();
    await t.tap(find.text('متابعة')); // تأكيد إغلاق الموسم النشط
    await t.pumpAndSettle();
    expect(find.text('اختر المحصول'), findsOneWidget);
    expect(find.text('حدّد تاريخ الزراعة'), findsOneWidget);
    expect(a.requests.where((r) => r.method == 'POST'), isEmpty);
  });

  test(
    'form cubit reuses one Idempotency-Key across retries of a create',
    () async {
      var calls = 0;
      final a = FakeAdapter((o) async {
        calls++;
        if (calls == 1) {
          return const FakeReply(422, {'detail': 'تاريخ البذار قبل الحراثة'});
        }
        return const FakeReply(201, {
          'season_id': 'ssn_2',
          'field_id': 'f1',
          'crops': ['wheat'],
          'status': 'active',
          'stages': [],
          'calendar_check': {
            'requires_review': true,
            'reason_ar': 'خارج النافذة',
          },
        });
      });
      final cubit = formCubit(a);
      final input = SeasonFormInput(
        crop: 'wheat',
        sowingDate: DateTime(2026, 3, 5),
      );
      await cubit.submit(input);
      expect(
        (cubit.state as SeasonFormEditing).submitError,
        'تاريخ البذار قبل الحراثة',
      );
      await cubit.submit(input);
      final saved = (cubit.state as SeasonFormSaved).season;
      expect(saved.calendarCheck?['reason_ar'], 'خارج النافذة');

      final posts = a.to('/api/v1/fields/f1/seasons');
      expect(posts, hasLength(2));
      expect(
        posts[0].headers['Idempotency-Key'],
        posts[1].headers['Idempotency-Key'],
      );
      expect(posts[0].data, {
        'crops': ['wheat'],
        'sowing_date': '2026-03-05',
      });
      await cubit.close();
    },
  );

  test(
    'UI-M3 (D1): an edited season after an unknown outcome is not sent and '
    'keeps the key; recovery returns the committed season with the edit '
    'pending',
    () async {
      // دلالة season.create: مفتاح معروف ⇒ النتيجة المخزّنة بلا مقارنة جسم.
      final committed = <String, Map<String, dynamic>>{};
      var calls = 0;
      final a = FakeAdapter((o) async {
        if (o.path != '/api/v1/fields/f1/seasons') {
          return const FakeReply(404, {'detail': 'x'});
        }
        calls++;
        final key = o.headers['Idempotency-Key'] as String;
        final body = o.data as Map;
        final result = committed.putIfAbsent(
          key,
          () => {
            'season_id': 'ssn_${committed.length + 1}',
            'field_id': 'f1',
            'crops': body['crops'],
            'status': 'active',
            'stages': [],
          },
        );
        return calls == 1
            ? const FakeReply.fail(DioExceptionType.receiveTimeout)
            : FakeReply(201, result);
      });
      final cubit = formCubit(a);
      await cubit.submit(
        SeasonFormInput(crop: 'wheat', sowingDate: DateTime(2026, 3, 5)),
      );
      expect(
        (cubit.state as SeasonFormUnconfirmed).outcome.messageAr,
        kOperationUnknownAr,
      );
      await cubit.submit(
        SeasonFormInput(crop: 'maize', sowingDate: DateTime(2026, 3, 5)),
      );
      expect(a.to('/api/v1/fields/f1/seasons'), hasLength(1));
      await cubit.recover();

      final keys = a
          .to('/api/v1/fields/f1/seasons')
          .map((r) => r.headers['Idempotency-Key'])
          .toSet();
      expect(keys, hasLength(1), reason: 'لا مفتاح جديد');
      expect(committed, hasLength(1), reason: 'موسم واحد');
      final rec = cubit.state as SeasonFormRecovered;
      expect(rec.season.crops, ['wheat']);
      expect(rec.pendingEdits.single.after, ['maize']);
      await cubit.close();
    },
  );

  test('a wrong crop-cards shape is an error, not an empty catalog', () async {
    final a = FakeAdapter((o) async => const FakeReply(200, {'unexpected': 1}));
    expect(apiFor(a).listCropCards(), throwsA(isA<FormatException>()));
    final b = FakeAdapter((o) async => const FakeReply(403, {'detail': 'x'}));
    expect(
      apiFor(b).listSeasons('f1'),
      throwsA(
        isA<ApiException>().having((e) => e.isForbidden, 'forbidden', true),
      ),
    );
    expect(SeasonStatus.parse('active'), SeasonStatus.active);
  });
}
