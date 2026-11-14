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


async def session_revoked(*checks: Coroutine[Any, Any, bool] | None) -> bool:
    """Whether an access token is revoked: awaits each check (jti, user token floor).

    A revocation store that fails after boot (connection refused, timeout, ACL) leaves the
    state unknown, so the request is refused with 503, in every environment. Before this,
    the redis error escaped ``main.get_current_user`` as an opaque 500 (live witness:
    ``tests_v9/test_auth_admin_authz_live_pg_redis.py``, ``[*-unreachable]``). Redis absent
    since boot is not a failure here: the checks then return ``False`` as before. A falsy
    entry (no jti in the token) is skipped.
    """
    revoked, failure = False, None
    for check in (c for c in checks if c):
        try:
            revoked = bool(await check) or revoked
        except Exception as exc:  # noqa: BLE001 — state unknown: refuse, never pass
            failure = exc
    if revoked:  # proof of revocation wins over an unknown (401, as in the platform)
        return True
    if failure is not None:
        logging.getLogger("auth").warning(
            "token revocation check failed: %s", type(failure).__name__
        )
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "تعذّر التحقّق من إبطال التوكن — أعد المحاولة"
        ) from failure
    return False
