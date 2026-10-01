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

ولا يسمح بالإرسال الخارجيّ إلّا ``full_external``: ``redacted_external`` يسمح بسياقٍ
منقّح، وTTS يُرسِل **النصَّ الخامَ كاملاً** فلا تنقيحَ ممكن.

وحدةٌ بالمكتبة القياسيّة وحدها (لا ``httpx`` في تبعيّات الخدمة)، ولا تستورد ``main``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.request
from collections.abc import Awaitable, Callable
from typing import Any

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

MeFetcher = Callable[[str, str], Awaitable[dict[str, Any]]]


def external_allowed(policy_mode: str) -> bool:
    """الإرسالُ الخارجيّ للنصّ الخام مسموحٌ لـ``full_external`` وحده."""
    return policy_mode == POLICY_FULL_EXTERNAL


def policy_mode_from_me(payload: Any, tenant_id: str) -> str:
    """يستخرج ``policy_mode`` من ردّ ``/api/v1/me`` بعد التحقّق من المستأجِر — وإلّا الأشدّ."""
    if not isinstance(payload, dict) or not tenant_id:
        return POLICY_LOCAL_ONLY
    envelope = payload.get("ai_policy_envelope")
    if not isinstance(envelope, dict):
        return POLICY_LOCAL_ONLY
    if str(payload.get("tenant_id") or "") != tenant_id:
        return POLICY_LOCAL_ONLY
    if str(envelope.get("tenant_id") or "") != tenant_id:
        return POLICY_LOCAL_ONLY
    mode = envelope.get("policy_mode")
    return mode if mode in POLICY_MODES else POLICY_LOCAL_ONLY


def _get_json(url: str, authorization: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": authorization})
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310 - عنوانٌ داخليّ من الإعداد
        if response.status != 200:
            raise RuntimeError(f"platform /me returned {response.status}")
        return json.loads(response.read().decode("utf-8"))


async def _fetch_me(url: str, authorization: str) -> dict[str, Any]:
    return await asyncio.to_thread(_get_json, url, authorization)


async def resolve_policy_mode(
    user: dict[str, Any],
    authorization: str | None,
    *,
    fetch: MeFetcher | None = None,
) -> str:
    """مستوى مشاركة البيانات الفعّال لصاحب الطلب — ``local_only`` عند أيّ شكّ."""
    tenant_id = str(user.get("tenant_id") or "")
    if not tenant_id or tenant_id == SERVICE_TENANT:
        return POLICY_LOCAL_ONLY
    if not authorization or not authorization.lower().startswith("bearer "):
        return POLICY_LOCAL_ONLY
    base = os.getenv("PLATFORM_API_URL", "").strip().rstrip("/")
    if not base:
        return POLICY_LOCAL_ONLY
    try:
        payload = await (fetch or _fetch_me)(f"{base}/api/v1/me", authorization)
    except Exception as exc:  # noqa: BLE001 - تعذّر القراءة ⇒ الأشدّ، لا قيمةٌ سابقة
        logger.warning("tenant policy unavailable (fail-closed local_only): %s", exc)
        return POLICY_LOCAL_ONLY
    return policy_mode_from_me(payload, tenant_id)
