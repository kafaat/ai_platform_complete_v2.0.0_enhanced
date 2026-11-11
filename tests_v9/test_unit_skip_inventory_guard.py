"""The unit skip inventory guard blocks every undeclared change to the unit suite's skips.

S1 F3 (`OFFICE-20261110:F3` on #1369). Each case below is one way a skip could change without
anyone deciding it: a new skip, a changed reason, a declared skip that stopped happening, the
same test skipping in another stage. Each must be BLOCKED, and none may turn a skip into a pass.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts/ci/unit_skip_inventory_guard.py"


def _load():
    spec = importlib.util.spec_from_file_location("_unit_skip_inventory_guard", GUARD)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load()

PCSE = "tests_v9/test_wofost_pcse_offline_integration.py::test_every_registry_crop_runs_offline"
REASON = "pcse not installed"


def _junit(tmp_path: Path, name: str, cases: list[tuple[str, str, str | None]]) -> Path:
    """cases: (classname, name, skip message or None for a pass)."""
    body = []
    for classname, test, skipped in cases:
        inner = "" if skipped is None else f'<skipped type="pytest.skip" message="{skipped}"/>'
        body.append(
            f'<testcase classname="{classname}" name="{test}" time="0.1">{inner}</testcase>'
        )
    path = tmp_path / name
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        + "".join(body)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def _entry(nodeid=PCSE, reason=REASON, stage="parallel", **extra) -> dict:
    entry = {
        "stage": stage,
        "nodeid": nodeid,
        "reason": reason,
        "classification": "optional-profile",
        "required_gate": "a pinned offline pcse job",
        "status": "open",
    }
    entry.update(extra)
    return entry


def _inventory(tmp_path: Path, entries: list[dict]) -> Path:
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps({"skips": entries}, ensure_ascii=False), encoding="utf-8")
    return path


PCSE_CASE = (
    "tests_v9.test_wofost_pcse_offline_integration",
    "test_every_registry_crop_runs_offline",
    REASON,
)


def _run(tmp_path, cases, entries, stage="parallel") -> int:
    report = _junit(tmp_path, f"{stage}.xml", cases)
    return guard.main(
        ["--junit", f"{stage}={report}", "--inventory", str(_inventory(tmp_path, entries))]
    )


def test_reports_equal_to_the_inventory_pass_and_say_skips_stay_open(tmp_path, capsys):
    assert _run(tmp_path, [PCSE_CASE, ("tests_v9.test_x", "test_ok", None)], [_entry()]) == 0
    out = capsys.readouterr().out
    assert "1 open" in out and "never turns a skip into a pass" in out


def test_an_undeclared_skip_is_blocked(tmp_path, capsys):
    """A test that stopped running yesterday: the case the guard exists for."""
    new = ("tests_v9.test_new", "test_started_skipping", "service down")
    assert _run(tmp_path, [PCSE_CASE, new], [_entry()]) == 1
    assert "undeclared skip in stage parallel: tests_v9/test_new.py::test_started_skipping" in (
        capsys.readouterr().out
    )


def test_a_changed_reason_is_blocked(tmp_path, capsys):
    """Same test, different cause: the declared decision no longer describes it."""
    moved = (*PCSE_CASE[:2], "pcse import crashed")
    assert _run(tmp_path, [moved], [_entry()]) == 1
    assert "skip reason changed" in capsys.readouterr().out


def test_a_declared_skip_that_stopped_happening_is_blocked(tmp_path, capsys):
    """The inventory only shrinks: a fixed skip must leave the list in the same change."""
    assert _run(tmp_path, [(*PCSE_CASE[:2], None)], [_entry()]) == 1
    assert "no longer occurs" in capsys.readouterr().out


def test_the_same_skip_in_another_stage_is_blocked(tmp_path, capsys):
    assert _run(tmp_path, [PCSE_CASE], [_entry()], stage="tree_writer") == 1
    out = capsys.readouterr().out
    assert "undeclared skip in stage tree_writer (declared for stage parallel)" in out


def test_a_collection_skip_is_named_by_its_file(tmp_path):
    """pytest reports a module skipped at collection with an empty classname."""
    report = _junit(tmp_path, "c.xml", [("", "tests_v9.test_h51_field_source_binding_pg", "x")])
    assert guard.skips_in("parallel", report) == [
        ("parallel", "tests_v9/test_h51_field_source_binding_pg.py", "x")
    ]


def test_a_class_method_keeps_its_class_in_the_node_id(tmp_path):
    report = _junit(
        tmp_path,
        "k.xml",
        [
            (
                "tests_v9.test_tts_providers_20260702.TestProviderAvailability",
                "test_edge_available",
                "s",
            )
        ],
    )
    assert guard.skips_in("parallel", report)[0][1] == (
        "tests_v9/test_tts_providers_20260702.py::TestProviderAvailability::test_edge_available"
    )


def test_an_exception_needs_the_owners_decision(tmp_path):
    entries = [_entry(status="exception")]
    with pytest.raises(guard.InventoryError, match="owner's decision"):
        guard.load_inventory(_inventory(tmp_path, entries))
    entries[0]["decision"] = "owner ruling 2026-11-10, comment #…"
    assert guard.load_inventory(_inventory(tmp_path, entries))


def test_an_entry_without_its_gate_or_with_an_unknown_class_is_unreadable(tmp_path):
    with pytest.raises(guard.InventoryError, match="required_gate"):
        guard.load_inventory(_inventory(tmp_path, [_entry(required_gate="")]))
    with pytest.raises(guard.InventoryError, match="classification"):
        guard.load_inventory(_inventory(tmp_path, [_entry(classification="flaky")]))


def test_an_unreadable_report_is_not_a_pass(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_text("<testsuites>", encoding="utf-8")
    inventory = _inventory(tmp_path, [_entry()])
    assert guard.main(["--junit", f"parallel={bad}", "--inventory", str(inventory)]) == 2


def test_the_committed_inventory_is_valid_and_keeps_every_entry_open_or_decided():
    entries = guard.load_inventory()
    assert entries, "an empty inventory would mean S1 has no skip left; prove it by a run first"
    assert all(e["status"] in {"open", "exception"} for e in entries)


def test_the_unit_job_feeds_both_stages_to_the_guard():
    """The guard is only a gate if the job that runs the suite also runs it on that run."""
    text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    joined = " ".join(text.split())
    assert '-m "unit and not tree_writer"' in joined and "--junitxml=unit-par.xml" in joined
    assert '-m "unit and tree_writer"' in joined and "--junitxml=unit-tw.xml" in joined
    assert (
        "python scripts/ci/unit_skip_inventory_guard.py --junit parallel=unit-par.xml "
        "--junit tree_writer=unit-tw.xml"
    ) in joined


def test_the_unit_job_runs_the_live_redis_proofs_instead_of_declaring_them():
    """REDIS-ACL-LIVE-IN-NO-CI-JOB-01: the 18 live Redis ACL proofs skipped in this job for lack
    of a binary and ran in no CI job. The remedy is the binary plus a flag that fails on its
    absence, never 18 more inventory lines. Removing either makes this test red."""
    import yaml

    document = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = document["jobs"]["unit-tests"]["steps"]
    runs = [str(step.get("run", "")) for step in steps]
    install = next(
        i for i, run in enumerate(runs) if "resilient_apt_install.sh redis-server" in run
    )
    assert "systemctl stop redis-server" in runs[install], "the distro service must not hold 6379"
    suites = [i for i, run in enumerate(runs) if '-m "unit and' in run]
    assert len(suites) == 2 and all(install < i for i in suites)
    for i in suites:
        assert (steps[i].get("env") or {}).get("REDIS_ACL_LIVE_REQUIRED") == "1", runs[i]
    entries = guard.load_inventory()
    assert not [e for e in entries if e["reason"].startswith("لا redis-server")]
    assert not [e for e in entries if e["reason"] == "redis-server unavailable"]
