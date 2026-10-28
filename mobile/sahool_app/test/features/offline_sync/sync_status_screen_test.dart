// صفحة حالة المزامنة وشارة العدد: تحميل، صندوق غير متاح، فارغ، قوائم المعلّق
// والمرفوض برسالة الخادم، عدم الاتّصال، تأكيد التجاهل، إعادة المحاولة، والشارة.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hive/hive.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/data/offline_sync_api.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_record.dart';
import 'package:sahool_app/features/offline_sync/data/outbox_store.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/offline_sync/presentation/pending_sync_badge.dart';
import 'package:sahool_app/features/offline_sync/presentation/sync_status_screen.dart';

import '../../core/fake_http.dart';
import 'outbox_test_support.dart';

Widget _app(Widget child) => MaterialApp(
  theme: AppTheme.light,
  locale: const Locale('ar', 'YE'),
  supportedLocales: const [Locale('ar', 'YE')],
  localizationsDelegates: GlobalMaterialLocalizations.delegates,
  home: child,
);

OutboxRecord _rec(
  String id,
  int seq, {
  String? label,
  String? fieldId,
  bool rejected = false,
  String owner = 'alice',
}) => OutboxRecord(
  id: id,
  seq: seq,
  owner: OutboxOwner(userId: owner, tenantId: 't1'),
  op: op('/api/v1/tasks/$id', fieldId: fieldId, label: label),
  createdAt: DateTime.utc(2026, 10, 26, 6), // قبل ساعتين من ساعة Harness
  state: rejected ? OutboxRecordState.rejected : OutboxRecordState.pending,
  attempts: rejected ? 1 : 0,
  rejectedStatus: rejected ? 422 : null,
  rejectedMessageAr: rejected ? 'الحالة غير صالحة لهذه المهمّة' : null,
);

void main() {
  Future<Harness> seeded(
    WidgetTester tester,
    List<OutboxRecord> records, {
    bool online = false,
    FakeHandler? handler,
  }) async {
    final h = Harness(online: online, handler: handler);
    for (final r in records) {
      await h.store.put(r);
    }
    return h;
  }

  Future<void> pumpScreen(WidgetTester tester, Harness h) async {
    // شاشة طويلة كي تُبنى كلّ البطاقات (القائمة كسولة).
    tester.view.physicalSize = const Size(1080, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      _app(
        SyncStatusScreen(
          outbox: h.outbox,
          connectivity: h.connectivity,
          now: () => h.now,
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  test('every kind an app producer enqueues has an Arabic label', () {
    for (final kind in [
      'observation_create',
      'task_update',
      'activity_complete',
      'activity_create',
      'water_applied',
      'inventory_batch_add',
      'equipment_maintenance_log',
      'lab_sample_create',
      'farm_book_entry',
    ]) {
      expect(outboxKindLabelAr(kind), isNot(kind), reason: kind);
    }
    // نوع لا يعرفه هذا الإصدار يُعرض باسمه، لا يُخفى ولا يُرفض.
    expect(outboxKindLabelAr('new_kind'), 'new_kind');
  });

  testWidgets('loading while the encrypted box opens', (tester) async {
    final never = Completer<OutboxStore>();
    final outbox = DurableOfflineOutbox(
      openStore: () => never.future,
      currentOwner: () => const OutboxOwner(userId: 'a', tenantId: 't'),
    );
    await tester.pumpWidget(
      _app(SyncStatusScreen(outbox: outbox, connectivity: ValueNotifier(true))),
    );
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('unavailable box shows the honest reason, not an empty list', (
    tester,
  ) async {
    final outbox = DurableOfflineOutbox(
      openStore: () async =>
          throw const OutboxStoreException(OutboxStoreFailure.keyStorage),
      currentOwner: () => const OutboxOwner(userId: 'a', tenantId: 't'),
    );
    await tester.pumpWidget(
      _app(SyncStatusScreen(outbox: outbox, connectivity: ValueNotifier(true))),
    );
    await tester.pump();
    await tester.pump();
    expect(find.text('صندوق المزامنة غير متاح'), findsOneWidget);
    expect(find.textContaining('مفتاح التشفير'), findsOneWidget);
    expect(find.textContaining('لا عمليّات'), findsNothing);
    expect(find.text('حذف الصندوق غير المقروء'), findsNothing);
  });

  testWidgets('unreadable box can be deleted only after confirmation', (
    tester,
  ) async {
    var deleted = 0;
    var keyLost = true;
    final store = MemoryOutboxStore();
    final outbox = DurableOfflineOutbox(
      openStore: () async {
        if (keyLost) {
          throw const OutboxStoreException(
            OutboxStoreFailure.keyMissingForExistingBox,
          );
        }
        return store;
      },
      currentOwner: () => const OutboxOwner(userId: 'a', tenantId: 't'),
      deleteUnreadableBox: () async {
        deleted++;
        keyLost = false;
      },
    );
    await tester.pumpWidget(
      _app(SyncStatusScreen(outbox: outbox, connectivity: ValueNotifier(true))),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.text('حذف الصندوق غير المقروء'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('إلغاء'));
    await tester.pumpAndSettle();
    expect(deleted, 0);

    await tester.tap(find.text('حذف الصندوق غير المقروء'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'حذف'));
    await tester.pumpAndSettle();
    expect(deleted, 1);
    expect(find.textContaining('لا عمليّات بانتظار المزامنة'), findsOneWidget);
  });

  testWidgets('empty state when nothing waits', (tester) async {
    final h = await seeded(tester, []);
    await pumpScreen(tester, h);
    expect(find.textContaining('لا عمليّات بانتظار المزامنة'), findsOneWidget);
    expect(find.text('إرسال الآن'), findsNothing);
  });

  testWidgets('an undecodable stored row is not reported as "everything '
      'reached the server" (UI-S2)', (tester) async {
    final dir = Directory.systemTemp.createTempSync('sync_unreadable');
    late OutboxStore store;
    await tester.runAsync(() async {
      Hive.init(dir.path);
      FlutterSecureStorage.setMockInitialValues({});
      final first = await HiveOutboxStore.openEncrypted();
      // سجلّ من إصدار أحدث/تالف: يبقى على القرص ولا يُفكّ.
      await Hive.box<String>(HiveOutboxStore.boxName).put('future', '{"v":9');
      await first.close();
      store = await HiveOutboxStore.openEncrypted();
    });
    addTearDown(() async {
      await tester.runAsync(() async {
        await Hive.close();
        dir.deleteSync(recursive: true);
      });
    });
    final h = Harness();
    final outbox = DurableOfflineOutbox(
      openStore: () async => store,
      currentOwner: () => OutboxOwner.fromAccessToken(h.tokens.accessToken),
      connectivity: h.connectivity,
    );
    tester.view.physicalSize = const Size(1080, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      _app(
        SyncStatusScreen(
          outbox: outbox,
          connectivity: h.connectivity,
          now: () => h.now,
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(find.textContaining('وصل إلى الخادم'), findsNothing);
    expect(find.byKey(const ValueKey('sync-unreadable')), findsOneWidget);
  });

  testWidgets('R12 — one corrupt row while every other row reaches the server: '
      'a clear needs-attention counter and no global success message, across '
      'a storage reopen and a fresh screen', (tester) async {
    final dir = Directory.systemTemp.createTempSync('sync_r12');
    late OutboxStore store;
    final h = Harness(online: true);
    final rows = [
      _rec('a', 1, label: 'مهمّة أ'),
      _rec('b', 2, label: 'مهمّة ب'),
    ];
    await tester.runAsync(() async {
      Hive.init(dir.path);
      FlutterSecureStorage.setMockInitialValues({});
      final first = await HiveOutboxStore.openEncrypted();
      for (final r in rows) {
        await first.put(r);
      }
      // صفّ تالف بين صفّين سليمين.
      await Hive.box<String>(HiveOutboxStore.boxName).put('corrupt', '{"v":1,');
      await first.close();
      store = await HiveOutboxStore.openEncrypted();
    });
    addTearDown(() async {
      await tester.runAsync(() async {
        await Hive.close();
        dir.deleteSync(recursive: true);
      });
    });
    DurableOfflineOutbox outboxOn(OutboxStore s) => DurableOfflineOutbox(
      openStore: () async => s,
      currentOwner: () => OutboxOwner.fromAccessToken(h.tokens.accessToken),
      api: OfflineSyncApi(testClient(h.adapter, h.tokens)),
      connectivity: h.connectivity,
      clock: () => h.now,
      timer: (d, cb) => RecordedTimer(d, cb),
    );
    tester.view.physicalSize = const Size(1080, 4000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final outbox = outboxOn(store);
    await tester.pumpWidget(
      _app(
        SyncStatusScreen(
          outbox: outbox,
          connectivity: h.connectivity,
          now: () => h.now,
        ),
      ),
    );
    await tester.pump();
    await tester.runAsync(() async {
      await outbox.drain();
      for (var i = 0; i < 50 && store.records.isNotEmpty; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
    });
    await tester.pump();
    await tester.pump();

    void expectHonest() {
      expect(find.textContaining('وصل إلى الخادم'), findsNothing);
      expect(find.textContaining('لا عمليّات بانتظار المزامنة'), findsNothing);
      expect(find.text('بانتظار الإرسال: 0'), findsOneWidget);
      final chip = find.byKey(const ValueKey('sync-attention-count'));
      expect(chip, findsOneWidget);
      expect(
        find.descendant(of: chip, matching: find.text('تحتاج تدخّلاً: 1')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('sync-unreadable')), findsOneWidget);
    }

    expect(h.adapter.requests.map((r) => r.path), [
      '/api/v1/tasks/a',
      '/api/v1/tasks/b',
    ]);
    expectHonest();

    // الشاشة تُغلق، التخزين يُعاد فتحه (إعادة تشغيل)، والشاشة تُفتح من جديد.
    await tester.pumpWidget(const SizedBox());
    late OutboxStore reopened;
    await tester.runAsync(() async {
      await (store as HiveOutboxStore).close();
      reopened = await HiveOutboxStore.openEncrypted();
    });
    await tester.pumpWidget(
      _app(
        SyncStatusScreen(
          outbox: outboxOn(reopened),
          connectivity: h.connectivity,
          now: () => h.now,
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    expect(reopened.records, isEmpty);
    expect(reopened.unreadableCount, 1);
    expectHonest();
  });

  testWidgets('each op shows its delivery state: saved locally, pending retry, '
      'outcome unknown, needs attention; a payload-mismatch conflict offers '
      'no blind retry; a server Retry-After is shown and blocks "send now"', (
    tester,
  ) async {
    OutboxRecord fromJson(Map<String, dynamic> extra, String id, int seq) {
      final base = _rec(id, seq, label: 'عمليّة $id').toJson();
      return OutboxRecord.fromJson({...base, ...extra});
    }

    final h = await seeded(tester, [
      fromJson({}, 'saved', 1),
      fromJson(
        {
          'attempts': 1,
          'last_outcome': 'retryLater',
          'next_attempt_at': '2026-10-26T08:10:00.000Z',
          'not_before': '2026-10-26T08:10:00.000Z',
        },
        'waiting',
        2,
      ),
      fromJson(
        {'attempts': 1, 'outcome_unknown': true, 'last_outcome': 'offline'},
        'unknown',
        3,
      ),
      fromJson(
        {
          'state': 'rejected',
          'attempts': 1,
          'rejected_status': 409,
          'rejected_message_ar': 'المفتاح مستعمَل لحمولة أخرى.',
          'conflict_reason': 'payload_mismatch',
        },
        'mismatch',
        4,
      ),
    ], online: true);
    await pumpScreen(tester, h);

    String stateOf(String id) {
      final chip = find.byKey(ValueKey('sync-op-state-$id'));
      expect(chip, findsOneWidget, reason: id);
      return tester
          .widgetList<Text>(
            find.descendant(of: chip, matching: find.byType(Text)),
          )
          .map((t) => t.data)
          .join();
    }

    expect(stateOf('saved'), 'محفوظة على الجهاز');
    expect(stateOf('waiting'), 'بانتظار إعادة المحاولة');
    expect(stateOf('unknown'), 'النتيجة غير مؤكَّدة');
    expect(stateOf('mismatch'), 'تحتاج تدخّلاً');
    expect(find.text('نتيجتها غير مؤكَّدة: 1'), findsOneWidget);
    expect(find.text('تحتاج تدخّلاً: 1'), findsOneWidget);

    // تعارض الحمولة: شرحٌ ولا زرّ إعادة؛ التجاهل وحده متاح.
    final mismatchCard = find.byKey(const ValueKey('sync-op-mismatch'));
    expect(
      find.byKey(const ValueKey('sync-op-mismatch-mismatch')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: mismatchCard, matching: find.text('إعادة المحاولة')),
      findsNothing,
    );
    expect(
      find.descendant(of: mismatchCard, matching: find.text('تجاهل')),
      findsOneWidget,
    );

    // Retry-After ظاهر، و«إرسال الآن» على بطاقته معطَّل.
    expect(
      find.byKey(const ValueKey('sync-op-not-before-waiting')),
      findsOneWidget,
    );
    final waitingCard = find.byKey(const ValueKey('sync-op-waiting'));
    final sendOnWaiting = tester.widget<ButtonStyleButton>(
      find
          .descendant(
            of: waitingCard,
            matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
          )
          .first,
    );
    expect(sendOnWaiting.onPressed, isNull);
  });

  testWidgets('lists rejected (with server message) and pending ops with '
      'label, field and age; offline disables sending', (tester) async {
    final h = await seeded(tester, [
      _rec('1', 1, label: 'إنهاء مهمّة الريّ', fieldId: 'field-7'),
      _rec('2', 2, rejected: true, fieldId: 'field-9'),
      _rec('3', 3, owner: 'bob'),
    ]);
    await pumpScreen(tester, h);

    expect(find.text('بانتظار الإرسال: 1'), findsOneWidget);
    expect(find.text('مرفوضة: 1'), findsOneWidget);
    expect(find.text('إنهاء مهمّة الريّ'), findsOneWidget);
    expect(find.text('الحقل: field-7'), findsOneWidget);
    expect(find.text('سُجِّلت منذ 2 ساعة'), findsNWidgets(2));
    // المعنون: النوع سطراً ثانياً؛ غير المعنون: النوع عنواناً والطريقة والمسار تحته.
    expect(find.text('تحديث مهمّة'), findsNWidgets(2));
    expect(find.text('PATCH /api/v1/tasks/2'), findsOneWidget);
    expect(find.text('رفضها الخادم (422)'), findsOneWidget);
    expect(find.text('الحالة غير صالحة لهذه المهمّة'), findsOneWidget);
    expect(find.textContaining('لحساب آخر'), findsOneWidget);
    expect(
      find.textContaining('/api/v1/tasks/3'),
      findsNothing,
      reason: 'bob\'s op is not shown to alice',
    );

    expect(find.textContaining('لا اتّصال بالشبكة'), findsOneWidget);
    final sendButtons = tester.widgetList<ButtonStyleButton>(
      find.ancestor(
        of: find.text('إرسال الآن'),
        matching: find.byWidgetPredicate((w) => w is ButtonStyleButton),
      ),
    );
    expect(sendButtons, hasLength(2)); // الملخّص + بطاقة العمليّة
    for (final b in sendButtons) {
      expect(b.onPressed, isNull);
    }
  });

  testWidgets('discard asks for confirmation; cancel keeps the op', (
    tester,
  ) async {
    final h = await seeded(tester, [_rec('1', 1, label: 'ملاحظة')]);
    await pumpScreen(tester, h);

    await tester.tap(find.text('تجاهل'));
    await tester.pumpAndSettle();
    expect(find.text('تجاهل هذه العمليّة؟'), findsOneWidget);
    await tester.tap(find.text('إلغاء'));
    await tester.pumpAndSettle();
    expect(h.store.records, hasLength(1));

    await tester.tap(find.text('تجاهل'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'تجاهل'));
    await tester.pumpAndSettle();
    expect(h.store.records, isEmpty);
    expect(find.textContaining('لا عمليّات بانتظار المزامنة'), findsOneWidget);
  });

  testWidgets('retry of a rejected op resends it and clears it on 2xx', (
    tester,
  ) async {
    final h = await seeded(tester, [
      _rec('1', 1, rejected: true),
    ], online: true);
    await pumpScreen(tester, h);
    await tester.runAsync(() async {
      await tester.tap(find.text('إعادة المحاولة'));
      for (var i = 0; i < 50 && h.store.records.isNotEmpty; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
    });
    await tester.pump();
    expect(h.adapter.to('/api/v1/tasks/1'), hasLength(1));
    expect(h.store.records, isEmpty);
    expect(find.textContaining('لا عمليّات بانتظار المزامنة'), findsOneWidget);
  });

  testWidgets('signed out ⇒ asks to sign in, shows no one\'s ops', (
    tester,
  ) async {
    final h = await seeded(tester, [_rec('1', 1)]);
    h.tokens.accessToken = null;
    await pumpScreen(tester, h);
    expect(find.textContaining('سجّل الدخول'), findsOneWidget);
    expect(find.text('تحديث مهمّة'), findsNothing);
  });

  group('PendingSyncBadge', () {
    testWidgets('hidden when nothing waits; shows the count otherwise', (
      tester,
    ) async {
      final h = await seeded(tester, []);
      var taps = 0;
      await tester.pumpWidget(
        _app(
          Scaffold(
            appBar: AppBar(
              actions: [
                PendingSyncBadge(outbox: h.outbox, onTap: () => taps++),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const ValueKey('pending-sync-badge')), findsNothing);

      await h.outbox.enqueue(op('/api/v1/tasks/1'));
      await h.outbox.enqueue(op('/api/v1/tasks/2'));
      await tester.pump();
      expect(find.byKey(const ValueKey('pending-sync-badge')), findsOneWidget);
      expect(find.text('2'), findsOneWidget);
      await tester.tap(find.byKey(const ValueKey('pending-sync-badge')));
      expect(taps, 1);
    });

    testWidgets('works with any OfflineOutbox through pendingCount', (
      tester,
    ) async {
      await tester.pumpWidget(
        _app(
          Scaffold(
            appBar: AppBar(
              actions: const [
                PendingSyncBadge(outbox: OfflineOutbox.unavailable),
              ],
            ),
          ),
        ),
      );
      await tester.pump();
      expect(find.byKey(const ValueKey('pending-sync-badge')), findsNothing);
    });
  });
}
