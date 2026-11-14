"""C-04: export_openapi.py is fail-closed for REQUIRED services and reports OPTIONAL skips.

Pure unit tests. ``export_one`` (the per-service import + ``app.openapi()`` seam) is
monkeypatched, except in the two loader tests, which build throwaway FastAPI services
under ``tmp_path``. Each behaviour has a negative control in the same test.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "_export_openapi_under_test", ROOT / "export_openapi.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def exp(monkeypatch, tmp_path):
    mod = _load_module()
    monkeypatch.setattr(mod, "REQUIRED", frozenset({"core-a", "core-b"}))
    monkeypatch.setattr(mod, "OPTIONAL", {"extra-c": "needs a heavy package"})
    inv = [
        {"service": "core-a", "main": "services/core-a/main.py"},
        {"service": "core-b", "main": "services/core-b/main.py"},
        {"service": "extra-c", "main": "services/extra-c/main.py"},
        {"service": "lib-d", "main": "-"},
    ]
    (tmp_path / "inv.json").write_text(json.dumps(inv), encoding="utf-8")
    routes = [{"service": s} for s in ["core-a"] * 2 + ["extra-c"] * 5 + ["lib-d"] * 3]
    (tmp_path / "routes.json").write_text(json.dumps(routes), encoding="utf-8")
    return mod


def _spec(*paths):
    return {"openapi": "3.1.0", "paths": {p: {"get": {}, "post": {}} for p in paths}}


def _fake_export(failing: dict[str, str]):
    calls = []

    def fake(service, main_path, timeout=0):
        calls.append(service)
        if service in failing:
            return None, failing[service]
        return _spec(f"/{service}/x", f"/{service}/y"), None

    fake.calls = calls
    return fake


def _run(exp, tmp_path, monkeypatch, failing):
    fake = _fake_export(failing)
    monkeypatch.setattr(exp, "export_one", fake)
    out = tmp_path / "out"
    code = exp.main(
        [
            "--out-dir",
            str(out),
            "--inventory",
            str(tmp_path / "inv.json"),
            "--route-inventory",
            str(tmp_path / "routes.json"),
        ]
    )
    summary = (
        json.loads((out / "EXPORT_SUMMARY.json").read_text(encoding="utf-8"))
        if out.exists()
        else None
    )
    return code, summary, out, fake


def test_required_failure_exits_nonzero_and_names_service(exp, tmp_path, monkeypatch, capsys):
    code, summary, _, _ = _run(
        exp, tmp_path, monkeypatch, {"core-b": "ModuleNotFoundError: No module named 'x'"}
    )
    err = capsys.readouterr().err
    assert code == exp.EXIT_REQUIRED_FAILED != 0
    assert summary["status"] == "failed"
    assert summary["required_failed"] == [
        {
            "service": "core-b",
            "error": "ModuleNotFoundError: No module named 'x'",
            "static_routes": 0,
        }
    ]
    assert "core-b" in err

    # Negative control: the same failure on an OPTIONAL service does not fail the run.
    code, summary, _, _ = _run(
        exp, tmp_path, monkeypatch, {"extra-c": "ModuleNotFoundError: No module named 'x'"}
    )
    assert code == exp.EXIT_OK
    assert summary["status"] == "ok"
    assert summary["required_failed"] == []


def test_openapi_failure_of_required_service_is_not_swallowed(exp, tmp_path, monkeypatch):
    code, summary, _, _ = _run(
        exp, tmp_path, monkeypatch, {"core-a": "exit 4: EXPORT-ERROR openapi(): boom"}
    )
    assert code == 1
    assert [e["service"] for e in summary["required_failed"]] == ["core-a"]
    # Negative control: nothing fails, exit 0.
    code, _, _, _ = _run(exp, tmp_path, monkeypatch, {})
    assert code == 0


def test_optional_skip_is_reported_in_summary_index_and_stdout(exp, tmp_path, monkeypatch, capsys):
    code, summary, out, _ = _run(
        exp, tmp_path, monkeypatch, {"extra-c": "ModuleNotFoundError: titiler"}
    )
    stdout = capsys.readouterr().out
    assert code == 0
    assert summary["optional_skipped"] == [
        {
            "service": "extra-c",
            "error": "ModuleNotFoundError: titiler",
            "static_routes": 5,
            "reason": "needs a heavy package",
        }
    ]
    index = (out / "INDEX.md").read_text(encoding="utf-8")
    assert "`extra-c`" in index and "needs a heavy package" in index
    assert "extra-c" in stdout and "optional skipped: 1" in stdout
    assert not (out / "extra-c.openapi.json").exists()

    # Negative control: when the optional service exports, no skip is recorded.
    code, summary, out, _ = _run(exp, tmp_path, monkeypatch, {})
    assert summary["optional_skipped"] == []
    assert (out / "extra-c.openapi.json").exists()


def test_summary_counts(exp, tmp_path, monkeypatch):
    code, summary, out, fake = _run(
        exp, tmp_path, monkeypatch, {"core-b": "boom", "extra-c": "missing dep"}
    )
    assert code == 1
    assert fake.calls == ["core-a", "core-b", "extra-c"]  # lib-d has no main: never imported
    assert summary["counts"] == {
        "inventory_services": 4,
        "required": 2,
        "optional": 1,
        "not_asgi": 1,
        "exported": 1,
        "exported_required": 1,
        "exported_optional": 0,
        "optional_skipped": 1,
        "required_failed": 1,
        "exported_paths": 2,
        "exported_operations": 4,
    }
    assert summary["not_asgi"] == [{"service": "lib-d", "static_routes": 3}]
    assert summary["exported"][0]["static_routes"] == 2
    # Successful export still writes its spec even when another required service failed.
    assert json.loads((out / "core-a.openapi.json").read_text(encoding="utf-8")) == _spec(
        "/core-a/x", "/core-a/y"
    )

    # Negative control: all succeed -> the counts move accordingly.
    _, summary, _, _ = _run(exp, tmp_path, monkeypatch, {})
    c = summary["counts"]
    assert (c["exported"], c["optional_skipped"], c["required_failed"], c["exported_paths"]) == (
        3,
        0,
        0,
        6,
    )


def test_unclassified_service_is_a_registry_error_before_any_import(exp, tmp_path, monkeypatch):
    inv = json.loads((tmp_path / "inv.json").read_text(encoding="utf-8"))
    inv.append({"service": "new-e", "main": "services/new-e/main.py"})
    (tmp_path / "inv.json").write_text(json.dumps(inv), encoding="utf-8")
    code, summary, _, fake = _run(exp, tmp_path, monkeypatch, {})
    assert code == exp.EXIT_REGISTRY_ERROR == 2
    assert fake.calls == [] and summary is None

    # Negative control: classify it as optional and the run proceeds.
    monkeypatch.setattr(exp, "OPTIONAL", {"extra-c": "x", "new-e": "y"})
    code, _, _, fake = _run(exp, tmp_path, monkeypatch, {})
    assert code == 0 and "new-e" in fake.calls


def test_real_inventory_is_fully_classified():
    mod = _load_module()
    inventory = mod.load_inventory(mod.DEFAULT_INVENTORY)
    classes = mod.classify(inventory)
    assert set(classes) == {svc for svc, _ in inventory}
    assert {s for s, c in classes.items() if c == "required"} == set(mod.REQUIRED)

    # Negative control: a service the classification does not know is rejected.
    with pytest.raises(mod.RegistryError, match="neither REQUIRED nor OPTIONAL"):
        mod.classify([*inventory, ("brand-new-svc", "services/brand-new-svc/main.py")])


_FWD_REF_MAIN = """
from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    child: Child

class Child(BaseModel):
    name: str

@app.post("/items")
def create(item: Item) -> Item:
    return item
"""


def test_load_app_resolves_forward_refs(tmp_path):
    """Regression: decision-service, knowledge-graph and sahool-platform failed because the
    loaded module was not registered in sys.modules, so pydantic could not resolve
    forward references."""
    mod = _load_module()
    main = tmp_path / "fwd" / "main.py"
    main.parent.mkdir()
    main.write_text(_FWD_REF_MAIN, encoding="utf-8")
    try:
        app, err = mod.load_app("fwd-test", str(main))
        assert err is None
        assert "/items" in app.openapi()["paths"]
    finally:
        sys.modules.pop("_svc_fwd_test", None)
        for p in (str(main.parent), str(ROOT)):
            while p in sys.path:
                sys.path.remove(p)

    # Negative control: a main.py without `app` is reported, not returned as success.
    (tmp_path / "noapp").mkdir()
    (tmp_path / "noapp" / "main.py").write_text("x = 1\n", encoding="utf-8")
    try:
        app, err = mod.load_app("noapp-test", str(tmp_path / "noapp" / "main.py"))
        assert app is None and "no `app`" in err
    finally:
        sys.modules.pop("_svc_noapp_test", None)


def _write_service(base: Path, name: str, route: str) -> Path:
    d = base / name
    d.mkdir()
    (d / "routers.py").write_text(
        f"from fastapi import APIRouter\nr = APIRouter()\n\n@r.get('{route}')\ndef h():\n    return {{}}\n",
        encoding="utf-8",
    )
    (d / "main.py").write_text(
        "from fastapi import FastAPI\nimport routers\napp = FastAPI()\napp.include_router(routers.r)\n",
        encoding="utf-8",
    )
    return d / "main.py"


def test_export_one_isolates_services_with_same_local_module_names(tmp_path):
    """Regression: in one process the second service re-used the first one's cached
    `routers` module and exported the wrong paths without any error."""
    mod = _load_module()
    a = _write_service(tmp_path, "svc_a", "/only-a")
    b = _write_service(tmp_path, "svc_b", "/only-b")
    spec_a, err_a = mod.export_one("svc-a", str(a), timeout=120)
    spec_b, err_b = mod.export_one("svc-b", str(b), timeout=120)
    assert err_a is None and err_b is None
    assert list(spec_a["paths"]) == ["/only-a"]
    assert list(spec_b["paths"]) == ["/only-b"]

    # Negative control: loading both in this one process reproduces the contamination.
    saved = sys.modules.pop("routers", None)
    try:
        app_a, _ = mod.load_app("svc-a2", str(a))
        app_b, _ = mod.load_app("svc-b2", str(b))
        assert list(app_b.openapi()["paths"]) == ["/only-a"]
    finally:
        for k in ("routers", "_svc_svc_a2", "_svc_svc_b2"):
            sys.modules.pop(k, None)
        if saved is not None:
            sys.modules["routers"] = saved
        for p in (str(a.parent), str(b.parent), str(ROOT)):
            while p in sys.path:
                sys.path.remove(p)


def test_import_time_state_path_is_redirected_to_a_temp_dir(tmp_path, monkeypatch):
    """Regression (CI, non-root runner): knowledge-graph opens its SQLite store at import
    under KG_SQLITE_PATH, defaulting to /data, which a runner cannot create. The export
    points each declared variable into a per-run temp dir and removes it afterwards."""
    mod = _load_module()
    svc_dir = tmp_path / "svc_state"
    svc_dir.mkdir()
    main = svc_dir / "main.py"
    main.write_text(
        "import os\n"
        "from pathlib import Path\n"
        "from fastapi import FastAPI\n"
        "target = Path(os.environ.get('SVC_STATE_PATH', '/dev/null/state.db'))\n"
        "target.parent.mkdir(parents=True, exist_ok=True)\n"
        "target.write_text('x')\n"
        "app = FastAPI()\n"
        "@app.get('/state')\n"
        "def state():\n"
        "    return {'path': str(target)}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "IMPORT_ENV_PATHS", {"svc-state": {"SVC_STATE_PATH": "state.db"}})
    monkeypatch.delenv("SVC_STATE_PATH", raising=False)
    spec, err = mod.export_one("svc-state", str(main), timeout=120)
    assert err is None, err
    assert list(spec["paths"]) == ["/state"]

    # Negative control: without the declared redirect the import fails on the default path
    # (under /dev/null, which no user, root included, can create a directory in).
    monkeypatch.setattr(mod, "IMPORT_ENV_PATHS", {})
    spec, err = mod.export_one("svc-state", str(main), timeout=120)
    assert spec is None and "EXPORT-ERROR import" in err


def test_knowledge_graph_state_path_is_declared():
    mod = _load_module()
    assert mod.IMPORT_ENV_PATHS["knowledge-graph"] == {"KG_SQLITE_PATH": "kg.sqlite"}
