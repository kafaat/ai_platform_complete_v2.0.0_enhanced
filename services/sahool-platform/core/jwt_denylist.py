"""core/jwt_denylist.py — فحص إبطال توكنات JWT (jti denylist) — نواة قابلة للنقل.

السياق (مراجعة الجولة ٢، H1): خدمة auth تُبطِل التوكن على تسجيل الخروج بمفتاح Redis
`sahool:jti:revoked:{jti}`، لكنّ **المنصّة** (نقاط البيانات) لا تستشير القائمة ⇒ تسجيل
الخروج/تعطيل المستخدم لا يُبطِل الوصول فعليّاً حتى انتهاء التوكن.

هذه الوحدة النواة (بلا اعتماد صلب على Redis): backend مُحقَّن (Redis في الإنتاج،
ذاكرة في الاختبار)، بنفس مخطّط المفتاح. الربط في get_current_user = خطوة نشر
(تحتاج عميل Redis حيّ — انظر docs/AUTH_DENYLIST_DESIGN.md).

⚠ المبدأ:
  • **fail-open**: تعذّر فحص القائمة (Redis ساقط) لا يقفل كلّ المستخدمين — يُسجَّل
    ويُسمَح (التوفّر فوق التشدّد؛ الإبطال طبقة دفاع لا الوحيدة). صريح وموثَّق.
  • نفس مخطّط مفتاح خدمة auth (لا مخطّط موازٍ): `sahool:jti:revoked:{jti}`.
  • نقيّة قابلة للاختبار offline (backend ذاكرة).
"""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Mapping
from typing import Any, Protocol

logger = logging.getLogger("sahool.jwt_denylist")

# نفس مخطّط مفتاح خدمة auth (services/auth: revoke_jti/is_jti_revoked).
JTI_REVOKED_KEY = "sahool:jti:revoked:{jti}"
# أرضيّة «إبطال كلّ الجلسات» في auth (services/auth: set_user_token_floor/is_token_below_floor).
# المنصّة تقرؤها ولا تكتبها: auth وحده يضعها عند تغيير كلمة المرور/الدور/التعطيل.
TOKEN_FLOOR_KEY = "sahool:user:token_floor:{sub}"


def denylist_redis_url(env: Mapping[str, str] | None = None) -> str:
    """رابطُ Redis الذي تُقرأ منه القائمة وتُكتَب: ``DENYLIST_REDIS_URL`` إن ضُبط، وإلّا ``REDIS_URL``.

    JWT-REVOCATION-WRITTEN-AND-READ-ON-DIFFERENT-REDIS-SERVERS-01: auth يكتب الإبطال على خادم
    الحالة (``sahool-redis-state``) و``REDIS_URL`` المنصّة يشير إلى الكاش، فكان توكنٌ أُبطِل عند
    الخروج مقبولاً لدى المنصّة حتّى انقضائه. ``DENYLIST_REDIS_URL`` يضع القائمة على خادم auth
    نفسه، ويبقى ``REDIS_URL`` لحدّ المعدّل والطقس. غيرُ مضبوطٍ (أو فارغ) ⇒ ``REDIS_URL`` كما كان
    حرفيّاً، فكلُّ نشرٍ لم يضبطه يتصرّف كما قبل.
    """
    env = os.environ if env is None else env
    return (env.get("DENYLIST_REDIS_URL") or "").strip() or env.get("REDIS_URL", "")


class DenylistBackend(Protocol):
    """عقد backend الإبطال (Redis/ذاكرة): فحص + إبطال بمهلة."""

    def is_revoked(self, jti: str) -> bool: ...

    def revoke(self, jti: str, ttl_seconds: int) -> None: ...

    def token_floor(self, sub: str) -> int | None: ...


class InMemoryDenylist:
    """backend ذاكرة (اختبار/تطوير) — يحترم انتهاء المهلة. ليس للإنتاج متعدّد العمليّات."""

    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}  # jti -> expiry epoch
        self._floors: dict[str, int] = {}  # sub -> floor epoch (يضعها auth؛ هنا للاختبار)

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        self._revoked[jti] = time.time() + max(0, ttl_seconds)

    def is_revoked(self, jti: str) -> bool:
        exp = self._revoked.get(jti)
        if exp is None:
            return False
        if exp <= time.time():  # انتهت المهلة — نظّف واعتبره غير مُبطَل
            self._revoked.pop(jti, None)
            return False
        return True

    def set_token_floor(self, sub: str, floor_epoch: int) -> None:
        self._floors[str(sub)] = int(floor_epoch)

    def token_floor(self, sub: str) -> int | None:
        return self._floors.get(str(sub))


class RedisDenylist:
    """backend Redis للإنتاج — يطابق مفتاح خدمة auth. يقبل عميل Redis مُحقَّناً (sync)."""

    def __init__(self, redis_client: Any):
        self._r = redis_client

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        self._r.setex(JTI_REVOKED_KEY.format(jti=jti), max(1, ttl_seconds), "1")

    def is_revoked(self, jti: str) -> bool:
        return bool(self._r.exists(JTI_REVOKED_KEY.format(jti=jti)))

    def token_floor(self, sub: str) -> int | None:
        raw = self._r.get(TOKEN_FLOOR_KEY.format(sub=sub))
        return None if raw is None else int(raw)


def is_token_revoked(backend: DenylistBackend | None, jti: str | None) -> bool:
    """يفحص إبطال jti عبر backend — **fail-open** (لا قفل عند تعذّر الفحص).

    jti غائب ⇒ غير مُبطَل (توافق خلفي مع توكنات بلا jti). backend None ⇒ غير مُبطَل
    (الميزة غير مُفعَّلة). أيّ استثناء في الفحص (Redis ساقط) ⇒ غير مُبطَل + تحذير.
    """
    if not jti or backend is None:
        return False
    try:
        return bool(backend.is_revoked(jti))
    except Exception as e:  # noqa: BLE001 — fail-open: تعذّر الفحص لا يقفل المستخدم
        logger.warning("تعذّر فحص إبطال jti=%s (يُسمَح، fail-open): %s", jti, e)
        return False


def is_token_below_floor(backend: DenylistBackend | None, payload: Mapping[str, Any]) -> bool:
    """هل أُصدِر التوكن قبل أرضيّة مستخدمه في auth؟ (⇒ مُبطَل جماعيّاً) — **fail-open**.

    PLATFORM-IGNORES-AUTH-REVOKE-ALL-SESSIONS-FLOOR-01: auth يضع ``sahool:user:token_floor:{sub}``
    عند تغيير كلمة المرور أو إعادتها أو الدور أو التعطيل، ويرفض ما ``iat`` فيه أقدم منها؛ والمنصّة لم
    تكن تقرؤها، فكانت تقبل توكنات حسابٍ عُطِّل أو غُيِّرت كلمته حتّى انقضائها. القاعدة نفسها هنا
    حرفيّاً: ``int(iat) < int(floor)``، ولا ``sub``/``iat``/أرضيّة ⇒ غير مُبطَل. backend بلا أرضيّات
    أو تعذّر القراءة ⇒ غير مُبطَل + تحذير، كما في ``is_token_revoked``.
    """
    sub = payload.get("sub")
    iat = payload.get("iat")
    floor_of = getattr(backend, "token_floor", None)
    if sub is None or iat is None or floor_of is None:
        return False
    try:
        floor = floor_of(str(sub))
        return floor is not None and int(iat) < int(floor)
    except Exception as e:  # noqa: BLE001 — fail-open: تعذّر الفحص لا يقفل المستخدم
        logger.warning("تعذّر فحص أرضيّة توكن sub=%s (يُسمَح، fail-open): %s", sub, e)
        return False
