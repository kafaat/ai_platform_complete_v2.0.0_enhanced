"""Local-only STT and actual codec conversion; never download model artifacts."""

from __future__ import annotations

import asyncio
import hashlib
import io
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verified_model(path: str, weights_sha256: str, bundle_sha256: str) -> Path:
    if not all(re.fullmatch(r"[a-f0-9]{64}", value) for value in (weights_sha256, bundle_sha256)):
        raise ValueError("explicit_model_checksums_required")
    root = Path(path)
    if root.is_symlink() or not root.is_dir() or not root.is_absolute():
        raise ValueError("local_model_directory_required")
    root = root.resolve(strict=True)
    files = sorted(root.rglob("*"))
    if any(p.is_symlink() for p in files):
        raise ValueError("model_symlink_forbidden")
    model = root / "model.bin"
    if not model.is_file() or _file_sha256(model) != weights_sha256:
        raise ValueError("model_weights_checksum_mismatch")
    bundle = hashlib.sha256()
    for entry in files:
        if entry.is_file():
            relative = entry.relative_to(root).as_posix()
            bundle.update(relative.encode("utf-8") + b"\n")
            bundle.update(_file_sha256(entry).encode("ascii") + b"\n")
    if bundle.hexdigest() != bundle_sha256:
        raise ValueError("model_bundle_checksum_mismatch")
    for required in ("config.json", "tokenizer.json"):
        if not (root / required).is_file():
            raise ValueError("incomplete_local_model_bundle")
    return root


class LocalWhisperSTT:
    def __init__(self, path: str, weights_sha256: str, bundle_sha256: str):
        root = verified_model(path, weights_sha256, bundle_sha256)
        from faster_whisper import WhisperModel

        # No identifier/hub lookup; missing files are a startup failure.
        self._model = WhisperModel(
            str(root),
            device="cpu",
            compute_type="int8",
            cpu_threads=2,
            num_workers=1,
            local_files_only=True,
        )
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sahool-local-stt")

    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str:
        if sample_rate != 16000 or len(pcm16) % 2 or len(pcm16) > 16000 * 2 * 15:
            raise ValueError("invalid_stt_audio")

        cancelled = threading.Event()

        def run() -> str:
            import numpy as np

            # Thread lock survives cancellation of the awaiting coroutine: a native
            # inference already in flight cannot overlap a newly superseding turn.
            with self._lock:
                if cancelled.is_set():
                    return ""
                samples = np.frombuffer(pcm16, dtype="<i2").astype(np.float32) / 32768.0
                segments, _ = self._model.transcribe(
                    samples,
                    language="ar",
                    beam_size=1,
                    vad_filter=False,
                    condition_on_previous_text=False,
                )
                text = " ".join(segment.text.strip() for segment in segments).strip()
                if len(text) > 4000:
                    raise ValueError("transcript_too_large")
                return text

        try:
            return await asyncio.get_running_loop().run_in_executor(self._executor, run)
        except asyncio.CancelledError:
            cancelled.set()
            raise


def decode_audio(data: bytes, *, max_seconds: int = 45) -> bytes:
    if not data or len(data) > 16 * 1024 * 1024:
        raise ValueError("invalid_tts_audio")
    import av

    try:
        with av.open(io.BytesIO(data), mode="r") as container:
            if container.format.name not in ("wav", "mp3"):
                raise ValueError("unsupported_tts_codec")
            if len(container.streams.audio) != 1 or container.streams.video:
                raise ValueError("audio_only_required")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=48000)
            output = bytearray()
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    output.extend(bytes(converted.planes[0])[: converted.samples * 2])
                    if len(output) > 48000 * 2 * max_seconds:
                        raise ValueError("tts_audio_too_long")
            for converted in resampler.resample(None):
                output.extend(bytes(converted.planes[0])[: converted.samples * 2])
            if not output or len(output) > 48000 * 2 * max_seconds:
                raise ValueError("invalid_tts_audio_duration")
            return bytes(output)
    except (av.FFmpegError, EOFError) as exc:
        raise ValueError("invalid_tts_audio") from exc
