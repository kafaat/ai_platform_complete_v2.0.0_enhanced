"""فكُّ توكن الوصول في موضعٍ واحد — ``shared/security/access_tokens.py``.

``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01``: كان الفكُّ مكتوباً ١٦ مرّةً في ١٥ ملفّاً خارج
الوحدة المشتركة، وكلُّ نسخةٍ تقرّر الجمهورَ والمُصدِرَ والمطالباتِ المطلوبة وحدها. هذا الملفّ
يقيس العقدَ الواحد الذي انتقلت إليه كلُّها:

1. **مصفوفةُ الحكم متطابقةٌ على الخلفيّتين** (PyJWT وpython-jose) — فلا تنحرف إحداهما صامتة.
2. **المفتاحُ الفارغ خطأُ تهيئة** — وهو ثقبٌ مقيس في python-jose (يقبل HMAC بمفتاحٍ فارغ).
3. **الوحدةُ تُستورَد بلا python-jose** — صورُ PyJWT وحدها (المنصّة · الحواجز · MCP · المشرف)
   لا تحمله، واستيرادُه على مستوى الوحدة كان سيُسقِطها عند الإقلاع.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.security import access_tokens as at  # noqa: E402

SECRET = "s" * 40
BACKENDS = ("pyjwt", "jose")


def _claims(**overrides):
    now = int(time.time())
    claims = {
        "sub": "42",
        "tenant_id": "tenant-a",
        "iss": "sahool-auth",
        "aud": "sahool",
        "iat": now - 5,
        "exp": now + 300,
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def _hs(claims, key=SECRET, alg="HS256"):
    import jwt

    return jwt.encode(claims, key, algorithm=alg)


@pytest.fixture(scope="module")
def rsa_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        private.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return private_pem, public_pem


# (الحالة، دالّةٌ تبني (توكن، مفتاح، خوارزميّة)، الحكمُ المتوقَّع)
def _matrix(rsa_pair):
    private_pem, public_pem = rsa_pair
    return [
        ("hs256_valid", lambda: (_hs(_claims()), SECRET, "HS256"), "ok"),
        ("platform_issuer", lambda: (_hs(_claims(iss="sahool-platform")), SECRET, "HS256"), "ok"),
        ("rs256_valid", lambda: (_hs(_claims(), private_pem, "RS256"), public_pem, "RS256"), "ok"),
        ("wrong_key", lambda: (_hs(_claims(), "w" * 40), SECRET, "HS256"), "invalid"),
        ("expired", lambda: (_hs(_claims(exp=int(time.time()) - 60)), SECRET, "HS256"), "invalid"),
        ("no_exp", lambda: (_hs(_claims(exp=None)), SECRET, "HS256"), "invalid"),
        ("no_sub", lambda: (_hs(_claims(sub=None)), SECRET, "HS256"), "invalid"),
        ("no_iss", lambda: (_hs(_claims(iss=None)), SECRET, "HS256"), "invalid"),
        ("no_aud", lambda: (_hs(_claims(aud=None)), SECRET, "HS256"), "invalid"),
        ("wrong_aud", lambda: (_hs(_claims(aud="other")), SECRET, "HS256"), "invalid"),
        ("unknown_issuer", lambda: (_hs(_claims(iss="evil")), SECRET, "HS256"), "invalid"),
        # خلطُ الخوارزميّة: توكن HS256 وُقِّع بالمفتاح العامّ نصّاً، والمتحقِّق على RS256.
        (
            "alg_confusion",
            lambda: (_forge_hs_with_public(public_pem), public_pem, "RS256"),
            "invalid",
        ),
        ("garbage", lambda: ("not.a.jwt", SECRET, "HS256"), "invalid"),
        ("empty_token", lambda: ("", SECRET, "HS256"), "invalid"),
        ("empty_key", lambda: (_hs(_claims()), "", "HS256"), "config"),
        ("blank_key", lambda: (_hs(_claims()), "   ", "HS256"), "config"),
        ("unsupported_alg", lambda: (_hs(_claims()), SECRET, "none"), "config"),
    ]


def _forge_hs_with_public(public_pem: str) -> str:
    import base64
    import hashlib
    import hmac
    import json

    def b64(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(_claims()).encode())
    sig = hmac.new(public_pem.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{b64(sig)}"


def _verdict(token, key, alg, backend) -> str:
    try:
        at.decode_access_token(token, key, alg, backend=backend)
    except at.AccessTokenConfigurationError:
        return "config"
    except at.InvalidAccessTokenError:
        return "invalid"
    return "ok"


def test_both_backends_give_the_same_verdict_on_every_case(rsa_pair):
    rows = []
    for name, build, expected in _matrix(rsa_pair):
        token, key, alg = build()
        got = {backend: _verdict(token, key, alg, backend) for backend in BACKENDS}
        rows.append((name, expected, got))
    mismatched = [(n, e, g) for n, e, g in rows if set(g.values()) != {e}]
    assert not mismatched, mismatched


def test_python_jose_accepts_an_empty_hmac_key_and_the_shared_decoder_does_not():
    """الثقبُ الذي كان مفتوحاً في video-processor: jose يفكّ توكناً وُقِّع بمفتاحٍ فارغ."""
    from jose import jwt as jose_jwt

    forged = jose_jwt.encode(_claims(), "", algorithm="HS256")
    # المكتبةُ نفسُها تقبله — لو صار هذا يرفض يوماً، فالحارسُ أدناه يبقى صحيحاً ولا ضرر.
    assert jose_jwt.decode(forged, "", algorithms=["HS256"], audience="sahool")["sub"] == "42"
    for backend in BACKENDS:
        with pytest.raises(at.AccessTokenConfigurationError):
            at.decode_access_token(forged, "", "HS256", backend=backend)


def test_errors_stay_value_errors_for_existing_callers():
    """المستهلكون القائمون (الإشعارات · rag-retrieval · odoo-bridge) يلتقطون ``ValueError``."""
    assert issubclass(at.AccessTokenConfigurationError, ValueError)
    assert issubclass(at.InvalidAccessTokenError, ValueError)
    with pytest.raises(at.AccessTokenConfigurationError):
        at.decode_access_token("x", SECRET, "HS256", backend="unknown")  # type: ignore[arg-type]


def test_verify_access_token_keeps_its_contract(monkeypatch):
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", SECRET)
    assert at.verify_access_token(_hs(_claims()))["tenant_id"] == "tenant-a"
    with pytest.raises(at.InvalidAccessTokenError):
        at.verify_access_token(_hs(_claims(tenant_id=None)))
    with pytest.raises(at.InvalidAccessTokenError):
        at.verify_access_token(_hs(_claims(tenant_id="  ")))
    monkeypatch.setenv("SAHOOL_ENV", "production")
    with pytest.raises(at.AccessTokenConfigurationError):
        at.verify_access_token(_hs(_claims()))


def test_the_module_imports_and_decodes_without_python_jose():
    """صورُ PyJWT وحدها لا تحمل python-jose؛ استيرادُه أعلى الوحدة كان سيُسقِطها عند الإقلاع."""
    probe = textwrap.dedent(
        f"""
        import importlib.abc, sys, time
        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name == "jose" or name.startswith("jose."):
                    raise ImportError("blocked: " + name)
        sys.meta_path.insert(0, Block())
        sys.path.insert(0, {str(ROOT)!r})
        import jwt
        from shared.security import access_tokens as at
        now = int(time.time())
        tok = jwt.encode({{"sub": "1", "iss": "sahool-auth", "aud": "sahool", "exp": now + 60}},
                         "k" * 40, algorithm="HS256")
        assert at.decode_access_token(tok, "k" * 40, "HS256", backend="pyjwt")["sub"] == "1"
        try:
            at.decode_access_token(tok, "k" * 40, "HS256", backend="jose")
        except at.AccessTokenConfigurationError:
            print("ok")
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert out.returncode == 0 and out.stdout.strip() == "ok", out.stderr
