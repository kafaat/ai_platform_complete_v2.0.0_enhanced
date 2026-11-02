"""S16 (تدقيق 2026-11-01) — أربعة أجزاء في خدمة auth، كلٌّ بشاهدٍ يحمرّ على origin/main.

(a) سياسة كلمة مرور واحدة: كانت ثلاث نسخ متباينة — الاستعادة بلا رمز خاصّ، والتغيير بلا
    أيّ فحص — فأضعفها يغلب. الآن ``mfa_crypto.enforce_password_policy`` في كلّ نموذج.
(b) رمز الاستعادة لمرّة واحدة: كان GET ثمّ DELETE بعد التحديث، فطلبان متزامنان نجحا معاً.
(c) تعداد الحسابات بالتوقيت: الدخول لمستخدم مجهول/معطَّل تخطّى bcrypt، وطلب الاستعادة
    لبريدٍ موجود انتظر SMTP داخل الطلب.
(d) ``SAHOOL_ENV=prod`` عطّلت تصليب auth بصمت (المقارنة كانت ``== "production"`` حرفيّاً).

لا اتّصال قاعدة وهميّ: تُرقَّع **دوالّ** الحدّ (``_load_login_row`` · ``_lookup_user_id`` ·
``_store_password_hash``) لا الاتّصال.
"""

from __future__ import annotations

import ast
import asyncio
import sys
from pathlib import Path

import bcrypt
import pytest

_REAL_CHECKPW = bcrypt.checkpw
pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
AUTH_DIR = ROOT / "services" / "auth"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from service_module import load_service_main  # noqa: E402

STRONG = "Str0ng!pass"
WEAK = {
    "no_special": "Password12",
    "no_upper": "password1!",
    "no_digit": "Password!!",
    "too_short": "Pa1!",
}


@pytest.fixture
def auth():
    return load_service_main(str(AUTH_DIR), required_attrs=("app", "PasswordResetConfirm"))


def _router(name: str):
    return sys.modules[f"routers.{name}"]


def _request(path: str):
    from starlette.requests import Request

    return Request(
        {"type": "http", "method": "POST", "path": path, "headers": [], "client": ("1.2.3.4", 1)}
    )


# ── (a) سياسة واحدة ──────────────────────────────────────────────────────────
_MODELS = [
    ("RegisterRequest", "password", {"email": "a@example.com", "full_name": "Ab"}),
    ("PasswordResetConfirm", "new_password", {"token": "t"}),
    ("ChangePasswordRequest", "new_password", {"current_password": "old"}),
    ("InvitationAcceptRequest", "password", {"token": "x" * 16, "full_name": "Ab"}),
]


@pytest.mark.parametrize("weak", sorted(WEAK))
@pytest.mark.parametrize(("model", "field", "extra"), _MODELS, ids=[m[0] for m in _MODELS])
def test_every_password_setting_model_rejects_the_same_weak_passwords(
    auth, model, field, extra, weak
):
    from pydantic import ValidationError

    cls = getattr(auth, model)
    assert cls(**extra, **{field: STRONG})  # الكلمة القويّة تمرّ في كلّ مسار
    with pytest.raises(ValidationError):
        cls(**extra, **{field: WEAK[weak]})


def test_no_password_setting_model_is_left_without_the_shared_policy():
    """حارس بنيويّ: أيّ نموذج جديد بحقل ``password``/``new_password`` يجب أن يطبّق السياسة.

    ``LoginRequest`` مُستثنى: لا يضع كلمة مرور، وفرضُ السياسة عليه يقفل حسابات قديمة.
    """
    tree = ast.parse((AUTH_DIR / "main.py").read_text(encoding="utf-8"))
    missing = []
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
        fields = {
            s.target.id
            for s in cls.body
            if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
        } & {"password", "new_password"}
        if not fields or cls.name == "LoginRequest":
            continue
        guarded = set()
        for fn in (n for n in cls.body if isinstance(n, ast.FunctionDef)):
            calls = {
                c.func.id
                for c in ast.walk(fn)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
            }
            if "enforce_password_policy" not in calls:
                continue
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "field_validator":
                    guarded |= {a.value for a in dec.args if isinstance(a, ast.Constant)}
        if fields - guarded:
            missing.append(f"{cls.name}: {sorted(fields - guarded)}")
    assert missing == [], missing


# ── (b) رمز الاستعادة لمرّة واحدة ────────────────────────────────────────────
class _ResetRedis:
    """Redis في الذاكرة: ``get`` يتنازل عن الحلقة بعد القراءة (نافذة السباق الحقيقيّة)،
    و``getdel`` عمليّة واحدة بلا ``await`` داخلها — كما في Redis."""

    def __init__(self, kv):
        self.kv = dict(kv)

    async def get(self, key):
        value = self.kv.get(key)
        await asyncio.sleep(0)
        return value

    async def delete(self, *keys):
        return sum(1 for k in keys if self.kv.pop(k, None) is not None)

    async def getdel(self, key):
        return self.kv.pop(key, None)


def test_two_concurrent_resets_with_one_token_cannot_both_succeed(auth, monkeypatch):
    from fastapi import HTTPException

    router = _router("password_reset")
    stored: list[int] = []

    async def store(user_id, hashed):
        stored.append(user_id)

    async def noop(*a, **k):
        return None

    monkeypatch.setattr(auth, "_redis", _ResetRedis({"sahool:reset:tok": "7"}))
    monkeypatch.setattr(auth, "BCRYPT_ROUNDS", 4)
    monkeypatch.setattr(auth, "revoke_all_user_sessions", noop)
    monkeypatch.setattr(auth, "audit_log", noop)
    monkeypatch.setattr(router, "_store_password_hash", store)

    async def race():
        req = auth.PasswordResetConfirm(token="tok", new_password=STRONG)
        return await asyncio.gather(
            router.confirm_password_reset(req),
            router.confirm_password_reset(req),
            return_exceptions=True,
        )

    results = asyncio.run(race())
    ok = [r for r in results if isinstance(r, dict)]
    rejected = [r for r in results if isinstance(r, HTTPException)]
    assert len(ok) == 1 and len(rejected) == 1, results
    assert rejected[0].status_code == 400
    assert stored == [7], f"كلمة المرور كُتبت {len(stored)} مرّة بالرمز نفسه"
    assert "sahool:reset:tok" not in auth._redis.kv


def test_reset_token_consumer_is_the_atomic_single_use_seam():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "s16_session_tokens", AUTH_DIR / "session_tokens.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    redis = _ResetRedis({"sahool:reset:abc": "9"})

    async def twice():
        return await mod.consume_reset_token(redis, "abc"), await mod.consume_reset_token(
            redis, "abc"
        )

    assert asyncio.run(twice()) == ("9", None)


# ── (c) لا تعداد بالتوقيت ────────────────────────────────────────────────────
def _login(auth, monkeypatch, row, password="Wr0ng!pass"):
    from fastapi import HTTPException
    from starlette.responses import Response

    router = _router("session")
    verified: list[bytes] = []
    real_checkpw = _REAL_CHECKPW  # الأصل قبل أيّ ترقيع — لا spy فوق spy

    def spy(pw, hashed):
        verified.append(hashed)
        return real_checkpw(pw, hashed)

    async def load(email):
        return row

    monkeypatch.setattr(auth, "_redis", None)  # الحدّ/القفل يعودان مبكّراً بلا Redis
    monkeypatch.setattr(auth, "BCRYPT_ROUNDS", 4)
    monkeypatch.setattr(auth.bcrypt, "checkpw", spy)
    monkeypatch.setattr(router, "_load_login_row", load)
    req = auth.LoginRequest(email="who@example.com", password=password)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(router.login(req, _request("/v1/auth/login"), Response()))
    return exc.value, verified


def _user(auth, active=True):
    hashed = auth.bcrypt.hashpw(STRONG.encode(), auth.bcrypt.gensalt(4)).decode()
    return {"id": 1, "password_hash": hashed, "active": active, "mfa_enabled": False}


@pytest.mark.parametrize("case", ["unknown", "inactive"])
def test_login_does_one_bcrypt_verify_of_equal_cost_for_unknown_or_inactive(
    auth, monkeypatch, case
):
    row = None if case == "unknown" else _user(auth, active=False)
    exc, verified = _login(auth, monkeypatch, row, password=STRONG)
    wrong, _ = _login(auth, monkeypatch, _user(auth), password="Wr0ng!pass")
    assert len(verified) == 1, f"{case}: bcrypt لم يُستدعَ ⇒ ردّ أسرع يكشف الحساب"
    assert verified[0].startswith(b"$2b$04$"), verified[0][:7]  # كلفة BCRYPT_ROUNDS نفسها
    assert (exc.status_code, exc.detail) == (wrong.status_code, wrong.detail)


def test_reset_request_defers_all_per_account_work_until_after_the_response(auth, monkeypatch):
    from fastapi import BackgroundTasks

    router = _router("password_reset")
    sent: list[str] = []

    class _Counter:
        def inc(self):
            return None

    async def send(email, token):
        sent.append(email)

    async def noop(*a, **k):
        return None

    async def setex(*a):
        sent.append("setex")

    monkeypatch.setattr(auth, "_redis", type("R", (), {"setex": staticmethod(setex)})())
    monkeypatch.setattr(auth, "check_ip_rate", noop)
    monkeypatch.setattr(auth, "RESET_COUNTER", _Counter())
    monkeypatch.setattr(auth, "send_reset_email", send)
    monkeypatch.setattr(auth, "audit_log", noop)

    def run(user_id):
        async def lookup(email):
            return user_id

        monkeypatch.setattr(router, "_lookup_user_id", lookup)
        tasks = BackgroundTasks()
        req = auth.PasswordResetRequest(email="who@example.com")
        body = asyncio.run(
            router.request_password_reset(req, _request("/v1/auth/password-reset/request"), tasks)
        )
        in_request = list(sent)
        asyncio.run(tasks())
        return body, in_request, len(tasks.tasks)

    known = run(5)
    sent.clear()
    unknown = run(None)
    assert known[0] == unknown[0], "الردّ يختلف بين بريدٍ موجود ومجهول"
    assert known[1] == [], f"عملٌ خاصّ بالحساب داخل الطلب يكشفه بالتوقيت: {known[1]}"
    assert (known[2], unknown[2]) == (1, 0)
    assert sent == [], "البريد المجهول لا يُرسَل له شيء"


# ── (d) تطبيع SAHOOL_ENV ─────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "environ", "expected"),
    [
        ("production", {}, "production"),
        ("prod", {}, "production"),
        (" PROD ", {}, "production"),
        ("development", {}, "non-production"),
        ("staging", {"RAILWAY_ENVIRONMENT_ID": "x"}, "non-production"),
        ("", {"RAILWAY_ENVIRONMENT_ID": "x"}, "non-production"),
        (None, {}, "non-production"),
        ("prdo", {}, "non-production"),  # مجهول محلّيّاً: لا يكسر التطوير
        ("prdo", {"RAILWAY_ENVIRONMENT_ID": "x"}, "production"),  # مجهول منشوراً: fail-closed
        ("live", {"KUBERNETES_SERVICE_HOST": "10.0.0.1"}, "production"),
    ],
)
def test_resolve_sahool_env(raw, environ, expected):
    if str(AUTH_DIR) not in sys.path:
        sys.path.insert(0, str(AUTH_DIR))
    import mfa_crypto

    assert mfa_crypto.resolve_sahool_env(raw, environ) == expected


@pytest.mark.parametrize("value", ["prod", "production"])
def test_prod_alias_turns_on_every_auth_hardening_gate(auth, monkeypatch, value):
    import mfa_crypto

    for k in ("RAILWAY_ENVIRONMENT_ID", "RAILWAY_ENVIRONMENT", "KUBERNETES_SERVICE_HOST"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("ENFORCE_ADMIN_STEPUP_MFA", raising=False)
    monkeypatch.setenv("SAHOOL_ENV", value)
    assert auth._is_production() is True  # RS256 إلزاميّ · Redis إلزاميّ
    assert auth._admin_stepup_required() is True
    assert mfa_crypto._is_production() is True  # رفض مفتاح MFA المشتقّ


def test_cors_production_flag_comes_from_the_normalised_env():
    """مشتقّ cors_policy يقبل ``production`` حرفيّاً فقط؛ auth يمرّر قراره المُطبَّع."""
    tree = ast.parse((AUTH_DIR / "main.py").read_text(encoding="utf-8"))
    calls = [
        c
        for c in ast.walk(tree)
        if isinstance(c, ast.Call) and getattr(c.func, "id", "") == "parse_cors_origins"
    ]
    assert calls, "parse_cors_origins غاب من main.py"
    for call in calls:
        kw = {k.arg: k.value for k in call.keywords}
        assert "production" in kw and "resolve_sahool_env" in ast.unparse(kw["production"])
