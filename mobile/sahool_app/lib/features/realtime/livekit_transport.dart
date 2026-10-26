import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:livekit_client/livekit_client.dart';
import 'package:permission_handler/permission_handler.dart';

import 'realtime_controller.dart';

class LiveKitTransport implements RealtimeTransport {
  Room? _room;
  EventsListener<RoomEvent>? _events;
  VoidCallback? _interrupted;

  @override
  set onConnectionInterrupted(VoidCallback callback) => _interrupted = callback;

  @override
  Future<void> connect(RealtimeGrant grant) async {
    final room = Room(roomOptions: const RoomOptions(adaptiveStream: true));
    _room = room;
    _events = room.createListener()
      ..on<RoomReconnectingEvent>((_) {
        _interrupted?.call();
      })
      ..on<RoomReconnectedEvent>((_) {
        _interrupted?.call();
      })
      ..on<RoomDisconnectedEvent>((_) {
        _interrupted?.call();
      })
      ..on<TrackPublishedEvent>((event) {
        if (event.publication.kind == TrackType.AUDIO) {
          unawaited(event.publication.subscribe());
        }
      });
    await room.connect(
      grant.url,
      grant.token,
      connectOptions: const ConnectOptions(autoSubscribe: false),
    );
    for (final participant in room.remoteParticipants.values) {
      for (final publication in participant.audioTrackPublications) {
        await publication.subscribe();
      }
    }
    // No capture, camera, data or automatic microphone action at connection.
  }

  @override
  Future<bool> requestMicrophone() async =>
      (await Permission.microphone.request()).isGranted;

  @override
  Future<RealtimeCapture> createMicrophone() async {
    final room = _room;
    if (room == null || room.connectionState != ConnectionState.connected) {
      throw StateError('room_not_connected');
    }
    final track = await LocalAudioTrack.create();
    return _LiveCapture(track, room);
  }

  @override
  Future<void> publish(RealtimeCapture capture) async {
    if (capture is! _LiveCapture || capture.stopped) {
      throw StateError('capture_no_longer_authorized');
    }
    final participant = capture.room.localParticipant;
    if (participant == null || !identical(capture.room, _room)) {
      await capture.stop();
      throw StateError('participant_unavailable');
    }
    final publication = await participant.publishAudioTrack(capture.track);
    capture.publicationId = publication.sid;
    if (capture.stopped) {
      await participant.removePublishedTrack(publication.sid);
    }
  }

  @override
  Future<void> disconnect() async {
    final room = _room;
    _room = null;
    await _events?.dispose();
    _events = null;
    if (room != null) {
      try {
        await room.disconnect();
      } finally {
        await room.dispose();
      }
    }
  }
}

class _LiveCapture implements RealtimeCapture {
  _LiveCapture(this.track, this.room);
  final LocalAudioTrack track;
  final Room room;
  bool stopped = false;
  String? publicationId;

  @override
  Future<void> stop() async {
    stopped = true;
    // Physical capture stops before signaling or network cleanup can await.
    track.mediaStreamTrack.enabled = false;
    final id = publicationId;
    publicationId = null;
    // removePublishedTrack removes the publication map entry synchronously,
    // before it awaits track.stop. Reconnect cannot republish that entry.
    final unpublish = id == null
        ? null
        : room.localParticipant?.removePublishedTrack(id);
    try {
      await track.stop();
    } finally {
      await unpublish;
    }
  }
}
