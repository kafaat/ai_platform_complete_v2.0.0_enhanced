from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from scripts.ci.platform_route_classification import INFRASTRUCTURE_ROUTES
from scripts.ci.platform_route_placement_guard import CONTRACT_PATH, verify_placement

REPO = Path(__file__).resolve().parents[2]
PLATFORM = REPO / "services/sahool-platform"


def _fixture_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    shutil.copytree(PLATFORM, repo / "services/sahool-platform")
    contract = repo / "docs/architecture/platform_route_placement_contract.json"
    contract.parent.mkdir(parents=True)
    shutil.copy2(CONTRACT_PATH, contract)
    return repo


def _identity_block() -> str:
    return """\n\n# Runtime identity is read from a build-time generated, read-only image file.\n# Mutable runtime environment values are deliberately not trusted.\n@router.get("/runtime-identity", include_in_schema=True)\ndef runtime_evidence_identity():\n    from shared.runtime_identity import load_build_identity\n\n    return load_build_identity("sahool-platform")\n"""


def test_live_runtime_identity_placement_is_contract_compliant() -> None:
    evidence = verify_placement()
    route = next(
        row
        for row in evidence["routes"]
        if (row["method"], row["path"]) == ("GET", "/runtime-identity")
    )
    assert route["actual_source"] == ("services/sahool-platform/api/routers/platform_health.py")
    assert route["contract_satisfied"] is True


def test_placement_contract_exactly_covers_infrastructure_allowlist() -> None:
    evidence = verify_placement()
    pairs = {(row["method"], row["path"]) for row in evidence["routes"]}
    assert pairs == INFRASTRUCTURE_ROUTES


def test_runtime_identity_in_main_fails_with_required_source(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    health = repo / "services/sahool-platform/api/routers/platform_health.py"
    main = repo / "services/sahool-platform/api/main.py"
    block = _identity_block()
    health.write_text(health.read_text().replace(block, "\n"))
    main.write_text(main.read_text() + block.replace("@router.get", "@app.get"))
    with pytest.raises(AssertionError, match="required source") as caught:
        verify_placement(repo=repo)
    assert "routers/platform_health.py" in str(caught.value)
    assert "api/main.py" in str(caught.value)


def test_duplicate_runtime_identity_in_main_fails_exactly_one(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    main = repo / "services/sahool-platform/api/main.py"
    main.write_text(main.read_text() + _identity_block().replace("@router.get", "@app.get"))
    with pytest.raises(AssertionError, match="exactly one"):
        verify_placement(repo=repo)


def test_contract_change_is_machine_visible(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    contract_path = repo / "docs/architecture/platform_route_placement_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["routes"][0]["required_source"] = "services/sahool-platform/api/main.py"
    contract_path.write_text(json.dumps(contract))
    with pytest.raises(AssertionError, match="required source"):
        verify_placement(repo=repo)


def test_missing_infrastructure_placement_rule_fails(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    contract_path = repo / "docs/architecture/platform_route_placement_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["routes"] = [rule for rule in contract["routes"] if rule["path"] != "/metrics"]
    contract_path.write_text(json.dumps(contract))
    with pytest.raises(AssertionError, match="missing placement rules"):
        verify_placement(repo=repo)


def test_non_infrastructure_placement_rule_fails(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    contract_path = repo / "docs/architecture/platform_route_placement_contract.json"
    contract = json.loads(contract_path.read_text())
    extra = dict(contract["routes"][0])
    extra["path"] = "/runtime-identity/export"
    contract["routes"].append(extra)
    contract_path.write_text(json.dumps(contract))
    with pytest.raises(AssertionError, match="non-infrastructure placement rules"):
        verify_placement(repo=repo)


def test_duplicate_placement_rule_fails(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path)
    contract_path = repo / "docs/architecture/platform_route_placement_contract.json"
    contract = json.loads(contract_path.read_text())
    contract["routes"].append(dict(contract["routes"][0]))
    contract_path.write_text(json.dumps(contract))
    with pytest.raises(AssertionError, match="duplicate method/path"):
        verify_placement(repo=repo)
