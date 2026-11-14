"""دورةُ حياة توكن التجديد — استهلاكٌ ذرّيٌّ مفصولٌ عن ``main.py``.

**لماذا وحدةٌ شقيقةٌ لا سطرٌ في ``main.py``:** حارسُ التفكيك
(``scripts/ci/auth_main_decomposition_guard.py``) يحدّ أسطرَ ``main.py`` بـ1050،
ومنطقُ التشغيل يُفكَّك إلى وحداتٍ شقيقة (نمط ``mfa_crypto`` · ``otp``). ومحاولتي
الأولى أضافت المنطقَ والتوثيقَ إلى ``main.py`` فتجاوزَته — والحارسُ أمسكها.

**العطلُ الذي وُجِدت هذه لأجله (D02 من تدقيق 2026-09-22):** كان تدويرُ توكن
التجديد ``GET`` ثمّ ``DELETE`` منفصلَين. فطلبان متزامنان يقرآن القيمةَ القديمةَ
نفسَها ثمّ يمضيان معاً إلى استجابتين ناجحتين بتوكنين جديدين مختلفين **للجلسة
نفسِها**. والحذفُ يُرجِع ``1`` للأوّل و``0`` للثاني — **لكنّ أحداً لم يكن يقرأ
ذلك الرقم**، فالفائزُ لم يكن محسوماً.

**حدُّ صدقٍ مُعلَن:** هذا يُثبِت ذرّيّةَ **الاستهلاك** وحدَه. لا يُثبِت ذرّيّةَ
السلسلة كلّها (إنشاءُ التوكن الجديد وفهرستُه وإبطالُ العائلة)، ولا يكشف إعادةَ
الاستعمال بعد التدوير، ولا يعالج انقطاعَ الشبكة بعد نجاحٍ خادميّ. تلك بقيّةُ
شرط الإغلاق في D02 وهي **لم تُنفَّذ في هذه الشريحة**.
"""

from __future__ import annotations

import logging
from collections.abc import Coroutine
from typing import Any

from fastapi import HTTPException, status


async def consume_refresh_token(redis: Any, token: str) -> str | None:
    """يستهلك التوكن ذرّيّاً ويُعيد قيمته — أو ``None`` إن لم يكن هذا الطلبُ الفائز.

    ``GETDEL`` عمليّةٌ واحدة، فواحدٌ فقط يحصل على القيمة. وعند نسخةِ Redis قديمةٍ
    بلا ``GETDEL`` يُستعاض بـ``GET``+``DELETE`` في أنبوبٍ مُعامَلاتيّ ويُقرَأ
    **عدَدُ المحذوف**: من حذف ``0`` لم يكن الفائزَ وإن رأى قيمة.

    ``redis`` يُمرَّر صراحةً (لا يُقرأ من حالةٍ عامّة) كي تُختبَر الدالّةُ بمُضاعَفٍ
    بلا استيراد الخدمة كلّها.
    """
    return await consume_once(redis, f"sahool:refresh:{token}")


async def consume_reset_token(redis: Any, token: str) -> str | None:
    """S16(b): رمزُ إعادة تعيين كلمة المرور لمرّةٍ واحدة — الاستهلاكُ نفسُه.

    كان ``confirm_password_reset`` يقرأ ``GET`` ثمّ يحذف ``DELETE`` بعد تحديث كلمة
    المرور، فطلبان متزامنان بالرمز نفسِه ينجحان معاً (كلٌّ يضع كلمةَ مروره). الآن
    يُستهلَك الرمزُ **قبل** أيّ عمل، وواحدٌ فقط يحصل على معرّف المستخدم.
    """
    return await consume_once(redis, f"sahool:reset:{token}")


async def consume_once(redis: Any, key: str) -> str | None:
    """قراءةٌ وحذفٌ ذرّيّان لمفتاحٍ واحد (single-use) — ``None`` لغير الفائز."""
    if not redis:
        return None
    getdel = getattr(redis, "getdel", None)
    if getdel is not None:
        return await getdel(key)
    # المعاملةُ تجعل القراءةَ والحذفَ غيرَ قابلَين للتداخل، و**عدَدُ المحذوف** هو ما
    # يفصل الفائزَ عن الخاسر — لا وجودُ القيمة. خاسرٌ رأى قيمةً وحذف صفراً يُرَدّ.
    async with redis.pipeline(transaction=True) as pipe:
        pipe.get(key)
        pipe.delete(key)
        value, deleted = await pipe.execute()
    return value if deleted else None


# Safe methods: they read and change nothing, so the owner lets them through while the
# revocation store is down at runtime (decision of 14 November 2026, AUTH_DENYLIST_DESIGN.md).
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
READ_ALLOWED_REASON = "REVOCATION-STORE-UNAVAILABLE-READ-ALLOWED"


async def session_revoked(*checks: Coroutine[Any, Any, bool] | None, request: Any = None) -> bool:
    """Whether an access token is revoked: awaits each check (jti, user token floor).

    A revocation store that fails after boot (connection refused, timeout, ACL) leaves the
    state unknown. Before #1427 the redis error escaped ``main.get_current_user`` as an opaque
    500 (live witness: ``tests_v9/test_auth_admin_authz_live_pg_redis.py``, ``[*-unreachable]``);
    #1427 refused every request with 503. Owner decision (14 November 2026): a safe method
    (``SAFE_METHODS`` on ``request.method``) proceeds with a WARNING carrying
    ``READ_ALLOWED_REASON``, and any other method, or a call without a request (direct callers
    such as ``mfa_enrollment.user_for``), is still refused with 503, in every environment.
    Proof of revocation from any check wins over an unknown: 401 for every method.

    Redis absent since boot is not a failure here: the checks then return ``False`` as before
    (production refuses to start without it, ``main.lifespan``). A falsy entry (no jti in the
    token) is skipped.
    """
    revoked, failure = False, None
    for check in (c for c in checks if c):
        try:
            revoked = bool(await check) or revoked
        except Exception as exc:  # noqa: BLE001 — state unknown: decided below, never 500
            failure = exc
    if revoked:  # proof of revocation wins over an unknown (401, as in the platform)
        return True
    if failure is None:
        return False
    method = str(getattr(request, "method", "") or "").upper()
    log = logging.getLogger("auth")
    if method in SAFE_METHODS:
        log.warning(
            "%s: token revocation check failed (%s); %s allowed",
            READ_ALLOWED_REASON,
            type(failure).__name__,
            method,
        )
        # Routes whose GET authorizes something else (nginx auth_request gates) read this
        # mark through ``refuse_unknown_revocation`` and fail closed after all.
        state = getattr(request, "state", None)
        if state is not None:
            state.revocation_unknown = True
        return False
    log.warning("token revocation check failed: %s", type(failure).__name__)
    raise _unknown_revocation() from failure


def _unknown_revocation() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE, "تعذّر التحقّق من إبطال التوكن — أعد المحاولة"
    )


# Set by nginx on every ``auth_request`` subrequest to the client's own method
# (``proxy_set_header X-Original-Method $request_method``, which also replaces a client value).
# A subrequest is always GET, so without it the method of the gated request is unknown.
ORIGINAL_METHOD_HEADER = "X-Original-Method"


def refuse_unknown_revocation(request: Any, gated_method: str | None = None) -> None:
    """503 on a read let through with unknown revocation state, unless the gated method is safe.

    For a GET that authorizes another request rather than reading: ``GET /v1/auth/edge-sign``
    signs an attestation for ``POST .../accept`` (``gated_method`` None: always refused) and
    ``GET /v1/auth/verify`` gates whatever the client sent to nginx (``gated_method`` from
    ``ORIGINAL_METHOD_HEADER``; missing => unknown => refused). Review of #1449.
    """
    if not getattr(getattr(request, "state", None), "revocation_unknown", False):
        return
    if str(gated_method or "").strip().upper() in SAFE_METHODS:
        return
    logging.getLogger("auth").warning(
        "token revocation unknown on a gate route; gated method %r refused", gated_method
    )
    raise _unknown_revocation()
