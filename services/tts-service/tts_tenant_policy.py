"""سياسةُ مشاركة بيانات المستأجِر لخدمة TTS — مصدرُها المنصّة، والفشلُ مغلق.

TTS-LOCAL-ONLY-FALLS-BACK-TO-EXTERNAL-PROVIDER-01 · TTS-STREAM-BYPASSES-PROVIDER-SELECTION-01:
كانت الخدمة لا تقرأ سياسةَ المستأجِر أصلاً، فنصُّ النصيحة يخرج إلى مزوّدٍ خارجيّ (edge)
لأيّ مستأجِر. **المنصّة هي سلطةُ السياسة** (``core/ai_policy_envelope.py``: تقرأ
``tenant_ai_policies`` بنطاق RLS وتسقط إلى ``local_only`` حين لا صفّ)، فتُقرأ هنا من
``GET /api/v1/me`` (حقل ``ai_policy_envelope``) بتوكن المستخدم نفسه — لا مسارَ جديد،
فميزانيّة مسارات المنصّة 629/629 بلا هامش.

قواعدُ الفشل المغلق (كلُّها تُرجِع ``local_only``):
  • هويّةٌ خدميّة (``__service__``) أو بلا مستأجِر: لا مستأجِرَ موثَّقاً تُقرأ سياسته.
  • لا توكن Bearer، أو ``PLATFORM_API_URL`` غير مضبوط.
  • تعذّر القراءة (شبكة/مهلة/رمز غير 200/JSON تالف) — **بلا رجوعٍ إلى قيمةٍ سابقة**:
    لا ذاكرةَ للسياسة هنا أصلاً، فلا نسخةَ قديمة تسمح بالإرسال حين يتعذّر التحديث.
  • مستأجِرُ الغلاف أو الهويّة يخالف مستأجِرَ التوكن، أو ``policy_mode`` غير قانونيّ.
  • غلافٌ بلا ``contract_version`` (منصّةٌ لا تُصدر العقد v2) — لا يُقرأ ``external_llm_allowed``.

ولا يسمح بالإرسال الخارجيّ إلّا ``full_external``: ``redacted_external`` يسمح بسياقٍ
منقّح، وTTS يُرسِل **النصَّ الخامَ كاملاً** فلا تنقيحَ ممكن.

**عقدُ الغلاف v2 (``contract_version`` ≥ 2) هو العقدُ الوحيد — إذنُ TTS منفصلٌ عن إذن LLM:**
الإرسالُ الخارجيّ يشترط ``external_tts_allowed`` صريحاً، والمزوّدُ الخارجيّ يجب أن يكون في
``external_tts_providers``. غيابُ الحقل، أو رقمُ عقدٍ تالف، أو قائمةُ مزوّدين فارغة ⇒
``local_only``. ``external_llm_allowed`` لا يُقرأ هنا أبداً: إذنُ LLM لا يفتح TTS. (أُزيل مسارُ
التوافق مع الغلاف القديم بقرار المالك 2026-10-12 — المنصّةُ والخدمةُ تعملان من نسخةٍ واحدة.)

وحدةٌ بالمكتبة القياسيّة وحدها (لا ``httpx`` في تبعيّات الخدمة)، ولا تستورد ``main``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger("tts.tenant_policy")

POLICY_LOCAL_ONLY = "local_only"
POLICY_REDACTED_EXTERNAL = "redacted_external"
POLICY_FULL_EXTERNAL = "full_external"
POLICY_MODES = (POLICY_LOCAL_ONLY, POLICY_REDACTED_EXTERNAL, POLICY_FULL_EXTERNAL)

#: هويّةُ مسار توكن الخدمة في ``main.get_current_user`` — لا مستأجِرَ موثَّقاً.
SERVICE_TENANT = "__service__"

#: رمزُ الخطأ المُسمّى حين لا يتوفّر مزوّدٌ تسمح به السياسة (قرار المالك).
POLICY_BLOCKED_ERROR = "local_provider_unavailable_for_policy"

_TIMEOUT_SECONDS = 3.0
_MAX_RESPONSE_BYTES = 64 * 1024

#: أدنى رقمِ عقدٍ يحمل إذنَ TTS المنفصل (``core/ai_policy_envelope.ENVELOPE_CONTRACT_VERSION``).
TTS_CONTRACT_VERSION = 2


@dataclass(frozen=True)
class TTSPolicy:
    """قرارُ السياسة لطلبٍ واحد: الوضع، والمزوّدون الخارجيّون المسموحون.

    ``external_providers``: المزوّدون الخارجيّون المُسمَّون في الغلاف؛ أيُّ مزوّدٍ خارجيٍّ
    خارجها محجوب، والمجموعةُ الفارغة تحجبها كلَّها. الوضعُ غيرُ ``full_external`` لا يأذن.
    """

    mode: str
    external_providers: frozenset[str] = frozenset()

    @property
    def external_allowed(self) -> bool:
        return external_allowed(self.mode)


LOCAL_ONLY_POLICY = TTSPolicy(POLICY_LOCAL_ONLY, frozenset())

MeFetcher = Callable[[str, str], Awaitable[dict[str, Any]]]


def external_allowed(policy_mode: str) -> bool:
    """الإرسالُ الخارجيّ للنصّ الخام مسموحٌ لـ``full_external`` وحده."""
    return policy_mode == POLICY_FULL_EXTERNAL


def policy_from_me(payload: Any, tenant_id: str) -> TTSPolicy:
    """يستخرج قرارَ السياسة من ردّ ``/api/v1/me`` بعد التحقّق من المستأجِر — وإلّا الأشدّ."""
    if not isinstance(payload, dict) or not tenant_id:
        return LOCAL_ONLY_POLICY
    envelope = payload.get("ai_policy_envelope")
    if not isinstance(envelope, dict):
        return LOCAL_ONLY_POLICY
    if str(payload.get("tenant_id") or "") != tenant_id:
        return LOCAL_ONLY_POLICY
    if str(envelope.get("tenant_id") or "") != tenant_id:
        return LOCAL_ONLY_POLICY
    mode = envelope.get("policy_mode")
    if mode not in POLICY_MODES:
        return LOCAL_ONLY_POLICY
    # غلافٌ بلا رقم عقد ⇒ الأشدّ: لا رجوعَ إلى ``external_llm_allowed`` (قرار المالك).
    return _policy_from_v2(envelope, mode)


def _policy_from_v2(envelope: dict[str, Any], mode: str) -> TTSPolicy:
    """غلافُ v2: إذنُ TTS الصريح وحده يفتح الإرسال الخارجيّ، ولا يُقرأ إذنُ LLM."""
    version = envelope.get("contract_version")  # غائبٌ ⇒ None ⇒ الأشدّ
    if isinstance(version, bool) or not isinstance(version, int) or version < TTS_CONTRACT_VERSION:
        return LOCAL_ONLY_POLICY
    if mode != POLICY_FULL_EXTERNAL or envelope.get("external_tts_allowed") is not True:
        return LOCAL_ONLY_POLICY
    providers = envelope.get("external_tts_providers")
    if not isinstance(providers, list) or not all(isinstance(p, str) for p in providers):
        return LOCAL_ONLY_POLICY
    named = frozenset(providers)
    if not named:
        return LOCAL_ONLY_POLICY
    return TTSPolicy(POLICY_FULL_EXTERNAL, named)


def policy_mode_from_me(payload: Any, tenant_id: str) -> str:
    """الوضعُ وحده (للمستدعين القائمين) — ``policy_from_me(...).mode``."""
    return policy_from_me(payload, tenant_id).mode


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a user's bearer token to a redirected policy endpoint.
        raise RuntimeError("platform policy redirects are forbidden")


def _policy_url(base: str) -> str:
    parts = urlsplit(base)
    if (
        parts.scheme not in {"http", "https"}
        or not parts.hostname
        or parts.username is not None
        or parts.password is not None
        or parts.path not in {"", "/"}
        or parts.query
        or parts.fragment
        or any(char.isspace() for char in base)
        or "\\" in base
    ):
        raise ValueError("PLATFORM_API_URL must be an HTTP(S) origin")
    # Force validation of malformed/out-of-range ports before sending credentials.
    _ = parts.port
    return f"{parts.scheme}://{parts.netloc}/api/v1/me"


def _get_json(url: str, authorization: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": authorization})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    with opener.open(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - validated operator-configured origin
        if response.status != 200:
            raise RuntimeError(f"platform /me returned {response.status}")
        raw = response.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise RuntimeError("platform policy response exceeds size limit")
        return json.loads(raw.decode("utf-8"))


async def _fetch_me(url: str, authorization: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get_json, url, authorization)


async def resolve_policy(
    user: dict[str, Any],
    authorization: str | None,
    *,
    fetch: MeFetcher | None = None,
) -> TTSPolicy:
    """قرارُ السياسة الفعّال لصاحب الطلب — ``local_only`` عند أيّ شكّ."""
    tenant_id = str(user.get("tenant_id") or "")
    if not tenant_id or tenant_id == SERVICE_TENANT:
        return LOCAL_ONLY_POLICY
    if not authorization or not authorization.lower().startswith("bearer "):
        return LOCAL_ONLY_POLICY
    base = os.getenv("PLATFORM_API_URL", "").strip()
    if not base:
        return LOCAL_ONLY_POLICY
    try:
        payload = await (fetch or _fetch_me)(_policy_url(base), authorization)
    except Exception as exc:  # noqa: BLE001 - تعذّر القراءة ⇒ الأشدّ، لا قيمةٌ سابقة
        logger.warning("tenant policy unavailable (fail-closed local_only): %s", exc)
        return LOCAL_ONLY_POLICY
    return policy_from_me(payload, tenant_id)


async def resolve_policy_mode(
    user: dict[str, Any],
    authorization: str | None,
    *,
    fetch: MeFetcher | None = None,
) -> str:
    """مستوى مشاركة البيانات الفعّال لصاحب الطلب — ``local_only`` عند أيّ شكّ."""
    return (await resolve_policy(user, authorization, fetch=fetch)).mode
