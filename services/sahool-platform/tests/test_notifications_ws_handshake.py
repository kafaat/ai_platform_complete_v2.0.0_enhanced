"""notifications WS handshake — behavioral contract + static regression guard.

The bug this pins: the endpoint used to ``close(1008)`` *before* ``accept()`` whenever the URL
carried no ``?token=``. A pre-accept close surfaces in the browser as a 1006 abnormal close, which
the frontend (FE-10: token never in the URL) reads as a failure and retries — an infinite reconnect
loop. The token also only came from the URL, so the FE-10 client (token in the first ``auth`` frame)
was never authenticated, and no ``auth_ok`` was ever sent, so the FE-09 outbox gate stayed locked.

The fixed contract (matches frontend/src/services/websocket.ts):
  1. accept FIRST, always (no close-before-accept).
  2. token from the first ``{"type":"auth","token":<JWT>}`` frame (primary, FE-10) OR the
     ``Sec-WebSocket-Protocol: sahool-bearer, <JWT>`` channel (clean fallback). NO URL ``?token=``.
  3. single verification path — get_current_user (the one JWT verifier).
  4. explicit ``{"type":"auth_ok"}`` ack (unlocks FE-09), then ``subscribed``, then ping→pong.
  5. auth failure ⇒ a clean 1008 close AFTER accept (bounded FE retries, not an infinite loop).

Behavioral tests monkeypatch get_current_user (independently tested) to exercise the handshake FSM
without JWT internals. No DB, no network.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
API_DIR = SERVICE_ROOT / "api"
for p in (SERVICE_ROOT, API_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

pytestmark = pytest.mark.unit

import api.main  # noqa: E402,F401 — تهيئة api.main قبل استيراد الموجِّه
from api.routers import notifications as notif  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

WS_URL = "/api/v1/notifications/ws"
_TENANT = "11111111-1111-1111-1111-111111111111"


def _fake_get_current_user(authorization: str | None = None):
    """يقبل التوكن الصحيح فقط ويردّ كائناً يحمل tenant_id (ما يستخدمه المعالِج)."""
    if authorization == "Bearer good":
        return types.SimpleNamespace(tenant_id=_TENANT)
    raise HTTPException(status_code=401, detail="invalid token")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(notif, "get_current_user", _fake_get_current_user)
    return TestClient(api.main.app)


# 1 — القناة المفضّلة: أوّل إطار auth ⇒ accept ثمّ auth_ok ثمّ subscribed ثمّ pong.
def test_first_frame_auth_admits_and_acks(client):
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "auth", "token": "good"})
        assert ws.receive_json() == {"type": "auth_ok"}  # FE-09 gate unlock
        sub = ws.receive_json()
        assert sub["type"] == "subscribed" and sub["tenant_id"] == _TENANT
        ws.send_json({"type": "ping"})
        assert ws.receive_json() == {"type": "pong"}  # heartbeat


# 2 — توكن غير صالح في أوّل إطار ⇒ قُبِلت القناة (لا إغلاق قبل accept) ثمّ أُغلقت 1008.
def test_bad_token_is_accepted_then_closed_1008_not_before_accept(client):
    with client.websocket_connect(WS_URL) as ws:  # يدخل السياق ⇒ accept نجح
        ws.send_json({"type": "auth", "token": "wrong"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008  # إغلاق سياسة نظيف بعد accept


# 3 — أوّل إطار ليس auth ⇒ لا توكن ⇒ إغلاق 1008 (fail-closed، حتميّ بلا مهلة).
def test_non_auth_first_frame_is_rejected(client):
    with client.websocket_connect(WS_URL) as ws:
        ws.send_json({"type": "ping"})  # ليس إطار مصادقة
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


# 4 — لا إطار خلال المهلة ⇒ إغلاق 1008 (نُقصّر المهلة كي لا ننتظر 10s).
def test_auth_timeout_closes_1008(client, monkeypatch):
    monkeypatch.setattr(notif, "_WS_AUTH_TIMEOUT_SECONDS", 0.2)
    with client.websocket_connect(WS_URL) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()  # لا نُرسل شيئاً — تنقضي المهلة
    assert exc.value.code == 1008


# 5 — القناة البديلة النظيفة: Sec-WebSocket-Protocol "sahool-bearer, <JWT>" ⇒ admit، والصدى صحيح.
def test_subprotocol_channel_admits(client):
    with client.websocket_connect(WS_URL, subprotocols=["sahool-bearer", "good"]) as ws:
        assert ws.accepted_subprotocol == "sahool-bearer"  # الصدى الدلاليّ لا التوكن
        assert ws.receive_json() == {"type": "auth_ok"}
        assert ws.receive_json()["type"] == "subscribed"


# 6 — القناة البديلة بتوكن خاطئ ⇒ إغلاق 1008 (نفس مسار التحقّق الواحد).
def test_subprotocol_bad_token_closed(client):
    with client.websocket_connect(WS_URL, subprotocols=["sahool-bearer", "nope"]) as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 1008


# ── حارس انحدار ساكن: accept قبل close، لا توكن في الـURL، إقرار auth_ok حاضر ──────────
def test_static_guard_accept_before_close_no_url_token():
    import inspect

    src = inspect.getsource(notif.notifications_ws)
    # accept يسبق أيّ close(1008) — لا إغلاق قبل accept (سبب حلقة إعادة الاتّصال).
    i_accept = src.find("accept(")
    i_close = src.find("close(code=1008")
    assert i_accept != -1 and i_close != -1 and i_accept < i_close, (
        "notifications_ws يجب أن يقبل (accept) قبل أيّ إغلاق 1008 — الإغلاق قبل accept "
        "يُنتِج 1006 في المتصفّح ويُطلق حلقة إعادة اتّصال (FE-10)."
    )
    # إقرار FE-09 حاضر.
    assert "auth_ok" in src, "يجب إرسال إطار auth_ok (يفكّ بوّابة الصندوق الصادر FE-09)."
    # لا توكن في الـURL: لا معامل استعلام token على التوقيع، ولا استعمال Query.
    sig = inspect.signature(notif.notifications_ws)
    assert list(sig.parameters) == ["websocket"], (
        "توقيع notifications_ws يجب أن يقتصر على websocket — لا معامل token في الـURL "
        "(توكن الـURL يتسرّب إلى سجلّات الوصول)."
    )
    mod_src = inspect.getsource(notif)
    assert "Query(" not in mod_src, "أُزيل توكن ?token= من الـURL — لا يُعاد عبر Query."
