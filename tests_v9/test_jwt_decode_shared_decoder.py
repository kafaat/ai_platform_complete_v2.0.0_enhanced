"""شاهد ``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01``: فكُّ توكن الوصول في موضعٍ واحد، بوضع مراقبة.

**ما يُثبته (أحمر على ``origin/main`` قبل الإصلاح، أخضر بعده):**

1. **المسح الثابت:** لا نداءَ فكّ JWT في ملفّات الإنتاج خارج ``shared/security/`` إلّا في
   قائمة سماحٍ صريحة مُعلَّلة (المُشغِّل مجمَّد بـGATE-01؛ موضعا MCP انتقلا عبر جسر الحزمة الضيّق)، وكلُّ
   ملفٍّ منقول يمرّ بـ``decode_access_token`` بخوارزميّةٍ واحدة مثبَّتة ودلالةِ مطالباتٍ مُعلَنة.
2. **السلوك:** المفكِّك المشترك (PyJWT وحدها بعد إزالة python-jose) يحفظ حكمَ كلّ موضع:
   ``claim_semantics="pyjwt"`` لمن كان على PyJWT، و``"python-jose"`` لمن كان على python-jose
   (``aud`` يُفحَص حين يوجد، و``iat`` لا يُقارَن بالساعة)؛ يرفض المفتاحَ الفارغ، ويعدّ ما كانت
   السياسةُ الأشدّ (exp/sub/aud/iss) سترفضه **دون رفضه** إلّا في وضع ``enforce`` (قرار المالك
   2026-10-01، #1118: عدّادٌ قبل الفرض).
3. **ثقبٌ حقيقيّ أُغلق:** video-processor بلا ``JWT_SECRET`` كان يقبل توكناً موقَّعاً بمفتاحٍ
   فارغ (python-jose 3.5.0 كان يقبله)، فيُزوَّر أيُّ مستأجِر. الآن 401.
"""

from __future__ import annotations

import ast
import base64
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path

import pytest

from tests_v9 import service_module

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOTS = ("services", "shared", "agents", "bots")
CANONICAL = "shared/security/"
SECRET = "unit-test-secret-0123456789-abcdefghijklmnopqrstuvwxyz-0123456789-ABCDEF"

#: ما يبقى يفكّ بنفسه — مُعلَّلٌ لا مُعفى؛ الإغلاقُ يُفرِغ هذه القائمة.
ALLOWED_DIRECT_DECODE = {
    # GATE-01: frozen_paths في docs/architecture/gate01_policy.json — لا يُمسّ بلا تفويضٍ محكَّم.
    "services/actuator-service/actuator_runtime.py": 1,
}

#: الملفّ ← (دلالةُ المطالبات المحفوظة، عددُ النداءات). ``python-jose`` = الموضعُ كان على
#: python-jose قبل إزالته (DEP-PYTHON-JOSE-HMAC-PUBKEY-CONFUSION-01) فيُحفَظ حكمُه.
MIGRATED = {
    "services/mcp_servers/market_server.py": ("pyjwt", 1),
    "services/mcp_servers/shared/oauth_middleware.py": ("pyjwt", 1),
    "services/auth/main.py": ("python-jose", 1),  # `_decode_issued_token` (سقفُ أسطر main)
    "services/auth/routers/session.py": ("python-jose", 1),
    "services/guardrails-engine/main.py": ("pyjwt", 2),
    "services/local-ai-rag/main.py": ("python-jose", 1),
    "services/odoo-bridge/main.py": ("python-jose", 1),
    "services/sahool-platform/api/chat_proxy_reference.py": ("pyjwt", 1),
    "services/sahool-platform/api/main.py": ("pyjwt", 1),
    "services/sahool-platform/api/routers/auth.py": ("pyjwt", 1),
    "services/supervisor-agent/main.py": ("pyjwt", 1),
    "services/tts-service/main.py": ("python-jose", 1),
    "services/vegetation-analysis-service/vegetation_runtime.py": ("pyjwt", 1),
    "services/video-processor/main.py": ("python-jose", 1),
}


# ── المسح الثابت ──────────────────────────────────────────────────────────────


def _direct_decode_calls(tree: ast.AST) -> int:
    modules: set[str] = set()
    funcs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in {"jwt", "jose.jwt"}:
                    modules.add(a.asname or a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                full = f"{node.module or ''}.{a.name}"
                if full in {"jose.jwt"}:
                    modules.add(a.asname or a.name)
                elif node.module in {"jwt", "jose.jwt"} and a.name == "decode":
                    funcs.add(a.asname or a.name)
    n = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr == "decode" and isinstance(f.value, ast.Name):
            n += f.value.id in modules
        elif isinstance(f, ast.Name):
            n += f.id in funcs
    return n


def _production_files():
    for top in SEARCH_ROOTS:
        for path in sorted((ROOT / top).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            parts = rel.split("/")
            if rel.startswith(CANONICAL) or "tests" in parts or "__pycache__" in parts:
                continue
            if parts[-1].startswith("test_") or parts[-1].endswith("_test.py"):
                continue
            yield rel, path


def test_no_jwt_decode_outside_shared_security_except_the_declared_allowlist():
    live = {}
    for rel, path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        n = _direct_decode_calls(tree)
        if n:
            live[rel] = n
    assert live == ALLOWED_DIRECT_DECODE, (
        "JWT-DECODE-OUTSIDE-SHARED-SECURITY-01: فكٌّ خارج shared/security غير مُعلَن — "
        f"انقله إلى decode_access_token: { {k: v for k, v in live.items() if ALLOWED_DIRECT_DECODE.get(k) != v} }"
    )


@pytest.mark.parametrize("rel", sorted(MIGRATED))
def test_each_migrated_site_decodes_through_the_shared_decoder_with_one_pinned_algorithm(rel):
    semantics, expected = MIGRATED[rel]
    tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "decode_access_token"
    ]
    assert len(calls) == expected, f"{rel}: {len(calls)} != {expected}"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "algorithms" not in kw and "algorithm" in kw, f"{rel}: خوارزميّةٌ واحدة مثبَّتة"
        # لا خلفيّةَ غير PyJWT: ``backend`` إمّا غائب أو "pyjwt" حرفيّاً.
        assert "backend" not in kw or (
            isinstance(kw["backend"], ast.Constant) and kw["backend"].value == "pyjwt"
        ), f"{rel}: python-jose أُزيل — لا خلفيّة غير pyjwt"
        declared = kw.get("claim_semantics")
        got = declared.value if isinstance(declared, ast.Constant) else "pyjwt"
        assert declared is None or isinstance(declared, ast.Constant)
        assert got == semantics, f"{rel}: دلالةُ المطالبات {got} != {semantics}"
        assert isinstance(kw.get("site"), ast.Constant) and kw["site"].value


# ── سلوك المفكِّك المشترك ─────────────────────────────────────────────────────


@pytest.fixture
def tokens(monkeypatch):
    from shared.security import access_tokens

    monkeypatch.delenv(access_tokens.CLAIM_POLICY_ENV, raising=False)
    access_tokens.reset_would_reject_counts()
    yield access_tokens
    access_tokens.reset_would_reject_counts()


def _claims(**over):
    claims = {
        "sub": "user-1",
        "tenant_id": "t1",
        "iss": "sahool-auth",
        "aud": "sahool",
        "exp": int(time.time()) + 300,
    }
    for k, v in over.items():
        if v is None:
            claims.pop(k, None)
        else:
            claims[k] = v
    return claims


def _encode(claims, key=SECRET, alg="HS256"):
    import jwt

    return jwt.encode(claims, key, algorithm=alg)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def forge_hs256(claims: dict, key: bytes) -> str:
    """توكن HS256 يُبنى يدويّاً: PyJWT يرفض توقيعَ HMAC بمفتاحٍ فارغ أو بمفتاحٍ عامّ، والمهاجم لا."""
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(claims).encode())
    sig = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64(sig)}"


def _invalid():
    import jwt

    return jwt.InvalidTokenError


SEMANTICS = ("pyjwt", "python-jose")


@pytest.mark.parametrize("semantics", SEMANTICS)
def test_valid_token_is_accepted_and_not_counted(tokens, semantics):
    payload = tokens.decode_access_token(
        _encode(_claims()), SECRET, algorithm="HS256", claim_semantics=semantics, site="u"
    )
    assert payload["sub"] == "user-1"
    assert tokens.would_reject_counts() == {}


@pytest.mark.parametrize("semantics", SEMANTICS)
@pytest.mark.parametrize(
    "case", ["signature", "audience", "expired", "header_alg_mismatch", "unpinned_algorithm"]
)
def test_the_native_rejections_are_preserved(tokens, semantics, case):
    key, alg, claims, enc_alg = SECRET, "HS256", _claims(), "HS256"
    if case == "signature":
        key = SECRET + "x"
    elif case == "audience":
        claims = _claims(aud="another-service")
    elif case == "expired":
        claims = _claims(exp=int(time.time()) - 60)
    elif case == "header_alg_mismatch":
        enc_alg = "HS512"
    elif case == "unpinned_algorithm":
        alg = "none"
    token = _encode(claims, alg=enc_alg)
    with pytest.raises(_invalid()):
        tokens.decode_access_token(token, key, algorithm=alg, claim_semantics=semantics, site="u")


@pytest.mark.parametrize("semantics", SEMANTICS)
@pytest.mark.parametrize("key", ["", "   "])
def test_an_empty_verification_key_is_rejected(tokens, semantics, key):
    forged = forge_hs256(_claims(), key.encode())
    with pytest.raises(_invalid()):
        tokens.decode_access_token(
            forged, key, algorithm="HS256", claim_semantics=semantics, site="u"
        )


def test_pyjwt_itself_refuses_an_empty_hmac_key_and_the_guard_does_not_rely_on_it():
    """المعايرة: python-jose 3.5.0 كان يقبل مفتاحاً فارغاً؛ PyJWT يرفضه، والحارسُ يسبقه أصلاً."""
    import jwt

    forged = forge_hs256(_claims(), b"")
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(forged, "", algorithms=["HS256"], audience="sahool")


def test_the_backend_parameter_accepts_only_pyjwt(tokens):
    token = _encode(_claims())
    assert (
        tokens.decode_access_token(token, SECRET, algorithm="HS256", backend="pyjwt", site="u")[
            "sub"
        ]
        == "user-1"
    )
    with pytest.raises(ValueError, match="python-jose was removed"):
        tokens.decode_access_token(token, SECRET, algorithm="HS256", backend="jose", site="u")


@pytest.mark.parametrize("semantics", SEMANTICS)
@pytest.mark.parametrize(
    ("override", "reason"),
    # التعديلُ لا المطالباتُ في المعامِلات: ``exp`` يُحسب وقتَ التشغيل لا وقتَ الجمع، وإلّا
    # انتهى التوكن في جناحٍ يطول عشرين دقيقة فيُرفَض لسببٍ غير المقيس.
    [
        ({"exp": None}, "missing_exp"),
        ({"sub": None}, "missing_sub"),
        ({"iss": None}, "missing_iss"),
        ({"iss": "someone-else"}, "issuer_not_allowed"),
    ],
    ids=["no_exp", "no_sub", "no_iss", "foreign_iss"],
)
def test_observe_mode_counts_what_strict_policy_would_reject_without_rejecting(
    tokens, semantics, override, reason, caplog
):
    token = _encode(_claims(**override))
    with caplog.at_level(logging.WARNING, logger="sahool.security.access_tokens"):
        payload = tokens.decode_access_token(
            token, SECRET, algorithm="HS256", claim_semantics=semantics, site="svc:fn"
        )
    assert payload.get("tenant_id") == "t1"  # قُبِل كما كان
    assert tokens.would_reject_counts() == {"svc:fn": {reason: 1}}
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "svc:fn" in logged and reason in logged
    assert token not in logged and "user-1" not in logged  # لا توكن ولا قيمة مطالبة


def test_observe_mode_counts_a_missing_audience_jose_used_to_accept_silently(tokens):
    token = _encode(_claims(aud=None))
    tokens.decode_access_token(
        token, SECRET, algorithm="HS256", claim_semantics="python-jose", site="s"
    )
    assert tokens.would_reject_counts() == {"s": {"missing_aud": 1}}


def test_pyjwt_semantics_keep_rejecting_a_missing_audience(tokens):
    with pytest.raises(_invalid()):
        tokens.decode_access_token(
            _encode(_claims(aud=None)), SECRET, algorithm="HS256", backend="pyjwt", site="s"
        )


@pytest.mark.parametrize("semantics", SEMANTICS)
def test_enforce_mode_turns_the_same_verdict_into_a_rejection(tokens, semantics, monkeypatch):
    monkeypatch.setenv(tokens.CLAIM_POLICY_ENV, "enforce")
    with pytest.raises(_invalid()):
        tokens.decode_access_token(
            _encode(_claims(exp=None)),
            SECRET,
            algorithm="HS256",
            claim_semantics=semantics,
            site="s",
        )
    assert tokens.would_reject_counts() == {"s": {"missing_exp": 1}}


@pytest.mark.parametrize("value", ["", "observe", "ENFORCED", "on", "1"])
def test_anything_but_explicit_enforce_observes(tokens, monkeypatch, value):
    monkeypatch.setenv(tokens.CLAIM_POLICY_ENV, value)
    assert tokens.claim_policy_mode() == "observe"


# ── الثقب الحقيقيّ: video-processor بلا JWT_SECRET ─────────────────────────────


def test_video_processor_rejects_a_token_forged_with_an_empty_key(monkeypatch):
    import asyncio

    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", "development")
    service_module.purge_generic_modules()
    try:
        module = service_module.load_service_main(
            str(ROOT / "services" / "video-processor"), required_attrs=("app", "_get_current_user")
        )
    finally:
        service_module.purge_generic_modules()

    forged = forge_hs256(_claims(tenant_id="victim-tenant"), b"")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(module._get_current_user(creds))
    assert exc.value.status_code == 401
