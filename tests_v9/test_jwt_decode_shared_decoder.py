"""شاهد ``JWT-DECODE-OUTSIDE-SHARED-SECURITY-01``: فكُّ توكن الوصول في موضعٍ واحد، بوضع مراقبة.

**ما يُثبته (أحمر على ``origin/main`` قبل الإصلاح، أخضر بعده):**

1. **المسح الثابت:** لا نداءَ فكّ JWT في ملفّات الإنتاج خارج ``shared/security/`` إلّا في
   قائمة سماحٍ صريحة مُعلَّلة (المُشغِّل مجمَّد بـGATE-01؛ ``auth`` مُصدِرٌ يُنقَل آخِراً)،
   وكلُّ ملفٍّ منقول يمرّ بـ``decode_access_token`` بخوارزميّةٍ واحدة مثبَّتة.
2. **السلوك:** المفكِّك المشترك يحفظ حكمَ كلّ خلفيّة (PyJWT/python-jose) ونوعَ خطئها، يرفض
   المفتاحَ الفارغ، ويعدّ ما كانت السياسةُ الأشدّ (exp/sub/aud/iss) سترفضه **دون رفضه**
   إلّا في وضع ``enforce`` (قرار المالك 2026-10-01، #1118: عدّادٌ قبل الفرض).
3. **ثقبٌ حقيقيّ أُغلق:** video-processor بلا ``JWT_SECRET`` كان يقبل توكناً موقَّعاً بمفتاحٍ
   فارغ (python-jose 3.5.0 يقبله)، فيُزوَّر أيُّ مستأجِر. الآن 401.
"""

from __future__ import annotations

import ast
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
    # المُصدِر: يُنقَل بعد قراءة عدّاد المستهلكين (قيدُ ترتيبٍ في سجلّ الفجوات).
    "services/auth/main.py": 2,
    "services/auth/routers/session.py": 1,
    # MCP: ``shared`` في شجرة التطوير هو ``services/mcp_servers/shared`` وحده (الدمجُ يحدث في
    # الصورة فقط)، فلا يُرى ``shared.security`` إلّا بدمج مسارَي الحزمة — وهو ما يمنعه عمداً
    # ``test_season_api_static.py::test_blob_store_immune_to_shared_package_shadow``. قرارٌ مستقلّ.
    "services/mcp_servers/market_server.py": 1,
    "services/mcp_servers/shared/oauth_middleware.py": 1,
    # tts-service/decision-service decode sites deferred to avoid overlap with the readiness
    # slice (توجيه المنسّق 2026-10-14: وكيلٌ آخر يعدّل الخدمتين الآن). decision-service بلا
    # نداء فكٍّ مباشر مقيس، فلا مدخل له هنا.
    "services/tts-service/main.py": 1,
}

MIGRATED = {
    "services/guardrails-engine/main.py": ("pyjwt", 2),
    "services/local-ai-rag/main.py": ("jose", 1),
    "services/odoo-bridge/main.py": ("jose", 1),
    "services/sahool-platform/api/chat_proxy_reference.py": ("pyjwt", 1),
    "services/sahool-platform/api/main.py": ("pyjwt", 1),
    "services/sahool-platform/api/routers/auth.py": ("pyjwt", 1),
    "services/supervisor-agent/main.py": ("pyjwt", 1),
    "services/vegetation-analysis-service/vegetation_runtime.py": ("pyjwt", 1),
    "services/video-processor/main.py": ("jose", 1),
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
    backend, expected = MIGRATED[rel]
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
        assert isinstance(kw.get("backend"), ast.Constant) and kw["backend"].value == backend
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


def _encode(backend, claims, key=SECRET, alg="HS256"):
    if backend == "pyjwt":
        import jwt

        return jwt.encode(claims, key, algorithm=alg)
    from jose import jwt

    return jwt.encode(claims, key, algorithm=alg)


def _invalid(backend):
    if backend == "pyjwt":
        import jwt

        return jwt.InvalidTokenError
    from jose import JWTError

    return JWTError


BACKENDS = ("pyjwt", "jose")


@pytest.mark.parametrize("backend", BACKENDS)
def test_valid_token_is_accepted_and_not_counted(tokens, backend):
    payload = tokens.decode_access_token(
        _encode(backend, _claims()), SECRET, algorithm="HS256", backend=backend, site="u"
    )
    assert payload["sub"] == "user-1"
    assert tokens.would_reject_counts() == {}


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize(
    "case", ["signature", "audience", "expired", "header_alg_mismatch", "unpinned_algorithm"]
)
def test_the_backends_native_rejections_are_preserved(tokens, backend, case):
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
    token = _encode(backend, claims, alg=enc_alg)
    with pytest.raises(_invalid(backend)):
        tokens.decode_access_token(token, key, algorithm=alg, backend=backend, site="u")


@pytest.mark.parametrize("backend", BACKENDS)
def test_an_empty_verification_key_is_rejected(tokens, backend):
    forged = _encode("jose", _claims(), key="")
    with pytest.raises(_invalid(backend)):
        tokens.decode_access_token(forged, "", algorithm="HS256", backend=backend, site="u")


def test_python_jose_itself_accepts_an_empty_key_which_is_why_the_guard_exists():
    """المعايرة: لو أصلح python-jose هذا، يصير الحارسُ دفاعاً عميقاً لا إغلاقاً لثقب."""
    from jose import jwt

    forged = jwt.encode(_claims(), "", algorithm="HS256")
    assert jwt.decode(forged, "", algorithms=["HS256"], audience="sahool")["sub"] == "user-1"


@pytest.mark.parametrize("backend", BACKENDS)
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
    tokens, backend, override, reason, caplog
):
    token = _encode(backend, _claims(**override))
    with caplog.at_level(logging.WARNING, logger="sahool.security.access_tokens"):
        payload = tokens.decode_access_token(
            token, SECRET, algorithm="HS256", backend=backend, site="svc:fn"
        )
    assert payload.get("tenant_id") == "t1"  # قُبِل كما كان
    assert tokens.would_reject_counts() == {"svc:fn": {reason: 1}}
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "svc:fn" in logged and reason in logged
    assert token not in logged and "user-1" not in logged  # لا توكن ولا قيمة مطالبة


def test_observe_mode_counts_a_missing_audience_jose_used_to_accept_silently(tokens):
    token = _encode("jose", _claims(aud=None))
    tokens.decode_access_token(token, SECRET, algorithm="HS256", backend="jose", site="s")
    assert tokens.would_reject_counts() == {"s": {"missing_aud": 1}}


@pytest.mark.parametrize("backend", BACKENDS)
def test_enforce_mode_turns_the_same_verdict_into_the_backends_rejection(
    tokens, backend, monkeypatch
):
    monkeypatch.setenv(tokens.CLAIM_POLICY_ENV, "enforce")
    with pytest.raises(_invalid(backend)):
        tokens.decode_access_token(
            _encode(backend, _claims(exp=None)),
            SECRET,
            algorithm="HS256",
            backend=backend,
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
    from jose import jwt

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

    forged = jwt.encode(_claims(tenant_id="victim-tenant"), "", algorithm="HS256")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(module._get_current_user(creds))
    assert exc.value.status_code == 401
