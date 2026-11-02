"""مِسبار HTTP على تطبيقَي الإنتاج الحقيقيّين (auth · local-ai-rag) بلا خدمات حيّة.

لماذا (تدقيق 2026-11-01 Q1/Q2): خطوة CI الحاجبة ``pytest -m security`` كانت تفكّ توكنات
مساعِد الاختبار بـPyJWT نفسها (تختبر المكتبة لا كود الإنتاج)، واختباراتها الخمسة عبر HTTP
تنادي ``127.0.0.1:8120/8203`` فتتخطّى **دائماً** في CI (لا خدمات هناك)، وتُقرأ خضراء.

هنا يُحمَّل ``main.py`` الحقيقيّ لكلّ خدمة ويُخدَم عبر ``TestClient`` (بلا lifespan ⇒ بلا
Postgres/Redis/Ollama)، مع مزيّفات في الذاكرة للمسبح وRedis فقط. فالتحقّق من التوكن،
والقفل بعد المحاولات، وربط معامل SQL هي **شيفرة الإنتاج نفسها**.

كلّ خدمة في عمليّة فرعيّة مستقلّة: اسما ``main`` و``routers`` عامّان عبر ٢٤ خدمة
(نمط #570)، فالتحميل في عمليّة pytest المشتركة يُعرّض لنجاحٍ كاذب على وحدة خدمة أخرى.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# ≥32 حرفاً — كلا التطبيقين يرفضان سرّ HS256 أقصر (fail-closed).
PROBE_JWT_SECRET = "probe_secret_min_32_chars_for_sahool_security"

_COMMON = r"""
import base64, json, sys, time, types, uuid

import jwt

SECRET = sys.argv[1]


def _b64(obj):
    raw = json.dumps(obj, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def claims(**over):
    now = int(time.time())
    out = {
        "sub": "7", "email": "probe@sahool.ye", "role": "farmer", "full_name": "probe",
        "tenant_id": "b3ee640f-e0a0-4455-abe3-dfb8e5fdf122", "jti": str(uuid.uuid4()),
        "iss": "sahool-auth", "aud": "sahool", "iat": now, "nbf": now, "exp": now + 3600,
    }
    out.update(over)
    return out


def alg_none_token():
    # توكن «alg=none» بلا توقيع — هجوم الخلط الكلاسيكيّ.
    return _b64({"alg": "none", "typ": "JWT"}) + "." + _b64(claims()) + "."


def wrong_secret_token():
    return jwt.encode(claims(), "attacker_secret_also_at_least_32_chars!", algorithm="HS256")


def bearer(tok):
    return {"Authorization": "Bearer " + tok}
"""

_AUTH_SCRIPT = (
    _COMMON
    + r"""
import asyncio
import bcrypt
import main
from fastapi.testclient import TestClient

assert main.__file__.replace("\\", "/").endswith("services/auth/main.py"), main.__file__

PASSWORD = "Correct-Pass!2026"
HASH = bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt(4)).decode()
EMAIL = "probe@sahool.ye"
INJECTION_EMAIL = "admin'--@sahool.ye"


class FakeRedis:
    def __init__(self):
        self.kv, self.sets = {}, {}

    async def incr(self, k):
        self.kv[k] = int(self.kv.get(k, 0)) + 1
        return self.kv[k]

    async def expire(self, k, ttl):
        return True

    async def exists(self, k):
        return int(k in self.kv)

    async def ttl(self, k):
        return 900

    async def setex(self, k, ttl, v):
        self.kv[k] = v

    async def get(self, k):
        return self.kv.get(k)

    async def delete(self, *ks):
        for k in ks:
            self.kv.pop(k, None)
            self.sets.pop(k, None)

    async def sadd(self, k, *v):
        self.sets.setdefault(k, set()).update(v)

    async def smembers(self, k):
        return set(self.sets.get(k, set()))


class Conn:
    def __init__(self, log):
        self.log = log

    async def execute(self, sql, *args):
        self.log.append((sql, args))
        return "INSERT 0 1"

    async def fetchrow(self, sql, *args):
        self.log.append((sql, args))
        if "FROM users WHERE email" in sql and args and args[0] == EMAIL:
            return {
                "id": 7, "email": EMAIL, "password_hash": HASH, "role": "farmer",
                "full_name": "probe", "tenant_id": "b3ee640f-e0a0-4455-abe3-dfb8e5fdf122",
                "active": True, "mfa_enabled": False, "mfa_secret": None,
                "encrypted_mfa_secret": None, "mfa_failed_attempts": 0, "mfa_locked_until": None,
            }
        return None

    async def fetchval(self, sql, *args):
        self.log.append((sql, args))
        return None


class Acquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *exc):
        return False


class Pool:
    def __init__(self):
        self.log = []

    def acquire(self):
        return Acquire(Conn(self.log))


def fresh():
    main._pool, main._redis = Pool(), FakeRedis()
    # بلا ``with``: لا lifespan ⇒ لا Postgres/Redis حقيقيّان.
    return TestClient(main.app, raise_server_exceptions=False)


out = {}
c = fresh()
out["me_no_token"] = c.get("/v1/auth/me").status_code
out["me_alg_none"] = c.get("/v1/auth/me", headers=bearer(alg_none_token())).status_code
out["me_wrong_secret"] = c.get("/v1/auth/me", headers=bearer(wrong_secret_token())).status_code
out["me_foreign_issuer"] = c.get(
    "/v1/auth/me", headers=bearer(jwt.encode(claims(iss="evil"), SECRET, algorithm="HS256"))
).status_code
issued, _jti = main.create_access_token(7, EMAIL, "farmer", "probe", "t-1")
issued_claims = jwt.decode(issued, options={"verify_signature": False})
out["issued_header_alg"] = jwt.get_unverified_header(issued)["alg"]
out["issued_has_jti"] = len(str(issued_claims.get("jti", ""))) > 10
out["issued_has_nbf"] = "nbf" in issued_claims
out["me_issued_token"] = c.get("/v1/auth/me", headers=bearer(issued)).status_code
# إبطال الـjti في Redis ⇒ التوكن نفسه مرفوض (شيفرة الإنتاج تقرأ القائمة السوداء).
asyncio.run(main.revoke_jti(issued_claims["jti"], issued_claims["exp"]))
out["me_revoked_token"] = c.get("/v1/auth/me", headers=bearer(issued)).status_code

c = fresh()
r = c.post("/v1/auth/login", json={"email": EMAIL, "password": "WrongPass123!"})
out["login_wrong_password"] = r.status_code
r = c.post("/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
out["login_ok"] = r.status_code
tok = r.json().get("access_token") if r.status_code == 200 else ""
out["me_after_login"] = c.get("/v1/auth/me", headers=bearer(tok)).status_code if tok else None

c = fresh()
out["login_injection_not_email"] = c.post(
    "/v1/auth/login", json={"email": "' OR '1'='1", "password": "anything"}
).status_code
r = c.post("/v1/auth/login", json={"email": INJECTION_EMAIL, "password": "anything"})
out["login_injection_in_valid_email"] = r.status_code
user_queries = [(s, a) for s, a in main._pool.log if "FROM users WHERE email" in s]
out["injection_bound_as_parameter"] = bool(user_queries) and all(
    "$1" in s and INJECTION_EMAIL not in s and a == (INJECTION_EMAIL,) for s, a in user_queries
)

c = fresh()
out["lockout_sequence"] = [
    c.post("/v1/auth/login", json={"email": EMAIL, "password": "Wrong123!"}).status_code
    for _ in range(main.MAX_LOGIN_ATTEMPTS + 2)
]
# القفل يحجب حتى كلمة المرور الصحيحة — وإلّا فهو عدّاد لا قفل.
out["login_correct_while_locked"] = c.post(
    "/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}
).status_code
out["max_login_attempts"] = main.MAX_LOGIN_ATTEMPTS
print(json.dumps(out))
"""
)

# حزم LangChain ثقيلة وغير لازمة لحارس المصادقة؛ تُستبدَل بأسماء فارغة قبل الاستيراد.
_RAG_SCRIPT = (
    _COMMON
    + r"""
for name, attrs in {
    "langchain_community": (),
    "langchain_community.document_loaders": ("PyPDFLoader", "TextLoader"),
    "langchain_core": (),
    "langchain_core.documents": ("Document",),
    "langchain_ollama": ("ChatOllama", "OllamaEmbeddings"),
    "langchain_qdrant": ("QdrantVectorStore",),
    "langchain_text_splitters": ("RecursiveCharacterTextSplitter",),
}.items():
    mod = types.ModuleType(name)
    for attr in attrs:
        setattr(mod, attr, type(attr, (), {}))
    sys.modules[name] = mod

import main
from fastapi.testclient import TestClient

assert main.__file__.replace("\\", "/").endswith("services/local-ai-rag/main.py"), main.__file__

c = TestClient(main.app, raise_server_exceptions=False)
body = {"question": "What is NDVI?"}
out = {
    "query_no_token": c.post("/v1/query", json=body).status_code,
    "query_alg_none": c.post("/v1/query", json=body, headers=bearer(alg_none_token())).status_code,
    "query_wrong_secret": c.post(
        "/v1/query", json=body, headers=bearer(wrong_secret_token())
    ).status_code,
    "query_foreign_issuer": c.post(
        "/v1/query",
        json=body,
        headers=bearer(jwt.encode(claims(iss="evil"), SECRET, algorithm="HS256")),
    ).status_code,
    # شاهدٌ موجب: توكن صالح يعبر الحارس فيصل إلى «النماذج قيد التحميل» (503) لا 401.
    "query_valid_token": c.post(
        "/v1/query", json=body, headers=bearer(jwt.encode(claims(), SECRET, algorithm="HS256"))
    ).status_code,
}
print(json.dumps(out))
"""
)


# ``edge_tts`` مزوّدٌ خارجيّ اختياريّ وغير مُثبَّت في طبقة الوحدة؛ يُستبدَل باسمٍ فارغ.
# بلا ``PLATFORM_API_URL`` تبقى السياسة ``local_only`` بلا أيّ طلب شبكة.
_TTS_SCRIPT = (
    _COMMON
    + r"""
sys.modules.setdefault("edge_tts", types.ModuleType("edge_tts"))
import main
from fastapi.testclient import TestClient

assert main.__file__.replace("\\", "/").endswith("services/tts-service/main.py"), main.__file__

c = TestClient(main.app, raise_server_exceptions=False)
body = {"text": "test", "voice": "yemeni_male"}
out = {}
for path in ("/v1/tts/synthesize", "/v1/tts/stream"):
    out[path + ":no_token"] = c.post(path, json=body).status_code
    out[path + ":alg_none"] = c.post(path, json=body, headers=bearer(alg_none_token())).status_code
    out[path + ":wrong_secret"] = c.post(
        path, json=body, headers=bearer(wrong_secret_token())
    ).status_code
# شاهدٌ موجب: توكن صالح يعبر الحارس فيبلغ قرار السياسة (503 لا مزوّد محلّيّ) لا 401.
out["/v1/tts/synthesize:valid_token"] = c.post(
    "/v1/tts/synthesize",
    json=body,
    headers=bearer(jwt.encode(claims(), SECRET, algorithm="HS256")),
).status_code
print(json.dumps(out))
"""
)


def _run(script: str, service_dir: str) -> dict:
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "JWT_SECRET": PROBE_JWT_SECRET,
        "JWT_PRIVATE_KEY": "",
        "JWT_PUBLIC_KEY": "",
        "SAHOOL_ENV": "development",
        "SAHOOL_ACCESS_TOKEN_CLAIM_POLICY": "observe",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "PLATFORM_API_URL": "",
        "XTTS_ENABLE": "0",
    }
    proc = subprocess.run(  # noqa: S603 — مفسّر الاختبار نفسه وسكربت ثابت
        [sys.executable, "-c", script, PROBE_JWT_SECRET],
        cwd=ROOT / service_dir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    # فشل الاستيراد أو التحميل **فشلٌ** لا تخطٍّ: هذا هو الصنف الذي يُصلحه الملفّ.
    assert proc.returncode == 0, (
        f"مِسبار {service_dir} انهار (rc={proc.returncode}):\n{proc.stderr[-3000:]}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


def probe_auth() -> dict:
    return _run(_AUTH_SCRIPT, "services/auth")


def probe_rag() -> dict:
    return _run(_RAG_SCRIPT, "services/local-ai-rag")


def probe_tts() -> dict:
    return _run(_TTS_SCRIPT, "services/tts-service")
