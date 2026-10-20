"""أداة MCP `get_historical_weather` تطلب التاريخ من مضيف أرشيف Open-Meteo.

كانت الأداة تبني ``f"{OPEN_METEO_URL}/archive"`` أي ``https://api.open-meteo.com/v1/archive``.
وفي خادم Open-Meteo يُسجَّل المسار ``/v1/archive`` على متحكّمٍ مضيفُه ``archive-api``
(``Sources/App/Controllers/ForecastapiController.swift``)، و``withApiParameter`` يرفض
أيّ مضيفٍ من ``open-meteo.com`` لا يبدأ بذلك المضيف بـ``Abort(.notFound)``
(``Sources/App/Helper/Vapor/ApiKeyManager.swift``). أي أنّ كلّ نداء تاريخيّ من الأداة
ينتهي بـ404. والمضيف الموثَّق ``archive-api.open-meteo.com``، وهو ما يستعمله محرّك
الطقس (``services/weather-service/open_meteo.py``: ``ARCHIVE_URL``).

قسمان:
- **ساكن** (بلا استيراد، يعمل في كلّ بيئة): الخادم يقرأ ``OPEN_METEO_ARCHIVE_URL``
  وافتراضيّه هو افتراضيّ محرّك الطقس نفسه، على مضيف الأرشيف.
- **سلوكيّ** (``httpx.AsyncClient`` مزيَّف، يتخطّى بصدق إن تعذّر الاستيراد): الأداة
  تطلب مضيف الأرشيف، وتحترم تجاوز البيئة، والتوقّع يبقى على ``api.open-meteo.com``.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parent.parent
_MCP_DIR = _ROOT / "services" / "mcp_servers"
_MCP_SERVER = _MCP_DIR / "weather_server.py"
_WEATHER_SERVICE = _ROOT / "services" / "weather-service" / "open_meteo.py"

_ARCHIVE_ENV = "OPEN_METEO_ARCHIVE_URL"
_ARCHIVE_HOST = "archive-api.open-meteo.com"


# ─── ساكن: افتراضيّ واحد لمضيف الأرشيف في الخدمتين ─────────────────────────


def _env_default(path: Path, env_name: str) -> str | None:
    """افتراضيّ ``os.getenv(env_name, <default>)`` في الملفّ، أو None إن لم يُقرأ المتغيّر.

    يقبل الافتراضيّ نصّاً حرفيّاً أو اسماً مُسنَداً إليه نصٌّ في مستوى الوحدة.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    module_strings: dict[str, str] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    module_strings[target.id] = node.value.value
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "getenv"
            and len(node.args) == 2
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == env_name
        ):
            continue
        default = node.args[1]
        if isinstance(default, ast.Constant) and isinstance(default.value, str):
            return default.value
        if isinstance(default, ast.Name):
            return module_strings.get(default.id)
    return None


def test_weather_service_archive_default_is_the_archive_host():
    default = _env_default(_WEATHER_SERVICE, _ARCHIVE_ENV)
    assert default is not None, "weather-service no longer reads OPEN_METEO_ARCHIVE_URL"
    assert urlsplit(default).netloc == _ARCHIVE_HOST


def test_mcp_server_reads_the_same_archive_env_with_the_same_default():
    mcp_default = _env_default(_MCP_SERVER, _ARCHIVE_ENV)
    assert mcp_default is not None, (
        "weather_server.py must read OPEN_METEO_ARCHIVE_URL for the history call"
    )
    assert mcp_default == _env_default(_WEATHER_SERVICE, _ARCHIVE_ENV)


# ─── سلوكيّ (httpx مزيَّف) ───────────────────────────────────────────────────


# حمّل تبعيات MCP الحقيقية من موضعها الإنتاجي (النمط نفسه في
# test_mcp_weather_et0_engine_delegation.py): لا ModuleType مزيّف باسم
# shared.oauth_middleware يلوّث sys.modules أثناء collection.
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

if str(_MCP_DIR) not in sys.path:
    sys.path.append(str(_MCP_DIR))

try:
    import weather_server as ws  # noqa: E402
except Exception:  # noqa: BLE001 — تبعيّات الخادم غير متوفّرة في بيئة الوحدة الأدنى
    ws = None


class _FakeResp:
    def __init__(self, payload: dict):
        self.status_code = 200
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


def _fake_client(calls: list[dict], payload: dict):
    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, params=None, timeout=None):
            calls.append({"url": url, "params": params})
            return _FakeResp(payload)

    return _FakeClient


_HIST_ARGS = {"lat": 15.35, "lon": 44.2, "start_date": "2024-01-01", "end_date": "2024-01-31"}
_DAILY = {"time": ["2024-01-01"], "temperature_2m_max": [24.1]}


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_historical_tool_requests_the_archive_host(monkeypatch):
    monkeypatch.delenv(_ARCHIVE_ENV, raising=False)
    calls: list[dict] = []
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(calls, {"daily": _DAILY}))

    res = await ws._execute("get_historical_weather", dict(_HIST_ARGS))

    assert len(calls) == 1
    url = urlsplit(calls[0]["url"])
    assert (url.scheme, url.netloc, url.path) == ("https", _ARCHIVE_HOST, "/v1/archive")
    params = calls[0]["params"]
    assert params["start_date"] == "2024-01-01" and params["end_date"] == "2024-01-31"
    assert params["latitude"] == 15.35 and params["longitude"] == 44.2
    out = json.loads(res["content"][0]["text"])
    assert out["daily"] == _DAILY and out["source"] == "Open-Meteo Historical"


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_historical_tool_honours_archive_env_override(monkeypatch):
    override = "http://evidence-wiremock:8080/open-meteo/v1/archive"
    monkeypatch.setenv(_ARCHIVE_ENV, override)
    calls: list[dict] = []
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(calls, {"daily": _DAILY}))

    await ws._execute("get_historical_weather", dict(_HIST_ARGS))

    assert [c["url"] for c in calls] == [override]


@pytest.mark.skipif(ws is None, reason="weather_server deps unavailable")
async def test_forecast_tool_stays_on_the_forecast_host(monkeypatch):
    # تجاوز مضيف الأرشيف لا يمسّ التوقّع: التوقّع يبقى على api.open-meteo.com/v1/forecast.
    monkeypatch.setenv(_ARCHIVE_ENV, "http://evidence-wiremock:8080/open-meteo/v1/archive")
    calls: list[dict] = []
    monkeypatch.setattr(ws.httpx, "AsyncClient", _fake_client(calls, {"daily": {}, "hourly": {}}))

    await ws._execute("get_weather_forecast", {"lat": 15.35, "lon": 44.2, "days": 1})

    assert len(calls) == 1
    url = urlsplit(calls[0]["url"])
    assert (url.scheme, url.netloc, url.path) == ("https", "api.open-meteo.com", "/v1/forecast")
