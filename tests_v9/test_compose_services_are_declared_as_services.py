"""A service declared under the wrong YAML key is not a service — it is silence.

Measured, and it fooled both a package and this repo's own reachability guard for a
full review round: ``sahool-canonical-execution-learning-worker`` was appended under
``networks:`` instead of ``services:`` in docker-compose.v9.yml. Compose would never
start it. Nothing looked wrong — the block had ``build``, ``command``, ``depends_on``
and a ``healthcheck``, and a text-level grep for its command matched perfectly, so
``platform_module_reachability_guard`` reported a registered worker root that did not
exist. The aggregate counts could not reveal it either: the modules that worker imports
are already route-reachable, so the summary was byte-identical either way.

The lesson is narrow and mechanical: anything shaped like a service must be measured
where Compose would actually execute it, never by matching text anywhere in the file.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]

# Keys that only ever belong to a service definition. A top-level mapping under
# `networks:` or `volumes:` carrying any of these is a misplaced service.
_SERVICE_ONLY_KEYS = frozenset(
    {"build", "image", "command", "entrypoint", "depends_on", "healthcheck", "environment"}
)


def _compose_files() -> list[Path]:
    return sorted(ROOT.glob("docker-compose*.yml"))


def test_no_service_definition_hides_under_networks_or_volumes():
    offenders: list[str] = []
    for compose in _compose_files():
        document = yaml.safe_load(compose.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            continue
        for block in ("networks", "volumes"):
            entries = document.get(block)
            if not isinstance(entries, dict):
                continue
            for name, spec in entries.items():
                if isinstance(spec, dict) and _SERVICE_ONLY_KEYS & set(spec):
                    leaked = sorted(_SERVICE_ONLY_KEYS & set(spec))
                    offenders.append(f"{compose.name}: {block}.{name} declares {leaked}")
    assert not offenders, (
        "service definitions found outside `services:` — Compose would never start them:\n"
        + "\n".join(f"    {item}" for item in offenders)
    )


def test_the_canonical_learning_worker_is_a_real_service():
    """The specific regression, pinned: it must resolve under `services:`."""
    compose = ROOT / "docker-compose.v9.yml"
    document = yaml.safe_load(compose.read_text(encoding="utf-8"))
    services = document.get("services") or {}
    name = "sahool-canonical-execution-learning-worker"
    assert name in services, f"{name} must be declared under services:"
    assert name not in (document.get("networks") or {})
    spec = services[name]
    command = " ".join(spec.get("command") or [])
    assert "canonical_execution_learning_worker.py" in command, (
        "the service must actually start the worker it is named for"
    )
