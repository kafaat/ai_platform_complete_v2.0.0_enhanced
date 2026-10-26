// شاشة دفتر المزرعة: نموذج القيد يقبل الأرقام العربيّة ويرسل مفتاحاً ثابتاً،
// العكس يمرّ بتأكيد ويرسل مرآة الأصل، الإجماليّات من الخادم وحده، والأدوار.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/permissions/permissions.dart';
import 'package:sahool_app/core/widgets/widgets.dart';
import 'package:sahool_app/features/farm_book/data/farm_book_api.dart';
import 'package:sahool_app/features/farm_book/presentation/farm_book_report_tab.dart';

import '../../core/fake_http.dart';
import 'farm_book_fakes.dart';

const _entries = '/api/v1/farm-book/entries';

Future<void> _pump(WidgetTester t, Widget app) async {
  t.view.physicalSize = const Size(1080, 3000);
  t.view.devicePixelRatio = 3;
  addTearDown(t.view.reset);
  await t.pumpWidget(app);
  await t.pumpAndSettle();
}

Future<void> _openForm(WidgetTester t) async {
  await t.tap(find.text('قيد جديد'));
  await t.pumpAndSettle();
}

Future<void> _save(WidgetTester t) async {
  final save = find.text('حفظ القيد');
  await t.ensureVisible(save);
  await t.pumpAndSettle();
  await t.tap(save);
  await t.pumpAndSettle();
}

void main() {
  group('entry form', () {
    testWidgets('accepts Arabic-Indic digits and ٫, posts a normalised amount '
        'with client_operation_id equal to the Idempotency-Key', (t) async {
      final server = FakeFarmBookServer();
      await _pump(t, server.app(AppRole.owner));
      await _openForm(t);

      await t.tap(find.text('أسمدة'));
      await t.enterText(
        find.byKey(const ValueKey('farm_book_amount')),
        '١٢٣٤٫٥',
      );
      await t.pump();
      expect(
        find.text('1234.5'),
        findsOneWidget,
        reason: 'the formatter converts Arabic-Indic digits while typing',
      );
      await _save(t);

      final posts = server.calls('POST', _entries);
      expect(posts, hasLength(1));
      final body = posts.single.body;
      expect(body['amount'], '1234.5');
      expect(body['entry_type'], 'expense');
      expect(body['payment_method'], 'cash');
      expect(body['category'], 'fertilizer');
      expect(body['currency'], 'YER');
      expect(body['farm_id'], 'farm1');
      expect(body['occurred_on'], '2026-10-26');
      expect(body['source'], 'manual_mobile');
      expect(body['client_operation_id'], isNotEmpty);
      expect(
        posts.single.headers['Idempotency-Key'],
        body['client_operation_id'],
      );
      expect(find.text('حُفظ القيد.'), findsOneWidget);
    });

    testWidgets(
      'rejects empty, zero and three-decimal amounts without a request',
      (t) async {
        final server = FakeFarmBookServer();
        await _pump(t, server.app(AppRole.owner));
        await _openForm(t);
        final amount = find.byKey(const ValueKey('farm_book_amount'));

        await _save(t);
        expect(find.text('أدخل المبلغ'), findsOneWidget);

        await t.enterText(amount, '٠');
        await _save(t);
        expect(find.text('المبلغ يجب أن يكون أكبر من صفر'), findsOneWidget);

        await t.enterText(amount, '١٫٢٣٤');
        await _save(t);
        expect(
          find.text('المبلغ يقبل منزلتين عشريّتين كحدّ أقصى'),
          findsOneWidget,
        );

        expect(server.calls('POST', _entries), isEmpty);
      },
    );

    testWidgets('credit requires a party (the server would 422 otherwise)', (
      t,
    ) async {
      final server = FakeFarmBookServer();
      await _pump(t, server.app(AppRole.owner));
      await _openForm(t);
      await t.tap(find.text('آجل'));
      await t.enterText(find.byKey(const ValueKey('farm_book_amount')), '٥٠٠');
      await _save(t);
      expect(find.text('الآجل يحتاج تحديد المورد أو العميل'), findsOneWidget);
      expect(server.calls('POST', _entries), isEmpty);
    });

    testWidgets(
      'a retried save reuses the same key; server detail is shown in Arabic',
      (t) async {
        final server = FakeFarmBookServer();
        var n = 0;
        server.onCreateEntry = (b) => ++n == 1
            ? const FakeReply(409, {'detail': 'payment_exceeds_remaining_debt'})
            : FakeReply(201, {
                'entry_id': 'fbe_new',
                'client_operation_id': b['client_operation_id'],
                'persisted': true,
                'replayed': true,
                'sync_status': 'synced',
              });
        await _pump(t, server.app(AppRole.worker));
        await _openForm(t);
        await t.enterText(
          find.byKey(const ValueKey('farm_book_amount')),
          '٢٠٠',
        );
        await _save(t);
        expect(
          find.text('المبلغ أكبر من المتبقّي على هذا القيد الآجل.'),
          findsOneWidget,
        );
        await _save(t);
        final keys = server
            .calls('POST', _entries)
            .map((s) => s.body['client_operation_id'])
            .toSet();
        expect(server.calls('POST', _entries), hasLength(2));
        expect(keys, hasLength(1), reason: 'one intent ⇒ one key');
        expect(find.text('القيد محفوظ مسبقاً (لم يُكرَّر).'), findsOneWidget);
      },
    );
  });

  group('reversal', () {
    FakeFarmBookServer serverWithEntry() => FakeFarmBookServer(
      entries: [
        entryJson(
          id: 'fbe_1',
          category: 'seed',
          amount: 1500.5,
          method: 'credit',
          partyId: 'party_a',
          partyName: 'مورد البذور',
          on: '2026-10-05',
          fieldId: 'f1',
        ),
      ],
    );

    testWidgets('asks for confirmation; cancelling sends nothing', (t) async {
      final server = serverWithEntry();
      await _pump(t, server.app(AppRole.owner));
      await t.tap(find.text('مصروف: بذور'));
      await t.pumpAndSettle();
      await t.tap(find.text('عكس القيد (تصحيح)'));
      await t.pumpAndSettle();
      expect(find.text('عكس القيد؟'), findsOneWidget);
      await t.tap(find.text('إلغاء'));
      await t.pumpAndSettle();
      expect(server.calls('POST', _entries), isEmpty);
    });

    testWidgets(
      'confirmed reversal posts an exact mirror with reverses_entry_id',
      (t) async {
        final server = serverWithEntry();
        await _pump(t, server.app(AppRole.owner));
        await t.tap(find.text('مصروف: بذور'));
        await t.pumpAndSettle();
        await t.tap(find.text('عكس القيد (تصحيح)'));
        await t.pumpAndSettle();
        await t.tap(find.text('اعكس القيد'));
        await t.pumpAndSettle();

        final post = server.calls('POST', _entries).single;
        final b = post.body;
        expect(b['reverses_entry_id'], 'fbe_1');
        expect(b['entry_type'], 'expense');
        expect(b['payment_method'], 'credit');
        expect(b['category'], 'seed');
        expect(b['amount'], '1500.50');
        expect(b['currency'], 'YER');
        expect(b['party_id'], 'party_a');
        expect(b['field_id'], 'f1');
        expect(b['farm_id'], 'farm1');
        expect(b['occurred_on'], '2026-10-26', reason: 'dated today');
        expect(b.containsKey('settles_entry_id'), isFalse);
        expect(post.headers['Idempotency-Key'], b['client_operation_id']);
        expect(
          find.text('سُجّل القيد العكسي؛ أثر القيد الأصليّ أُلغي.'),
          findsOneWidget,
        );
      },
    );

    testWidgets('already reversed / payment entries offer no reverse button', (
      t,
    ) async {
      final server = FakeFarmBookServer(
        entries: [
          entryJson(id: 'fbe_r', reverses: 'fbe_1', on: '2026-10-07'),
          entryJson(id: 'fbe_1', on: '2026-10-05'),
          entryJson(
            id: 'fbe_p',
            type: 'payment',
            category: 'debt_payment',
            on: '2026-10-06',
          ),
        ],
      );
      await _pump(t, server.app(AppRole.owner));
      expect(find.text('معكوس'), findsOneWidget);
      expect(find.text('قيد عكسي (تصحيح)'), findsOneWidget);

      await t.tap(find.text('معكوس'));
      await t.pumpAndSettle();
      expect(find.text('عكس القيد (تصحيح)'), findsNothing);
      expect(
        find.text('هذا القيد عُكس من قبل؛ لا يُعكس مرّتين.'),
        findsOneWidget,
      );
      Navigator.of(t.element(find.byType(BottomSheet))).pop();
      await t.pumpAndSettle();

      await t.tap(find.text('سداد دين: سداد دين'));
      await t.pumpAndSettle();
      expect(find.text('عكس القيد (تصحيح)'), findsNothing);
      expect(find.text('لا يمكن عكس قيد سداد.'), findsOneWidget);
    });

    testWidgets('a server refusal stays in the sheet in Arabic', (t) async {
      final server = serverWithEntry()
        ..onCreateEntry = (_) =>
            const FakeReply(409, {'detail': 'entry_already_reversed'});
      await _pump(t, server.app(AppRole.owner));
      await t.tap(find.text('مصروف: بذور'));
      await t.pumpAndSettle();
      await t.tap(find.text('عكس القيد (تصحيح)'));
      await t.pumpAndSettle();
      await t.tap(find.text('اعكس القيد'));
      await t.pumpAndSettle();
      expect(
        find.text('هذا القيد عُكس من قبل؛ لا يُعكس مرّتين.'),
        findsOneWidget,
      );
      expect(find.byType(BottomSheet), findsOneWidget);
    });
  });

  group('monthly report', () {
    testWidgets('renders the server totals only, not a client-side sum', (
      t,
    ) async {
      // القيود المعروضة مجموعها 100، لكنّ الخادم (بعد مصافاة عكسٍ من شهر سابق)
      // يقول 4,250.75 — الشاشة تعرض رقم الخادم.
      final server = FakeFarmBookServer(
        entries: [entryJson(id: 'fbe_1', amount: 100)],
        monthlySummary: summaryJson(
          expenses: 4250.75,
          income: 9000,
          net: 4749.25,
          cash: -120,
          payable: 300,
          receivable: 0,
          count: 3,
          expenseBreakdown: {'seed': 4250.75},
        ),
        balancesSummary: summaryJson(payable: 777, receivable: 55),
      );
      await _pump(t, server.app(AppRole.owner));
      await t.tap(find.text('التقرير الشهريّ'));
      await t.pumpAndSettle();

      expect(find.text('4,250.75'), findsOneWidget);
      expect(find.text('9,000'), findsOneWidget);
      expect(find.text('4,749.25'), findsOneWidget);
      expect(find.text('-120'), findsOneWidget);
      expect(find.text('100'), findsNothing);
      expect(find.text('777'), findsOneWidget);
      expect(find.text('4,250.75 ر.ي'), findsOneWidget, reason: 'breakdown');

      final monthly = server.calls('GET', '/api/v1/farm-book/monthly').single;
      expect(monthly.query, {'month': '2026-10', 'farm_id': 'farm1'});
      final bal = server.calls('GET', '/api/v1/farm-book/balances').single;
      expect(bal.query['as_of'], '2026-10-26');
      final list = server.calls('GET', _entries).single;
      expect(list.query, {
        'farm_id': 'farm1',
        'from': '2026-10-01',
        'to': '2026-10-31',
      });
    });

    testWidgets('multiple currencies: no fabricated total', (t) async {
      final server = FakeFarmBookServer(
        monthlySummary: {
          'status': 'multiple_currencies',
          'currencies': ['USD', 'YER'],
          'entries_count': 2,
        },
      );
      await _pump(t, server.app(AppRole.manager));
      await t.tap(find.text('التقرير الشهريّ'));
      await t.pumpAndSettle();
      expect(find.textContaining('USD، YER'), findsOneWidget);
      expect(find.text('المصروف'), findsNothing);
    });

    testWidgets('previous month reloads the window from the server', (t) async {
      final server = FakeFarmBookServer();
      await _pump(t, server.app(AppRole.owner));
      expect(find.text('أكتوبر 2026'), findsOneWidget);
      await t.tap(find.byTooltip('الشهر السابق'));
      await t.pumpAndSettle();
      expect(find.text('سبتمبر 2026'), findsOneWidget);
      expect(
        server.calls('GET', '/api/v1/farm-book/monthly').last.query['month'],
        '2026-09',
      );
      expect(server.calls('GET', _entries).last.query['to'], '2026-09-30');
    });

    testWidgets('a 503 on the report shows the honest message', (t) async {
      final server = FakeFarmBookServer()
        ..intercept = (o) => o.path == '/api/v1/farm-book/monthly'
            ? const FakeReply(503, {'detail': 'db down'})
            : null;
      await _pump(t, server.app(AppRole.owner));
      await t.tap(find.text('التقرير الشهريّ'));
      await t.pumpAndSettle();
      expect(
        find.text(
          'الخدمة غير متاحة حاليّاً (قاعدة البيانات معطّلة على الخادم).',
        ),
        findsOneWidget,
      );
    });
  });

  group('roles', () {
    testWidgets('worker writes but gets no report calls (no ANALYTICS_VIEW)', (
      t,
    ) async {
      final server = FakeFarmBookServer();
      await _pump(t, server.app(AppRole.worker));
      expect(find.text('قيد جديد'), findsOneWidget);
      expect(find.byTooltip('تصدير تقرير الشهر'), findsNothing);
      await t.tap(find.text('التقرير الشهريّ'));
      await t.pumpAndSettle();
      expect(find.text(kReportNotAllowedAr), findsOneWidget);
      expect(server.calls('GET', '/api/v1/farm-book/monthly'), isEmpty);
      expect(server.calls('GET', '/api/v1/farm-book/balances'), isEmpty);
    });

    testWidgets('agronomist reads reports but cannot add or reverse', (
      t,
    ) async {
      final server = FakeFarmBookServer(entries: [entryJson(id: 'fbe_1')]);
      await _pump(t, server.app(AppRole.agronomist));
      expect(find.text('قيد جديد'), findsNothing);
      await t.tap(find.text('مصروف: بذور'));
      await t.pumpAndSettle();
      expect(find.text('عكس القيد (تصحيح)'), findsNothing);
    });
  });

  testWidgets('export hands the server bytes to the sharer', (t) async {
    final server = FakeFarmBookServer();
    FarmBookExport? shared;
    await _pump(t, server.app(AppRole.owner, sharer: (f) async => shared = f));
    await t.tap(find.byTooltip('تصدير تقرير الشهر'));
    await t.pumpAndSettle();
    await t.tap(find.text('تصدير CSV (جدول)'));
    await t.pumpAndSettle();
    // المحوّل المزيّف يعيد 404 لمسار التصدير ⇒ رسالة صادقة لا ملفّ مُختلَق.
    expect(shared, isNull);
    expect(find.textContaining('تعذّر التصدير'), findsOneWidget);
  });

  testWidgets('export success: server file (name from Content-Disposition) '
      'goes to the sharer', (t) async {
    final server = FakeFarmBookServer()
      ..intercept = (o) => o.path == '/api/v1/farm-book/export'
          ? const FakeReply(200, 'entry_id,amount', {
              'content-disposition': [
                'attachment; filename="farm_book_2026-10.pdf"',
              ],
            })
          : null;
    FarmBookExport? shared;
    await _pump(
      t,
      server.app(AppRole.manager, sharer: (f) async => shared = f),
    );
    await t.tap(find.byTooltip('تصدير تقرير الشهر'));
    await t.pumpAndSettle();
    await t.tap(find.text('تصدير PDF'));
    await t.pumpAndSettle();
    expect(shared, isNotNull);
    expect(shared!.filename, 'farm_book_2026-10.pdf');
    expect(shared!.bytes, isNotEmpty);
    final q = server.calls('GET', '/api/v1/farm-book/export').single.query;
    expect(q, {'month': '2026-10', 'format': 'pdf', 'farm_id': 'farm1'});
  });

  testWidgets('parties tab says per-party balances are not available yet', (
    t,
  ) async {
    final server = FakeFarmBookServer();
    await _pump(t, server.app(AppRole.owner));
    await t.tap(find.text('الأطراف'));
    await t.pumpAndSettle();
    expect(find.text('مورد البذور'), findsOneWidget);
    expect(
      find.textContaining('رصيد كلّ طرف على حدة غير متاح بعد'),
      findsOneWidget,
    );
    expect(find.byType(EmptyState), findsNothing);
  });
}
