// صفحة حالة المزامنة وشارة العدد: تحميل، صندوق غير متاح، فارغ، قوائم المعلّق
// والمرفوض برسالة الخادم، عدم الاتّصال، تأكيد التجاهل، إعادة المحاولة، والشارة.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/core/theme/app_theme.dart';
import 'package:sahool_app/features/offline_sync/data/durable_offline_outbox.dart';
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
