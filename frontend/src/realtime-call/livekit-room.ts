import { createLocalAudioTrack, Room, RoomEvent, Track, type LocalAudioTrack } from 'livekit-client';
import type { AudioTrack, CallMedia, CallRoom } from './controller';
/** Audio only. No data handlers or camera publication are installed. */
export const livekitMedia: CallMedia = {
  microphone: () => createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true, autoGainControl: true }),
  room(): CallRoom {
    const room = new Room({ adaptiveStream: true, dynacast: true });
    const elements = new Set<HTMLMediaElement>();
    room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind !== Track.Kind.Audio) return;
      const element = track.attach(); element.autoplay = true; elements.add(element); document.body.append(element);
      void element.play().catch(() => {});
    });
    room.on(RoomEvent.TrackPublished, (publication) => {
      if (publication.kind === Track.Kind.Audio) publication.setSubscribed(true);
    });
    room.on(RoomEvent.Connected, () => {
      for (const participant of room.remoteParticipants.values()) {
        for (const publication of participant.trackPublications.values()) {
          if (publication.kind === Track.Kind.Audio) publication.setSubscribed(true);
        }
      }
    });
    return {
      connect: (url, token) => room.connect(url, token, { autoSubscribe: false }),
      disconnect: async () => { for (const element of elements) { element.pause(); element.srcObject = null; element.remove(); } elements.clear(); await room.disconnect(); },
      publish: async (track: AudioTrack) => { await room.localParticipant.publishTrack(track as LocalAudioTrack, { source: Track.Source.Microphone }); },
      onDisconnected: (callback) => { room.on(RoomEvent.Disconnected, callback); },
      onReconnecting: (callback) => { room.on(RoomEvent.Reconnecting, callback); },
    };
  },
};
