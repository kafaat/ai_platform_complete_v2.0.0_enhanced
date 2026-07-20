"""definition_sync_token — توكن مزامنة النماذج HMAC ذاتيّ التحقّق (GAP-FIELD-FORMS-01 §9).

ذاتيّ التحقّق **بلا جدول خامس**: ``base64url(payload_json) + "." + base64url(HMAC)``.
الحمولة: token_version / key_id / tenant_id / actor_id / device_id / assignment_id /
revision / form_version_id / schema_hash / issued_at.

تدوير المفاتيح: التحقّق يقبل المفتاح الحاليّ أو مفتاحًا سابقًا محتفَظًا به صراحةً **بحدّ زمنيّ**
(يمرّر المتصل ``previous_until_epoch`` — لا سرّ قديم بلا انتهاء). نافذة offline القصوى
يفرضها المتصل على ``issued_at`` (لا تُفحص هنا — الوحدة نقيّة).

الفرق الجوهريّ (§9.5): «تقاعد بعد أن حصلتَ عليه بإثبات» =/= «تدّعي أنّك أنشأت قبل التقاعد» —
هذا التوكن هو الإثبات الخادميّ الوحيد المعتمد، و``local_created_at`` لا يُوثَق أبدًا.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

TOKEN_VERSION = 1

REQUIRED_CLAIMS = (
    "token_version",
    "key_id",
    "tenant_id",
    "actor_id",
    "device_id",
    "assignment_id",
    "revision",
    "form_version_id",
    "schema_hash",
    "issued_at",
)


class SyncTokenError(ValueError):
    """توكن مكسور/منتحل/منتهي المفتاح — يقابله invalid_sync_proof في الأنبوب."""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode(text + pad)
    except Exception as exc:  # noqa: BLE001
        raise SyncTokenError("malformed_base64") from exc


def _sign(payload_b64: str, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256)
    return _b64url_encode(mac.digest())


def issue_token(claims: dict[str, Any], *, secret: str, key_id: str) -> str:
    """يُصدر توكنًا موقّعًا. المتصل (نقطة التنزيل) يملأ المطالبات العشر كلّها."""
    missing = [c for c in REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise SyncTokenError(f"missing_claims: {missing}")
    if claims["token_version"] != TOKEN_VERSION:
        raise SyncTokenError("unsupported_token_version")
    payload = dict(claims)
    payload["key_id"] = key_id
    payload_b64 = _b64url_encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def verify_token(
    token: str,
    *,
    current_secret: str,
    current_key_id: str,
    previous_secret: str | None = None,
    previous_key_id: str | None = None,
    previous_until_epoch: float | None = None,
    now_epoch: float | None = None,
) -> dict[str, Any]:
    """يتحقّق من التوقيع والبنية ويعيد المطالبات. يرفع SyncTokenError على أيّ خلل.

    التحقّقات المتروكة للمتصل (تحتاج سياق DB/سياسة): تطابق الهويّة (tenant/actor/device)،
    وجود الوجهة (assignment/form_version)، صلاحية الإصدار عند issued_at، نافذة offline القصوى.
    """
    if not token or token.count(".") != 1:
        raise SyncTokenError("malformed_token")
    payload_b64, sig = token.split(".", 1)
    try:
        claims = json.loads(_b64url_decode(payload_b64))
    except (ValueError, UnicodeDecodeError) as exc:
        raise SyncTokenError("malformed_payload") from exc
    if not isinstance(claims, dict):
        raise SyncTokenError("malformed_payload")
    missing = [c for c in REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise SyncTokenError(f"missing_claims: {missing}")
    if claims["token_version"] != TOKEN_VERSION:
        raise SyncTokenError("unsupported_token_version")
    now = time.time() if now_epoch is None else now_epoch
    key_id = claims["key_id"]
    if key_id == current_key_id:
        secret = current_secret
    elif (
        previous_secret
        and previous_key_id
        and key_id == previous_key_id
        and previous_until_epoch is not None
        and now <= previous_until_epoch
    ):
        secret = previous_secret  # مفتاح سابق محتفَظ به صراحةً بحدّ زمنيّ
    else:
        raise SyncTokenError("unknown_or_expired_key_id")
    expected = _sign(payload_b64, secret)
    if not hmac.compare_digest(expected, sig):
        raise SyncTokenError("bad_signature")
    return claims
