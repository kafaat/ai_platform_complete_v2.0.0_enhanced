// شاشة «مشاهدة جديدة»: رسائل التحقّق، مسار رفض GPS ومركز الحقل، إشعار الصور
// الصادق، و«محفوظ للإرسال» فقط حين يقول الإيصال ذلك.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/offline_sync/offline_outbox.dart';
import 'package:sahool_app/features/scouting/data/device_sources.dart';
import 'package:sahool_app/features/scouting/presentation/new_observation_screen.dart';

import '../../core/fake_http.dart';
import 'scouting_fakes.dart';

/// شاشة طويلة كي تُبنى كلّ البطاقات (القائمة كسولة البناء).
void tallTest(String name, Future<void> Function(WidgetTester t) body) =>
    testWidgets(name, (t) async {
      t.view.physicalSize = const Size(800, 3200);
      t.view.devicePixelRatio = 1;
      addTearDown(t.view.reset);
      await body(t);
    });

void main() {
  Future<FakeReply> taxonomy(dynamic o) async =>
      const FakeReply(200, {'crop': 'wheat', 'issues': []});

  Future<void> tapVisible(WidgetTester t, Finder f) async {
    await t.ensureVisible(f);
    await t.pumpAndSettle();
    await t.tap(f);
    await t.pumpAndSettle();
  }

  tallTest('submit with nothing chosen shows every validation message', (
    t,
  ) async {
    final (api, adapter) = fakeApi((o) async => taxonomy(o));
    await t.pumpWidget(
      host(
        NewObservationScreen(
          field: sanaaField,
          deps: testDeps(
            api: api,
            location: FakeLocation(const GpsFailure(GpsFailureReason.denied)),
          ),
        ),
      ),
    );
    await t.pumpAndSettle();
    await t.tap(find.text('حفظ المشاهدة'));
    await t.pumpAndSettle();
    expect(
      find.text('حدّد الموقع (GPS أو مركز الحقل) قبل الحفظ.'),
      findsOneWidget,
    );
    expect(find.text('اختر نوع المشكلة.'), findsOneWidget);
    expect(find.text('اختر الشدّة.'), findsOneWidget);
    expect(adapter.to('/api/v1/fields/f1/pins'), isEmpty);
  });

  tallTest(
    'GPS denied: honest message, then "use field centre" fills the location',
    (t) async {
      final (api, _) = fakeApi((o) async => taxonomy(o));
      await t.pumpWidget(
        host(
          NewObservationScreen(
            field: sanaaField,
            deps: testDeps(
              api: api,
              location: FakeLocation(const GpsFailure(GpsFailureReason.denied)),
            ),
          ),
        ),
      );
      await t.pumpAndSettle();
      expect(find.text('إذن الموقع مرفوض — لم يُحدَّد موقعك.'), findsOneWidget);
      await t.tap(find.text('استخدم مركز الحقل'));
      await t.pumpAndSettle();
      expect(
        find.text('مركز الحقل — ليس موقع المشاهدة المقيس'),
        findsOneWidget,
      );
      expect(find.text('15.350000, 44.200000'), findsOneWidget);
    },
  );

  tallTest('denied forever offers the settings button', (t) async {
    final loc = FakeLocation(const GpsFailure(GpsFailureReason.deniedForever));
    final (api, _) = fakeApi((o) async => taxonomy(o));
    await t.pumpWidget(
      host(
        NewObservationScreen(
          field: noCentreField,
          deps: testDeps(api: api, location: loc),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('لا مركز مسجَّل لهذا الحقل على الخادم.'), findsOneWidget);
    await tapVisible(t, find.text('فتح الإعدادات'));
    expect(loc.settingsOpened, 1);
  });

  tallTest('GPS fix shows the accuracy', (t) async {
    final (api, _) = fakeApi((o) async => taxonomy(o));
    await t.pumpWidget(
      host(
        NewObservationScreen(
          field: sanaaField,
          deps: testDeps(api: api),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('الدقّة ±8 م'), findsOneWidget);
  });

  tallTest('photo notice says uploads are not available on the server', (
    t,
  ) async {
    final (api, _) = fakeApi((o) async => taxonomy(o));
    await t.pumpWidget(
      host(
        NewObservationScreen(
          field: sanaaField,
          deps: testDeps(api: api),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text(kPhotoUploadUnavailable), findsOneWidget);
  });

  Future<void> fillAndSave(WidgetTester t) async {
    await tapVisible(t, find.byKey(const ValueKey('category-pest')));
    await tapVisible(t, find.byKey(const ValueKey('severity-high')));
    await t.tap(find.text('حفظ المشاهدة'));
    await t.pumpAndSettle();
  }

  tallTest('offline + queued receipt ⇒ "محفوظ للإرسال"', (t) async {
    final outbox = FakeOutbox();
    final (api, adapter) = fakeApi((o) async => taxonomy(o));
    await t.pumpWidget(
      host(
        NewObservationScreen(
          field: sanaaField,
          deps: testDeps(
            api: api,
            outbox: outbox,
            net: connectivity(online: false),
          ),
        ),
      ),
    );
    await t.pumpAndSettle();
    await fillAndSave(t);
    expect(find.textContaining('محفوظ للإرسال'), findsOneWidget);
    expect(outbox.ops.single.kind, 'observation_create');
    expect(adapter.to('/api/v1/fields/f1/pins'), isEmpty);
  });

  tallTest(
    'offline + not-queued receipt ⇒ honest error, never "محفوظ للإرسال"',
    (t) async {
      final outbox = FakeOutbox(
        const OutboxReceipt.notQueued('offline_queue_unavailable'),
      );
      final (api, _) = fakeApi((o) async => taxonomy(o));
      await t.pumpWidget(
        host(
          NewObservationScreen(
            field: sanaaField,
            deps: testDeps(
              api: api,
              outbox: outbox,
              net: connectivity(online: false),
            ),
          ),
        ),
      );
      await t.pumpAndSettle();
      await fillAndSave(t);
      expect(find.textContaining('محفوظ للإرسال'), findsNothing);
      expect(find.textContaining('لم تُحفظ'), findsOneWidget);
      // الشاشة باقية والزرّ متاح لإعادة المحاولة.
      expect(find.text('حفظ المشاهدة'), findsOneWidget);
    },
  );

  tallTest('online success pops with true', (t) async {
    final (api, _) = fakeApi((o) async {
      if (o.path == '/api/v1/scouting/taxonomy') return taxonomy(o);
      return FakeReply(200, {...pinJson('x'), 'persisted': true});
    });
    bool? popped;
    await t.pumpWidget(
      host(
        Builder(
          builder: (context) => Scaffold(
            body: TextButton(
              onPressed: () async {
                popped = await Navigator.of(context).push<bool>(
                  MaterialPageRoute(
                    builder: (_) => NewObservationScreen(
                      field: sanaaField,
                      deps: testDeps(api: api),
                    ),
                  ),
                );
              },
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );
    await t.tap(find.text('open'));
    await t.pumpAndSettle();
    await fillAndSave(t);
    expect(popped, isTrue);
    expect(find.text('حُفظت المشاهدة على الخادم.'), findsOneWidget);
  });

  tallTest('viewer gets a read-only notice instead of the form', (t) async {
    final (api, _) = fakeApi((o) async => taxonomy(o));
    await t.pumpWidget(
      host(
        NewObservationScreen(
          field: sanaaField,
          deps: testDeps(api: api, role: 'viewer'),
        ),
      ),
    );
    await t.pumpAndSettle();
    expect(find.text('عرض فقط'), findsOneWidget);
    expect(find.text('حفظ المشاهدة'), findsNothing);
  });
}
