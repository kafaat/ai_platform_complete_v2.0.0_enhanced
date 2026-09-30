"""Access-token verification for consumers of the existing auth service.

The configured key chooses one algorithm; an untrusted JWT header never chooses
the key or enables a fallback. Production follows auth's explicit migration flag.

**وهذه الوحدةُ موضعُ فكّ توكن الوصول الوحيد** (``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01``).
كان الفكُّ مكتوباً ١٦ مرّةً في ١٥ ملفّاً خارجها، وكلُّ نسخةٍ تُقرّر وحدها الجمهورَ والمُصدِرَ
والمطالباتِ المطلوبة. والافتراقُ **مقيسٌ لا محتمل** (على ``bcb7f0ed``):

- ``video-processor`` كان يفكّ بـ``os.getenv("JWT_SECRET", "")`` بلا حارس فراغ، وpython-jose
  3.5.0 **يقبل** توكناً وُقِّع بمفتاح HMAC فارغ حين يكون مفتاحُ التحقّق فارغاً (PyJWT 2.14
  يرفضه ``InvalidKeyError``). فبلا ``JWT_SECRET`` كان أيُّ أحدٍ يُزوّر هويّةً لأيّ مستأجِر.
- ``chat_proxy_reference`` لم يكن يفرض المُصدِر أصلاً (تدقيق B فاته).
- ``market-mcp`` كان يفكّ بـHS256 و``JWT_SECRET`` وحدهما ويتجاهل ``JWT_PUBLIC_KEY`` — فتحت
  RS256 يرفض كلَّ توكنٍ صادرٍ من auth، بينما نقاطُ MCP في الخادم نفسه تقبله.
- لا نسخةَ خارج ``verify_access_token`` كانت تشترط ``exp``: توكنٌ بلا انتهاءٍ صالحٌ أبداً.

**ولماذا خلفيّتان لا واحدة:** الخدماتُ منقسمةٌ مقيساً بين PyJWT (المنصّة · الحواجز · MCP ·
المشرف) وpython-jose (auth · الإشعارات · RAG · ERP · TTS · الفيديو). وهما يختلفان فعلاً لا
شكلاً: PyJWT يرفض ``iat`` في المستقبل (``ImmatureSignatureError``) وjose يقبله — فنقلُ خدمةٍ
من مكتبةٍ إلى أخرى يُغيّر سلوكَها تحت انحراف الساعة. فالسياسةُ هنا مرّةً واحدة، والمكتبةُ
يختارها **المُستدعي صراحةً** بما تحمله صورتُه (``backend=``)، ويُفرَض تطابقُ حكم الخلفيّتين
على مصفوفة الحالات نفسها باختبار (``tests_v9/test_shared_access_tokens.py``).
"""

from __future__ import annotations

import os
from typing import Literal

from .jwt_key_validation import looks_like_placeholder, validate_rsa_public_key_pem

#: الجمهورُ الذي يُصدِره auth والمنصّة معاً (``"aud": "sahool"``).
ACCESS_TOKEN_AUDIENCE = "sahool"
#: المُصدِرون الداخليّون المسموح بهم — يُفرَض بعد فكٍّ ناجح (تدقيق B).
ALLOWED_ISSUERS = frozenset({"sahool-auth", "sahool-platform"})
#: مطالباتٌ **شرطُ وجود** لا «تُفحَص إن وُجدت»: توكنٌ بلا ``exp`` لا ينتهي أبداً.
REQUIRED_CLAIMS = ("exp", "sub", "aud", "iss")
_ALGORITHMS = frozenset({"RS256", "HS256"})

Backend = Literal["pyjwt", "jose"]


class AccessTokenConfigurationError(ValueError):
    """التحقّق **لا يمكن أن يجري**: مفتاحٌ غائب/وهميّ أو خوارزميّةٌ غير مدعومة — فشلٌ مغلق (503)."""


class InvalidAccessTokenError(ValueError):
    """التوكن نفسُه مرفوض: توقيع · انتهاء · جمهور · مُصدِر · مطالبةٌ ناقصة (401)."""


def access_token_verification_key() -> tuple[str, str]:
    try:
        public_key = validate_rsa_public_key_pem(os.getenv("JWT_PUBLIC_KEY", ""))
    except ValueError as exc:
        raise AccessTokenConfigurationError(str(exc)) from exc
    if public_key:
        return public_key, "RS256"
    production = os.getenv("SAHOOL_ENV", "development").strip().lower() in {"production", "prod"}
    migration = os.getenv("SAHOOL_ALLOW_HS256_IN_PROD", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if production and not migration:
        raise AccessTokenConfigurationError("RS256 required in production")
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32 or looks_like_placeholder(secret):
        raise AccessTokenConfigurationError("Access-token verification is not configured")
    return secret, "HS256"


def _decode_with_pyjwt(token: str, key: str, algorithm: str) -> dict:
    try:
        import jwt
    except ImportError as exc:  # الصورةُ لا تحمل المكتبة التي سمّاها المُستدعي ⇒ فشلٌ مغلق
        raise AccessTokenConfigurationError("PyJWT is not installed") from exc
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=ACCESS_TOKEN_AUDIENCE,
            options={"require": list(REQUIRED_CLAIMS)},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError("Invalid access token") from exc


def _decode_with_jose(token: str, key: str, algorithm: str) -> dict:
    try:
        from jose import jwt
        from jose.exceptions import JOSEError
    except ImportError as exc:
        raise AccessTokenConfigurationError("python-jose is not installed") from exc
    try:
        return jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=ACCESS_TOKEN_AUDIENCE,
            options={f"require_{claim}": True for claim in REQUIRED_CLAIMS},
        )
    except JOSEError as exc:
        raise InvalidAccessTokenError("Invalid access token") from exc


_BACKENDS = {"pyjwt": _decode_with_pyjwt, "jose": _decode_with_jose}


def decode_access_token(token: str, key: str, algorithm: str, *, backend: Backend) -> dict:
    """التحقّقُ الوحيد من توقيع توكن وصول: خوارزميّةٌ واحدة · جمهور · مطالبات · مُصدِر.

    ``key``/``algorithm`` يختارهما المُستدعي من تهيئته كما كان يفعل (لم تُنقَل سياسةُ اختيار
    المفتاح في هذه الشريحة — الادّعاءُ أضيق: **الفكُّ** في موضعٍ واحد). والمفتاحُ الفارغ **خطأُ
    تهيئة** لا توكنٌ مرفوض: هو الثقبُ المقيس في python-jose.
    """
    if backend not in _BACKENDS:
        raise AccessTokenConfigurationError(f"Unsupported JWT backend: {backend!r}")
    if algorithm not in _ALGORITHMS:
        raise AccessTokenConfigurationError(f"Unsupported access-token algorithm: {algorithm!r}")
    if not isinstance(key, str) or not key.strip():
        raise AccessTokenConfigurationError("Access-token verification key is empty")
    if not isinstance(token, str) or not token:
        raise InvalidAccessTokenError("Missing access token")
    payload = _BACKENDS[backend](token, key, algorithm)
    if payload.get("iss") not in ALLOWED_ISSUERS:
        raise InvalidAccessTokenError("Invalid token issuer")
    return payload


def _installed_backend() -> Backend:
    """لـ``verify_access_token`` وحده: jose أوّلاً لأنّه ما كان يفكّ به مستهلكاه (الإشعارات ·
    rag-retrieval) قبل هذه الشريحة، فلا يتغيّر سلوكُهما في بيئةٍ تحمل المكتبتين."""
    try:
        import jose.jwt  # noqa: F401

        return "jose"
    except ImportError:
        pass
    try:
        import jwt

        if hasattr(jwt, "PyJWTError"):
            return "pyjwt"
    except ImportError:
        pass
    raise AccessTokenConfigurationError("No JWT library installed (PyJWT or python-jose)")


def verify_access_token(token: str) -> dict:
    if not isinstance(token, str) or not token:
        raise InvalidAccessTokenError("Missing access token")
    key, algorithm = access_token_verification_key()
    payload = decode_access_token(token, key, algorithm, backend=_installed_backend())
    if (
        not payload.get("sub")
        or not isinstance(payload.get("tenant_id"), str)
        or not payload["tenant_id"].strip()
    ):
        raise InvalidAccessTokenError("Missing token identity")
    return payload
