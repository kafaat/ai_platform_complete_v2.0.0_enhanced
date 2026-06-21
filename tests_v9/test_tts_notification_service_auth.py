"""وحدات أمنيّة: توحيد مصادقة tts/notification + عزل ذاكرة tts بالمستأجِر.

يغطّي الفجوات المُتحقَّق منها:
  (أ) tts يقبل X-Agent-Token صالحاً، يرفض الخاطئ/الغائب، ويظلّ يقبل JWT aud=sahool.
  (ب) مفتاح الذاكرة يختلف باختلاف المستأجِر (لا تسميم/تسريب عابر للمستأجرين).
  (ج) Cache-Control = private (لا تخزين عامّ في وسطاء/CDN مشتركة).
  (د) وكيل الإشعارات يُرسل رأس X-Agent-Token (لا Bearer) إلى tts.
  (هـ) WebSocket يرفض حين غياب/بطلان إطار المصادقة (auth-frame).

اختبارات منطق صرف (بلا خدمات): نرقّع edge_tts غير المتوفّر في بيئة الوحدات
الخفيفة كي نُحمّل وحدة tts ونمارس دوالّها فعليّاً. لا Redis/شبكة.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import types

import pytest
from jose import jwt

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JWT_SECRET = "test_secret_min_32_chars_for_sahool_v9"
AGENT_TOKEN = "test-agent-shared-secret-0001"


# ── تحميل وحدة tts مع ترقيع edge_tts (غير متوفّر في بيئة الوحدات) ─────────────
# تُحمَّل الوحدة مرّة واحدة فقط: prometheus يرفض تكرار تسجيل المقاييس، وإعادة
# الاستيراد تُكرّر سلسلة الوقت. السرّ يُقرأ وقت النداء داخل الوحدة فالـmonkeypatch
# على البيئة يكفي لتغيير السلوك بين الاختبارات دون إعادة تحميل.
_TTS_MOD = None


def _load_tts(monkeypatch):
    global _TTS_MOD
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", AGENT_TOKEN)

    if _TTS_MOD is not None:
        return _TTS_MOD

    if "edge_tts" not in sys.modules:
        stub = types.ModuleType("edge_tts")

        class _Communicate:  # pragma: no cover - لا يُستدعى في هذه الاختبارات
            def __init__(self, *a, **k):
                pass

            async def stream(self):
                if False:
                    yield {}

        stub.Communicate = _Communicate
        sys.modules["edge_tts"] = stub

    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    spec = importlib.util.spec_from_file_location(
        "sahool_tts_main", os.path.join(ROOT, "services/tts-service/main.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sahool_tts_main"] = mod
    spec.loader.exec_module(mod)
    _TTS_MOD = mod
    return mod


def _jwt_for(tenant_id: str = "t1", iss: str = "sahool-auth") -> str:
    return jwt.encode(
        {"sub": "user-1", "iss": iss, "tenant_id": tenant_id, "aud": "sahool"},
        JWT_SECRET,
        algorithm="HS256",
    )


# ── (أ) مصادقة tts: X-Agent-Token + JWT، fail-closed ─────────────────────────
def test_agent_token_valid_accepts_matching_secret(monkeypatch):
    tts = _load_tts(monkeypatch)
    assert tts._agent_token_valid(AGENT_TOKEN) is True
    assert tts._agent_token_valid("wrong") is False
    assert tts._agent_token_valid(None) is False
    assert tts._agent_token_valid("") is False


def test_agent_token_fail_closed_when_secret_unset(monkeypatch):
    """بلا SAHOOL_AGENT_TOKEN مضبوط (التطوير/CI) ⇒ مسار توكن الخدمة مرفوض دوماً."""
    tts = _load_tts(monkeypatch)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "")
    # حتى لو أرسل المهاجم سلسلة فارغة مطابقة، لا يُقبل (لا باب بمفتاح فارغ).
    assert tts._agent_token_valid("") is False
    assert tts._agent_token_valid("anything") is False


@pytest.mark.asyncio
async def test_get_current_user_accepts_x_agent_token(monkeypatch):
    tts = _load_tts(monkeypatch)
    payload = await tts.get_current_user(creds=None, x_agent_token=AGENT_TOKEN)
    assert payload["iss"] == "sahool-service"
    assert payload["tenant_id"] == "__service__"


@pytest.mark.asyncio
async def test_get_current_user_rejects_wrong_agent_token(monkeypatch):
    tts = _load_tts(monkeypatch)
    with pytest.raises(tts.HTTPException) as exc:
        await tts.get_current_user(creds=None, x_agent_token="wrong-secret")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_absent_credentials(monkeypatch):
    tts = _load_tts(monkeypatch)
    with pytest.raises(tts.HTTPException) as exc:
        await tts.get_current_user(creds=None, x_agent_token=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_still_accepts_jwt_aud_sahool(monkeypatch):
    tts = _load_tts(monkeypatch)
    from fastapi.security import HTTPAuthorizationCredentials

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_jwt_for("tenant-9"))
    payload = await tts.get_current_user(creds=creds, x_agent_token=None)
    assert payload["tenant_id"] == "tenant-9"
    assert payload["iss"] == "sahool-auth"


@pytest.mark.asyncio
async def test_get_current_user_rejects_unknown_issuer(monkeypatch):
    tts = _load_tts(monkeypatch)
    from fastapi.security import HTTPAuthorizationCredentials

    creds = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=_jwt_for("t1", iss="evil")
    )
    with pytest.raises(tts.HTTPException) as exc:
        await tts.get_current_user(creds=creds, x_agent_token=None)
    assert exc.value.status_code == 401


# ── (ب) مفتاح الذاكرة معزول بالمستأجِر ───────────────────────────────────────
def test_cache_key_differs_across_tenants(monkeypatch):
    tts = _load_tts(monkeypatch)
    a = tts._cache_key("tenantA", "نصّ", "yemeni_male", "+0%", "+0Hz", "+0%")
    b = tts._cache_key("tenantB", "نصّ", "yemeni_male", "+0%", "+0Hz", "+0%")
    assert a != b, "مفتاح الذاكرة يجب أن يختلف باختلاف المستأجِر"
    # نفس المستأجِر/المدخلات ⇒ مفتاح ثابت (determinism)
    assert a == tts._cache_key("tenantA", "نصّ", "yemeni_male", "+0%", "+0Hz", "+0%")
    # المستأجِر جزء صريح من نطاق المفتاح
    assert ":tenantA:" in a and ":tenantB:" in b


def test_cache_key_empty_tenant_normalized(monkeypatch):
    tts = _load_tts(monkeypatch)
    k = tts._cache_key("", "نصّ", "yemeni_male", "+0%", "+0Hz", "+0%")
    assert k.startswith("sahool:tts:_:")


# ── (ج) Cache-Control = private (مصدريّ، يغطّي مساري HIT/MISS) ────────────────
def test_cache_control_is_private_not_public():
    src = open(
        os.path.join(ROOT, "services/tts-service/main.py"), encoding="utf-8"
    ).read()
    assert "Cache-Control" in src
    assert "public" not in src.split("Cache-Control")[1][:60], (
        "أصل TTS لكلّ مستأجِر يجب ألّا يكون public"
    )
    # كلّ ظهور لـCache-Control يجب أن يكون private
    for chunk in src.split('"Cache-Control":')[1:]:
        head = chunk[:40]
        assert "private" in head, f"Cache-Control غير private: {head!r}"
        assert "public" not in head, f"Cache-Control لا يزال public: {head!r}"


# ── (د) وكيل الإشعارات يُرسل X-Agent-Token (لا Bearer) إلى tts ────────────────
def test_notification_sends_x_agent_token_source():
    src = open(
        os.path.join(ROOT, "agents/notification/agent.py"), encoding="utf-8"
    ).read()
    block = src[src.index("async def send_tts_voice") :]
    block = block[: block.index("async def send_telegram")]
    assert '"X-Agent-Token"' in block, "نداء tts لا يُرسل رأس X-Agent-Token"
    # لا حاملة Bearer فعليّة في رؤوس النداء (نتجاهل ذكر الكلمة في التعليق).
    assert 'f"Bearer {tts_token}"' not in block, (
        "نداء tts لا يزال يستخدم حاملة Bearer (الاعتماد الخاطئ)"
    )
    assert '"Authorization"' not in block, "نداء tts لا يزال يبني رأس Authorization"


@pytest.mark.skipif(
    importlib.util.find_spec("httpx") is None, reason="httpx غير متاح في بيئة الوحدات الخفيفة"
)
@pytest.mark.asyncio
async def test_notification_tts_call_sends_agent_token_header(monkeypatch):
    """سلوكيّ: send_tts_voice يبني الرأس X-Agent-Token == SAHOOL_AGENT_TOKEN فعليّاً."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    # نرقّع التبعيّات الثقيلة لوكيل الإشعارات كي يُستورَد في بيئة الوحدات.
    for name in ("asyncpg", "nats", "nats.aio", "nats.aio.client", "nats.js"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["nats.aio.client"].Client = object  # type: ignore[attr-defined]
    sys.modules["nats.js"].JetStreamContext = object  # type: ignore[attr-defined]

    import httpx

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", AGENT_TOKEN)
    monkeypatch.setenv("TTS_URL", "http://tts-test:8000")

    spec = importlib.util.spec_from_file_location(
        "sahool_notif_agent", os.path.join(ROOT, "agents/notification/agent.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sahool_notif_agent"] = mod
    spec.loader.exec_module(mod)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["X-Agent-Token"] = request.headers.get("X-Agent-Token")
        captured["Authorization"] = request.headers.get("Authorization")
        return httpx.Response(200, content=b"\x00\x01audio")

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: real_async_client(transport=httpx.MockTransport(handler)),
    )

    ok = await mod.send_tts_voice("مرحبا", telegram_chat_id=123, voice="yemeni_male")
    assert ok is True
    assert captured["X-Agent-Token"] == AGENT_TOKEN
    assert captured["Authorization"] is None, "يجب ألّا يُرسَل توكن الوكيل كحاملة Bearer"


# ── (هـ) WebSocket: رفض حين غياب/بطلان إطار المصادقة ─────────────────────────
def test_ws_no_query_token_param_source():
    """تأكيد مصدريّ: مسار ?token= أُزيل — التوقيع لم يعُد يقبل token من الـquery."""
    src = open(
        os.path.join(ROOT, "agents/notification/agent.py"), encoding="utf-8"
    ).read()
    sig = src[src.index("async def ws_notifications") : src.index("async def ws_notifications") + 120]
    assert "token: str" not in sig, "WS لا يزال يقرأ token من الـquery"


@pytest.mark.asyncio
async def test_ws_rejects_missing_and_invalid_auth_frame(monkeypatch):
    """سلوكيّ: WS يقبل الاتصال ثمّ يُغلق (1008) إن غاب/بطل إطار auth الأوّل."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    for name in ("asyncpg", "nats", "nats.aio", "nats.aio.client", "nats.js"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["nats.aio.client"].Client = object  # type: ignore[attr-defined]
    sys.modules["nats.js"].JetStreamContext = object  # type: ignore[attr-defined]

    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    spec = importlib.util.spec_from_file_location(
        "sahool_notif_agent_ws", os.path.join(ROOT, "agents/notification/agent.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sahool_notif_agent_ws"] = mod
    spec.loader.exec_module(mod)

    class FakeWS:
        def __init__(self, first_frame):
            self._first = first_frame
            self.accepted = False
            self.closed = None

        async def accept(self):
            self.accepted = True

        async def receive_json(self):
            if isinstance(self._first, Exception):
                raise self._first
            return self._first

        async def close(self, code=1000, reason=""):
            self.closed = (code, reason)

        async def send_json(self, data):
            pass

    # 1) إطار غير auth ⇒ إغلاق 1008، ولم يُسجَّل أيّ اتّصال
    ws = FakeWS({"type": "ping"})
    await mod.ws_notifications(ws)
    assert ws.accepted is True
    assert ws.closed is not None and ws.closed[0] == 1008
    assert mod.manager.total_connections == 0

    # 2) إطار auth بتوكن باطل ⇒ إغلاق 1008
    ws2 = FakeWS({"type": "auth", "token": "not-a-valid-jwt"})
    await mod.ws_notifications(ws2)
    assert ws2.closed is not None and ws2.closed[0] == 1008
    assert mod.manager.total_connections == 0

    # 3) لا إطار إطلاقاً (مهلة) ⇒ إغلاق 1008
    ws3 = FakeWS(TimeoutError())
    await mod.ws_notifications(ws3)
    assert ws3.closed is not None and ws3.closed[0] == 1008
