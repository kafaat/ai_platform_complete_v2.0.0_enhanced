from pathlib import Path

import pytest

# Without a marker this file runs in NO CI job: pytest.ini scopes testpaths to
# tests_v9 and the gating job selects `-m unit`. An unmarked test is not a weak
# test, it is an absent one.
pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]


def test_no_temporary_probe_is_present_in_source_tree() -> None:
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in ROOT.rglob("*.py")
        if "probe_unadjudicated" in path.name or path.name.startswith("_probe_")
    ]
    assert offenders == [], f"temporary probe files must never be tracked: {offenders}"
