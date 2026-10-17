"""شاهد ``DEP-PYTHON-JOSE-HMAC-PUBKEY-CONFUSION-01``: python-jose خارج الشجرة، والحكمُ محفوظ.

python-jose <=3.5.0 يقبل مفتاحاً عامّاً (DER بلا غلاف PEM) سرّاً لـHMAC (CVE-2026-85394،
GHSA-3qf3-8w2g-rqmx) بلا إصدارٍ مُصلِح، ويجرّ ``ecdsa`` (PYSEC-2026-1325، بلا إصلاح). كلاهما
كان مُعفىً مؤقّتاً في ``config/security_exceptions.json`` حتّى 2026-11-05/2026-11-30. المخرجُ
الوحيد كان الإزالة: PyJWT وحدها، بخوارزميّةٍ واحدة مثبَّتة لكلّ موضع.

**(أ) الغياب — أحمر على ``origin/main@5472740e``:** لا ملفّ Python يستورد ``jose``، ولا ملفّ
متطلّبات يُدرج ``python-jose`` أو ``ecdsa``، وكلُّ صورةٍ كانت تحمل python-jose تُعلن
``PyJWT[crypto]`` (مزوّد RSA؛ بدونه يُرفَض كلُّ RS256 — درسُ المنصّة/المُشغِّل/الغطاء).

**(ب) التكافؤ السلوكيّ:** RS256 صالح يُقبَل؛ توكن HS256 موقَّعٌ بالمفتاح العامّ (هجومُ الخلط
نفسُه، PEM وDER) يُرفَض؛ الجمهورُ الخطأ · المُصدِرُ الخطأ · المنتهي · ``alg=none`` · المفتاحُ
الفارغ تُرفَض — في المفكِّك المشترك، وفي ``verify_access_token``، وفي المُصدِر ``auth`` نفسِه.
ودلالةُ python-jose في المواضع التي كانت عليه محفوظة: ``aud`` غائب يُقبَل (ويُعَدّ)،
و``iat`` في المستقبل لا يُرفَض. وتوقيعُ FCM يُنتج JWT يتحقّق بالمفتاح العامّ.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from packaging.requirements import InvalidRequirement, Requirement

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SECRET = "unit-test-secret-0123456789-abcdefghijklmnopqrstuvwxyz-0123456789-ABCDEF"
FORBIDDEN_DISTRIBUTIONS = frozenset({"python-jose", "ecdsa"})
SKIP_DIRS = frozenset(
    {".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache", ".ruff_cache"}
)

#: الصورُ التي كانت تحمل python-jose[cryptography] على main@5472740e — كلٌّ يتحقّق من RS256
#: أو يوقّع به (FCM)، فيلزمه مزوّدُ RSA مُعلَناً في ملفّه هو لا عبوريّاً من بيئة CI.
FORMER_JOSE_REQUIREMENTS = (
    "agents/notification/requirements.txt",
    "requirements-dev.txt",
    "services/auth/requirements.txt",
    "services/local-ai-rag/requirements.txt",
    "services/odoo-bridge/requirements.txt",
    "services/rag-retrieval/requirements.txt",
    "services/tts-service/requirements.txt",
    "services/video-processor/requirements.txt",
    "tests_v9/requirements-test.txt",
)


# ── (أ) الغياب ────────────────────────────────────────────────────────────────


def _tracked(pattern: str) -> list[Path]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", pattern],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
        paths = [ROOT / p for p in out.decode("utf-8").split("\0") if p]
        if paths:
            return [p for p in paths if p.is_file()]
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for path in ROOT.rglob(pattern.rsplit("/", 1)[-1]):
        if not SKIP_DIRS.intersection(path.relative_to(ROOT).parts) and path.is_file():
            found.append(path)
    return found


def jose_imports_in_source(source: str) -> list[int]:
    """أسطرُ استيراد ``jose`` (بأيّ صيغة) — بالـAST، فالنصوصُ والتعليقات لا تُعَدّ."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(a.name == "jose" or a.name.startswith("jose.") for a in node.names):
                lines.append(node.lineno)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and (mod == "jose" or mod.startswith("jose.")):
                lines.append(node.lineno)
        elif isinstance(node, ast.Call) and node.args:
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            arg = node.args[0]
            if (
                name in {"importorskip", "import_module", "__import__"}
                and isinstance(arg, ast.Constant)
                and isinstance(arg.value, str)
                and (arg.value == "jose" or arg.value.startswith("jose."))
            ):
                lines.append(node.lineno)
    return lines


def forbidden_requirements_in_text(text: str) -> list[str]:
    hits = []
    for raw in text.splitlines():
        spec = raw.split("#", 1)[0].strip()
        if not spec or spec.startswith("-"):
            continue
        try:
            name = Requirement(spec).name
        except InvalidRequirement:
            continue
        if name.lower().replace("_", "-") in FORBIDDEN_DISTRIBUTIONS:
            hits.append(spec)
    return hits


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from jose import jwt\n", [1]),
        ("import jose.jwt as j\n", [1]),
        ("from jose.exceptions import JWTError\n", [1]),
        ("import pytest\npytest.importorskip('jose')\n", [2]),
        ("import jwt\ns = 'from jose import jwt'\n# from jose import jwt\n", []),
        ("from .jose import x\n", []),
    ],
    ids=["from", "dotted_alias", "submodule", "importorskip", "string_comment", "relative"],
)
def test_the_import_detector_is_not_vacuous(source, expected):
    assert jose_imports_in_source(source) == expected


def test_the_requirement_detector_is_not_vacuous():
    text = "fastapi==1\npython-jose[cryptography]>=3.4.0  # x\n# ecdsa\nECDSA==0.19.2\n-c x.txt\n"
    assert forbidden_requirements_in_text(text) == [
        "python-jose[cryptography]>=3.4.0",
        "ECDSA==0.19.2",
    ]


def test_no_python_file_imports_python_jose():
    me = Path(__file__).resolve()
    offenders = {}
    for path in _tracked("*.py"):
        if path.resolve() == me:
            continue
        try:
            source = path.read_text(encoding="utf-8")
            lines = jose_imports_in_source(source)
        except (SyntaxError, UnicodeDecodeError, ValueError):
            continue
        if lines:
            offenders[path.relative_to(ROOT).as_posix()] = lines
    assert not offenders, (
        "DEP-PYTHON-JOSE-HMAC-PUBKEY-CONFUSION-01: python-jose عاد — استعمل PyJWT عبر "
        f"shared/security/access_tokens.py: {offenders}"
    )


def test_no_requirements_file_lists_python_jose_or_ecdsa():
    offenders = {}
    for pattern in ("*requirements*.txt", "*requirements*.in", "constraints*.txt"):
        for path in _tracked(pattern):
            hits = forbidden_requirements_in_text(path.read_text(encoding="utf-8"))
            if hits:
                offenders[path.relative_to(ROOT).as_posix()] = hits
    assert not offenders, (
        "python-jose/ecdsa في ملفّ متطلّبات — ثغرتان بلا إصلاح (CVE-2026-85394، PYSEC-2026-1325): "
        f"{offenders}"
    )


@pytest.mark.parametrize("rel", FORMER_JOSE_REQUIREMENTS)
def test_each_former_jose_image_declares_pyjwt_with_its_rsa_provider(rel):
    reqs = []
    for raw in (ROOT / rel).read_text(encoding="utf-8").splitlines():
        spec = raw.split("#", 1)[0].strip()
        if spec and not spec.startswith("-"):
            reqs.append(Requirement(spec))
    pyjwt = [r for r in reqs if r.name.lower() == "pyjwt"]
    assert len(pyjwt) == 1, f"{rel}: PyJWT غير مُعلَن (أو مُعلَن مرّتين)"
    assert "crypto" in pyjwt[0].extras, f"{rel}: بلا [crypto] يُرفَض كلُّ RS256 في الصورة"
    pins = list(pyjwt[0].specifier)
    assert len(pins) == 1 and pins[0].operator == "==" and pins[0].version == "2.15.0", (
        f"{rel}: PyJWT مثبَّتٌ عند 2.15.0 كالمنصّة (يُغلق CVE-2026-101918 وما قبله)"
    )


def test_the_waivers_python_jose_needed_are_gone():
    """ما كان مُعفىً لأجل python-jose يُزال معه — إعفاءٌ بلا تبعيّة يُعمي البوّابة عن عودتها."""
    waivers = json.loads((ROOT / "config/security_exceptions.json").read_text(encoding="utf-8"))
    ids = {w.get("id") for w in waivers.get("waivers", [])}
    assert not ids & {"CVE-2026-85394", "PYSEC-2026-1325"}, ids
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "--ignore-vuln CVE-2026-85394" not in ci, (
        "python-jose أُزيل؛ إعفاءٌ بقي بعده يُعمي pip-audit عن عودته ثغرةً حيّة"
    )
    assert "--ignore-vuln PYSEC-2026-1325" not in ci, (
        "ecdsa كان عبوريّاً من python-jose وحده؛ بقاءُ إعفائه يُخفي عودته من مسارٍ آخر"
    )
    installs = [
        ln for ln in ci.splitlines() if "pip install" in ln and not ln.lstrip().startswith("#")
    ]
    assert not [ln for ln in installs if "python-jose" in ln], "CI ما زال يثبّت python-jose"


# ── (ب) التكافؤ السلوكيّ ───────────────────────────────────────────────────────


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def forge(claims: dict, *, alg: str, key: bytes | None) -> str:
    """توكن يُبنى يدويّاً كما يبنيه مهاجم: PyJWT يرفض توقيعَ HMAC بمفتاحٍ عامّ أو فارغ."""
    head = _b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = _b64(json.dumps(claims).encode())
    signing_input = f"{head}.{body}".encode()
    if key is None:  # alg=none
        return f"{head}.{body}."
    return f"{head}.{body}.{_b64(hmac.new(key, signing_input, hashlib.sha256).digest())}"


def _claims(**over):
    claims = {
        "sub": "user-1",
        "tenant_id": "t1",
        "iss": "sahool-auth",
        "aud": "sahool",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    for k, v in over.items():
        if v is None:
            claims.pop(k, None)
        else:
            claims[k] = v
    return claims


def _other_pair():
    return _make_pair()


@pytest.fixture(scope="module")
def rsa_pair():
    return _make_pair()


def _make_pair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public = key.public_key()
    public_pem = public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    public_der = public.public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private_pem, public_pem, public_der


@pytest.fixture
def tokens(monkeypatch):
    from shared.security import access_tokens

    monkeypatch.delenv(access_tokens.CLAIM_POLICY_ENV, raising=False)
    access_tokens.reset_would_reject_counts()
    yield access_tokens
    access_tokens.reset_would_reject_counts()


def _rs256(private_pem, claims):
    import jwt

    return jwt.encode(claims, private_pem, algorithm="RS256")


def _confusion_tokens(public_pem: str, public_der: bytes) -> dict[str, str]:
    return {
        "hs256_with_public_pem": forge(_claims(), alg="HS256", key=public_pem.encode()),
        "hs256_with_public_der": forge(_claims(), alg="HS256", key=public_der),
    }


def test_the_confusion_tokens_are_real_attack_tokens(rsa_pair):
    """تكذيبٌ ذاتيّ: التوكن المزوَّر يصحّ فعلاً تحت فاحصٍ ساذج يقبل HMAC بالمفتاح العامّ."""
    _, public_pem, public_der = rsa_pair
    for key, token in zip(
        (public_pem.encode(), public_der),
        _confusion_tokens(public_pem, public_der).values(),
        strict=True,
    ):
        head, body, sig = token.split(".")
        expected = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
        assert _b64(expected) == sig


SEMANTICS = ("pyjwt", "python-jose")


@pytest.mark.parametrize("semantics", SEMANTICS)
def test_rs256_token_is_accepted(tokens, rsa_pair, semantics):
    private_pem, public_pem, _ = rsa_pair
    payload = tokens.decode_access_token(
        _rs256(private_pem, _claims()),
        public_pem,
        algorithm="RS256",
        claim_semantics=semantics,
        site="parity",
    )
    assert payload["tenant_id"] == "t1"
    assert tokens.would_reject_counts() == {}


@pytest.mark.parametrize("semantics", SEMANTICS)
@pytest.mark.parametrize("variant", ["hs256_with_public_pem", "hs256_with_public_der"])
def test_hmac_signed_with_the_public_key_is_rejected(tokens, rsa_pair, semantics, variant):
    """هجومُ الخلط (CVE-2026-85394): الخوارزميّةُ مثبَّتة RS256، فالرأسُ HS256 لا يختار المفتاح."""
    import jwt

    _, public_pem, public_der = rsa_pair
    token = _confusion_tokens(public_pem, public_der)[variant]
    with pytest.raises(jwt.InvalidTokenError):
        tokens.decode_access_token(
            token, public_pem, algorithm="RS256", claim_semantics=semantics, site="parity"
        )


def test_pyjwt_refuses_a_pem_public_key_as_an_hmac_secret_even_if_a_site_pinned_hs256(rsa_pair):
    """دفاعٌ عميق: حتّى موضعٌ مُخطئ يثبّت HS256 بالمفتاح العامّ لا يقبل التوكن المزوَّر."""
    import jwt

    _, public_pem, public_der = rsa_pair
    token = _confusion_tokens(public_pem, public_der)["hs256_with_public_pem"]
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(token, public_pem, algorithms=["HS256"], audience="sahool")


@pytest.mark.parametrize("algorithm", [["HS256", "RS256"], "HS256,RS256", "none", "HS512"])
def test_only_a_single_pinned_algorithm_is_accepted(tokens, rsa_pair, algorithm):
    import jwt

    private_pem, public_pem, _ = rsa_pair
    with pytest.raises(jwt.InvalidTokenError):
        tokens.decode_access_token(
            _rs256(private_pem, _claims()), public_pem, algorithm=algorithm, site="parity"
        )


@pytest.mark.parametrize("semantics", SEMANTICS)
@pytest.mark.parametrize(
    "case", ["wrong_audience", "malformed_audience", "expired", "not_yet_valid", "alg_none"]
)
def test_invalid_tokens_are_rejected(tokens, rsa_pair, semantics, case):
    import jwt

    private_pem, public_pem, _ = rsa_pair
    now = int(time.time())
    token = {
        "wrong_audience": lambda: _rs256(private_pem, _claims(aud="another-service")),
        "malformed_audience": lambda: _rs256(private_pem, _claims(aud=["sahool", 7])),
        "expired": lambda: _rs256(private_pem, _claims(exp=now - 60)),
        "not_yet_valid": lambda: _rs256(private_pem, _claims(nbf=now + 600)),
        "alg_none": lambda: forge(_claims(), alg="none", key=None),
    }[case]()
    for key, alg in ((public_pem, "RS256"), (SECRET, "HS256")):
        with pytest.raises(jwt.InvalidTokenError):
            tokens.decode_access_token(
                token, key, algorithm=alg, claim_semantics=semantics, site="parity"
            )


def test_wrong_issuer_is_rejected_in_enforce_mode_and_counted_in_observe(
    tokens, rsa_pair, monkeypatch
):
    import jwt

    private_pem, public_pem, _ = rsa_pair
    token = _rs256(private_pem, _claims(iss="someone-else"))
    tokens.decode_access_token(token, public_pem, algorithm="RS256", site="parity")
    assert tokens.would_reject_counts() == {"parity": {"issuer_not_allowed": 1}}
    monkeypatch.setenv(tokens.CLAIM_POLICY_ENV, "enforce")
    with pytest.raises(jwt.InvalidTokenError):
        tokens.decode_access_token(token, public_pem, algorithm="RS256", site="parity")


@pytest.mark.parametrize("semantics", SEMANTICS)
def test_empty_key_is_rejected(tokens, semantics):
    import jwt

    with pytest.raises(jwt.InvalidTokenError, match="empty"):
        tokens.decode_access_token(
            forge(_claims(), alg="HS256", key=b""),
            "",
            algorithm="HS256",
            claim_semantics=semantics,
            site="parity",
        )


# ── دلالةُ python-jose المحفوظة (ما كان يقبله يُقبَل، وما كان يرفضه يُرفَض) ─────────


def test_python_jose_semantics_accept_a_missing_audience_and_count_it(tokens, rsa_pair):
    private_pem, public_pem, _ = rsa_pair
    payload = tokens.decode_access_token(
        _rs256(private_pem, _claims(aud=None)),
        public_pem,
        algorithm="RS256",
        claim_semantics="python-jose",
        site="parity",
    )
    assert payload["sub"] == "user-1"
    assert tokens.would_reject_counts() == {"parity": {"missing_aud": 1}}


def test_python_jose_semantics_do_not_reject_an_iat_in_the_future(tokens, rsa_pair):
    """python-jose لم يقارن ``iat`` بالساعة؛ PyJWT يقارنه — فانزياحُ ساعةٍ بين auth والمستهلك
    كان سيصير 401 جديدة. يُحفَظ في مواضع python-jose ويبقى في مواضع PyJWT."""
    import jwt

    private_pem, public_pem, _ = rsa_pair
    token = _rs256(private_pem, _claims(iat=int(time.time()) + 120))
    assert (
        tokens.decode_access_token(
            token, public_pem, algorithm="RS256", claim_semantics="python-jose", site="p"
        )["sub"]
        == "user-1"
    )
    with pytest.raises(jwt.ImmatureSignatureError):
        tokens.decode_access_token(token, public_pem, algorithm="RS256", site="p")


@pytest.mark.parametrize("semantics", SEMANTICS)
def test_a_non_integer_iat_is_rejected(tokens, semantics):
    import jwt

    token = jwt.encode(_claims(iat="yesterday"), SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        tokens.decode_access_token(
            token, SECRET, algorithm="HS256", claim_semantics=semantics, site="p"
        )


@pytest.mark.parametrize("semantics", SEMANTICS)
def test_an_audience_list_containing_sahool_is_accepted(tokens, semantics):
    import jwt

    token = jwt.encode(_claims(aud=["other", "sahool"]), SECRET, algorithm="HS256")
    assert tokens.decode_access_token(
        token, SECRET, algorithm="HS256", claim_semantics=semantics, site="p"
    )["aud"] == ["other", "sahool"]


# ── verify_access_token (notification · rag-retrieval) ────────────────────────


@pytest.fixture
def rs256_env(monkeypatch, rsa_pair):
    _, public_pem, _ = rsa_pair
    monkeypatch.setenv("JWT_PUBLIC_KEY", public_pem)
    monkeypatch.setenv("SAHOOL_ENV", "production")
    monkeypatch.delenv("SAHOOL_ALLOW_HS256_IN_PROD", raising=False)
    return rsa_pair


def test_verify_access_token_accepts_rs256(tokens, rs256_env):
    private_pem, _, _ = rs256_env
    assert tokens.verify_access_token(_rs256(private_pem, _claims()))["tenant_id"] == "t1"


@pytest.mark.parametrize(
    "case",
    [
        "hs256_with_public_pem",
        "hs256_with_public_der",
        "alg_none",
        "wrong_audience",
        "wrong_issuer",
        "expired",
        "missing_aud",
        "missing_exp",
    ],
)
def test_verify_access_token_rejects(tokens, rs256_env, case):
    private_pem, public_pem, public_der = rs256_env
    confusion = _confusion_tokens(public_pem, public_der)
    token = {
        "hs256_with_public_pem": lambda: confusion["hs256_with_public_pem"],
        "hs256_with_public_der": lambda: confusion["hs256_with_public_der"],
        "alg_none": lambda: forge(_claims(), alg="none", key=None),
        "wrong_audience": lambda: _rs256(private_pem, _claims(aud="x")),
        "wrong_issuer": lambda: _rs256(private_pem, _claims(iss="x")),
        "expired": lambda: _rs256(private_pem, _claims(exp=int(time.time()) - 60)),
        "missing_aud": lambda: _rs256(private_pem, _claims(aud=None)),
        "missing_exp": lambda: _rs256(private_pem, _claims(exp=None)),
    }[case]()
    with pytest.raises(ValueError):
        tokens.verify_access_token(token)


# ── المُصدِر: services/auth (توقيع + تحقّق، في عمليّةٍ معزولة) ──────────────────

_AUTH_SCRIPT = r"""
import asyncio, base64, hashlib, hmac, json, os, sys, time
import main
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

def b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

def forge(claims, alg, key):
    head = b64(json.dumps({"alg": alg, "typ": "JWT"}).encode())
    body = b64(json.dumps(claims).encode())
    if key is None:
        return f"{head}.{body}."
    sig = hmac.new(key, f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{b64(sig)}"

def outcome(token):
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    try:
        payload = asyncio.run(main.get_current_user(creds))
        return ["ok", payload.get("sub")]
    except HTTPException as exc:
        return [exc.status_code, str(exc.detail)[:40]]

import jwt
now = int(time.time())
pub = os.environ["JWT_PUBLIC_KEY"]
der = base64.b64decode(os.environ["PUBLIC_DER_B64"])
issued, _ = main.create_access_token(7, "t@sahool.ye", "farmer", "T", "tenant-1")
base = jwt.decode(issued, pub, algorithms=["RS256"], audience="sahool")
def signed(**over):
    claims = dict(base)
    for k, v in over.items():
        if v is None:
            claims.pop(k, None)
        else:
            claims[k] = v
    return main.jwt.encode(claims, main.JWT_SIGNING_KEY, algorithm="RS256")

rows = {
    "algorithm": main.JWT_ALGORITHM,
    "issued_header": jwt.get_unverified_header(issued),
    "issued": outcome(issued),
    "hs256_with_public_pem": outcome(forge(base, "HS256", pub.encode())),
    "hs256_with_public_der": outcome(forge(base, "HS256", der)),
    "alg_none": outcome(forge(base, "none", None)),
    "wrong_audience": outcome(signed(aud="another-service")),
    "wrong_issuer": outcome(signed(iss="someone-else")),
    "expired": outcome(signed(exp=now - 60)),
    "missing_aud_kept_from_python_jose": outcome(signed(aud=None)),
    "future_iat_kept_from_python_jose": outcome(signed(iat=now + 120, nbf=now - 1)),
}
main.JWT_VERIFY_KEY, main.JWT_ALGORITHM = "", "HS256"
rows["empty_key"] = outcome(forge(base, "HS256", b""))
print(json.dumps(rows))
"""


def test_the_auth_issuer_signs_with_pyjwt_and_keeps_its_verdicts(rsa_pair):
    private_pem, public_pem, public_der = rsa_pair
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "JWT_PRIVATE_KEY": private_pem,
        "JWT_PUBLIC_KEY": public_pem,
        "PUBLIC_DER_B64": base64.b64encode(public_der).decode(),
        "JWT_SECRET": "",
        "SAHOOL_ENV": "development",
    }
    env.pop("SAHOOL_ACCESS_TOKEN_CLAIM_POLICY", None)  # observe: حكمُ اليوم لا حكمُ ما بعد الفرض
    proc = subprocess.run(
        [sys.executable, "-c", _AUTH_SCRIPT],
        cwd=ROOT / "services/auth",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if proc.returncode != 0 and "ModuleNotFoundError" in proc.stderr:
        pytest.skip(f"auth deps missing: {proc.stderr.strip().splitlines()[-1]}")
    assert proc.returncode == 0, proc.stderr
    rows = json.loads(proc.stdout.strip().splitlines()[-1])
    assert rows["algorithm"] == "RS256"
    assert rows["issued_header"]["alg"] == "RS256"
    assert rows["issued"] == ["ok", "7"]
    for case in (
        "hs256_with_public_pem",
        "hs256_with_public_der",
        "alg_none",
        "wrong_audience",
        "expired",
        "empty_key",
    ):
        assert rows[case][0] == 401 and rows[case][1].startswith("Invalid token"), (case, rows)
    assert rows["wrong_issuer"] == [401, "Invalid token issuer"]
    # ما كان python-jose يقبله في auth يبقى مقبولاً (يُعَدّ ولا يُرفَض قبل قرار الفرض).
    assert rows["missing_aud_kept_from_python_jose"] == ["ok", "7"]
    assert rows["future_iat_kept_from_python_jose"] == ["ok", "7"]


# ── FCM: التوقيع بـPyJWT يتحقّق بالمفتاح العامّ ────────────────────────────────


def test_fcm_assertion_is_an_rs256_jwt_that_verifies_with_the_public_key(monkeypatch, rsa_pair):
    import jwt

    from shared import fcm

    private_pem, public_pem, _ = rsa_pair
    account = fcm.Credentials(
        "unit-project", "unit@unit-project.iam.gserviceaccount.com", private_pem
    )
    sent = {}

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "synthetic", "expires_in": 3600, "token_type": "Bearer"}

    class _Client:
        async def post(self, url, data):
            sent.update(url=url, **data)
            return _Response()

    monkeypatch.setattr(fcm, "_token_cache", None)
    assert asyncio.run(fcm._access_token(_Client(), account)) == "synthetic"
    assertion = sent["assertion"]
    assert jwt.get_unverified_header(assertion) == {"alg": "RS256", "typ": "JWT"}
    claims = jwt.decode(assertion, public_pem, algorithms=["RS256"], audience=fcm.TOKEN_URI)
    assert claims["iss"] == account.client_email and claims["scope"] == fcm.SCOPE
    assert claims["exp"] - claims["iat"] == 3600
    _, other_public_pem, _ = _other_pair()
    with pytest.raises(jwt.InvalidSignatureError):
        jwt.decode(assertion, other_public_pem, algorithms=["RS256"], audience=fcm.TOKEN_URI)
