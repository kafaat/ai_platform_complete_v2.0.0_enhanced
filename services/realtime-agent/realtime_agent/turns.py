"""Bounded speech turns, interruption and independently expiring authorization."""

from __future__ import annotations

import asyncio
import math
import sys
import time
from array import array
from collections.abc import Awaitable, Callable
from typing import Protocol

from .context import VoiceContext
from .speech import decode_audio


class SpeechRecognizer(Protocol):
    async def transcribe(self, pcm16: bytes, sample_rate: int = 16000) -> str: ...


class Providers(Protocol):
    async def answer(self, context: dict, text: str) -> str: ...
    async def synthesize(self, context: dict, text: str) -> bytes: ...


class VoiceActivity:
    """Energy VAD baseline; acoustic/noisy-field acceptance remains separate."""

    def __init__(
        self,
        *,
        threshold: int = 500,
        onset_ms: int = 40,
        silence_ms: int = 700,
        max_ms: int = 15000,
    ):
        self.threshold = threshold
        self.onset_ms = onset_ms
        self.silence_ms = silence_ms
        self.max_ms = max_ms
        self._speech_ms = 0.0
        self._quiet_ms = 0.0
        self._active = False
        self._buffer = bytearray()

    def feed(self, pcm16: bytes) -> tuple[bool, bytes | None]:
        if len(pcm16) % 2 or len(pcm16) > 16000 * 2:
            raise ValueError("invalid_input_frame")
        samples = array("h", pcm16)
        if sys.byteorder != "little":
            samples.byteswap()
        duration_ms = len(samples) / 16
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
        voiced = rms >= self.threshold
        started = False
        if not self._active:
            if voiced:
                self._speech_ms += duration_ms
                self._buffer.extend(pcm16)
                if self._speech_ms >= self.onset_ms:
                    self._active = True
                    self._quiet_ms = 0
                    started = True
            else:
                self._speech_ms = 0
                self._buffer.clear()
        else:
            self._buffer.extend(pcm16)
            self._quiet_ms = 0 if voiced else self._quiet_ms + duration_ms
        complete = None
        if self._active and (
            self._quiet_ms >= self.silence_ms or len(self._buffer) >= self.max_ms * 32
        ):
            complete = bytes(self._buffer[: self.max_ms * 32])
            self._buffer.clear()
            self._active = False
            self._speech_ms = 0
            self._quiet_ms = 0
        return started, complete


class TurnRunner:
    def __init__(
        self,
        lease_fetch: Callable[[], Awaitable[VoiceContext]],
        recognizer: SpeechRecognizer,
        providers: Providers,
        publish: Callable[[bytes], Awaitable[None]],
        clear: Callable[[], None],
    ):
        self._fetch = lease_fetch
        self._stt = recognizer
        self._providers = providers
        self._publish = publish
        self._clear = clear
        self._task: asyncio.Task | None = None
        self._tasks: set[asyncio.Task] = set()
        self._epoch = 0
        self._closed = False

    def interrupt(self) -> None:
        self._epoch += 1
        self._clear()
        if self._task is not None:
            self._task.cancel()

    def submit(self, pcm16: bytes) -> None:
        if self._closed:
            return
        self.interrupt()
        epoch = self._epoch
        self._task = asyncio.create_task(self._run(pcm16, epoch))
        self._tasks.add(self._task)
        self._task.add_done_callback(self._tasks.discard)

    async def _run(self, pcm16: bytes, epoch: int) -> None:
        try:
            async with asyncio.timeout(45):
                await self._fetch()
                question = await self._stt.transcribe(pcm16, 16000)
                if not question.strip():
                    return
                context = await self._fetch()
                answer = await self._providers.answer(context.provider_context(), question)
                if not answer.strip():
                    return
                context = await self._fetch()
                payload = await self._providers.synthesize(context.provider_context(), answer)
                pcm = await asyncio.to_thread(decode_audio, payload)
                await self._fetch()
                if not self._closed and epoch == self._epoch:
                    await self._publish(pcm)
        except asyncio.CancelledError:
            self._clear()
            raise
        except Exception:
            # No raw provider exceptions, transcript, bearer or audio is logged.
            if epoch == self._epoch:
                self._clear()

    async def close(self) -> None:
        self._closed = True
        self.interrupt()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def guard_lease(
    fetch: Callable[[], Awaitable[VoiceContext]], initial: VoiceContext, stop: asyncio.Event
) -> None:
    """Independent wall-clock expiry; a stalled provider cannot keep media alive."""

    async def watch() -> None:
        try:
            while not stop.is_set():
                await asyncio.sleep(2)
                await fetch()
        except asyncio.CancelledError:
            raise
        except Exception:
            stop.set()

    async def expire() -> None:
        await asyncio.sleep(max(0, initial.expires_at - time.time()))
        stop.set()

    tasks = [asyncio.create_task(watch()), asyncio.create_task(expire())]
    try:
        await stop.wait()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
