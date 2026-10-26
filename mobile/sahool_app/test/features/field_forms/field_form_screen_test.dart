// شاشة النموذج كما يراها المزارع: ردّ قبول حقيقيّ يُعرض «اعتُمد» (كان يُعرض
// «محجوز (quarantined)»)، لا مفاتيح مخطّط خامّ ولا نصوص تصحيح إنجليزيّة، ضغطة
// إرسال ثانية لا تُنشئ عنصراً ثانياً، والأرقام العربيّة-الهنديّة تُقرأ أرقاماً.
import 'dart:async';
import 'dart:io';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive_flutter/hive_flutter.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/field_forms/contract/form_schema.dart';
import 'package:sahool_app/features/field_forms/data/draft_store.dart';
import 'package:sahool_app/features/field_forms/data/field_forms_api.dart';
import 'package:sahool_app/features/field_forms/data/form_package_store.dart';
import 'package:sahool_app/features/field_forms/data/submission_queue.dart';
import 'package:sahool_app/features/field_forms/presentation/field_form_screen.dart';
import 'package:sahool_app/features/field_forms/presentation/field_forms_list_screen.dart';
import 'package:sahool_app/features/field_forms/presentation/field_widget_registry.dart';
import 'package:sahool_app/features/field_forms/presentation/schema_form_renderer.dart';

import '../../core/fake_http.dart';
import 'ff_fixtures.dart';

const _package = DownloadedFormPackage(
  assignmentId: 'assign-1',
  revision: 1,
  formVersionId: 'v1',
  versionNumber: 2,
  schemaJson: {
    'title': 'استكشاف الآفات',
    'fields': [
      {
        'key': 'pest_name',
        'field_type': 'select',
        'label_ar': 'اسم الآفة',
        'options': ['aphid', 'thrips'],
        'option_labels': {'aphid': 'المنّ', 'thrips': 'التربس'},
      },
      {'key': 'leaf_count', 'field_type': 'number'},
    ],
  },
  schemaHash: 'hash-v1',
);

Widget _app(Widget home) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar'),
  supportedLocales: const [Locale('ar')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: home,
);

void main() {
  late Directory dir;
  late SubmissionQueue queue;
  late DraftStore drafts;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('ff_screen');
    Hive.init(dir.path);
    queue = SubmissionQueue(await Hive.openBox<dynamic>('q'));
    drafts = DraftStore(await Hive.openBox<dynamic>('d'));
  });

  tearDown(() async {
    await Hive.close();
    await dir.delete(recursive: true);
  });

  FieldFormCubit cubitWith(FakeAdapter? adapter) => FieldFormCubit(
    tenantId: 't',
    fieldId: 'f',
    package: _package,
    draftStore: drafts,
    submissionQueue: queue,
    api: adapter == null
        ? null
        : FieldFormsApi(
            Dio(BaseOptions(baseUrl: 'https://api.example.test'))
              ..httpClientAdapter = adapter,
          ),
    server: 'https://api.example.test',
    actorId: 'u1',
    deviceId: () async => 'dev-test',
  );

  test('ردّ قبول حقيقيّ ⇒ الحالة accepted لا quarantined', () async {
    final adapter = FakeAdapter((_) async => const FakeReply(201, kAccepted));
    final cubit = cubitWith(adapter);
    await cubit.open();
    await cubit.submit(const {'pest_name': 'aphid'});
    expect(cubit.state.status, FieldFormStatus.accepted);
    expect(queue.pending(), isEmpty);
    expect(adapter.requests.single.headers['X-Device-Id'], 'dev-test');
    await cubit.close();
  });

  test('ضغطتا إرسال متتاليتان ⇒ عنصر طابور واحد وطلب واحد', () async {
    final gate = Completer<void>();
    final adapter = FakeAdapter((_) async {
      await gate.future;
      return const FakeReply(201, kAccepted);
    });
    final cubit = cubitWith(adapter);
    await cubit.open();
    final a = cubit.submit(const {'pest_name': 'aphid'});
    final b = cubit.submit(const {'pest_name': 'aphid'});
    gate.complete();
    await Future.wait([a, b]);
    expect(adapter.requests, hasLength(1));
    await cubit.close();
  });

  test('server فارغ لا يُرسَل فارغاً (الخادم يشترط min_length=1)', () async {
    final adapter = FakeAdapter((_) async => const FakeReply(201, kAccepted));
    final cubit = FieldFormCubit(
      tenantId: 't',
      fieldId: 'f',
      package: _package,
      draftStore: drafts,
      submissionQueue: queue,
      api: FieldFormsApi(
        Dio(BaseOptions(baseUrl: 'https://api.example.test'))
          ..httpClientAdapter = adapter,
      ),
      deviceId: () async => 'dev-test',
    );
    await cubit.open();
    await cubit.submit(const {'pest_name': 'aphid'});
    final body = adapter.requests.single.data! as Map;
    expect((body['server'] as String).isNotEmpty, isTrue);
    await cubit.close();
  });

  test('انقطاع الشبكة ⇒ يبقى في الطابور برسالة عربيّة', () async {
    final adapter = FakeAdapter(
      (_) async => const FakeReply.fail(DioExceptionType.connectionError),
    );
    final cubit = cubitWith(adapter);
    await cubit.open();
    await cubit.submit(const {'pest_name': 'aphid'});
    expect(cubit.state.status, FieldFormStatus.syncFailure);
    expect(cubit.state.message, contains('محفوظة على الجهاز'));
    expect(queue.pending(), hasLength(1));
    await cubit.close();
  });

  testWidgets('تسميات بشريّة لا مفاتيح المخطّط', (tester) async {
    final cubit = cubitWith(null);
    await tester.runAsync(cubit.open);
    await tester.pumpWidget(_app(FieldFormScreen(cubit: cubit)));
    await tester.pumpAndSettle();
    expect(find.text('اسم الآفة'), findsOneWidget);
    expect(find.text('pest_name'), findsNothing);
    // بلا label_ar: المفتاح بمسافات بدل «_» (لا «leaf_count» خامّاً).
    expect(find.text('leaf count'), findsOneWidget);
    expect(find.text('leaf_count'), findsNothing);
    await tester.tap(find.byKey(const ValueKey('field_pest_name')));
    await tester.pumpAndSettle();
    expect(find.text('المنّ'), findsWidgets);
    await tester.runAsync(cubit.close);
  });

  testWidgets('نتيجة مقبولة تُعرض بالعربيّة بلا نصوص تصحيح', (tester) async {
    final adapter = FakeAdapter((_) async => const FakeReply(201, kAccepted));
    final cubit = cubitWith(adapter);
    await tester.runAsync(() async {
      await cubit.open();
      await cubit.submit(const {'pest_name': 'aphid'});
    });
    await tester.pumpWidget(_app(FieldFormScreen(cubit: cubit)));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('status_accepted')), findsOneWidget);
    expect(find.text('استُلمت إجاباتك واعتُمدت.'), findsOneWidget);
    expect(find.textContaining('quarantined'), findsNothing);
    expect(find.textContaining('version:'), findsNothing);
    expect(find.textContaining('validation:'), findsNothing);
    await tester.runAsync(cubit.close);
  });

  testWidgets('حجر يُشرح سببه بالعربيّة', (tester) async {
    final adapter = FakeAdapter(
      (_) async => const FakeReply(201, {
        'idempotent': false,
        'envelope_id': 3,
        'field_submission_id': 'fs',
        'trust_status': 'quarantined',
        'quarantine_reason': 'no_active_assignment',
        'version_resolution_status': 'no_active_assignment',
        'validation_errors': [],
      }),
    );
    final cubit = cubitWith(adapter);
    await tester.runAsync(() async {
      await cubit.open();
      await cubit.submit(const {'pest_name': 'aphid'});
    });
    await tester.pumpWidget(_app(FieldFormScreen(cubit: cubit)));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('status_quarantined')), findsOneWidget);
    expect(find.text('هذا النموذج لم يعد مُسنداً لهذا الحقل.'), findsOneWidget);
    await tester.runAsync(cubit.close);
  });

  testWidgets('نوع حقل مجهول ⇒ رسالة عربيّة لا «unsupported form schema»', (
    tester,
  ) async {
    final cubit = FieldFormCubit(
      tenantId: 't',
      fieldId: 'f',
      package: const DownloadedFormPackage(
        assignmentId: 'a',
        revision: 1,
        formVersionId: 'v',
        versionNumber: 1,
        schemaJson: {
          'fields': [
            {'key': 'x', 'field_type': 'signature'},
          ],
        },
        schemaHash: 'h',
      ),
      draftStore: drafts,
      submissionQueue: queue,
    );
    await tester.runAsync(cubit.open);
    await tester.pumpWidget(_app(FieldFormScreen(cubit: cubit)));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('unsupported_schema_message')),
      findsOneWidget,
    );
    expect(find.textContaining('unsupported'), findsNothing);
    await tester.runAsync(cubit.close);
  });

  testWidgets('رقم بأرقام عربيّة-هنديّة يُخزَّن رقماً', (tester) async {
    Map<String, Object?>? submitted;
    await tester.pumpWidget(
      _app(
        Scaffold(
          body: SchemaFormRenderer(
            schema: FormSchema.fromJson(const {
              'fields': [
                {'key': 'area', 'field_type': 'number'},
                {'key': 'count', 'field_type': 'integer'},
              ],
            }),
            onValidSubmit: (a) => submitted = a,
          ),
        ),
      ),
    );
    await tester.enterText(find.byKey(const ValueKey('field_area')), '٢٫٥');
    await tester.enterText(find.byKey(const ValueKey('field_count')), '١٢');
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted, {'area': 2.5, 'count': 12});
  });

  testWidgets('gps: «موقعي الحاليّ» يملأ الإحداثيّين', (tester) async {
    Map<String, Object?>? submitted;
    await tester.pumpWidget(
      _app(
        Scaffold(
          body: SchemaFormRenderer(
            schema: FormSchema.fromJson(const {
              'fields': [
                {'key': 'spot', 'field_type': 'gps', 'required': true},
              ],
            }),
            registry: FieldWidgetRegistry(
              locationPicker: () async => (lat: 15.35, lng: 44.2),
            ),
            onValidSubmit: (a) => submitted = a,
          ),
        ),
      ),
    );
    await tester.tap(find.byKey(const ValueKey('field_spot_locate')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('schema_form_submit')));
    await tester.pumpAndSettle();
    expect(submitted, {
      'spot': {'lat': 15.35, 'lng': 44.2},
    });
  });

  group('قائمة النماذج', () {
    late FormPackageStore packages;
    setUp(() async {
      packages = FormPackageStore(await Hive.openBox<dynamic>('p'));
    });

    testWidgets('تعرض الإرسالات المنتظرة والفاشلة بدل حذفها', (tester) async {
      await tester.runAsync(() async {
        await packages.save(tenantId: 't', fieldId: 'f', package: _package);
        await queue.enqueue(
          tenantId: 't',
          fieldId: 'f',
          assignmentId: 'a',
          assignmentRevision: 1,
          formVersionId: 'v',
          schemaHash: 'h',
          answers: const {},
          server: 's',
        );
        final bad = await queue.enqueue(
          tenantId: 't',
          fieldId: 'f',
          assignmentId: 'a',
          assignmentRevision: 1,
          formVersionId: 'v',
          schemaHash: 'h',
          answers: const {},
          server: 's',
        );
        await queue.markFailed(bad, 'HTTP 400');
      });
      final signal = ValueNotifier<int>(0);
      await tester.pumpWidget(
        _app(
          FieldFormsListScreen(
            fieldId: 'f',
            packages: packages,
            queue: queue,
            tenantId: 't',
            actorId: 'u1',
            server: 's',
            openDraftStore: () async => drafts,
            refreshSignal: signal,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('field_forms_pending')), findsOneWidget);
      expect(find.text('لم يُقبل'), findsOneWidget);
      expect(find.text('استكشاف الآفات'), findsOneWidget);

      // انتهاء تصريف في الخلفيّة ⇒ القائمة تُحدَّث بلا إعادة فتح.
      await tester.runAsync(() async {
        for (final p in queue.pending()) {
          await queue.remove(p.instanceId);
        }
      });
      signal.value++;
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('field_forms_pending')), findsNothing);
    });

    testWidgets('فشل فتح المسودّات يُعرض لا يُبتلَع', (tester) async {
      await tester.runAsync(
        () => packages.save(tenantId: 't', fieldId: 'f', package: _package),
      );
      await tester.pumpWidget(
        _app(
          FieldFormsListScreen(
            fieldId: 'f',
            packages: packages,
            queue: queue,
            tenantId: 't',
            server: 's',
            openDraftStore: () async => throw const FileSystemException('x'),
            refreshSignal: ValueNotifier<int>(0),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const ValueKey('field_form_assign-1')));
      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('field_forms_open_error')),
        findsOneWidget,
      );
    });
  });
}
