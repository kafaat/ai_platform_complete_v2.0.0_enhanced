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
import time
from typing import Any, Protocol

logger = logging.getLogger("sahool.jwt_denylist")

# نفس مخطّط مفتاح خدمة auth (services/auth: revoke_jti/is_jti_revoked).
JTI_REVOKED_KEY = "sahool:jti:revoked:{jti}"


class DenylistBackend(Protocol):
    """عقد backend الإبطال (Redis/ذاكرة): فحص + إبطال بمهلة."""

    def is_revoked(self, jti: str) -> bool: ...

    def revoke(self, jti: str, ttl_seconds: int) -> None: ...


class InMemoryDenylist:
    """backend ذاكرة (اختبار/تطوير) — يحترم انتهاء المهلة. ليس للإنتاج متعدّد العمليّات."""

    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}  # jti -> expiry epoch

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


class RedisDenylist:
    """backend Redis للإنتاج — يطابق مفتاح خدمة auth. يقبل عميل Redis مُحقَّناً (sync)."""

    def __init__(self, redis_client: Any):
        self._r = redis_client

    def revoke(self, jti: str, ttl_seconds: int) -> None:
        self._r.setex(JTI_REVOKED_KEY.format(jti=jti), max(1, ttl_seconds), "1")

    def is_revoked(self, jti: str) -> bool:
        return bool(self._r.exists(JTI_REVOKED_KEY.format(jti=jti)))


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
