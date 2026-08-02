"""WS-C.1b Zero-Legacy — راتشِت ET0 #3: أداة MCP `calculate_hargreaves_et0` تفوّض
لمنتج ET0 الكنسيّ (محرّك الطقس) بلا نواة محلّيّة.

قسمان:
- **حارس انحدار ساكن** (بلا استيراد): مصدر `weather_server.py` لا يحوي ثوابت/صيغة
  Hargreaves ولا نواة ET0 محلّيّة، ويستدعي نقطة المحرّك الكنسيّة — فلا تعود نواة ثانية.
- **قبول سلوكيّ** (mock لـhttpx، يتخطّى بصدق إن تعذّر الاستيراد): تعيين المنتج الكنسيّ
  لشكل الأداة · إرسال توكن الخدمة · timeout/اتّصال → unavailable · 5xx → unavailable ·
  et0 مفقود → unavailable · لا احتياط Hargreaves محلّيّ · إسقاط ra صريح.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_MCP_DIR = Path(__file__).resolve().parent.parent / "services" / "mcp_servers"
_SRC = (_MCP_DIR / "weather_server.py").read_text(encoding="utf-8")


# ─── حارس انحدار ساكن (لا يحتاج استيراد الوحدة) ─────────────────────────────


def test_no_local_hargreaves_constants_or_kernel():
    # ثوابت Hargreaves-Samani (0.0023 معامل + 17.8 إزاحة) يجب ألّا تظهر — لا نواة محلّيّة.
    assert "0.0023" not in _SRC, "Hargreaves coefficient must not live in the MCP server"
    assert "17.8" not in _SRC, "Hargreaves temperature offset must not live in the MCP server"
    # لا حساب إشعاع خارج الغلاف Ra محلّيّ (acos/sqrt للصيغة) — كان قلب النواة المحذوفة.
    assert "math.acos" not in _SRC and "math.sqrt" not in _SRC
    assert "import math" not in _SRC, "no math kernel needed once ET0 is delegated"


def test_delegates_to_canonical_engine_endpoint():
    # إثبات إيجابيّ للتفويض: الأداة تستدعي نقطة منتج ET0 الكنسيّة في محرّك الطقس.
    assert "/v1/weather/agro/et0" in _SRC
    assert "weather-engine" in _SRC


# ─── قبول سلوكيّ (mock لـhttpx) ─────────────────────────────────────────────


# حمّل تبعيات MCP الحقيقية من موضعها الإنتاجي. ممنوع إنشاء ModuleType باسم
# shared.oauth_middleware لأن ذلك يلوّث sys.modules أثناء collection ويجعل حراسة
# المصادقة رهينة ترتيب الملفات الأبجدي.
def _install_real_module(name: str, path: Path) -> None:
    existing = sys.modules.get(name)
    if existing is not None:
        origin = Path(getattr(existing, "__file__", "")).resolve()
        assert origin == path.resolve(), f"{name} shadowed by {origin}"
        return
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


_install_real_module("shared.oauth_middleware", _MCP_DIR / "shared" / "oauth_middleware.py")
_install_real_module("shared.streamable_http", _MCP_DIR / "shared" / "streamable_http.py")

# نُلحق مجلّد الخادم فيبقى shared.helpers الجذري متاحاً، بينما الوحدتان الحساستان
# أعلاه مثبتتان إلى ملفيهما الحقيقيين فقط.
if str(_MCP_DIR) not in sys.path:
    sys.path.append(str(_MCP_DIR))

try:
    import weather_server as ws  # noqa: E402
except Exception:  # noqa: BLE001 — تبعيّات الخادم غير متوفّرة في بيئة الوحدة الأدنى
    ws = None


class _FakeResp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _fake_client(*, status_code=200, payload=None, raise_exc=None, capture=None):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if capture is not None:
                capture.update(url=url, json=json, headers=headers)
            if raise_exc is not None:
                raise raise_exc
            return _FakeResp(status_code, payload or {})

    return _FakeClient


_ARGS = {
    "lat": 15.5,
    "lon": 45.0,
    "date": "2026-07-11",
    "t_max": 34.0,
    "t_min": 18.0,
    "solar_radiation": 22.0,
    "wind_speed": 2.0,
}


def _result_payload(res: dict) -> dict:
    return json.loads(res["content"][0]["text"])


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_canonical_product_mapped_and_ra_dropped(monkeypatch):
    monkeypatch.setattr(
        ws.httpx,
        "AsyncClient",
        _fake_client(
            payload={
                "et0_mm": 5.5,
                "method": "hargreaves_fallback",
                "quality_status": "degraded",
                "formula_version": "et0/fao56-pm/1.0.0",
            }
        ),
    )
    out = _result_payload(await ws._execute("calculate_hargreaves_et0", dict(_ARGS)))
    assert out["status"] == "ok"
    assert out["et0_mm_day"] == 5.5
    assert out["method"] == "hargreaves_fallback"
    assert out["quality_status"] == "degraded"
    assert out["source"] == "weather-engine"
    # ra_mj_m2_day أُسقِط صراحةً (لا مستهلك، كان وسيط النواة المحذوفة).
    assert "ra_mj_m2_day" not in out
    # t_mean/t_range حساب حسابيّ بسيط (ليس نواة ET0).
    assert out["t_mean_c"] == 26.0 and out["t_range_c"] == 16.0


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_service_identity_header_sent(monkeypatch):
    cap: dict = {}
    monkeypatch.setenv("SAHOOL_AGENT_TOKEN", "svc-tok-123")
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(payload={"et0_mm": 6.0}, capture=cap))
    await ws._execute("calculate_hargreaves_et0", dict(_ARGS))
    assert cap["headers"]["X-Agent-Token"] == "svc-tok-123"
    assert cap["headers"]["X-Service-Name"] == "sahool-weather-mcp"
    # يُرسِل حرارة اليوم للمحرّك (temp-only ⇒ Hargreaves داخل المحرّك)، لا يحسبها محلّيّاً.
    assert cap["json"]["t_max_c"] == 34.0 and cap["json"]["t_min_c"] == 18.0


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_transport_error_is_unavailable_not_local_calc(monkeypatch):
    monkeypatch.setattr(
        ws.httpx, "AsyncClient", _fake_client(raise_exc=ws.httpx.ConnectError("refused"))
    )
    out = _result_payload(await ws._execute("calculate_hargreaves_et0", dict(_ARGS)))
    assert out["status"] == "unavailable"
    assert out["reason"] == "weather_engine_unavailable"
    assert out["et0_mm"] is None and out["method"] is None
    assert out["quality_status"] == "insufficient"
    assert out["limitations"]


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_engine_5xx_is_unavailable(monkeypatch):
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(status_code=503, payload={}))
    out = _result_payload(await ws._execute("calculate_hargreaves_et0", dict(_ARGS)))
    assert out["status"] == "unavailable"
    assert out["reason"] == "weather_engine_error"
    assert out["et0_mm"] is None


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_missing_et0_in_product_is_unavailable(monkeypatch):
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(payload={"method": "insufficient"}))
    out = _result_payload(await ws._execute("calculate_hargreaves_et0", dict(_ARGS)))
    assert out["status"] == "unavailable"
    assert out["reason"] == "insufficient_inputs"
    assert out["et0_mm"] is None


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_invalid_input_is_client_error_not_unavailable(monkeypatch):
    # t_min>t_max خطأ عميل (400)، متمايز عن تعذّر التبعيّة (unavailable).
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(payload={"et0_mm": 5.0}))
    bad = dict(_ARGS, t_min=40.0, t_max=30.0)
    with pytest.raises(ws.HTTPException) as exc:
        await ws._execute("calculate_hargreaves_et0", bad)
    assert exc.value.status_code == 400
