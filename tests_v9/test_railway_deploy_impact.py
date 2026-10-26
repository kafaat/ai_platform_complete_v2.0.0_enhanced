"""The derived deploy effect must equal what Railway actually deployed.

PR-DEPLOY-EFFECT-CLAIM-NOT-DERIVED-FROM-WATCH-PATTERNS-01: #1285's body said only the
gateway would redeploy; Railway also rebuilt auth-main, soil and vegetation because
test files under their folders match their watch patterns. The tool reads the
watch patterns captured from Railway (``docs/architecture/railway_watch_patterns.json``)
and every merge in ``docs/architecture/railway_deploy_measurements.json`` is replayed
against the services Railway built for it, read back read-only after the merge.

The changed-path lists are stored in the measurement file, not read from git history,
so the test runs the same in a depth-1 CI clone.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MEASUREMENTS = ROOT / "docs" / "architecture" / "railway_deploy_measurements.json"


def _load():
    path = ROOT / "scripts" / "ci" / "railway_deploy_impact.py"
    spec = importlib.util.spec_from_file_location("railway_deploy_impact_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


rdi = _load()
SNAPSHOT = rdi.load_snapshot()
MEASURED = json.loads(MEASUREMENTS.read_text(encoding="utf-8"))["merges"]


@pytest.mark.parametrize(
    ("path", "patterns", "expected"),
    [
        ("shared/pool_shutdown.py", ["/shared/**"], True),
        ("shared/a/b/c.py", ["/shared/**"], True),
        ("services/shared/x.py", ["/shared/**"], False),  # anchored at the root
        ("services/auth/tests/test_x.py", ["/services/auth/**"], True),  # tests count
        ("services/auth-main/x.py", ["/services/auth/**"], False),  # no prefix match
        ("deploy/railway/Dockerfile.frontend", ["/deploy/railway/Dockerfile.frontend"], True),
        ("deploy/railway/Dockerfile.frontend.bak", ["/deploy/railway/Dockerfile.frontend"], False),
        ("agents/base_agent.py", ["/agents/base_agent.py"], True),
        ("agents/notification/base_agent.py", ["/agents/base_agent.py"], False),
        ("docs/x.md", ["*.md"], True),  # no slash: any depth
        ("docs/x.md", ["/*.md"], False),  # leading slash: root only
        ("a/b.py", ["/a/*"], True),
        ("a/b/c.py", ["/a/*.py"], False),  # * does not cross /
        ("a/b/c.py", ["/a/**/c.py"], True),
        ("a/c.py", ["/a/**/c.py"], True),  # **/ matches zero directories
        ("frontend/README.md", ["/frontend/**", "!/frontend/README.md"], False),  # negation
        ("frontend/README.md", ["!/frontend/README.md", "/frontend/**"], True),  # last wins
        ("frontend\\src\\x.ts", ["/frontend/**"], True),  # Windows separators
    ],
)
def test_watch_pattern_matching_is_gitignore_style(path, patterns, expected):
    assert rdi.matches(path, patterns) is expected


def test_snapshot_is_complete_and_shaped():
    services = SNAPSHOT["services"]
    assert {s["environment"] for s in services} == {"production", "staging"}
    for svc in services:
        assert svc["watch_patterns"], svc
        assert all(p.startswith(("/", "!")) for p in svc["watch_patterns"]), svc
        assert svc["branch"], svc
    keys = [(s["environment"], s["service"]) for s in services]
    assert len(keys) == len(set(keys))
    # Staging soil, weather and ai-agronomist deploy from main although
    # describe-environment shows no source for them; they must be in the snapshot.
    for name in ("sahool-soil-service", "sahool-weather-service", "sahool-ai-agronomist"):
        assert ("staging", name) in keys


@pytest.mark.parametrize("merge", MEASURED, ids=lambda m: m["pr"])
def test_derived_effect_equals_what_railway_built(merge):
    result = rdi.impact(merge["changed_paths"], SNAPSHOT)
    for env in ("production", "staging"):
        derived = sorted(e["service"] for e in result["triggered"].get(env, []))
        measured = merge["built"][env]
        # A service Railway built that is not in the snapshot would be a hole in the
        # capture, not a pass.
        assert derived == measured, f"{merge['pr']} {env}: derived {derived} != built {measured}"


def test_1285_hand_written_claim_is_what_the_tool_refutes():
    """Falsification of the old practice: the body said gateway only."""
    merge = next(m for m in MEASURED if m["pr"] == "#1285")
    result = rdi.impact(merge["changed_paths"], SNAPSHOT)
    production = {e["service"] for e in result["triggered"]["production"]}
    assert production != {"sahool-frontend"}
    assert {"sahool-auth-main", "sahool-vegetation-analysis"} <= production


def test_brain_only_change_deploys_nothing():
    result = rdi.impact(["sahool-brain/log.md", "sahool-brain/gaps/registry.md"], SNAPSHOT)
    assert result["triggered"] == {}
    assert rdi.deploy_effect_line(result) == "Deploy-Effect: NONE"


def test_migration_change_flags_the_migrator():
    result = rdi.impact(["migrations/999_example.sql"], SNAPSHOT)
    assert result["migrator"] == ["production/sahool-migrate-main", "staging/sahool-migrate-main"]


def test_non_main_branch_services_are_not_counted_as_triggered():
    result = rdi.impact(["services/sahool-platform/api/main.py"], SNAPSHOT)
    assert result["triggered"] == {}
    assert {(e["environment"], e["service"]) for e in result["other_branch"]} == {
        ("production", "sahool-platform"),
        ("staging", "sahool-platform"),
    }


def test_compare_reports_pattern_branch_and_membership_drift():
    old = {
        "services": [
            {
                "environment": "production",
                "service": "a",
                "branch": "main",
                "watch_patterns": ["/a/**"],
            }
        ]
    }
    assert rdi.compare(old, old) == []
    changed = {
        "services": [
            {
                "environment": "production",
                "service": "a",
                "branch": "main",
                "watch_patterns": ["/b/**"],
            }
        ]
    }
    assert len(rdi.compare(old, changed)) == 1
    added = {
        "services": old["services"]
        + [
            {
                "environment": "staging",
                "service": "b",
                "branch": "main",
                "watch_patterns": ["/b/**"],
            }
        ]
    }
    assert rdi.compare(old, added) == ["added: staging/b"]


def test_snapshot_without_watch_patterns_is_rejected(tmp_path):
    bad = tmp_path / "s.json"
    bad.write_text(
        json.dumps(
            {
                "services": [
                    {
                        "environment": "production",
                        "service": "x",
                        "branch": "main",
                        "watch_patterns": [],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        rdi.load_snapshot(bad)


def test_snapshot_age_is_computed_from_capture_time():
    now = datetime(2026, 11, 5, 9, 39, 58, tzinfo=UTC)
    assert round(rdi.snapshot_age_days({"captured_at": "2026-10-26T09:39:58Z"}, now)) == 10
