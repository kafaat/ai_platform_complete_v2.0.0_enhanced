"""Behavioral contract for the conservative capability linker."""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ci" / "capability_linker.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("capability_linker_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _minimal_repo(tmp_path: Path) -> tuple[Path, Path]:
    registry = tmp_path / "capabilities/registry/capabilities.json"
    generated = tmp_path / "capabilities/generated"
    registry.parent.mkdir(parents=True)
    generated.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "capabilities": [
                    {
                        "id": "FM-001",
                        "maturity": 3,
                        "status": "runtime_instrumented_production_unverified",
                        "evidence_level": 4,
                        "services": [],
                        "apis": [],
                        "tests": [],
                        "ui_consumers": [],
                        "mobile_consumers": [],
                        "dependencies": [],
                        "evidence": [],
                        "owner": "PLATFORM",
                        "confidence": "low",
                        "rationale": "seed",
                    }
                ]
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    service_main = tmp_path / "services/auth/main.py"
    service_main.parent.mkdir(parents=True)
    service_main.write_text("# tenant auth\n", encoding="utf-8")
    test_file = tmp_path / "tests/test_tenant_auth.py"
    test_file.parent.mkdir(parents=True)
    test_file.write_text("def test_tenant_auth(): pass\n", encoding="utf-8")
    _write_csv(
        tmp_path / "service_inventory.csv",
        ["service", "main"],
        [{"service": "auth", "main": "services/auth/main.py"}],
    )
    _write_csv(
        tmp_path / "route_inventory.csv",
        ["service", "method", "path", "file", "line", "function"],
        [
            {
                "service": "auth",
                "method": "GET",
                "path": "/tenant/auth",
                "file": "services/auth/main.py",
                "line": "1",
                "function": "tenant_auth",
            }
        ],
    )
    return registry, generated


def _configure(module, tmp_path: Path, registry: Path, generated: Path) -> None:
    module.ROOT = tmp_path
    module.REGISTRY = registry
    module.ROUTES = tmp_path / "route_inventory.csv"
    module.SERVICES = tmp_path / "service_inventory.csv"
    module.GENERATED = generated


def test_apply_links_shape_without_changing_certification(monkeypatch, tmp_path):
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])

    assert module.main() == 0
    capability = json.loads(registry.read_text(encoding="utf-8"))["capabilities"][0]
    assert capability["services"] == ["services/auth/main.py"]
    assert capability["apis"]
    assert capability["tests"] == ["tests/test_tenant_auth.py"]
    assert capability["status"] == "runtime_instrumented_production_unverified"
    assert capability["evidence_level"] == 4
    assert (generated / "capability_link_candidates.csv").is_file()


def test_check_is_pure_and_detects_both_registry_and_candidate_drift(monkeypatch, tmp_path):
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])
    assert module.main() == 0
    candidates = generated / "capability_link_candidates.csv"
    before_registry = registry.read_bytes()
    before_candidates = candidates.read_bytes()

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--check"])
    assert module.main() == 0
    assert registry.read_bytes() == before_registry
    assert candidates.read_bytes() == before_candidates

    candidates.write_text("drift\n", encoding="utf-8")
    drifted = candidates.read_bytes()
    assert module.main() == 1
    assert registry.read_bytes() == before_registry
    assert candidates.read_bytes() == drifted


def test_discovery_and_candidates_are_stable_when_filesystem_order_changes(monkeypatch, tmp_path):
    module = _load_module()
    registry, generated = _minimal_repo(tmp_path)
    _configure(module, tmp_path, registry, generated)

    extra = tmp_path / "services/auth/tenant_auth.py"
    extra.write_text("# auth tenant implementation\n", encoding="utf-8")

    original_rglob = Path.rglob

    def reversed_rglob(self: Path, pattern: str):
        return iter(reversed(list(original_rglob(self, pattern))))

    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--apply"])
    assert module.main() == 0
    first_registry = registry.read_bytes()
    first_candidates = (generated / "capability_link_candidates.csv").read_bytes()

    monkeypatch.setattr(Path, "rglob", reversed_rglob)
    assert module.main() == 0
    assert registry.read_bytes() == first_registry
    assert (generated / "capability_link_candidates.csv").read_bytes() == first_candidates
