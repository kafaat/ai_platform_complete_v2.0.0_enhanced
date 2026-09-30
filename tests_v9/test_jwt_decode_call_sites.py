"""مواضعُ الفكّ التي نُقِلت إلى ``shared.security.access_tokens`` — مقيسةً عند الحافّة.

``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01``: ``test_shared_access_tokens.py`` يقيس الوحدة؛ هذا
الملفّ يقيس أنّ **كلَّ خدمةٍ نُقِلت تنادي الوحدة فعلاً بالمفتاح والخوارزميّة الصحيحين** —
ويُثبت العيوبَ الثلاثة التي كانت النسخُ المحلّيّة تحملها (مقيسةً على ``bcb7f0ed``):

- **video-processor:** بلا ``JWT_PUBLIC_KEY``/``JWT_SECRET`` كان يقبل توكناً موقَّعاً بمفتاحٍ
  فارغ (python-jose يقبل HMAC بمفتاحٍ فارغ) ⇒ أيُّ أحدٍ يسكّ هويّةً لأيّ مستأجِر.
- **chat_proxy_reference:** لم يكن يفرض المُصدِر ⇒ توكنٌ بجمهور sahool من مُصدِرٍ مجهول يُقبَل.
- **market-mcp (REST):** HS256 و``JWT_SECRET`` وحدهما ⇒ تحت RS256 يُرفَض كلُّ توكنٍ من auth.
- **ولا نسخةَ كانت تشترط ``exp``** ⇒ توكنٌ بلا انتهاء صالحٌ أبداً (يُقاس هنا على auth — المُصدِر
  نفسُه، آخِرُ ما نُقِل — وعلى المنصّة).

وكلُّ مُستدعٍ يسمّي الخلفيّةَ التي تحملها صورتُه (``requirements.txt`` خدمته) — لأنّ المكتبتين
تختلفان فعلاً: PyJWT يرفض ``iat`` في المستقبل وjose يقبله، فنقلُ خدمةٍ بينهما يُغيّر سلوكَها.

الخدماتُ تتشارك اسم الوحدة ``main``، فكلُّ خدمةٍ تُقاس في عمليّةٍ فرعيّةٍ معزولة (نمطُ
``test_auth_service.py``) — وإلّا قاس الاختبارُ ``main`` خدمةٍ أخرى صامتاً.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SECRET = "test_secret_min_32_chars_for_sahool_v9"


_CLAIMS = """
import time
NOW = int(time.time())
def claims(**over):
    base = {"sub": "7", "tenant_id": "tenant-a", "iss": "sahool-auth", "aud": "sahool",
            "iat": NOW - 5, "exp": NOW + 300, "jti": "jti-1", "role": "farmer"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}
"""


def _run(script: str, cwd: Path, **env) -> dict:
    full_env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SAHOOL_ENV": "development",
        "JWT_PRIVATE_KEY": "",
        "JWT_PUBLIC_KEY": "",
        "JWT_SECRET": SECRET,
        **env,
    }
    proc = subprocess.run(
        [sys.executable, "-c", _CLAIMS + textwrap.dedent(script)],
        cwd=cwd,
        env=full_env,
        capture_output=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_auth_the_issuer_verifies_its_own_tokens_through_the_shared_decoder():
    out = _run(
        """
        import asyncio, json
        import main
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from fastapi.testclient import TestClient
        from jose import jwt

        def tok(**c):
            return jwt.encode(claims(**c), main.JWT_SIGNING_KEY, algorithm=main.JWT_ALGORITHM)

        async def status(t):
            try:
                await main.get_current_user(HTTPAuthorizationCredentials(scheme="Bearer", credentials=t))
                return 200
            except HTTPException as e:
                return e.status_code

        cases = {"valid": tok(), "platform_iss": tok(iss="sahool-platform"),
                 "no_exp": tok(exp=None), "foreign_iss": tok(iss="evil"), "wrong_aud": tok(aud="x")}
        me = {k: asyncio.run(status(v)) for k, v in cases.items()}

        revoked = []
        async def fake_revoke(jti, exp):
            revoked.append(jti)
        async def fake_audit(*a, **k):
            return None
        main.revoke_jti = fake_revoke
        main.audit_log = fake_audit
        client = TestClient(main.app)
        headers = {}
        for name in ("valid", "no_exp", "foreign_iss"):
            r = client.post("/v1/auth/logout", headers={"Authorization": "Bearer " + cases[name]})
            headers[name] = [r.status_code, r.headers.get("x-tenant-id")]
        print(json.dumps({"me": me, "revoked": revoked, "logout": headers}))
        """,
        cwd=ROOT / "services/auth",
    )
    assert out["me"] == {
        "valid": 200,
        "platform_iss": 200,
        "no_exp": 401,
        "foreign_iss": 401,
        "wrong_aud": 401,
    }
    # الخروج يُبطِل jti التوكن الصالح وحده، ولا يُشتقّ رأسُ المستأجِر إلّا منه.
    assert out["revoked"] == ["jti-1"]
    assert out["logout"]["valid"] == [200, "tenant-a"]
    assert out["logout"]["no_exp"] == [200, None]
    assert out["logout"]["foreign_iss"] == [200, None]


def test_platform_rejects_a_token_without_exp():
    out = _run(
        """
        import json, sys
        sys.path.insert(0, ".")
        import jwt
        from fastapi import HTTPException
        from api import main

        def status(c):
            try:
                main.get_current_user("Bearer " + jwt.encode(c, main.JWT_SECRET, algorithm="HS256"))
                return 200
            except HTTPException as e:
                return e.status_code

        print(json.dumps({"valid": status(claims()), "no_exp": status(claims(exp=None)),
                          "foreign_iss": status(claims(iss="evil"))}))
        """,
        cwd=ROOT / "services/sahool-platform",
        SAHOOL_JWT_SECRET=SECRET,
    )
    assert out == {"valid": 200, "no_exp": 401, "foreign_iss": 401}


def test_video_processor_refuses_an_empty_key_instead_of_accepting_forgeries():
    out = _run(
        """
        import asyncio, json, sys
        sys.path.insert(0, ".")
        import main
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from jose import jwt

        def status(token):
            try:
                asyncio.run(main._get_current_user(
                    HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)))
                return 200
            except HTTPException as e:
                return e.status_code

        forged = jwt.encode(claims(tenant_id="victim"), "", algorithm="HS256")
        print(json.dumps({"forged_with_empty_key": status(forged)}))
        """,
        cwd=ROOT / "services/video-processor",
        JWT_SECRET="",
    )
    assert out == {"forged_with_empty_key": 503}


def test_market_rest_accepts_rs256_auth_tokens_like_its_mcp_endpoints():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    out = _run(
        f"""
        import json, sys
        # تخطيطُ التطوير الذي كان يُخفي الخادم: services/mcp_servers **قبل** الجذر على sys.path،
        # فتُحَلّ ``shared`` إلى مجلّد MCP — ويجب أن يُرى ``shared.security`` مع ذلك.
        sys.path.insert(0, {str(ROOT)!r})
        sys.path.insert(0, ".")
        import jwt
        from fastapi import HTTPException
        import market_server
        import shared
        rs = jwt.encode(claims(), {private_pem!r}, algorithm="RS256")
        try:
            market_server.verify_token(rs)
            result = 200
        except HTTPException as e:
            result = e.status_code
        print(json.dumps({{"rs256": result, "shared_paths": len(shared.__path__)}}))
        """,
        cwd=ROOT / "services/mcp_servers",
        JWT_PUBLIC_KEY=public_pem,
    )
    assert out["rs256"] == 200
    assert out["shared_paths"] == 2, "mcp_servers/shared لم يُلحِق مجلّد shared الجذريّ"


def test_chat_proxy_reference_enforces_the_issuer():
    spec = importlib.util.spec_from_file_location(
        "_chat_proxy_issuer_probe", ROOT / "services/sahool-platform/api/chat_proxy_reference.py"
    )
    proxy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(proxy)
    if getattr(proxy, "app", None) is None:
        pytest.skip("fastapi/httpx غائبة — مثال الـFastAPI غير مُفعَّل")
    import jwt
    from fastapi import HTTPException
    from starlette.requests import Request

    proxy._JWT_PUBLIC_KEY = ""
    proxy._JWT_SECRET = SECRET
    now = int(time.time())

    def request_with(claims):
        token = jwt.encode(claims, SECRET, algorithm="HS256")
        scope = {
            "type": "http",
            "headers": [(b"authorization", f"Bearer {token}".encode())],
        }
        return Request(scope)

    base = {"sub": "1", "tenant_id": "t-1", "aud": "sahool", "exp": now + 60}
    assert proxy._tenant_from_jwt(request_with({**base, "iss": "sahool-auth"})) == "t-1"
    with pytest.raises(HTTPException) as foreign:
        proxy._tenant_from_jwt(request_with({**base, "iss": "evil"}))
    assert foreign.value.status_code == 401


# ── كلُّ مُستدعٍ يسمّي الخلفيّة التي تحملها صورتُه ─────────────────────────────

_REQUIREMENTS_BY_PREFIX = (
    ("services/sahool-platform/", "services/sahool-platform/api/requirements.txt"),
    ("services/mcp_servers/", "services/mcp_servers/requirements.txt"),
)
_LIB_FOR_BACKEND = {"pyjwt": "pyjwt", "jose": "python-jose"}


def _requirements_for(rel: str) -> Path:
    for prefix, req in _REQUIREMENTS_BY_PREFIX:
        if rel.startswith(prefix):
            return ROOT / req
    service = rel.split("/")[1]
    return ROOT / "services" / service / "requirements.txt"


def _declared_libs(req: Path) -> set[str]:
    libs = set()
    for line in req.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip().split("[", 1)[0]
        for sep in ("==", ">=", "<=", "~=", ">", "<"):
            name = name.split(sep, 1)[0]
        if name:
            libs.add(name.strip().lower())
    return libs


def _backend_calls(root: Path = ROOT):
    """``(ملفّ، سطر، الخلفيّة)`` لكلّ نداء ``decode_access_token(..., backend="…")`` في الخدمات."""
    for path in sorted((root / "services").rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if "/tests/" in rel or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        if "decode_access_token" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name != "decode_access_token":
                continue
            backend = next(
                (
                    kw.value.value
                    for kw in node.keywords
                    if kw.arg == "backend" and isinstance(kw.value, ast.Constant)
                ),
                None,
            )
            yield rel, node.lineno, backend


def test_every_caller_names_the_backend_its_image_installs():
    calls = list(_backend_calls())
    # ١٣ نداءً مقيساً بعد النقل (الحواجز وMCP جمعا نسختَيهما في مُساعِدٍ واحد) — أرضيّةٌ تكشف
    # كاشفاً أعمى، لا سقف.
    assert len(calls) >= 13, calls
    wrong = []
    for rel, line, backend in calls:
        if backend not in _LIB_FOR_BACKEND:
            wrong.append(f"{rel}:{line} backend={backend!r} (يجب أن يكون حرفيّاً pyjwt أو jose)")
            continue
        req = _requirements_for(rel)
        if _LIB_FOR_BACKEND[backend] not in _declared_libs(req):
            wrong.append(f"{rel}:{line} backend={backend} لكنّ {req.relative_to(ROOT)} لا يعلنها")
    assert not wrong, wrong
