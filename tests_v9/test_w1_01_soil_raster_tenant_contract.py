"""W1-01 — soil and raster reads of field-intelligence and ETc reach real, tenant-scoped routes.

Findings closed (audit ``soil-1``/``routes-1``, ``remote-6``/``routes-2``, ``remote-5``):

* ``soil_adapter`` asked soil-service for ``/api/v1/soil/{field_id}``, a route soil-service never
  declares: a deterministic 404, so the EC signal was always absent. It now reads the governed
  profile through ``resolve_canonical_soil_state`` (``/v1/fields/{id}/soil/profile``).
* ``sensing_adapter`` → ``get_indices_sync`` called raster ``/v1/indices`` with no tenant. Raster
  resolves field layers under ``X-Tenant-Id``, so every index came back null.
* ETc's fresh-NDVI read (``get_indicator_grid``) sent no tenant either, ignored the raster
  quality verdict, and stamped the value with ``date.today()``.

Acceptance (plan W1-01): the soil path called is in soil-service's route set, and every
field-scoped raster read sends ``X-Tenant-Id``. Each contract below has a negative control on
the pre-fix shape. No network, no database: the store/transport boundary is stubbed.
"""

from __future__ import annotations

import ast
import importlib.util
import inspect
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
PLATFORM = ROOT / "services" / "sahool-platform"
if str(PLATFORM) not in sys.path:
    sys.path.insert(0, str(PLATFORM))

from core import field_intelligence_adapters as fia  # noqa: E402


def _load_guard():
    path = ROOT / "scripts" / "ci" / "cross_service_path_contract_guard.py"
    spec = importlib.util.spec_from_file_location("_w1_01_path_guard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load_guard()
SOIL_DECLARED = guard.declared_paths(ROOT / "services" / "soil-service")

# The adapter exactly as it stood before W1-01 — the negative control for the path contract.
_PRE_W1_01_SOIL_ADAPTER = """
def soil_adapter(req):
    data = _get_json(f"{SOIL_URL}/api/v1/soil/{req.field_id}")
    if not data:
        return None
    return {"ec_dsm": data.get("ec_dsm", data.get("ec")), "sampled_at": data.get("sampled_at")}
"""


# ── soil: the path called is one soil-service declares ──────────────────────────────────
def test_the_soil_path_field_intelligence_calls_is_declared_by_soil_service():
    adapter_src = inspect.getsource(fia.soil_adapter)
    assert "resolve_canonical_soil_state" in adapter_src, (
        "soil_adapter must read the governed profile through resolve_canonical_soil_state"
    )
    canonical = (PLATFORM / "api" / "canonical_soil_state.py").read_text(encoding="utf-8")
    called = guard.requested_paths(adapter_src) | guard.requested_paths(canonical)
    assert called == {"/v1/fields/{}/soil/profile"}, f"unexpected soil paths: {sorted(called)}"
    assert called <= SOIL_DECLARED, (
        f"soil path(s) not declared by soil-service (deterministic 404): {sorted(called - SOIL_DECLARED)}"
    )


def test_negative_control_the_pre_fix_soil_path_is_not_declared():
    called = guard.requested_paths(_PRE_W1_01_SOIL_ADAPTER)
    assert called == {"/api/v1/soil/{}"}, f"the extractor no longer reads the old shape: {called}"
    assert not called <= SOIL_DECLARED, "the pre-W1-01 path must be absent from soil-service"


def test_soil_adapter_reads_the_profile_under_the_request_tenant(monkeypatch):
    import api.canonical_soil_state as css

    calls: list[dict] = []

    async def _fake_resolve(*, tenant_id, field_id):
        calls.append({"tenant_id": tenant_id, "field_id": field_id})
        return _profile()

    monkeypatch.setattr(css, "resolve_canonical_soil_state", _fake_resolve)

    class _Req:
        field_id, tenant_id = "F1", "tenant-a"

    out = fia.soil_adapter(_Req())
    assert calls == [{"tenant_id": "tenant-a", "field_id": "F1"}], f"profile read: {calls}"
    assert out is not None and out["ec_dsm"] == pytest.approx(6.2), f"EC not projected: {out}"
    assert out["sampled_at"] == "2026-10-01T00:00:00Z", f"EC observation time lost: {out}"


def test_soil_adapter_without_tenant_does_not_read(monkeypatch):
    import api.canonical_soil_state as css

    calls: list = []

    async def _fake_resolve(**kwargs):
        calls.append(kwargs)
        return _profile()

    monkeypatch.setattr(css, "resolve_canonical_soil_state", _fake_resolve)

    class _Req:
        field_id, tenant_id = "F1", None

    assert fia.soil_adapter(_Req()) is None, "a tenant-less soil read must not produce a signal"
    assert calls == [], f"soil-service was called without a tenant: {calls}"


def _profile(*, source="laboratory", passed=True, verification_required=False, unit="dS/m"):
    ec = {
        "value": 6.2,
        "unit": unit,
        "selected_source": source,
        "observed_at": "2026-10-01T00:00:00Z",
        "verification_required": verification_required,
    }
    return {
        "contract_version": "soil-profile.v1",
        "profile_id": "sp_1",
        "profile_hash": "a" * 64,
        "quality_gate": {"passed": passed, "executable": False, "reasons": []},
        "layers": [
            {"depth_from_cm": 30, "depth_to_cm": 60, "properties": {"ec": {**ec, "value": 9.9}}},
            {"depth_from_cm": 0, "depth_to_cm": 30, "properties": {"ec": ec}},
        ],
    }


def test_profile_projection_takes_the_shallowest_measured_ec():
    out = fia.soil_signal_from_profile(_profile())
    assert out is not None, "a lab EC in a passed profile must project"
    assert out["ec_dsm"] == pytest.approx(6.2), f"not the shallowest layer: {out}"
    assert out["depth_from_cm"] == 0 and out["selected_source"] == "laboratory", f"{out}"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "soilgrids", "verification_required": True},  # modelled, not measured
        {"passed": False},  # no accepted evidence in the profile
        {"unit": "mS/cm"},  # a unit the signal does not carry
    ],
)
def test_profile_projection_refuses_estimates_and_ungated_profiles(kwargs):
    assert fia.soil_signal_from_profile(_profile(**kwargs)) is None, (
        f"a high-confidence soil_ec signal must not be built from {kwargs}"
    )


def test_profile_projection_returns_none_for_absent_profile():
    assert fia.soil_signal_from_profile(None) is None, "absence must stay absence"


# ── raster: every field-scoped read sends X-Tenant-Id ───────────────────────────────────
def test_sensing_adapter_sends_the_request_tenant(monkeypatch):
    seen: list = []

    def _fake_indices(field_id, *, tenant_id, lat, lon, timeout_s=None):
        seen.append(tenant_id)
        return {"ndvi": 0.5}

    monkeypatch.setattr(fia, "get_indices_sync", _fake_indices)

    class _Req:
        field_id, lat, lon, tenant_id = "F1", 15.3, 44.2, "tenant-a"

    assert fia.sensing_adapter(_Req())["ndvi"] == 0.5, "indices not passed through"
    assert seen == ["tenant-a"], f"raster /v1/indices read without the tenant: {seen}"

    _Req.tenant_id = None
    seen.clear()
    assert fia.sensing_adapter(_Req()) is None, "a tenant-less sensing read must not run"
    assert seen == [], f"raster was called without a tenant: {seen}"


@pytest.mark.skipif(importlib.util.find_spec("httpx") is None, reason="httpx unavailable")
def test_get_indices_sync_puts_the_tenant_on_the_wire(monkeypatch):
    import httpx
    from api import raster_service_client as rsc

    captured: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("X-Tenant-Id"))
        return httpx.Response(200, json={"ndvi": 0.4})

    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda *a, **k: real_client(transport=httpx.MockTransport(handler))
    )
    out = rsc.get_indices_sync("F1", tenant_id="tenant-a", lat=15.3, lon=44.2)
    assert out == {"ndvi": 0.4}, f"unexpected raster payload: {out}"
    assert captured == ["tenant-a"], f"X-Tenant-Id missing from /v1/indices: {captured}"

    captured.clear()
    assert rsc.get_indices_sync("F1", tenant_id="", lat=15.3, lon=44.2) is None, (
        "an empty tenant must not reach raster"
    )
    assert captured == [], f"raster was called with an empty tenant: {captured}"


def _tenant_scoped_raster_functions() -> dict[str, list[str]]:
    tree = ast.parse((PLATFORM / "api" / "raster_service_client.py").read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = [a.arg for a in node.args.args + node.args.kwonlyargs]
            if "tenant_id" in names:
                out[node.name] = names
    return out


def tenantless_raster_calls(source: str, functions: dict[str, list[str]]) -> list[str]:
    """Calls to a tenant-aware raster facade function that do not pass a tenant.

    Inside the facade itself only field-scoped helpers (a ``field_id`` parameter) are held to
    it; catalogue reads by bbox (``/v1/imagery/best``) and provider status are tenant-free.
    """
    tree = ast.parse(source)
    bad = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name not in functions:
            continue
        value = {k.arg: k.value for k in node.keywords}.get("tenant_id")
        positional = len(node.args) > functions[name].index("tenant_id")
        missing = value is None and not positional
        explicit_none = isinstance(value, ast.Constant) and value.value is None
        if missing or explicit_none:
            bad.append(f"{name}@{node.lineno}")
    return bad


def test_every_platform_call_to_a_tenant_aware_raster_read_passes_the_tenant():
    functions = _tenant_scoped_raster_functions()
    assert {"get_indices_sync", "get_indicator_grid"} <= set(functions), (
        f"tenant-aware raster surface shrank: {sorted(functions)}"
    )
    offenders = []
    for base in (PLATFORM / "api", PLATFORM / "core"):
        for path in sorted(base.rglob("*.py")):
            if "tests" in path.relative_to(base).parts or path.name == "raster_service_client.py":
                continue
            for call in tenantless_raster_calls(path.read_text(encoding="utf-8"), functions):
                offenders.append(f"{path.relative_to(ROOT)}: {call}")
    assert offenders == [], f"raster reads without X-Tenant-Id: {offenders}"


def test_field_scoped_facade_helpers_forward_the_tenant():
    tree = ast.parse((PLATFORM / "api" / "raster_service_client.py").read_text(encoding="utf-8"))
    transport = {"raster_get_json", "raster_get_json_sync", "raster_post_json", "raster_get_raw"}
    offenders = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if "field_id" not in [a.arg for a in node.args.args + node.args.kwonlyargs]:
            continue
        for call in ast.walk(node):
            if isinstance(call, ast.Call) and getattr(call.func, "id", None) in transport:
                if "tenant_id" not in {k.arg for k in call.keywords}:
                    offenders.append(f"{node.name}@{call.lineno}")
    assert offenders == [], f"field-scoped raster helpers dropping the tenant: {offenders}"


def test_negative_control_the_pre_fix_etc_read_is_caught():
    functions = _tenant_scoped_raster_functions()
    pre_fix = (
        "async def _fetch_fresh_ndvi(field_id):\n"
        "    return await get_indicator_grid(field_id, index='ndvi', date='latest', timeout_s=8)\n"
    )
    assert tenantless_raster_calls(pre_fix, functions) == ["get_indicator_grid@2"], (
        "the static check no longer catches a tenant-less raster read"
    )
