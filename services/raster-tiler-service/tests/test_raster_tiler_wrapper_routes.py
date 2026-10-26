"""Contract tests for the two routes this service adds on top of TiTiler.

``services/raster-tiler-service/main.py`` is a thin wrapper: it takes the TiTiler ASGI
app as-is and adds ``GET /runtime-identity`` and ``GET /metrics``. These tests pin what
those two routes do, and that the Prometheus job named by the alert
``SahoolRasterTileJSONUnavailable`` really scrapes this service's ``/metrics`` — the
alert had no scrape target for its whole life and therefore could never fire (#1010).

TiTiler itself is not under test (upstream has its own suite, and GDAL/rasterio are not
in the unit-test environment). ``titiler.application.main`` is replaced in
``sys.modules`` by a plain ``FastAPI()`` before ``main.py`` is executed, so what runs is
this service's own code against a real FastAPI app. Nothing is skipped when TiTiler is
absent; the stub is the reason the tests run everywhere.

``shared.runtime_identity`` is NOT stubbed: the identity tests run the real loader and
only redirect the file it reads from ``/app/.sahool-build-metadata.json`` (written by
the image build) to a temporary file.

Run (CI step "raster-tiler-service wrapper route contracts" in the Unit Tests job):

    pytest -v services/raster-tiler-service/tests
"""

from __future__ import annotations

import functools
import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

SERVICE_DIR = Path(__file__).resolve().parents[1]
ROOT = SERVICE_DIR.parents[1]
SERVICE_NAME = "raster-tiler-service"
ALERT_NAME = "SahoolRasterTileJSONUnavailable"
WRAPPER_ROUTES = ("/runtime-identity", "/metrics")

PROMETHEUS_YML = ROOT / "prometheus" / "prometheus.yml"
ALERTS_YML = ROOT / "prometheus" / "alerts.yml"
COMPOSE_YML = ROOT / "docker-compose.v9.yml"
DOCKERFILE = SERVICE_DIR / "Dockerfile"


@pytest.fixture()
def tiler(monkeypatch):
    """Execute main.py against a stand-in TiTiler app; return the loaded module.

    The stand-in declares no routes of its own: the service inventory counts every
    route decorator under ``services/raster-tiler-service/`` (tests included) as a
    route of this service, so a stand-in route here would inflate it.
    """
    fake_titiler_app = FastAPI(title="titiler stand-in")

    titiler_pkg = types.ModuleType("titiler")
    application_pkg = types.ModuleType("titiler.application")
    main_mod = types.ModuleType("titiler.application.main")
    main_mod.app = fake_titiler_app
    application_pkg.main = main_mod
    titiler_pkg.application = application_pkg
    monkeypatch.setitem(sys.modules, "titiler", titiler_pkg)
    monkeypatch.setitem(sys.modules, "titiler.application", application_pkg)
    monkeypatch.setitem(sys.modules, "titiler.application.main", main_mod)
    # `shared` must resolve to the repo-root package (as /app/shared does in the image),
    # not services/mcp_servers/shared.
    monkeypatch.syspath_prepend(str(ROOT))

    name = "raster_tiler_service_main_under_test"
    spec = importlib.util.spec_from_file_location(name, SERVICE_DIR / "main.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    module.stand_in_titiler_app = fake_titiler_app
    return module


def _read_from(tiler, monkeypatch, metadata_path: Path) -> None:
    """Keep the real loader; change only the file it reads."""
    real_loader = tiler.load_build_identity
    assert real_loader.__module__ == "shared.runtime_identity", real_loader.__module__
    monkeypatch.setattr(
        tiler, "load_build_identity", functools.partial(real_loader, metadata_path=metadata_path)
    )


# ── /runtime-identity ────────────────────────────────────────────────────────


def test_runtime_identity_serves_the_image_stamp_for_this_service(tiler, monkeypatch, tmp_path):
    """The route returns the immutable stamp, validated for service ``raster-tiler-service``.

    The real loader rejects a stamp whose ``service`` differs from the name the route
    asks for, so this also pins the literal name in main.py: a copy of this wrapper that
    asked for another service's identity would fail here, not in production.
    """
    stamp = {
        "service": SERVICE_NAME,
        "git_sha": "0123456789abcdef0123456789abcdef01234567",
        "build_id": "gha-image-1-1-raster-tiler-service",
        "source_repository": "owner/repo",
        "source_ref": "refs/heads/main",
    }
    metadata = tmp_path / "sahool-build-metadata.json"
    metadata.write_text(json.dumps(stamp), encoding="utf-8")
    _read_from(tiler, monkeypatch, metadata)

    response = TestClient(tiler.app).get("/runtime-identity")

    assert response.status_code == 200, response.text
    assert response.json() == {**stamp, "metadata_source": "immutable-image-file"}


def test_runtime_identity_fails_closed_without_the_image_stamp(tiler, monkeypatch, tmp_path):
    """Outside an image (no stamp file) the route errors; it never invents an identity.

    Asserted at the HTTP boundary only: real TiTiler installs an exception handler that
    turns the loader's BuildIdentityError into a JSON 500, the stand-in app returns a
    plain 500. Either way no identity object is served.
    """
    _read_from(tiler, monkeypatch, tmp_path / "absent.json")

    response = TestClient(tiler.app, raise_server_exceptions=False).get("/runtime-identity")

    assert response.status_code == 500
    is_json = response.headers.get("content-type", "").startswith("application/json")
    body = response.json() if is_json else {}
    assert "git_sha" not in body, (
        "a failed lookup must not answer with an identity — an invented SHA is what this "
        "route exists to prevent"
    )


def test_image_stamp_is_written_for_this_service_where_the_loader_reads_it():
    """The Dockerfile's build-time stamp must match what the route asks the loader for.

    Otherwise the built image answers /runtime-identity with 500 on every request: the
    path and the service name are each read in a different file.
    """
    from shared.runtime_identity import BUILD_METADATA_PATH

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    written_to = re.search(r'Path\("([^"]+)"\)\.write_text', dockerfile)
    stamped_service = re.search(r"\"service\":\s*'([^']+)'", dockerfile)
    assert written_to is not None and stamped_service is not None
    assert written_to.group(1) == str(BUILD_METADATA_PATH)
    assert stamped_service.group(1) == SERVICE_NAME


# ── /metrics ─────────────────────────────────────────────────────────────────


def test_metrics_serves_prometheus_exposition_of_the_default_registry(tiler):
    """200, Prometheus content type, parseable exposition — from the process registry.

    A probe counter is registered on the default registry for the duration of the
    test: it must appear with its value, so a route that rendered an empty private
    registry (or anything other than the live process metrics) fails.
    """
    from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter
    from prometheus_client.parser import text_string_to_metric_families

    probe = Counter(
        "sahool_raster_tiler_contract_probe",
        "test-only probe that /metrics renders the default registry",
        registry=REGISTRY,
    )
    try:
        probe.inc(3)
        response = TestClient(tiler.app).get("/metrics")
    finally:
        REGISTRY.unregister(probe)

    assert response.status_code == 200
    assert response.headers["content-type"] == CONTENT_TYPE_LATEST
    assert response.headers["content-type"].startswith("text/plain")
    families = {family.name: family for family in text_string_to_metric_families(response.text)}
    samples = {
        sample.name: sample.value
        for sample in families["sahool_raster_tiler_contract_probe"].samples
    }
    assert samples["sahool_raster_tiler_contract_probe_total"] == 3.0


# ── OpenAPI surface ──────────────────────────────────────────────────────────


def test_neither_wrapper_route_is_in_the_openapi_schema(tiler):
    """Both routes are registered as GET but hidden from the public schema.

    Absence alone would also pass for a route that was never registered, so the
    registration and the route's own ``include_in_schema`` flag are asserted first.
    """
    registered = {route.path: route for route in tiler.app.routes if isinstance(route, APIRoute)}
    for path in WRAPPER_ROUTES:
        assert path in registered, (path, sorted(registered))
        assert registered[path].methods == {"GET"}, (path, registered[path].methods)
        assert registered[path].include_in_schema is False, path

    schema_paths = tiler.app.openapi()["paths"]
    for path in WRAPPER_ROUTES:
        assert path not in schema_paths, (
            f"{path} is operational evidence (include_in_schema=False), not public tiling API"
        )


def test_wrapper_routes_extend_the_titiler_app_rather_than_replace_it(tiler):
    """main.app must be TiTiler's app object, or every tiling route would vanish."""
    assert tiler.app is tiler.stand_in_titiler_app


# ── Alert → scrape job → this service ────────────────────────────────────────


def _load_yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _alert_job_selector() -> str:
    groups = _load_yaml(ALERTS_YML)["groups"]
    rules = [rule for group in groups for rule in group["rules"] if rule.get("alert") == ALERT_NAME]
    assert len(rules) == 1, f"expected exactly one {ALERT_NAME} rule, found {len(rules)}"
    match = re.search(r'up\{job=~"([^"]+)"\}\s*==\s*0', rules[0]["expr"])
    assert match is not None, rules[0]["expr"]
    return match.group(1)


def _scrape_job(job_name: str) -> dict:
    jobs = [
        job for job in _load_yaml(PROMETHEUS_YML)["scrape_configs"] if job["job_name"] == job_name
    ]
    assert len(jobs) == 1, f"expected exactly one scrape job {job_name!r}, found {len(jobs)}"
    return jobs[0]


def test_alert_selects_a_scrape_job_that_prometheus_loads():
    """The alert's `up{job=~...}` must match the `raster-tiler` job, and that job must exist.

    `up` only exists for jobs Prometheus scrapes. A selector naming a job with no
    scrape config yields no series and the alert is permanently silent — the gap #1010
    closed. The rules file must also reach Prometheus (rule_files + compose mount).
    """
    selector = _alert_job_selector()
    # PromQL `=~` is fully anchored.
    assert re.fullmatch(selector, "raster-tiler"), selector
    _scrape_job("raster-tiler")

    prometheus = _load_yaml(PROMETHEUS_YML)
    assert "alerts.yml" in prometheus["rule_files"]
    mounts = {
        volume.split(":")[0]: volume.split(":")[1]
        for volume in _load_yaml(COMPOSE_YML)["services"]["sahool-prometheus"]["volumes"]
    }
    assert mounts.get("./prometheus/alerts.yml") == "/etc/prometheus/alerts.yml"
    assert mounts.get("./prometheus/prometheus.yml") == "/etc/prometheus/prometheus.yml"


def test_raster_tiler_scrape_target_is_this_services_metrics_route(tiler):
    """The `raster-tiler` job scrapes this service's container, port and `/metrics` route."""
    job = _scrape_job("raster-tiler")
    metrics_path = job.get("metrics_path", "/metrics")  # Prometheus default
    assert job.get("scheme", "http") == "http"
    targets = [target for config in job["static_configs"] for target in config["targets"]]
    assert len(targets) == 1, targets
    host, port = targets[0].rsplit(":", 1)

    # The path Prometheus requests is a GET route of this service's app.
    registered = {
        route.path: route.methods for route in tiler.app.routes if isinstance(route, APIRoute)
    }
    assert "GET" in registered.get(metrics_path, set()), (metrics_path, sorted(registered))
    assert TestClient(tiler.app).get(metrics_path).status_code == 200

    # The host is the compose service built from this service's Dockerfile, on a
    # network Prometheus shares, listening on the scraped port.
    services = _load_yaml(COMPOSE_YML)["services"]
    assert host in services, f"scrape host {host!r} is not a compose service"
    service = services[host]
    assert service["build"]["dockerfile"] == "services/raster-tiler-service/Dockerfile"
    assert set(service["networks"]) & set(services["sahool-prometheus"]["networks"])
    assert f"PORT={port}" in service["environment"]
    exposed = re.search(r"^EXPOSE\s+(\d+)\s*$", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    assert exposed is not None and exposed.group(1) == port
