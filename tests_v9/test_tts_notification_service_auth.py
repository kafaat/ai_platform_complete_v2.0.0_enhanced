"""وحدات أمنيّة: توحيد مصادقة tts/notification + عزل ذاكرة tts بالمستأجِر.

يغطّي الفجوات المُتحقَّق منها:
  (أ) tts يقبل X-Agent-Token صالحاً، يرفض الخاطئ/الغائب، ويظلّ يقبل JWT aud=sahool.
  (ب) مفتاح الذاكرة يختلف باختلاف المستأجِر (لا تسميم/تسريب عابر للمستأجرين).
  (ج) Cache-Control = private (لا تخزين عامّ في وسطاء/CDN مشتركة).
  (د) إشعارات الصوت تمرّر هوية المستخدم إلى سياسة TTS (لا هوية خدمة مشتركة).
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

from tests_v9.service_module import load_service_main

# تحميل وحدة tts يستورد fastapi (غير مثبّت في بيئة الوحدات بـCI) ⇒ تخطٍّ على مستوى
# الوحدة كي لا تفشل اختبارات تحتاج الخدمة وقت التشغيل، مطابقةً لبقيّة اختبارات الخدمة.
pytest.importorskip("fastapi")

pytestmark = [pytest.mark.unit, pytest.mark.security]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JWT_SECRET = "test_secret_min_32_chars_for_sahool_v9"
AGENT_TOKEN = "test-agent-shared-secret-0001"


# ── تحميل وحدة tts مع ترقيع edge_tts (غير متوفّر في بيئة الوحدات) ─────────────
# The canonical loader preserves same-service reuse and checks the path while
# isolating generic router modules from other service tests.


def _load_tts(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.delenv("JWT_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", AGENT_TOKEN)

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
    return load_service_main(
        os.path.join(ROOT, "services/tts-service"),
        required_attrs=("get_current_user", "_agent_token_valid", "_cache_key"),
    )


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

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=_jwt_for("t1", iss="evil"))
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
    # بعد تفكيك main.py إلى routers/، انتقل مُعالِج /v1/tts/synthesize (مع رؤوس
    # Cache-Control) إلى routers/tts.py. نمسح main.py + routers/*.py معاً عبر
    # المساعِد المُجمِّع كي يبقى المسح صحيحاً بلا إضعاف أيّ تأكيد (توسيع نطاق فقط).
    from tts_route_source import tts_combined_source

    src = tts_combined_source(ROOT)
    assert "Cache-Control" in src
    assert "public" not in src.split("Cache-Control")[1][:60], (
        "أصل TTS لكلّ مستأجِر يجب ألّا يكون public"
    )
    # كلّ ظهور لـCache-Control يجب أن يكون private
    for chunk in src.split('"Cache-Control":')[1:]:
        head = chunk[:40]
        assert "private" in head, f"Cache-Control غير private: {head!r}"
        assert "public" not in head, f"Cache-Control لا يزال public: {head!r}"


# ── (د) إشعار الصوت يحفظ هوية المستأجر ولا يتجاوز سياسة TTS بهوية خدمة ──────
def test_notification_sends_caller_identity_source():
    src = open(os.path.join(ROOT, "agents/notification/agent.py"), encoding="utf-8").read()
    block = src[src.index("async def send_tts_voice") :]
    block = block[: block.index("async def send_telegram")]
    assert '"Authorization": f"Bearer {caller_token}"' in block
    assert '"X-Agent-Token"' not in block
    assert '"SAHOOL_AGENT_TOKEN"' not in block


@pytest.mark.skipif(
    importlib.util.find_spec("httpx") is None, reason="httpx غير متاح في بيئة الوحدات الخفيفة"
)
@pytest.mark.asyncio
async def test_notification_tts_call_sends_caller_token_header(monkeypatch):
    """الناقل يمرّر هوية المستخدم: توكن الخدمة لا يتجاوز local-only."""
    import ast
    import logging

    import httpx

    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", AGENT_TOKEN)
    monkeypatch.setenv("TTS_URL", "http://tts-test:8000")
    # Execute the real production function without unrelated DB/NATS startup.
    tree = ast.parse(
        open(os.path.join(ROOT, "agents/notification/agent.py"), encoding="utf-8").read()
    )
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "send_tts_voice"
    )
    namespace = {
        "os": os,
        "httpx": httpx,
        "TG_TOKEN": "test-bot-token",
        "logger": logging.getLogger("test-notification-tts"),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), "agent.py", "exec"), namespace)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "tts-test":
            captured["X-Agent-Token"] = request.headers.get("X-Agent-Token")
            captured["Authorization"] = request.headers.get("Authorization")
            return httpx.Response(200, content=b"ID3audio", headers={"Content-Type": "audio/mpeg"})
        return httpx.Response(
            200,
            json={
                "ok": True,
                "result": {"message_id": 42, "chat": {"id": 123}, "voice": {"file_id": "voice-42"}},
            },
        )

    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **k: real_async_client(transport=httpx.MockTransport(handler)),
    )

    ok = await namespace["send_tts_voice"](
        "مرحبا", telegram_chat_id=123, voice="yemeni_male", caller_token="caller-jwt"
    )
    assert ok is True
    assert captured["X-Agent-Token"] is None
    assert captured["Authorization"] == "Bearer caller-jwt"


# ── (هـ) WebSocket: رفض حين غياب/بطلان إطار المصادقة ─────────────────────────
def test_ws_no_query_token_param_source():
    """تأكيد مصدريّ: مسار ?token= أُزيل — التوقيع لم يعُد يقبل token من الـquery."""
    src = open(os.path.join(ROOT, "agents/notification/agent.py"), encoding="utf-8").read()
    sig = src[
        src.index("async def ws_notifications") : src.index("async def ws_notifications") + 120
    ]
    assert "token: str" not in sig, "WS لا يزال يقرأ token من الـquery"


@pytest.mark.asyncio
async def test_ws_rejects_missing_and_invalid_auth_frame(monkeypatch):
    """سلوكيّ: WS يقبل الاتصال ثمّ يُغلق (1008) إن غاب/بطل إطار auth الأوّل."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    for name in ("asyncpg", "nats", "nats.aio", "nats.aio.client", "nats.js"):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setattr(sys.modules["nats.aio.client"], "Client", object, raising=False)
    monkeypatch.setattr(sys.modules["nats.js"], "JetStreamContext", object, raising=False)
    # Queue provisioning is outside this WebSocket authentication test. Isolate
    # that import rather than exposing an incomplete fake nats.js package to it.
    consumers = types.ModuleType("shared.notification_consumers")
    consumers.SUBSCRIPTIONS = ()
    consumers.queue_name = lambda name: name
    consumers.validate_queue = lambda name: name
    monkeypatch.setitem(sys.modules, "shared.notification_consumers", consumers)

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
