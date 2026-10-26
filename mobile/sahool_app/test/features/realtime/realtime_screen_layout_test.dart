// شاشة المكالمة: نصّ الموافقة الطويل كان في عمود غير قابل للتمرير فيفيض على
// الهواتف الصغيرة أو مع تكبير الخطّ، فتختفي الموافقة وزرّ الاتصال.
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/realtime/realtime_controller.dart';
import 'package:sahool_app/features/realtime/realtime_screen.dart';

class _Api implements RealtimeSessionApi {
  @override
  Future<RealtimeGrant> create(String fieldId) async => RealtimeGrant(
    id: 's',
    fieldId: fieldId,
    url: 'wss://media.example.invalid',
    token: 't',
    expiresAt: DateTime.now().add(const Duration(minutes: 5)),
  );
  @override
  Future<void> close(String sessionId) async {}
}

class _Capture implements RealtimeCapture {
  @override
  Future<void> stop() async {}
}

class _Transport implements RealtimeTransport {
  @override
  set onConnectionInterrupted(VoidCallback callback) {}
  @override
  Future<void> connect(RealtimeGrant grant) async {}
  @override
  Future<bool> requestMicrophone() async => true;
  @override
  Future<RealtimeCapture> createMicrophone() async => _Capture();
  @override
  Future<void> publish(RealtimeCapture capture) async {}
  @override
  Future<void> disconnect() async {}
}

void main() {
  testWidgets('هاتف صغير وخطّ مكبّر: لا فيض والموافقة قابلة للوصول', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(320, 480);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final controller = RealtimeController(
      fieldId: 'field-1',
      api: _Api(),
      transport: _Transport(),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(
            size: Size(320, 480),
            textScaler: TextScaler.linear(2),
          ),
          child: RealtimeScreen(fieldId: 'field-1', controller: controller),
        ),
      ),
    );
    await tester.pump();
    expect(tester.takeException(), isNull);
    final join = find.text('إنشاء الجلسة والاتصال صامتًا');
    await tester.scrollUntilVisible(join, 100);
    expect(join, findsOneWidget);
    expect(find.byType(CheckboxListTile), findsOneWidget);
  });
}
