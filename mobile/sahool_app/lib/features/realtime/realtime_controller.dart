import 'dart:async';

import 'package:flutter/foundation.dart';

/// Credentials live only for this call and are never persisted or logged.
class RealtimeGrant {
  const RealtimeGrant({
    required this.id,
    required this.fieldId,
    required this.url,
    required this.token,
    required this.expiresAt,
  });

  final String id;
  final String fieldId;
  final String url;
  final String token;
  final DateTime expiresAt;
}

abstract interface class RealtimeSessionApi {
  Future<RealtimeGrant> create(String fieldId);
  Future<void> close(String sessionId);
}

abstract interface class RealtimeCapture {
  Future<void> stop();
}

abstract interface class RealtimeTransport {
  set onConnectionInterrupted(VoidCallback callback);
  Future<void> connect(RealtimeGrant grant);
  Future<bool> requestMicrophone();
  Future<RealtimeCapture> createMicrophone();
  Future<void> publish(RealtimeCapture capture);
  Future<void> disconnect();
}

enum RealtimePhase { idle, joining, muted, speaking, ended, failed }

/// Capture is authorized for one foreground generation and one explicit click.
/// Reconnection, navigation and lease expiry invalidate pending capture work.
class RealtimeController extends ChangeNotifier {
  RealtimeController({
    required this.fieldId,
    required RealtimeSessionApi api,
    required RealtimeTransport transport,
    DateTime Function()? now,
  })  : _api = api,
        _transport = transport,
        _now = now ?? DateTime.now {
    _transport.onConnectionInterrupted = () {
      unawaited(phase == RealtimePhase.joining ? leave() : mute());
    };
  }

  final String fieldId;
  final RealtimeSessionApi _api;
  final RealtimeTransport _transport;
  final DateTime Function() _now;
  RealtimePhase phase = RealtimePhase.idle;
  String? message;
  RealtimeGrant? _grant;
  RealtimeCapture? _capture;
  Timer? _expiry;
  int _generation = 0;
  bool _foreground = true;
  bool _disposed = false;
  bool _enabling = false;
  bool _joining = false;

  bool get canEnable => phase == RealtimePhase.muted && !_enabling && _foreground &&
      _grant != null && _now().isBefore(_grant!.expiresAt);
  void _notify() { if (!_disposed) notifyListeners(); }
  Future<void> _disconnectQuietly() async {
    try { await _transport.disconnect(); } catch (_) { /* Capture is stopped first. */ }
  }
  bool _current(int generation) => !_disposed && _foreground &&
      generation == _generation && _grant != null &&
      _now().isBefore(_grant!.expiresAt);

  Future<void> join({required bool consent}) async {
    if (!consent || _joining || phase != RealtimePhase.idle) return;
    _joining = true;
    final generation = ++_generation;
    phase = RealtimePhase.joining;
    _notify();
    RealtimeGrant? created;
    try {
      created = await _api.create(fieldId);
      if (_disposed || !_foreground || generation != _generation) {
        await _api.close(created.id);
        return;
      }
      if (created.fieldId != fieldId || !_now().isBefore(created.expiresAt)) {
        throw StateError('invalid_session_binding');
      }
      _grant = created;
      _expiry = Timer(created.expiresAt.difference(_now()), () {
        unawaited(leave());
      });
      await _transport.connect(created);
      if (!_current(generation)) {
        await _disconnectQuietly();
        await _api.close(created.id);
        return;
      }
      phase = RealtimePhase.muted;
    } catch (_) {
      _expiry?.cancel();
      _grant = null;
      await _disconnectQuietly();
      if (created != null) {
        try { await _api.close(created.id); } catch (_) { /* Server lease is bounded. */ }
      }
      if (!_disposed && generation == _generation) {
        phase = RealtimePhase.failed;
        message = 'تعذّر بدء الجلسة. حاول لاحقًا.';
      }
    } finally {
      _joining = false;
      _notify();
    }
  }

  Future<void> enableMicrophone() async {
    if (!canEnable || _grant == null) return;
    final generation = _generation;
    _enabling = true;
    RealtimeCapture? capture;
    try {
      if (!await _transport.requestMicrophone() || !_current(generation)) return;
      capture = await _transport.createMicrophone();
      if (!_current(generation)) {
        await capture.stop();
        return;
      }
      // Retain before publish awaits: blur/leave can stop an in-flight track.
      _capture = capture;
      await _transport.publish(capture);
      if (!_current(generation)) {
        await capture.stop();
        return;
      }
      phase = RealtimePhase.speaking;
      message = null;
    } catch (_) {
      if (capture != null) await capture.stop();
      if (identical(_capture, capture)) _capture = null;
      if (_current(generation)) message = 'تعذّر تشغيل الميكروفون.';
    } finally {
      _enabling = false;
      _notify();
    }
  }

  Future<void> mute() async {
    ++_generation;
    final capture = _capture;
    _capture = null;
    if (phase == RealtimePhase.speaking) phase = RealtimePhase.muted;
    _notify();
    if (capture != null) await capture.stop();
  }

  Future<void> setForeground(bool foreground) async {
    _foreground = foreground;
    if (!foreground) {
      // A suspended native screen ends the lease; resume requires a new session.
      await leave();
    }
  }

  Future<void> leave() async {
    ++_generation;
    _expiry?.cancel();
    final grant = _grant;
    _grant = null;
    final capture = _capture;
    _capture = null;
    phase = RealtimePhase.ended;
    _notify();
    try {
      if (capture != null) await capture.stop();
    } finally {
      try { await _transport.disconnect(); } catch (_) {
        // Capture was already stopped; cleanup still reaches the server.
      } finally {
        if (grant != null) {
          try { await _api.close(grant.id); } catch (_) { /* Server reconciles expiry. */ }
        }
      }
    }
  }

  @override
  void dispose() {
    _disposed = true;
    unawaited(leave());
    super.dispose();
  }
}
