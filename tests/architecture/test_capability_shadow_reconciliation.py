from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = ROOT / "scripts/ci" / name
    spec = importlib.util.spec_from_file_location(name.removesuffix(".py"), path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _policy(compare=None, exclude=None, third=False) -> dict:
    return {
        "schema": "sahool.capability-field-authority/v1",
        "field_authority": {
            "maturity": {
                "authority": "canonical_capability_definition",
                "legacy_role": "compatibility_projection",
            },
            "status": {
                "authority": "legacy_registry_projection",
                "reconciliation": "excluded_until_structured_normalization",
            },
        },
        "reconciliation": {
            "compare_raw": ["id", "maturity"] if compare is None else compare,
            "exclude_raw": ["status", "title"] if exclude is None else exclude,
            "no_third_value_registry": not third,
        },
    }


def _fixture(tmp_path: Path, monkeypatch, canonical_caps, legacy_caps, policy=None):
    mod = load_script("capability_shadow_reconciliation.py")
    canonical = tmp_path / "canonical.json"
    legacy = tmp_path / "legacy.json"
    policy_path = tmp_path / "policy.json"
    canonical.write_text(json.dumps({"capabilities": canonical_caps}), encoding="utf-8")
    legacy.write_text(json.dumps({"capabilities": legacy_caps}), encoding="utf-8")
    policy_path.write_text(json.dumps(policy or _policy()), encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "CANONICAL", canonical)
    monkeypatch.setattr(mod, "LEGACY", legacy)
    monkeypatch.setattr(mod, "FIELD_AUTHORITY_POLICY", policy_path)
    monkeypatch.setattr(mod, "OUT", tmp_path / "reconciliation")
    return mod


def test_the_comparison_plan_is_policy_data_and_its_absence_refuses_comparison(
    tmp_path: Path, monkeypatch
) -> None:
    policy = _policy()
    del policy["reconciliation"]
    mod = _fixture(tmp_path, monkeypatch, [], [], policy=policy)
    with pytest.raises(ValueError, match="no reconciliation block"):
        mod.build()


def test_a_policy_that_compares_and_excludes_the_same_field_is_refused(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _fixture(
        tmp_path,
        monkeypatch,
        [],
        [],
        policy=_policy(compare=["id", "status"], exclude=["status"]),
    )
    with pytest.raises(ValueError, match="compares and excludes"):
        mod.build()


def test_a_policy_permitting_a_third_value_registry_is_refused(tmp_path: Path, monkeypatch) -> None:
    mod = _fixture(tmp_path, monkeypatch, [], [], policy=_policy(third=True))
    with pytest.raises(ValueError, match="third value registry"):
        mod.build()


def test_a_raw_value_drift_is_reported_with_its_declared_authority(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _fixture(
        tmp_path,
        monkeypatch,
        [{"id": "X-001", "maturity": 3, "status": "active"}],
        [{"id": "X-001", "maturity": 1, "status": "different"}],
    )
    report = json.loads(mod.build()["shadow_reconciliation_report.json"])
    findings = report["findings"]
    assert [f["finding_id"] for f in findings] == ["X-001:maturity"]
    f = findings[0]
    assert f["canonical"] == 3 and f["legacy"] == 1
    assert f["authority"] == "canonical_capability_definition"
    assert f["legacy_role"] == "compatibility_projection"


def test_an_excluded_field_is_never_compared_even_when_it_differs(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _fixture(
        tmp_path,
        monkeypatch,
        [{"id": "X-001", "maturity": 2, "status": "active"}],
        [{"id": "X-001", "maturity": 2, "status": "wildly_different"}],
    )
    report = json.loads(mod.build()["shadow_reconciliation_report.json"])
    assert report["findings"] == []
    excluded = {e["field"]: e["reason"] for e in report["fields_excluded"]}
    assert excluded["status"] == "excluded_until_structured_normalization"


def test_a_capability_missing_from_either_side_is_an_identity_finding(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _fixture(
        tmp_path,
        monkeypatch,
        [{"id": "X-001", "maturity": 2}, {"id": "X-002", "maturity": 1}],
        [{"id": "X-001", "maturity": 2}],
    )
    report = json.loads(mod.build()["shadow_reconciliation_report.json"])
    assert [f["finding_id"] for f in report["findings"]] == ["X-002:identity"]
    assert report["findings"][0]["canonical"] == "present"
    assert report["findings"][0]["legacy"] == "absent"


def test_the_report_witnesses_both_sides_and_never_nominates_a_resolution(
    tmp_path: Path, monkeypatch
) -> None:
    mod = _fixture(
        tmp_path,
        monkeypatch,
        [{"id": "X-001", "maturity": 3}],
        [{"id": "X-001", "maturity": 1}],
    )
    report = json.loads(mod.build()["shadow_reconciliation_report.json"])
    assert report["no_third_value_registry"] is True
    assert report["mode"] == "shadow-report-only"
    f = report["findings"][0]
    assert "canonical" in f and "legacy" in f
    assert not any(k in f for k in ("resolved", "correct", "chosen", "winner"))


def test_findings_never_fail_the_run_but_a_stale_report_does(tmp_path: Path, monkeypatch) -> None:
    mod = _fixture(
        tmp_path,
        monkeypatch,
        [{"id": "X-001", "maturity": 3}],
        [{"id": "X-001", "maturity": 1}],
    )
    outputs = mod.build()
    assert json.loads(outputs["shadow_reconciliation_report.json"])["summary"]["findings_total"]
    mod.write(outputs)
    assert mod.check(outputs) == []

    legacy = tmp_path / "legacy.json"
    legacy.write_text(
        json.dumps({"capabilities": [{"id": "X-001", "maturity": 2}]}), encoding="utf-8"
    )
    stale = mod.check(mod.build())
    assert any(e.startswith("stale:") for e in stale)
