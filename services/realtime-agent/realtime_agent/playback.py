"""Native capture completion fencing before an interrupted source can be reused."""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from livekit import rtc


class PlaybackUncertain(Exception):
    """Native capture did not finish; the source must never be reused."""


class NativePlayback:
    def __init__(
        self,
        source: rtc.AudioSource,
        stop: asyncio.Event,
        invalidate: Callable[[], None],
        *,
        fence_timeout: float = 0.5,
    ):
        self._source = source
        self._stop = stop
        self._invalidate_track = invalidate
        self._fence_timeout = fence_timeout
        self._usable = True
        self._lock = asyncio.Lock()
        self._pending: set[asyncio.Task] = set()

    def _invalidate(self) -> None:
        self._usable = False
        try:
            self._invalidate_track()
        finally:
            self._stop.set()

    def _completed(self, task: asyncio.Task) -> None:
        self._pending.discard(task)
        if not task.cancelled():
            task.exception()  # Retrieve any late failure; never log its raw text.

    async def _capture(self, frame: rtc.AudioFrame) -> None:
        capture = asyncio.create_task(self._source.capture_frame(frame))
        self._pending.add(capture)
        capture.add_done_callback(self._completed)
        try:
            # Python cancellation must not detach the FFI completion listener.
            await asyncio.shield(capture)
        except asyncio.CancelledError:
            self._source.clear_queue()
            try:
                async with asyncio.timeout(self._fence_timeout):
                    await asyncio.shield(capture)
            except Exception as exc:
                self._invalidate()
                raise PlaybackUncertain("native_capture_completion_unconfirmed") from exc
            except asyncio.CancelledError as exc:
                self._invalidate()
                raise PlaybackUncertain("native_capture_fence_interrupted") from exc
            finally:
                # This clear follows the actual native acknowledgement, or follows
                # immediate track invalidation on failure; no uncertain source reuse.
                self._source.clear_queue()
            raise
        except Exception as exc:
            self._invalidate()
            raise PlaybackUncertain("native_capture_failed") from exc

    async def publish(self, pcm16: bytes) -> None:
        # A superseding turn cannot capture until the prior completion fence clears.
        async with self._lock:
            if not self._usable or self._stop.is_set():
                raise PlaybackUncertain("native_source_unusable")
            try:
                for offset in range(0, len(pcm16), 1920):
                    if not self._usable or self._stop.is_set():
                        raise PlaybackUncertain("native_source_unusable")
                    frame = pcm16[offset : offset + 1920]
                    await self._capture(rtc.AudioFrame(frame, 48000, 1, len(frame) // 2))
                await self._source.wait_for_playout()
            except asyncio.CancelledError:
                self._source.clear_queue()
                raise

    async def close(self) -> None:
        self._usable = False
        self._invalidate_track()
        self._source.clear_queue()
        # Any native operation whose deadline failed cannot be canceled via the
        # Python FFI API. The muted track and closing job prevent publication;
        # dispose Python listeners so no task escapes the job's scope.
        pending = list(self._pending)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
