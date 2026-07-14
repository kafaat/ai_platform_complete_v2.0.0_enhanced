"""حارس تماثل خوارزميّة JWT عبر compose (تدقيق 8678b4d / JWT-RUNTIME).

خلفيّة: يختار كلٌّ من ``sahool-auth`` و``sahool-platform`` الخوارزميّة من وجود المفتاح:
auth ``RS256 if JWT_PRIVATE_KEY else HS256`` (services/auth/main.py:65)، وplatform
``RS256 if JWT_PUBLIC_KEY else HS256`` (services/sahool-platform/api/main.py:82). كان
``sahool-auth`` في compose يعرض ``JWT_SECRET`` فقط دون ``JWT_PRIVATE_KEY``/``JWT_PUBLIC_KEY``/
``SAHOOL_ALLOW_HS256_IN_PROD``، بينما تعرضها المنصّة — فيستحيل ضبط RS256 على المُوقِّع.
ضبطُ ``JWT_PUBLIC_KEY`` عندئذٍ يدفع المنصّة إلى RS256 بينما يبقى auth على HS256 ⇒ عدم تطابق
(InvalidAlgorithmError → 401 في التطوير، رفض إقلاع fail-closed في الإنتاج).

هذا الحارس يفرض عقداً مشترَكاً متماثلاً: متغيّرات تحديد الخوارزميّة معروضة على المُصدِر
(auth) والمتحقِّق (platform) معاً، فلا يمكن ضبط أحدهما لـRS256 وترك الآخر على HS256. ``unit``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
_COMPOSE = ROOT / "docker-compose.v9.yml"

# مفاتيح تحديد الخوارزميّة على كلّ جانب: المُوقِّع (auth) يحتاج المفتاح الخاصّ + العامّ،
# والمتحقِّق (platform) يحتاج العامّ. ومهرب HS256 في الإنتاج يجب أن يكون متماثلاً.
_SIGNER = "sahool-auth"
_VERIFIER = "sahool-platform"


def _env(service: str) -> dict[str, str]:
    doc = yaml.safe_load(_COMPOSE.read_text())
    env = doc["services"][service].get("environment", {})
    if isinstance(env, list):
        env = {e.split("=", 1)[0]: (e.split("=", 1)[1] if "=" in e else "") for e in env}
    return {str(k): str(v) for k, v in env.items()}


def test_auth_exposes_rs256_key_pair_vars():
    # المُوقِّع لا يمكن أن يدخل وضع RS256 ما لم تُعرَض مفاتيحه — تماثلاً مع المنصّة.
    env = _env(_SIGNER)
    for var in ("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY"):
        assert var in env, f"{_SIGNER} لا يعرض {var} — مسار RS256 غير قابل للضبط على المُوقِّع"


def test_hs256_prod_escape_hatch_is_symmetric():
    # مهرب HS256 في الإنتاج معروض على الطرفين أو غائب عن كليهما (لا انقسام).
    a = "SAHOOL_ALLOW_HS256_IN_PROD" in _env(_SIGNER)
    p = "SAHOOL_ALLOW_HS256_IN_PROD" in _env(_VERIFIER)
    assert a == p, "مهرب SAHOOL_ALLOW_HS256_IN_PROD غير متماثل بين auth وplatform"


def test_public_key_var_present_on_both_sides():
    # عقد RS256: إن عرضت المنصّة JWT_PUBLIC_KEY فليعرضه auth أيضاً (نفس اسم المتغيّر) كي
    # يستطيع مُشغِّلٌ ضبطُ المفتاح العامّ عبر المتغيّر ذاته على الطرفين بلا انقسام صامت.
    if "JWT_PUBLIC_KEY" in _env(_VERIFIER):
        assert "JWT_PUBLIC_KEY" in _env(_SIGNER), (
            "platform يعرض JWT_PUBLIC_KEY (RS256) لكنّ auth لا يعرضه — عقد خوارزميّة منقسم"
        )


def test_both_services_still_share_jwt_secret_for_hs256():
    # في وضع HS256 (تطوير) يجب أن يحمل الطرفان السرّ المتماثل نفسه للتحقّق المتبادل.
    assert "JWT_SECRET" in _env(_SIGNER)
    verifier = _env(_VERIFIER)
    assert "JWT_SECRET" in verifier or "SAHOOL_JWT_SECRET" in verifier
