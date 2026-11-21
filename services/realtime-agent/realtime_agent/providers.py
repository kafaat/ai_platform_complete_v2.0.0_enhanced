"""Authenticated local providers; only persisted owner-validated facts are spoken.

AI Agronomist retains its existing question/advice audit. `no_store` prevents TTS
cache retention; it is not a promise that the entire platform retains no data.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
from typing import Any
from urllib.parse import urlsplit

import httpx

_SERVICE_NAME = re.compile(r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
MAX_ANSWER_CHARS = 8000
# The default TTSRequest bound; operators must not configure TTS below this
# without also choosing a lower chunk limit in their voice adapter.
MAX_TTS_CHUNK_CHARS = 1000


class VoiceProviderError(RuntimeError):
    """Stable errors never echo transcripts, credentials or provider payloads."""


def speech_chunks(text: str, *, max_chars: int = MAX_TTS_CHUNK_CHARS) -> list[str]:
    """Lossless bounded text slices; never cut a number, word or identifier.

    Prefer a sentence/newline boundary in the latter half of each chunk, then a
    whitespace boundary. A token/whitespace run that cannot fit is rejected,
    never clipped. Every TTS chunk also carries the *whole* original answer for
    the service's critical-speech gate; splitting is not semantic validation.
    """
    if (
        not isinstance(text, str)
        or not text.strip()
        or len(text) > MAX_ANSWER_CHARS
        or type(max_chars) is not int
        or not 1 <= max_chars <= MAX_TTS_CHUNK_CHARS
    ):
        raise VoiceProviderError("voice_answer_invalid")
    remaining = text
    chunks: list[str] = []
    while len(remaining) > max_chars:
        boundaries = [
            match.end()
            for match in re.finditer(r"\s+", remaining[: max_chars + 1])
            if match.end() <= max_chars
            and (match.end() == len(remaining) or not remaining[match.end()].isspace())
            and remaining[: match.end()].strip()
        ]
        if not boundaries:
            raise VoiceProviderError("voice_answer_unsplittable")
        sentence_ends = [
            boundary
            for boundary in boundaries
            if boundary >= max_chars // 2
            and (
                remaining[:boundary].rstrip().endswith((".", "!", "؟", "?", ";", "؛"))
                or "\n" in remaining[boundary - 2 : boundary]
            )
        ]
        boundary = (sentence_ends or boundaries)[-1]
        chunks.append(remaining[:boundary])
        remaining = remaining[boundary:]
    if not remaining.strip():
        # A trailing whitespace-only fragment cannot be silently removed.
        if not chunks or len(chunks[-1]) + len(remaining) > max_chars:
            raise VoiceProviderError("voice_answer_unsplittable")
        chunks[-1] += remaining
    else:
        chunks.append(remaining)
    return chunks


def _plaintext_host_allowed(hostname: str | None) -> bool:
    # Mirrors realtime_agent.config.plaintext_host_allowed; this module is also loaded
    # standalone (outside the package), so it cannot import it. These origins receive users'
    # bearer JWTs: http is trusted only for loopback, single-label internal service names
    # and *.railway.internal.
    host = (hostname or "").lower().rstrip(".")
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    return (
        host == "localhost"
        or _SERVICE_NAME.fullmatch(host) is not None
        or (host.endswith(".railway.internal") and host != ".railway.internal")
    )


def _origin(raw: str) -> str:
    try:
        parsed = urlsplit(raw)
        valid = (
            parsed.scheme in {"http", "https"}
            and parsed.hostname
            and (parsed.scheme == "https" or _plaintext_host_allowed(parsed.hostname))
            and not parsed.username
            and not parsed.password
            and parsed.path in {"", "/"}
            and not parsed.query
            and not parsed.fragment
            and parsed.port != 0
        )
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise VoiceProviderError("voice_provider_origin_invalid")
    return raw.rstrip("/")


def _authorize(context: dict[str, Any]) -> str:
    envelope = context.get("policy_envelope")
    if (
        not isinstance(envelope, dict)
        or envelope.get("contract") != "sahool.ai_policy_envelope"
        or type(envelope.get("contract_version")) is not int
        or envelope["contract_version"] != 2
        or envelope.get("version") != "v52"
        or not context.get("tenant_id")
        or not context.get("field_id")
        or envelope.get("tenant_id") != context["tenant_id"]
        or envelope.get("policy_mode") != "local_only"
        or envelope.get("external_llm_allowed") is not False
        or envelope.get("external_tts_allowed") is not False
        or not isinstance(envelope.get("allowed_tools"), list)
    ):
        raise VoiceProviderError("voice_local_policy_required")
    bearer = context.get("bearer")
    if not isinstance(bearer, str) or not bearer or any(c.isspace() for c in bearer):
        raise VoiceProviderError("voice_bearer_invalid")
    return bearer


def published_answer(payload: Any, context: dict[str, Any]) -> str:
    """Accept only the authenticated owner receipt already enforced by canonical AI.

    model_output_digest identifies the owner's validated model output; that raw
    output is deliberately not exposed by AI. Both receipt copies must agree.
    """
    if not isinstance(payload, dict):
        raise VoiceProviderError("voice_publication_rejected")
    audit = payload.get("audit_event")
    validation = payload.get("advisory_validation")
    answer = payload.get("answer_ar")
    if (
        payload.get("mode") != "validated_field_facts"
        or payload.get("generation_status") != "validated_structured_facts"
        or payload.get("generation_surfaced") is not True
        or payload.get("tenant_id") != context["tenant_id"]
        or payload.get("field_id") != context["field_id"]
        or payload.get("tool_calls") != []
        or payload.get("pending_approvals") != []
        or type(payload.get("provider_tool_rounds")) is not int
        or payload["provider_tool_rounds"] != 0
        or payload.get("tool_calls_truncated") is not False
        or not isinstance(audit, dict)
        or audit.get("persisted") is not True
        or not isinstance(validation, dict)
        or audit.get("advisory_validation") != validation
        or validation.get("status") != "verified"
        or validation.get("schema_version") != "sahool.structured_advisory.v1"
        or validation.get("tenant_id") != context["tenant_id"]
        or validation.get("field_id") != context["field_id"]
        or validation.get("executes_action") is not False
        or validation.get("creates_decision") is not False
        or validation.get("candidate_previews") != []
        or not isinstance(validation.get("claims"), list)
        or not validation["claims"]
        or not re.fullmatch(r"[0-9a-f]{64}", str(validation.get("model_output_digest", "")))
        or not isinstance(answer, str)
        or not answer.strip()
        or len(answer) > MAX_ANSWER_CHARS
        or answer != validation.get("answer_ar")
    ):
        raise VoiceProviderError("voice_publication_rejected")
    return answer


class HttpVoiceProviders:
    """Fixed BFF paths, user bearer only, redirects disabled and bounded calls."""

    def __init__(
        self,
        ai_origin: str,
        tts_origin: str,
        *,
        tts_provider: str = "piper",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.ai_origin = _origin(ai_origin)
        self.tts_origin = _origin(tts_origin)
        if tts_provider not in {"piper", "xtts"}:
            raise VoiceProviderError("voice_local_tts_required")
        self.tts_provider = tts_provider
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=5.0, follow_redirects=False, trust_env=False
        )

    async def _post(self, url: str, context: dict[str, Any], body: dict) -> httpx.Response:
        bearer = _authorize(context)
        try:
            async with asyncio.timeout(5.0):
                response = await self._client.post(
                    url,
                    json=body,
                    headers={"Authorization": "Bearer " + bearer},
                    follow_redirects=False,
                    timeout=5.0,
                )
            if response.status_code != 200:
                raise VoiceProviderError("voice_provider_unavailable")
            return response
        except (httpx.HTTPError, TimeoutError, ValueError):
            raise VoiceProviderError("voice_provider_unavailable") from None

    async def answer(self, context: dict[str, Any], text: str) -> str:
        _authorize(context)
        if not isinstance(text, str) or not text.strip() or len(text) > 4000:
            raise VoiceProviderError("voice_transcript_invalid")
        response = await self._post(
            self.ai_origin + "/api/ai-agronomist/chat",
            context,
            {
                "question": text,
                "field_id": context["field_id"],
                "language": "ar",
                "voice_read_only": True,
            },
        )
        try:
            payload = response.json()
        except ValueError:
            raise VoiceProviderError("voice_publication_rejected") from None
        return published_answer(payload, context)

    async def synthesize(self, context: dict[str, Any], text: str) -> bytes:
        return await self._synthesize(context, text)

    async def synthesize_chunk(
        self, context: dict[str, Any], text: str, *, validation_text: str
    ) -> bytes:
        """Send complete gate context so a boundary cannot hide a dose/unit."""
        if (
            not isinstance(validation_text, str)
            or not validation_text.strip()
            or len(validation_text) > MAX_ANSWER_CHARS
            or not isinstance(text, str)
            or text not in validation_text
        ):
            raise VoiceProviderError("voice_answer_invalid")
        return await self._synthesize(context, text, validation_text=validation_text)

    async def _synthesize(
        self, context: dict[str, Any], text: str, *, validation_text: str | None = None
    ) -> bytes:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TTS_CHUNK_CHARS:
            raise VoiceProviderError("voice_answer_invalid")
        body: dict[str, Any] = {"text": text, "provider": self.tts_provider, "no_store": True}
        if validation_text is not None:
            body["validation_text"] = validation_text
        response = await self._post(
            self.tts_origin + "/tts/synthesize",
            context,
            body,
        )
        if (
            response.headers.get("cache-control", "").lower() != "no-store"
            or response.headers.get("x-cache") != "BYPASS"
            or response.headers.get("content-type", "").split(";", 1)[0]
            not in {"audio/wav", "audio/x-wav", "audio/mpeg"}
            or (
                validation_text is not None
                and response.headers.get("x-speech-validation") != "full-context-v1"
            )
            or not response.content
            or len(response.content) > 16 * 1024 * 1024
        ):
            raise VoiceProviderError("voice_audio_rejected")
        return response.content

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
