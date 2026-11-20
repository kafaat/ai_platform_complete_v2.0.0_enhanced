"""The irrigation CI suite cannot certify a missing or skipped PostgreSQL case."""

from xml.etree import ElementTree as ET

import pytest

from scripts.irr_f01.required_cases import FRESH, LIVE, UPGRADE, validate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("suite", "extra", "module"),
    [
        ("fresh", FRESH, "test_v195_postgres"),
        ("upgrade", UPGRADE, "test_irr_f01_upgrade_gate_u1_pg"),
    ],
)
def test_required_evidence(tmp_path, suite, extra, module):
    report = tmp_path / "report.xml"
    root = ET.Element("testsuite")
    for name in LIVE:
        ET.SubElement(
            root, "testcase", classname="tests_v9.test_irr_f01_reservation_live_pg", name=name
        )
    for name in extra:
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
