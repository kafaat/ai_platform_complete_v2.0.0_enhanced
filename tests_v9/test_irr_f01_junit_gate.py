"""The irrigation CI suite cannot certify a missing or skipped PostgreSQL case."""

import json
import os
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from scripts.irr_f01.required_cases import COMPENSATION, FRESH, LIVE, UPGRADE, validate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("suite", "extras"),
    [
        (
            "fresh",
            [
                ("test_irr_f01_compensation_live_pg", COMPENSATION),
                ("test_v195_postgres", FRESH),
            ],
        ),
        ("upgrade", [("test_irr_f01_upgrade_gate_u1_pg", UPGRADE)]),
    ],
)
def test_required_evidence(tmp_path, suite, extras):
    report = tmp_path / "report.xml"
    root = ET.Element("testsuite")
    for name in LIVE:
        ET.SubElement(
            root, "testcase", classname="tests_v9.test_irr_f01_reservation_live_pg", name=name
        )
    for module, names in extras:
        for name in sorted(names):
            case = ET.SubElement(root, "testcase", classname=module, name=name)
    tree = ET.ElementTree(root)
    tree.write(report)
    validate(report, suite)
    ET.SubElement(case, "skipped")
    tree.write(report)
    with pytest.raises(ValueError, match="unsuccessful case"):
        validate(report, suite)
    root.remove(case)
    tree.write(report)
    with pytest.raises(ValueError, match="missing JUnit cases"):
        validate(report, suite)


@pytest.mark.parametrize(("status", "filename"), [("passed", "SUCCESS"), ("failed", "FAILURE")])
def test_certification_report_writes_utf8_under_c_locale(tmp_path, status, filename):
    script = Path(__file__).resolve().parents[1] / "scripts/irr_f01/build_report.py"
    subprocess.run(
        [sys.executable, str(script), "--report-dir", str(tmp_path), "--status", status],
        env={**os.environ, "LC_ALL": "C", "PYTHONUTF8": "0"},
        check=True,
    )
    report = (tmp_path / f"IRR_F01_{filename}_REPORT.md").read_text(encoding="utf-8")
    assert f"IRR-F01 LOCAL GATE — {status.upper()}" in report
    assert json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))["status"] == status


def test_compensation_cases_are_required_in_the_fresh_suite_and_listed_in_run_suite():
    """A compensation case that skips or goes missing must fail the certifying run."""
    import inspect
    import re

    import tests_v9.test_irr_f01_compensation_live_pg as compensation

    defined = {
        name
        for name, fn in inspect.getmembers(compensation, inspect.isfunction)
        if name.startswith("test_")
    }
    required = {name.split("[", 1)[0] for name in COMPENSATION}
    assert required == defined
    run_suite = (Path(__file__).resolve().parents[1] / "scripts/irr_f01/run_suite.sh").read_text(
        encoding="utf-8"
    )
    fresh = re.search(r"fresh\)(.*?);;", run_suite, re.S).group(1)
    assert "tests_v9/test_irr_f01_compensation_live_pg.py" in fresh
