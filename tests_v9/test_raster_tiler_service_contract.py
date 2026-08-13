"""raster-tiler-service contract tests (KEEP + HARDEN slice).

Covers the two things the service actually adds on top of TiTiler:
1. The ``/runtime-identity`` endpoint wired to the immutable build identity
   loader with the exact service name ``raster-tiler-service``.
2. The packaging contract in the Dockerfile (TiTiler pin range, port,
   non-root user, immutable build metadata, shared/ copy).

TiTiler itself is NOT re-tested here (upstream has its own suite); the heavy
``titiler.application`` dependency is stubbed in ``sys.modules`` before the
service ``main.py`` is loaded, so these tests stay fast and do not require the
GDAL/rasterio stack.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_DIR = REPO_ROOT / "services" / "raster-tiler-service"
SERVICE_MAIN = SERVICE_DIR / "main.py"
SERVICE_DOCKERFILE = SERVICE_DIR / "Dockerfile"
RUNTIME_IDENTITY_PY = REPO_ROOT / "shared" / "runtime_identity.py"

SERVICE_NAME = "raster-tiler-service"
VALID_GIT_SHA = "a" * 40
VALID_BUILD_ID = "build-2026.08.14-1"


def _load_module(abs_path: Path, module_name: str):
    """Load a module by absolute path (repo convention for collision-prone
    names like ``shared`` — see pytest.ini note)."""
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def runtime_identity_module():
    return _load_module(RUNTIME_IDENTITY_PY, "_rt_shared_runtime_identity")


@pytest.fixture()
def service_main(monkeypatch):
    """Load services/raster-tiler-service/main.py with a stubbed TiTiler app.

    The stub is a real FastAPI app so route registration, TestClient and the
    OpenAPI schema all behave exactly as they do against the real TiTiler app
    object — what we are testing is OUR wiring, not TiTiler's routes.
    """
    from fastapi import FastAPI

    fake_titiler_app = FastAPI(title="titiler-stub")

    titiler_pkg = types.ModuleType("titiler")
    titiler_app_pkg = types.ModuleType("titiler.application")
    titiler_main_mod = types.ModuleType("titiler.application.main")
    titiler_main_mod.app = fake_titiler_app
    titiler_app_pkg.main = titiler_main_mod
    titiler_pkg.application = titiler_app_pkg

    monkeypatch.setitem(sys.modules, "titiler", titiler_pkg)
    monkeypatch.setitem(sys.modules, "titiler.application", titiler_app_pkg)
    monkeypatch.setitem(sys.modules, "titiler.application.main", titiler_main_mod)

    # Repo root must be importable for `shared.runtime_identity`
    # (mirrors pytest.ini `pythonpath = .`).
    monkeypatch.syspath_prepend(str(REPO_ROOT))

    module = _load_module(SERVICE_MAIN, "_rt_raster_tiler_main")
    module._fake_titiler_app = fake_titiler_app  # test handle
    return module


# ---------------------------------------------------------------------------
# 1. /runtime-identity endpoint contract
# ---------------------------------------------------------------------------


def test_runtime_identity_route_returns_immutable_identity(service_main, monkeypatch):
    from fastapi.testclient import TestClient

    expected = {
        "service": SERVICE_NAME,
        "git_sha": VALID_GIT_SHA,
        "build_id": VALID_BUILD_ID,
        "source_repository": "kafaat/ai_platform_complete_v2.0.0_enhanced",
        "source_ref": "refs/heads/main",
        "metadata_source": "immutable-image-file",
    }
    monkeypatch.setattr(service_main, "load_build_identity", lambda service: expected)

    client = TestClient(service_main.app)
    response = client.get("/runtime-identity")

    assert response.status_code == 200
    assert response.json() == expected


def test_runtime_identity_binds_exact_service_name(service_main, monkeypatch):
    """A copy-paste of this wrapper into another service must not silently
    reuse the raster-tiler identity: the literal service name is the contract."""
    from fastapi.testclient import TestClient

    seen: dict[str, str] = {}

    def spy(service: str):
        seen["service"] = service
        return {"service": service}

    monkeypatch.setattr(service_main, "load_build_identity", spy)

    client = TestClient(service_main.app)
    response = client.get("/runtime-identity")

    assert response.status_code == 200
    assert seen["service"] == SERVICE_NAME
    assert response.json()["service"] == SERVICE_NAME


def test_runtime_identity_hidden_from_openapi_schema(service_main):
    """include_in_schema=False is part of the contract: the endpoint is
    internal runtime evidence, not public API surface."""
    schema_paths = service_main.app.openapi()["paths"]
    assert "/runtime-identity" not in schema_paths


def test_service_app_is_the_titiler_application(service_main):
    """The service must extend the real TiTiler ASGI app, not shadow it with
    a private FastAPI instance (which would drop every TiTiler route)."""
    assert service_main.app is service_main._fake_titiler_app


# ---------------------------------------------------------------------------
# 2. Immutable build identity loader — fail-closed behavior
# ---------------------------------------------------------------------------


def _write_metadata(path: Path, **overrides) -> Path:
    payload = {
        "service": SERVICE_NAME,
        "git_sha": VALID_GIT_SHA,
        "build_id": VALID_BUILD_ID,
        "source_repository": "kafaat/ai_platform_complete_v2.0.0_enhanced",
        "source_ref": "refs/heads/main",
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_loader_returns_six_key_identity(runtime_identity_module, tmp_path):
    meta = _write_metadata(tmp_path / "ok.json")
    identity = runtime_identity_module.load_build_identity(SERVICE_NAME, meta)
    assert identity == {
        "service": SERVICE_NAME,
        "git_sha": VALID_GIT_SHA,
        "build_id": VALID_BUILD_ID,
        "source_repository": "kafaat/ai_platform_complete_v2.0.0_enhanced",
        "source_ref": "refs/heads/main",
        "metadata_source": "immutable-image-file",
    }


def test_loader_fails_closed_when_metadata_missing(runtime_identity_module, tmp_path):
    with pytest.raises(runtime_identity_module.BuildIdentityError):
        runtime_identity_module.load_build_identity(SERVICE_NAME, tmp_path / "missing.json")


def test_loader_fails_closed_on_service_mismatch(runtime_identity_module, tmp_path):
    meta = _write_metadata(tmp_path / "wrong_service.json", service="other-service")
    with pytest.raises(runtime_identity_module.BuildIdentityError):
        runtime_identity_module.load_build_identity(SERVICE_NAME, meta)


def test_loader_fails_closed_on_uppercase_git_sha(runtime_identity_module, tmp_path):
    # 40 hex chars but uppercase: isolates the lowercase-hex contract
    # (_SHA_RE) without also failing on length.
    meta = _write_metadata(tmp_path / "uppercase_sha.json", git_sha="A" * 40)
    with pytest.raises(runtime_identity_module.BuildIdentityError):
        runtime_identity_module.load_build_identity(SERVICE_NAME, meta)


def test_loader_fails_closed_on_short_git_sha(runtime_identity_module, tmp_path):
    # Lowercase hex but 39 chars: isolates the exact-length contract.
    meta = _write_metadata(tmp_path / "short_sha.json", git_sha="a" * 39)
    with pytest.raises(runtime_identity_module.BuildIdentityError):
        runtime_identity_module.load_build_identity(SERVICE_NAME, meta)


def test_loader_fails_closed_on_invalid_build_id(runtime_identity_module, tmp_path):
    meta = _write_metadata(tmp_path / "bad_build.json", build_id="-bad")
    with pytest.raises(runtime_identity_module.BuildIdentityError):
        runtime_identity_module.load_build_identity(SERVICE_NAME, meta)


# ---------------------------------------------------------------------------
# 3. Dockerfile packaging contract (static, no image build)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def dockerfile_text() -> str:
    return SERVICE_DOCKERFILE.read_text(encoding="utf-8")


def test_dockerfile_pins_titiler_within_supported_range(dockerfile_text):
    assert "titiler.application>=0.20,<0.23" in dockerfile_text


def test_dockerfile_exposes_documented_port(dockerfile_text):
    # README documents the internal base URL on port 8088.
    assert "PORT=8088" in dockerfile_text
    assert "EXPOSE 8088" in dockerfile_text


def test_dockerfile_runs_as_non_root_locked_user(dockerfile_text):
    assert "useradd --create-home --shell /usr/sbin/nologin sahool" in dockerfile_text
    assert "USER sahool" in dockerfile_text


def test_dockerfile_writes_immutable_build_metadata_readonly(dockerfile_text):
    assert "/app/.sahool-build-metadata.json" in dockerfile_text
    assert "chmod 0444 /app/.sahool-build-metadata.json" in dockerfile_text


def test_dockerfile_copies_shared_runtime_identity(dockerfile_text):
    # Without shared/ the /runtime-identity import chain breaks at runtime.
    assert "COPY shared/ /app/shared/" in dockerfile_text
