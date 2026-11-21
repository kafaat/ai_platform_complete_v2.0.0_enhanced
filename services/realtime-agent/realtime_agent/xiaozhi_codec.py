"""Bounded Xiaozhi WebSocket framing and raw Opus conversion.

Wire contract: 78/xiaozhi-esp32@92d400d6374bbe750e0a0188fa969fc4042820c2
docs/websocket.md and main/protocols/websocket_protocol.cc.
PyAV APIs: https://pyav.org/docs/stable/api/audio.html
"""

from __future__ import annotations

import struct
from fractions import Fraction

MAX_PACKET = 4096


def unpack_audio(data: bytes, version: int) -> bytes:
    if not isinstance(data, bytes) or not data or len(data) > MAX_PACKET + 16:
        raise ValueError("invalid_audio_packet")
    if version == 1:
        payload = data
    elif version == 2 and len(data) >= 16:
        wire_version, kind, reserved, _timestamp, size = struct.unpack("!HHIII", data[:16])
        if (wire_version, kind, reserved) != (2, 0, 0) or size != len(data) - 16:
            raise ValueError("invalid_audio_header")
        payload = data[16:]
    elif version == 3 and len(data) >= 4:
        kind, reserved, size = struct.unpack("!BBH", data[:4])
        if (kind, reserved) != (0, 0) or size != len(data) - 4:
            raise ValueError("invalid_audio_header")
        payload = data[4:]
    else:
        raise ValueError("unsupported_audio_version")
    if not 1 <= len(payload) <= MAX_PACKET:
        raise ValueError("invalid_audio_packet")
    return payload


def pack_audio(payload: bytes, version: int, timestamp: int = 0) -> bytes:
    if not 1 <= len(payload) <= MAX_PACKET:
        raise ValueError("invalid_audio_packet")
    if version == 1:
        return payload
    if version == 2:
        return struct.pack("!HHIII", 2, 0, 0, timestamp & 0xFFFFFFFF, len(payload)) + payload
    if version == 3:
        return struct.pack("!BBH", 0, 0, len(payload)) + payload
    raise ValueError("unsupported_audio_version")


class OpusCodec:
    """One decoder per connection; s16 mono 16k input and 48k output.

    Only 20/40/60ms input frames are negotiated. The decoded sample bound is
    independently checked; a compressed packet cannot request arbitrary PCM.
    """

    def __init__(self, frame_ms: int = 60):
        if type(frame_ms) is not int or frame_ms not in {20, 40, 60}:
            raise ValueError("unsupported_frame_duration")
        import av

        self.frame_ms = frame_ms
        self._decoder = av.CodecContext.create("opus", "r")
        self._decoder.sample_rate = 48000
        self._decoder.layout = "mono"
        # RFC7845 identification header: mono, no container preskip. WebSocket
        # carries raw packets, not Ogg; the gateway does not accept file uploads.
        self._decoder.extradata = b"OpusHead" + bytes([1, 1]) + struct.pack("<HIhB", 0, 16000, 0, 0)
        self._resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

    def decode(self, payload: bytes) -> bytes:
        import av

        if not 1 <= len(payload) <= MAX_PACKET:
            raise ValueError("invalid_audio_packet")
        # RFC6716 section3.1: TOC stereo flag is mask0x04. FFmpeg may
        # downmix stereo to the configured layout, hiding a wire mismatch.
        # https://www.rfc-editor.org/rfc/rfc6716.html#section-3.1
        if payload[0] & 0x04:
            raise ValueError("mono_audio_required")
        try:
            frames = self._decoder.decode(av.Packet(payload))
            total_samples = sum(frame.samples for frame in frames)
            if not frames or total_samples != self.frame_ms * 48:
                raise ValueError("audio_duration_mismatch")
            output = bytearray()
            for frame in frames:
                if len(frame.layout.channels) != 1:
                    raise ValueError("mono_audio_required")
                for converted in self._resampler.resample(frame):
                    output.extend(bytes(converted.planes[0])[: converted.samples * 2])
            if len(output) > self.frame_ms * 32:
                raise ValueError("decoded_audio_too_large")
            return bytes(output)
        except av.FFmpegError:
            raise ValueError("invalid_opus_audio") from None

    @staticmethod
    def encode(pcm48: bytes) -> list[bytes]:
        import av

        if not pcm48 or len(pcm48) % 2 or len(pcm48) > 48000 * 2 * 45:
            raise ValueError("invalid_output_audio")
        encoder = av.CodecContext.create("libopus", "w")
        encoder.sample_rate = 48000
        encoder.layout = "mono"
        encoder.format = "s16"
        encoder.bit_rate = 24000
        encoder.time_base = Fraction(1, 48000)
        encoder.options = {"application": "voip", "frame_duration": "60"}
        encoder.open()
        packets = []
        frame_bytes = 2880 * 2
        for offset in range(0, len(pcm48), frame_bytes):
            chunk = pcm48[offset : offset + frame_bytes]
            frame = av.AudioFrame(format="s16", layout="mono", samples=2880)
            frame.sample_rate = 48000
            frame.time_base = Fraction(1, 48000)
            frame.pts = offset // 2
            frame.planes[0].update(chunk.ljust(frame_bytes, b"\0"))
            packets.extend(bytes(packet) for packet in encoder.encode(frame))
        packets.extend(bytes(packet) for packet in encoder.encode(None))
        if not packets or len(packets) > 752 or any(not 1 <= len(p) <= MAX_PACKET for p in packets):
            raise ValueError("invalid_encoded_audio")
        return packets
