"""The unified schema validator must fail on every way a schema can be wrong.

``JSON-SCHEMAS-WITH-NO-VALIDATOR-01``. A guard that only passes on a healthy tree is
indistinguishable from a guard that does nothing — this repository has measured that
twice (``guard_mutation_guard`` exists because of it). So each check below is proven by
planting the defect it claims to catch and watching the guard fail with that code.

The seven acceptance conditions are exercised directly:
JSON must parse · ``$schema`` must be declared · the meta-schema must be known · the
document must be a valid schema for the draft it declares · every ``$ref`` must resolve ·
none may be external · and the four domains that own schemas must pass through this one
validator rather than four of their own.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/ci/schema_validation_guard.py"
POLICY = ROOT / "docs/architecture/schema_validation_policy.json"

jsonschema = pytest.importorskip(
    "jsonschema",
    reason="declared in requirements-preflight.txt; the guard itself fails closed without it",
)


def _guard():
    spec = importlib.util.spec_from_file_location("_schema_validation_guard", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


VALID = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "probe",
    "type": "object",
    "$defs": {"leaf": {"type": "string"}},
    "properties": {"a": {"$ref": "#/$defs/leaf"}},
}


def _codes(tmp_path: Path, document, *, name: str = "probe.schema.json") -> list[str]:
    """Run the guard's per-file check on a planted document and return its finding codes."""
    guard = _guard()
    path = tmp_path / name
    path.write_text(
        document if isinstance(document, str) else json.dumps(document), encoding="utf-8"
    )
    policy = guard.load_policy(POLICY)
    return [f.code for f in guard.check_file(name, policy, root=tmp_path)]


# ── the six planted defects ────────────────────────────────────────────────


def test_broken_json_is_caught(tmp_path):
    assert "INVALID_JSON" in _codes(tmp_path, '{"title": "probe",}')


def test_a_missing_meta_schema_is_caught(tmp_path):
    document = {k: v for k, v in VALID.items() if k != "$schema"}
    assert "NO_META_SCHEMA" in _codes(tmp_path, document)


def test_an_unknown_meta_schema_is_caught(tmp_path):
    document = {**VALID, "$schema": "https://example.invalid/draft/9999/schema"}
    assert "UNKNOWN_META_SCHEMA" in _codes(tmp_path, document)


def test_a_schema_invalid_for_its_declared_draft_is_caught(tmp_path):
    # `type` must be a string or an array of strings; an integer is invalid under 2020-12.
    document = {**VALID, "type": 7}
    assert "INVALID_SCHEMA" in _codes(tmp_path, document)


def test_a_dangling_local_ref_is_caught(tmp_path):
    document = {**VALID, "properties": {"a": {"$ref": "#/$defs/absent"}}}
    assert "UNRESOLVED_REF" in _codes(tmp_path, document)


def test_an_external_ref_is_caught(tmp_path):
    """External references make the result describe the environment, not the contract."""
    document = {**VALID, "properties": {"a": {"$ref": "https://example.invalid/x.json"}}}
    assert "EXTERNAL_REF" in _codes(tmp_path, document)


def test_a_correct_schema_passes(tmp_path):
    """Without this, every assertion above would also hold for a guard that always fails."""
    assert _codes(tmp_path, VALID) == []


# ── the repository as it stands ────────────────────────────────────────────


def test_every_tracked_schema_is_discovered_from_git_not_from_a_list():
    guard = _guard()
    discovered = guard.discover(ROOT)
    expected = sorted(
        line
        for line in subprocess.run(
            ["git", "ls-files", "*.schema.json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.splitlines()
        if line.strip()
    )
    assert discovered == expected
    assert discovered, "no schemas discovered — the gate would be vacuously green"

    policy_text = POLICY.read_text(encoding="utf-8")
    for path in discovered:
        assert path not in policy_text, (
            f"the policy names {path} — an index that must be edited when a schema is "
            "added is the drift this gate exists to close"
        )


def test_the_whole_repository_passes_the_one_validator():
    guard = _guard()
    policy = guard.load_policy(POLICY)
    failures = [f for path in guard.discover(ROOT) for f in guard.check_file(path, policy)]
    assert not failures, "\n".join(str(f) for f in failures)


def test_all_four_schema_owning_domains_go_through_this_validator():
    """One validator, not one per domain — separate checkers drift apart.

    Measured in this repository: two engines answering the same capability-impact
    question returned 0 and 12 on identical input.
    """
    discovered = _guard().discover(ROOT)
    for domain in (
        "shared/contracts/remote_sensing/",
        "shared/contracts/soil/",
        "capabilities/schema/",
        "services/sahool-platform/api/",
    ):
        assert any(p.startswith(domain) for p in discovered), f"domain unrepresented: {domain}"

    # Scoped to `scripts/`: the property is one *validator*, not one filename containing
    # both words — the test file itself matches such a pattern, and excluding it by name
    # would be a special case rather than the rule.
    validators = subprocess.run(
        ["git", "ls-files", "scripts/**/*schema*valid*.py", "scripts/**/*valid*schema*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    assert validators == ["scripts/ci/schema_validation_guard.py"], (
        f"schema validation must live in exactly one place; found: {validators}"
    )


def test_no_schema_declares_an_external_reference_anywhere():
    """The acceptance condition "0 network dependency", checked on the real tree."""
    guard = _guard()
    for path in guard.discover(ROOT):
        document = json.loads((ROOT / path).read_text(encoding="utf-8"))
        external = [r for r in guard._iter_refs(document) if not r.startswith("#")]
        assert not external, f"{path}: external references {external}"


# ── the exception contract ─────────────────────────────────────────────────


def test_an_exception_without_the_full_record_is_rejected():
    guard = _guard()
    policy = {"exceptions": [{"path": "x.schema.json", "reason": "later"}]}
    problems = guard._expired_exceptions(policy, date(2026, 8, 5))
    assert problems and "missing" in problems[0]


def test_an_expired_exception_fails_the_guard():
    """An exception with no live expiry is a permanent decision nobody owns."""
    guard = _guard()
    yesterday = (date(2026, 8, 5) - timedelta(days=1)).isoformat()
    policy = {
        "exceptions": [
            {
                "path": "x.schema.json",
                "reason": "pending upstream fix",
                "owner": "platform",
                "decision_id": "DEC-TEST",
                "expires_on": yesterday,
            }
        ]
    }
    assert guard._expired_exceptions(policy, date(2026, 8, 5))


def test_the_policy_holds_no_file_list_and_carries_its_adjudication():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["schema"] == "sahool.schema_validation_policy"
    assert isinstance(policy["version"], int) and policy["version"] >= 1
    assert policy["adjudicated_on"], "a decided artifact carries the date it was decided"
    assert policy["ref_policy"]["local_only"] is True
    assert policy["network_policy"]["allowed"] is False
    assert policy["allowed_meta_schemas"], "an empty allow-list would reject everything"
