"""فحصُ مقطعِ WAV بقراءة **كلِّ** إطاراته — لا الترويسة وحدها.

يرفض:
  • ترويسةً بلا عيّنات، أو عيّناتٍ أقلَّ ممّا تعلنه الترويسة (مقطعٌ مبتور).
  • صمتاً تامّاً (RMS دون العتبة).
  • مدّةً خارج المعقول لطول النصّ (بترٌ أو حشو) — حدودٌ واسعة عمداً، تكشف الشاذّ لا تقيس الجودة.
"""

from __future__ import annotations

import array
import io
import math
import sys
import wave
from dataclasses import dataclass


class AudioRejected(ValueError):
    pass


@dataclass(frozen=True)
class AudioCheck:
    seconds: float
    frames: int
    rate: int
    channels: int
    rms: float


MIN_RMS = 1e-3  # نسبةً إلى أقصى PCM16
SECONDS_PER_CHAR = (0.02, 0.5)  # نطاقٌ واسع: أبطأُ نطقٍ معقول وأسرعُه لكلّ حرف


def validate_wav(data: bytes, text: str | None = None) -> AudioCheck:
    try:
        with wave.open(io.BytesIO(data), "rb") as w:
            channels, width, rate, declared = (
                w.getnchannels(),
                w.getsampwidth(),
                w.getframerate(),
                w.getnframes(),
            )
            payload = w.readframes(declared)
    except (wave.Error, EOFError) as exc:
        raise AudioRejected(f"ليس WAV صالحاً: {exc}") from exc
    if channels <= 0 or rate <= 0 or width not in (1, 2, 4):
        raise AudioRejected(f"معاملاتٌ غير صالحة: channels={channels} rate={rate} width={width}")
    frame_bytes = width * channels
    actual = len(payload) // frame_bytes
    if actual == 0:
        raise AudioRejected("ترويسةٌ بلا عيّناتٍ صوتيّة")
    if actual != declared or len(payload) % frame_bytes:
        raise AudioRejected(f"مبتور: الترويسة {declared} إطاراً، الفعليّ {actual}")
    if width == 2:
        samples = array.array("h", payload[: actual * frame_bytes])
        if sys.byteorder == "big":
            samples.byteswap()
        peak = 32768.0
    elif width == 4:
        samples = array.array("i", payload[: actual * frame_bytes])
        if sys.byteorder == "big":
            samples.byteswap()
        peak = 2147483648.0
    else:
        # PCM8 بلا إشارة (WAV): يُمركَز حول 128 أعداداً صحيحة — ``bytes()`` لا تقبل السالب فكانت تنهار على كلّ عيّنة < 128
        samples = [b - 128 for b in payload[: actual * frame_bytes]]
        peak = 128.0
    rms = math.sqrt(sum(s * s for s in samples) / len(samples)) / peak
    if rms < MIN_RMS:
        raise AudioRejected(f"صمت: RMS={rms:.2e}")
    seconds = actual / rate
    if text:
        lo, hi = (len(text) * k for k in SECONDS_PER_CHAR)
        if not lo <= seconds <= hi:
            raise AudioRejected(
                f"مدّةٌ شاذّة {seconds:.2f}ث لنصٍّ من {len(text)} حرفاً (المعقول {lo:.1f}–{hi:.1f})"
            )
    return AudioCheck(
        seconds=seconds, frames=actual, rate=rate, channels=channels, rms=round(rms, 5)
    )
