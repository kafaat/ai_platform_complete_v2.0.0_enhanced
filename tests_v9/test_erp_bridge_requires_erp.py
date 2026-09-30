"""ERP-BRIDGE-RUNS-WITHOUT-ODOO-AND-READYZ-SAYS-READY-01 — قرار المالك §3.4 (2026-09-30).

«خدمةٌ لا تعمل بلا تبعيّتها لا تُشغَّل بلا تبعيّتها»، بشقّيه:

  (أ) Compose: الجسر خلف profile odoo في v9/fixed/unified، وكلّ من يعتمد عليه يُعلنه
      ``required: false`` — وإلّا انكسر ``docker compose config``/``up`` بلا الـprofile
      («depends on undefined service»، مقيسٌ على v9 قبل الإصلاح).
  (ب) /readyz: 503 حين ERP غير مهيّأ أو غير مستجيب (بمهلة محدودة، بلا أسرار في الجسم)،
      و200 حين مهيّأ ومستجيب؛ و/healthz (الحياة) 200 في كلّ الحالات.

الراوتر الحقيقيّ (routers/health.py) + OdooClient/OdooProvider الحقيقيّان؛ المُستبدَل وحده
هو ناقل HTTP (``httpx.MockTransport``) أو منفذ مغلق حقيقيّ للاتّصال المرفوض.
"""

from __future__ import annotations

import asyncio
import importlib
import socket
import sys
import time
from pathlib import Path

import pytest
import yaml

pytest.importorskip("fastapi", reason="integration job installs minimal deps (no fastapi)")
import httpx  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tests_v9 import service_module  # noqa: E402

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "services/odoo-bridge"
SECRET = "readyz-must-not-leak-this-3f9a"


# ══════════════════════════════════════════════════════════════════
# (أ) Compose — profile odoo + required: false لكلّ معتمد
# ══════════════════════════════════════════════════════════════════
_COMPOSE_BRIDGE = {
    "docker-compose.v9.yml": "sahool-erp-bridge",
    "docker-compose.fixed.yml": "sahool-erp-bridge",
    "docker-compose.unified.yml": "erp-bridge",
}


@pytest.mark.parametrize(("compose_file", "bridge"), sorted(_COMPOSE_BRIDGE.items()))
def test_bridge_is_behind_odoo_profile(compose_file: str, bridge: str) -> None:
    services = yaml.safe_load((ROOT / compose_file).read_text(encoding="utf-8"))["services"]
    assert services[bridge].get("profiles") == ["odoo"], (
        f"{compose_file}: {bridge} يعمل بلا profile odoo — الجسر بلا ERP لا يفعل شيئاً (§3.4)"
    )


@pytest.mark.parametrize(("compose_file", "bridge"), sorted(_COMPOSE_BRIDGE.items()))
def test_every_dependent_declares_bridge_optional(compose_file: str, bridge: str) -> None:
    services = yaml.safe_load((ROOT / compose_file).read_text(encoding="utf-8"))["services"]
    dependents = []
    for name, spec in services.items():
        deps = (spec or {}).get("depends_on") or {}
        if bridge not in deps:
            continue
        dependents.append(name)
        # القائمة القصيرة (``- erp-bridge``) لا تحمل required ⇒ required: true ضمناً.
        entry = deps[bridge] if isinstance(deps, dict) else {}
        assert entry.get("required") is False, (
            f"{compose_file}: {name} يعتمد على {bridge} (خلف profile odoo) بلا required: false "
            "⇒ `docker compose config/up` بلا الـprofile يفشل: depends on undefined service"
        )
    assert dependents, f"{compose_file}: لا معتمد على {bridge} — الجرد تغيّر؛ راجع هذا الحارس"


# ══════════════════════════════════════════════════════════════════
# (ب) /readyz على الراوتر الحقيقيّ
# ══════════════════════════════════════════════════════════════════
@pytest.fixture
def bridge(monkeypatch):
    """يُحمّل main الجسر عبر المُحمِّل المشترك (main.py اسم عامّ عبر الخدمات) ثمّ راوتر الصحّة."""
    for var in ("ERPNEXT_URL", "ERPNEXT_API_KEY", "ERPNEXT_API_SECRET", "DATABASE_URL"):
        monkeypatch.delenv(var, raising=False)
    service_module.purge_generic_modules()
    main = service_module.load_service_main(
        str(SERVICE), required_attrs=("app", "get_active_erp_provider", "OdooClient")
    )
    health = importlib.import_module("routers.health")
    assert Path(health.__file__).resolve().is_relative_to(SERVICE.resolve())
    if str(ROOT) not in sys.path:
        monkeypatch.syspath_prepend(str(ROOT))
    rt = health._erp_rt
    monkeypatch.setattr(rt, "_pool", None)  # بلا DATABASE_URL: DB ليس شرطاً — ERP وحده المقيس
    monkeypatch.setattr(rt, "_odoo", None)
    app = FastAPI()
    app.include_router(health.router)
    yield main, health, rt, TestClient(app)
    service_module.purge_generic_modules()


def _odoo_client(rt, handler=None, *, url="http://odoo.test:8069", password=SECRET):
    client = rt.OdooClient(url, "sahool_erp", "admin", password, "")
    if handler is not None:
        client._session = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def _jsonrpc(result):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    return handler


def _closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _assert_not_ready(client: TestClient, reason: str) -> dict:
    r = client.get("/readyz")
    assert r.status_code == 503, f"/readyz={r.status_code} بلا ERP جاهز: {r.text}"
    erp = r.json()["detail"]["erp"]
    assert erp["reachable"] is False
    assert erp["reason"] == reason, erp
    assert SECRET not in r.text
    # الحياة مستقلّة عن ERP: غيابه يُخرج الجسر من التوجيه ولا يُعيد تشغيله.
    assert client.get("/healthz").status_code == 200
    assert client.get("/health").status_code == 200
    return erp


def test_readyz_503_when_erp_disabled(bridge, monkeypatch) -> None:
    _, _, _, client = bridge
    monkeypatch.setenv("ERP_PROVIDER", "none")
    erp = _assert_not_ready(client, "erp_not_configured")
    assert erp["configured"] is False


def test_readyz_503_when_default_erpnext_is_unconfigured(bridge, monkeypatch) -> None:
    """الافتراضيّ erpnext بلا عنوان ومفتاحين ⇒ NullProvider ⇒ غير مهيّأ (لا «جاهز» كاذب)."""
    _, _, _, client = bridge
    monkeypatch.delenv("ERP_PROVIDER", raising=False)
    erp = _assert_not_ready(client, "erp_not_configured")
    assert erp["provider"] == "erpnext"


def test_readyz_503_when_odoo_has_no_credentials_without_network(bridge, monkeypatch) -> None:
    _, _, rt, client = bridge
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 2})

    monkeypatch.setenv("ERP_PROVIDER", "odoo")
    monkeypatch.setattr(rt, "_odoo", _odoo_client(rt, handler, password=None))
    erp = _assert_not_ready(client, "odoo_credentials_missing")
    assert erp["configured"] is False
    assert calls == [], "غير المهيّأ يُحكَم بلا شبكة"


def test_readyz_503_when_odoo_unreachable(bridge, monkeypatch) -> None:
    """منفذ مغلق حقيقيّ: اتّصال مرفوض عبر ناقل httpx الحقيقيّ ⇒ 503 بلا عنوان في الجسم."""
    _, _, rt, client = bridge
    url = f"http://127.0.0.1:{_closed_port()}"
    monkeypatch.setenv("ERP_PROVIDER", "odoo")
    monkeypatch.setattr(rt, "_odoo", _odoo_client(rt, url=url))
    erp = _assert_not_ready(client, "erp_unreachable")
    assert erp == {
        "provider": "odoo",
        "configured": True,
        "reachable": False,
        "reason": "erp_unreachable",
    }
    assert url not in client.get("/readyz").text


def test_readyz_503_when_odoo_rejects_credentials(bridge, monkeypatch) -> None:
    """Odoo يُرجِع result=false لاعتماد خاطئ — ليس «connected» (كان uid is not None ⇒ جاهز)."""
    _, _, rt, client = bridge
    monkeypatch.setenv("ERP_PROVIDER", "odoo")
    monkeypatch.setattr(rt, "_odoo", _odoo_client(rt, _jsonrpc(False)))
    _assert_not_ready(client, "erp_unreachable")


def test_readyz_probe_is_bounded_when_odoo_hangs(bridge, monkeypatch) -> None:
    _, health, rt, client = bridge

    async def hang(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(30)
        return httpx.Response(200, json={"result": 2})

    monkeypatch.setenv("ERP_PROVIDER", "odoo")
    monkeypatch.setattr(rt, "_odoo", _odoo_client(rt, hang))
    monkeypatch.setattr(health, "_READYZ_ERP_PROBE_TIMEOUT", 0.2)
    started = time.monotonic()
    _assert_not_ready(client, "erp_probe_timeout")
    assert time.monotonic() - started < 5, "مسبار الجاهزيّة عُلِّق بلا مهلة"


def test_readyz_503_when_configured_erpnext_unreachable(bridge, monkeypatch) -> None:
    _, _, _, client = bridge
    monkeypatch.setenv("ERP_PROVIDER", "erpnext")
    monkeypatch.setenv("ERPNEXT_URL", f"http://127.0.0.1:{_closed_port()}")
    monkeypatch.setenv("ERPNEXT_API_KEY", "k")
    monkeypatch.setenv("ERPNEXT_API_SECRET", SECRET)
    erp = _assert_not_ready(client, "erp_unreachable")
    assert erp["provider"] == "erpnext"


def test_readyz_200_when_odoo_configured_and_reachable(bridge, monkeypatch) -> None:
    _, _, rt, client = bridge
    monkeypatch.setenv("ERP_PROVIDER", "odoo")
    monkeypatch.setattr(rt, "_odoo", _odoo_client(rt, _jsonrpc(2)))
    r = client.get("/readyz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ready"
    assert body["erp"] == {"provider": "odoo", "configured": True, "reachable": True}
    assert SECRET not in r.text
    assert client.get("/healthz").status_code == 200
