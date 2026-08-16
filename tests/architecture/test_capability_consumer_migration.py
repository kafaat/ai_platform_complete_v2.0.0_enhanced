from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/ci/capability_authority_view.py"


def _load():
    spec = importlib.util.spec_from_file_location("capability_authority_view_under_test", SOURCE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, canonical_rows: list[dict], legacy_rows: list[dict]) -> None:
    policy = {
        "schema": "sahool.capability-field-authority/v1",
        "field_authority": {
            "id": {"authority": "canonical_capability_definition"},
            "domain": {"authority": "canonical_capability_definition"},
            "dependencies": {"authority": "canonical_capability_definition"},
            "maturity": {"authority": "canonical_capability_definition"},
            "evidence_level": {"authority": "canonical_capability_definition"},
            "owner": {"authority": "canonical_capability_definition"},
            "runtime_verified": {"authority": "runtime_verification"},
            "production_certified": {"authority": "certification"},
        },
        "reconciliation": {"no_third_value_registry": True},
    }
    paths = {
        "docs/capability-registry/field_authority_policy.json": policy,
        "docs/capability-registry/generated/capability_registry.json": {
            "capabilities": canonical_rows
        },
        "capabilities/registry/capabilities.json": {"capabilities": legacy_rows},
    }
    for rel, payload in paths.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")


def test_canonical_definition_fields_win_while_mutable_runtime_fields_survive(tmp_path):
    module = _load()
    canonical = [
        {
            "id": "INT-004",
            "domain": "farm_management",
            "dependencies": ["PA-005"],
            "maturity": 3,
            "evidence_level": 3,
            "owner": "sahool-platform",
        }
    ]
    legacy = [
        {
            "id": "INT-004",
            "title": "Machinery integration",
            "domain": "integration",
            "dependencies": [],
            "maturity": 1,
            "evidence_level": 1,
            "owner": "UNASSIGNED",
            "runtime_verified": True,
            "production_certified": False,
            "runtime": {"receipts": [{"type": "attested-runtime-verification"}]},
            "services": ["services/sahool-platform/main.py"],
            "apis": [],
            "tests": [],
            "ui_consumers": [],
            "mobile_consumers": [],
            "evidence": [],
        }
    ]
    _write(tmp_path, canonical, legacy)

    [row] = module.load_authoritative_capabilities(tmp_path)
    assert (
        row["domain"],
        row["dependencies"],
        row["maturity"],
        row["evidence_level"],
        row["owner"],
    ) == ("farm_management", ["PA-005"], 3, 3, "sahool-platform")
    assert row["runtime_verified"] is True
    assert row["production_certified"] is False
    assert row["runtime"]["receipts"][0]["type"] == "attested-runtime-verification"
    assert row["title"] == "Machinery integration"


def test_identity_disagreement_fails_closed_instead_of_joining_by_intersection(tmp_path):
    module = _load()
    canonical = [
        {
            "id": "A",
            "domain": "d",
            "dependencies": [],
            "maturity": 0,
            "evidence_level": 0,
            "owner": "x",
        }
    ]
    legacy = [
        {
            "id": "B",
            "domain": "d",
            "dependencies": [],
            "maturity": 0,
            "evidence_level": 0,
            "owner": "x",
        }
    ]
    _write(tmp_path, canonical, legacy)

    try:
        module.load_authoritative_capabilities(tmp_path)
    except module.CapabilityAuthorityError as exc:
        assert "identity sets disagree" in str(exc)
    else:
        raise AssertionError("identity drift must fail closed")


def test_missing_canonical_authoritative_field_fails_closed(tmp_path):
    module = _load()
    canonical = [{"id": "A", "domain": "d", "dependencies": [], "maturity": 0, "evidence_level": 0}]
    legacy = [
        {
            "id": "A",
            "domain": "d",
            "dependencies": [],
            "maturity": 0,
            "evidence_level": 0,
            "owner": "legacy",
        }
    ]
    _write(tmp_path, canonical, legacy)

    try:
        module.load_authoritative_capabilities(tmp_path)
    except module.CapabilityAuthorityError as exc:
        assert "lacks authoritative field: owner" in str(exc)
    else:
        raise AssertionError("missing authoritative data must fail closed")


def test_first_read_only_consumers_are_wired_to_the_authority_view():
    root = Path(__file__).resolve().parents[2]
    for rel in (
        "scripts/ci/capability_traceability_report.py",
        "scripts/ci/capability_certification_gate.py",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "load_authoritative_capabilities(ROOT)" in text, rel
        assert 'ROOT / "capabilities/registry/capabilities.json"' not in text, rel


def test_a_policy_that_stops_forbidding_a_third_registry_is_refused(tmp_path):
    """العرض لا يعمل تحت سياسةٍ تخلّت عن تحريم مصدر القيم الثالث — الشرط يُقاس
    لا يُفترَض (من حزمة المالك الثانية لهذه الشريحة)."""
    module = _load()
    canonical = [
        {
            "id": "A",
            "domain": "d",
            "dependencies": [],
            "maturity": 0,
            "evidence_level": 0,
            "owner": "x",
        }
    ]
    _write(tmp_path, canonical, canonical)
    import json as _json

    policy_path = tmp_path / "docs/capability-registry/field_authority_policy.json"
    doc = _json.loads(policy_path.read_text(encoding="utf-8"))
    doc["reconciliation"]["no_third_value_registry"] = False
    policy_path.write_text(_json.dumps(doc), encoding="utf-8")

    try:
        module.load_authoritative_capabilities(tmp_path)
    except module.CapabilityAuthorityError as exc:
        assert "third value registry" in str(exc)
    else:
        raise AssertionError("a permissive policy must be refused")


def test_a_nested_canonical_field_demands_an_explicit_merger(tmp_path):
    """حقلٌ منقوط يُمنَح للتعريف القانونيّ يُرفَض حتى يُكتَب دامجُه الصريح —
    لا مفتاح حرفيّ باسمٍ منقوط يكتب فوق لا شيء (من حزمة المالك الثانية)."""
    module = _load()
    canonical = [
        {
            "id": "A",
            "domain": "d",
            "dependencies": [],
            "maturity": 0,
            "evidence_level": 0,
            "owner": "x",
        }
    ]
    _write(tmp_path, canonical, canonical)
    import json as _json

    policy_path = tmp_path / "docs/capability-registry/field_authority_policy.json"
    doc = _json.loads(policy_path.read_text(encoding="utf-8"))
    doc["field_authority"]["runtime.nested_thing"] = {
        "authority": "canonical_capability_definition"
    }
    policy_path.write_text(_json.dumps(doc), encoding="utf-8")

    try:
        module.load_authoritative_capabilities(tmp_path)
    except module.CapabilityAuthorityError as exc:
        assert "explicit merger" in str(exc)
    else:
        raise AssertionError("a nested canonical field must be refused until merged explicitly")
