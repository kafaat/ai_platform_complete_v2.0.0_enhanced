import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sahool_app/features/realtime/realtime_controller.dart';

class FakeApi implements RealtimeSessionApi {
  int creates = 0;
  final closed = <String>[];
  Completer<RealtimeGrant>? pending;
  RealtimeGrant grant = RealtimeGrant(id: 'session-1', fieldId: 'field-1',
    url: 'wss://media.example.invalid', token: 'ephemeral-test-token',
    expiresAt: DateTime.now().add(const Duration(minutes: 5)),
  );
  @override
  Future<RealtimeGrant> create(String fieldId) async {
    creates++;
    if (pending != null) return pending!.future;
    return grant;
  }
  @override
  Future<void> close(String id) async { closed.add(id); }
}

class FakeCapture implements RealtimeCapture {
  int stopped = 0;
  @override
  Future<void> stop() async { stopped++; }
}

class FakeTransport implements RealtimeTransport {
  VoidCallback? interrupted;
  int connections = 0;
  int microphones = 0;
  int published = 0;
  int disconnected = 0;
  bool permission = true;
  Completer<bool>? pendingPermission;
  Completer<RealtimeCapture>? pendingCapture;
  Completer<void>? pendingPublish;
  final capture = FakeCapture();
  @override
  set onConnectionInterrupted(VoidCallback callback) { interrupted = callback; }
  @override
  Future<void> connect(RealtimeGrant grant) async { connections++; }
  @override
  Future<bool> requestMicrophone() async {
    if (pendingPermission != null) return pendingPermission!.future;
    return permission;
  }
  @override
  Future<RealtimeCapture> createMicrophone() async {
    microphones++;
    if (pendingCapture != null) return pendingCapture!.future;
    return capture;
  }
  @override
  Future<void> publish(RealtimeCapture capture) async {
    published++;
    await pendingPublish?.future;
  }
  @override
  Future<void> disconnect() async { disconnected++; }
}

Future<void> settle() async { await Future<void>.delayed(Duration.zero); }

void main() {
  late FakeApi api;
  late FakeTransport transport;
  late RealtimeController controller;
  setUp(() {
    api = FakeApi();
    transport = FakeTransport();
    controller = RealtimeController(fieldId: 'field-1', api: api, transport: transport);
  });
  tearDown(() async { await controller.leave(); controller.dispose(); });

  test('consent is required and joining never captures audio', () async {
    await controller.join(consent: false);
    expect(api.creates, 0);
    await controller.join(consent: true);
    expect(transport.connections, 1);
    expect(transport.microphones, 0);
    expect(controller.phase, RealtimePhase.muted);
  });

  test('permission refusal does not create or publish a microphone', () async {
    await controller.join(consent: true);
    transport.permission = false;
    await controller.enableMicrophone();
    expect(transport.microphones, 0);
    expect(transport.published, 0);
  });

  test('explicit microphone action and mute stop physical capture', () async {
    await controller.join(consent: true);
    await controller.enableMicrophone();
    expect(controller.phase, RealtimePhase.speaking);
    await controller.mute();
    expect(transport.capture.stopped, 1);
    expect(controller.phase, RealtimePhase.muted);
  });

  test('leaving while native permission is pending never starts capture', () async {
    await controller.join(consent: true);
    transport.pendingPermission = Completer<bool>();
    final enable = controller.enableMicrophone();
    await settle();
    await controller.leave();
    transport.pendingPermission!.complete(true);
    await enable;
    expect(transport.microphones, 0);
    expect(transport.published, 0);
  });

  test('late-created microphone after blur is stopped before publication', () async {
    await controller.join(consent: true);
    transport.pendingCapture = Completer<RealtimeCapture>();
    final enable = controller.enableMicrophone();
    await settle();
    await controller.setForeground(false);
    transport.pendingCapture!.complete(transport.capture);
    await enable;
    expect(transport.capture.stopped, 1);
    expect(transport.published, 0);
    expect(api.closed, contains('session-1'));
  });

  test('capture retained during publish is stopped and late completion stays ended', () async {
    await controller.join(consent: true);
    transport.pendingPublish = Completer<void>();
    final enable = controller.enableMicrophone();
    await settle();
    expect(transport.published, 1);
    await controller.leave();
    expect(transport.capture.stopped, greaterThanOrEqualTo(1));
    transport.pendingPublish!.complete();
    await enable;
    expect(controller.phase, RealtimePhase.ended);
    expect(transport.capture.stopped, greaterThanOrEqualTo(2));
  });

  test('interrupted connection stops pending capture and requires another click', () async {
    await controller.join(consent: true);
    transport.pendingCapture = Completer<RealtimeCapture>();
    final enable = controller.enableMicrophone();
    await settle();
    transport.interrupted!();
    transport.pendingCapture!.complete(transport.capture);
    await enable;
    expect(transport.capture.stopped, 1);
    expect(transport.published, 0);
    expect(controller.phase, RealtimePhase.muted);
  });

  test('wrong-field grant is never sent to the media transport', () async {
    api.grant = RealtimeGrant(id: 'foreign-session', fieldId: 'field-2',
      url: api.grant.url, token: api.grant.token, expiresAt: api.grant.expiresAt,
    );
    await controller.join(consent: true);
    expect(controller.phase, RealtimePhase.failed);
    expect(transport.connections, 0);
    expect(api.closed, contains('foreign-session'));
  });

  test('late session response after navigation is closed without media connection', () async {
    api.pending = Completer<RealtimeGrant>();
    final joining = controller.join(consent: true);
    await settle();
    await controller.leave();
    api.pending!.complete(api.grant);
    await joining;
    expect(transport.connections, 0);
    expect(api.closed, contains('session-1'));
  });

  test('expired local lease cannot request another OS microphone permission', () async {
    var now = DateTime.now();
    controller.dispose();
    controller = RealtimeController(fieldId: 'field-1', api: api, transport: transport, now: () => now);
    await controller.join(consent: true);
    now = api.grant.expiresAt.add(const Duration(seconds: 1));
    expect(controller.canEnable, isFalse);
    await controller.enableMicrophone();
    expect(transport.microphones, 0);
    expect(transport.published, 0);
  });

  test('permission resolving after lease expiry never creates native capture', () async {
    var now = DateTime.now();
    controller.dispose();
    controller = RealtimeController(fieldId: 'field-1', api: api, transport: transport, now: () => now);
    await controller.join(consent: true);
    transport.pendingPermission = Completer<bool>();
    final enabling = controller.enableMicrophone();
    now = api.grant.expiresAt.add(const Duration(seconds: 1));
    transport.pendingPermission!.complete(true);
    await enabling;
    expect(transport.microphones, 0);
    expect(transport.published, 0);
  });

  testWidgets('lease expiry stops audio and closes the server session', (tester) async {
    api.grant = RealtimeGrant(id: 'short-session', fieldId: 'field-1',
      url: api.grant.url, token: api.grant.token,
      expiresAt: DateTime.now().add(const Duration(seconds: 2)),
    );
    await controller.join(consent: true);
    await controller.enableMicrophone();
    await tester.pump(const Duration(seconds: 3));
    expect(controller.phase, RealtimePhase.ended);
    expect(transport.capture.stopped, greaterThanOrEqualTo(1));
    expect(api.closed, contains('short-session'));
  });
}
