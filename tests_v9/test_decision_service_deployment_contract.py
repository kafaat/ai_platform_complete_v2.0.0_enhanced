"""Guard: decision-service is actually deployable — the P4.5–P4.7 boundary is only
production-valid if the mirror host it targets exists.

Context (interim dual-path, d201527): sahool-platform is the authoritative Source-of-Record;
it performs the real DB write and then best-effort mirrors to decision-service at
``DECISION_SERVICE_URL`` (default ``http://sahool-decision-service:8160``). Before this guard
the service had a facade caller but NO Dockerfile, NO compose service and NO env wiring —
so the mirror host ``sahool-decision-service:8160`` did not resolve and every mirror call died
(a warning per write; the authoritative platform write still succeeded, so no data loss).

This guard pins the deployment contract so the mirror is reachable and the extraction is
honestly production-shippable:
- a Dockerfile exists, runs non-root, exposes/serves port 8160, healthchecks /healthz;
- both compose files (v9 + fixed) define sahool-decision-service with build + healthcheck;
- the platform service wires DECISION_SERVICE_URL to the mirror host in both compose files.

Honesty note asserted here too: the service is still an interim stub with NO database, so NO
DATABASE_URL/JOBS_DATABASE_URL is wired into it (unused DB env would falsely imply
persistence). That wiring lands with the real-SoR upgrade.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
DECISION_PORT = "8160"
MIRROR_HOST = "http://sahool-decision-service:8160"
COMPOSE_FILES = ["docker-compose.v9.yml", "docker-compose.fixed.yml"]


def _load(rel: str):
    import yaml

    return yaml.safe_load((ROOT / rel).read_text(encoding="utf-8"))


def test_dockerfile_exists_nonroot_port_8160_healthcheck():
    df = ROOT / "services/decision-service/Dockerfile"
    assert df.exists(), "decision-service has no Dockerfile — cannot be built/deployed"
    src = df.read_text(encoding="utf-8")
    assert "USER sahool" in src, "container must run non-root (SEC-2)"
    assert f'--port", "{DECISION_PORT}' in src or f":{DECISION_PORT}" in src, (
        "must serve on 8160 (the facade's DECISION_SERVICE_URL port)"
    )
    assert f"localhost:{DECISION_PORT}/healthz" in src, "healthcheck must hit /healthz on 8160"


@pytest.mark.parametrize("compose", COMPOSE_FILES)
def test_compose_defines_decision_service(compose):
    svc = _load(compose)["services"].get("sahool-decision-service")
    assert svc, f"{compose}: sahool-decision-service is not defined"
    assert "build" in svc, f"{compose}: decision-service must build from its Dockerfile"
    assert svc["build"]["dockerfile"] == "services/decision-service/Dockerfile"
    assert "healthcheck" in svc, f"{compose}: decision-service needs a healthcheck"
    hc = " ".join(map(str, svc["healthcheck"]["test"]))
    assert f"localhost:{DECISION_PORT}/healthz" in hc, (
        f"{compose}: healthcheck must probe 8160/healthz"
    )


@pytest.mark.parametrize("compose", COMPOSE_FILES)
def test_platform_wires_decision_service_url(compose):
    env = _load(compose)["services"]["sahool-platform"]["environment"]
    assert isinstance(env, dict), f"{compose}: platform env should be a mapping"
    val = env.get("DECISION_SERVICE_URL")
    assert val, f"{compose}: platform must wire DECISION_SERVICE_URL so the mirror is reachable"
    assert MIRROR_HOST in val, (
        f"{compose}: DECISION_SERVICE_URL must target the mirror host {MIRROR_HOST}"
    )


@pytest.mark.parametrize("compose", COMPOSE_FILES)
def test_decision_service_has_no_misleading_db_env(compose):
    """Honesty: the interim stub has no database — it must NOT carry DATABASE_URL/JOBS_DATABASE_URL,
    which would falsely imply persistence. DB env lands with the real-SoR upgrade."""
    svc = _load(compose)["services"]["sahool-decision-service"]
    env = svc.get("environment") or {}
    keys = set(env.keys()) if isinstance(env, dict) else {e.split("=", 1)[0] for e in env}
    leaked = {"DATABASE_URL", "JOBS_DATABASE_URL"} & keys
    assert not leaked, (
        f"{compose}: interim mirror must not carry DB env {leaked} (implies persistence it does not have)"
    )


# Internal service-URL vars whose .env.example value must match the docker-compose default —
# these are container-to-container URLs, so the port must be the service's real container port.
# Drift here is a silent footgun: an operator copying .env.example verbatim points the platform
# at a dead port and the read silently degrades (e.g. WEATHER=8092/SOIL=8094 vs real 8000).
_INTERNAL_SERVICE_URL_VARS = [
    "RASTER_SERVICE_URL",
    "WEATHER_SERVICE_URL",
    "SOIL_SERVICE_URL",
    "DECISION_SERVICE_URL",
]


def _env_example() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _compose_default(env_val: str) -> str | None:
    """Extract the ``${VAR:-default}`` fallback from a compose env value, else None."""
    import re

    m = re.search(r":-([^}]+)\}", str(env_val))
    return m.group(1).strip() if m else None


@pytest.mark.parametrize("var", _INTERNAL_SERVICE_URL_VARS)
def test_env_example_service_urls_match_compose_default_ports(var):
    """.env.example internal service URLs must match the v9 compose default (real container port).

    Regression: WEATHER_SERVICE_URL=:8092 and SOIL_SERVICE_URL=:8094 in .env.example pointed at
    ports the services never listen on (real port 8000), so copying the example verbatim broke
    weather/soil reads.  Pin them to the compose default so the example is deployable as-is.
    """
    example = _env_example()
    assert var in example, f".env.example is missing {var}"
    plat_env = _load("docker-compose.v9.yml")["services"]["sahool-platform"]["environment"]
    default = _compose_default(plat_env[var])
    assert default, f"docker-compose.v9.yml platform env {var} has no :- default to compare against"
    assert example[var] == default, (
        f".env.example {var}={example[var]} does not match compose default {default} "
        f"(container-to-container URL must use the real service port)"
    )
