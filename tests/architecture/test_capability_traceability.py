from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "capabilities/registry/capabilities.json"
MOBILE_LIB = ROOT / "mobile/sahool_app/lib"

# import/export/part with a quoted target (``part of foo;`` has no quote → ignored).
_DART_DIRECTIVE = re.compile(r"""^\s*(?:import|export|part)\s+['"]([^'"]+)['"]""", re.MULTILINE)


def _caps():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))["capabilities"]


def test_no_service_or_test_pointer_is_missing():
    for cap in _caps():
        for field in ("services", "tests", "ui_consumers", "mobile_consumers"):
            for pointer in cap.get(field, []):
                assert (ROOT / pointer).exists(), f"{cap['id']} missing {field}: {pointer}"


def _capability_dart_files():
    files = set()
    for cap in _caps():
        for field in ("services", "tests", "ui_consumers", "mobile_consumers"):
            for pointer in cap.get(field, []):
                path = pointer.split(" @ ")[0].strip()
                if path.endswith(".dart"):
                    files.add(path)
    return sorted(files)


def _resolve_first_party_import(importer: Path, target: str):
    """Resolve a Dart import to a repo path, or None for SDK / third-party pub
    packages (resolved by pub, not the source tree)."""
    if target.startswith("dart:"):
        return None
    if target.startswith("package:sahool_app/"):
        return MOBILE_LIB / target[len("package:sahool_app/") :]
    if target.startswith("package:"):
        return None
    return (importer.parent / target).resolve()  # relative import


def test_capability_dart_imports_resolve():
    """Close the blind spot of the pointer-existence check: a registered Dart
    screen can itself ``import`` a module that does not exist (non-compiling
    mobile code) while every *registry pointer* still resolves. Resolve every
    first-party (relative or ``package:sahool_app/``) import/export/part of each
    capability-referenced Dart file and assert the target is on disk."""
    missing = []
    for rel in _capability_dart_files():
        src = ROOT / rel
        if not src.exists():
            continue  # absence of the pointer itself is covered above
        for target in _DART_DIRECTIVE.findall(src.read_text(encoding="utf-8", errors="ignore")):
            resolved = _resolve_first_party_import(src, target)
            if resolved is not None and not resolved.exists():
                missing.append(f"{rel} → {target}")
    assert not missing, "capability-referenced Dart files import missing modules:\n" + "\n".join(
        missing[:40]
    )


def test_high_confidence_requires_service_api_and_test():
    for cap in _caps():
        if cap["confidence"] == "high":
            assert cap["services"], cap["id"]
            assert cap["apis"], cap["id"]
            assert cap["tests"], cap["id"]


def test_known_missing_precision_capabilities_are_not_inflated():
    by_id = {c["id"]: c for c in _caps()}
    for cid in ("PA-003", "PA-004"):
        assert by_id[cid]["maturity"] <= 2
        assert not by_id[cid]["production_certified"]


def test_decision_chain_is_explicit():
    by_id = {c["id"]: c for c in _caps()}
    expected = {
        "DEC-002": "DEC-001",
        "DEC-003": "DEC-002",
        "DEC-004": "DEC-003",
        "DEC-005": "DEC-004",
        "DEC-006": "DEC-005",
        "DEC-007": "DEC-006",
        "DEC-008": "DEC-007",
        "DEC-009": "DEC-008",
        "DEC-010": "DEC-009",
    }
    for cid, dep in expected.items():
        assert dep in by_id[cid]["dependencies"]


def test_committed_traceability_reports_match_authoritative_view():
    from scripts.ci import capability_traceability_report as report

    committed = report.OUT
    expected = {
        "CAPABILITY_TRACEABILITY_REPORT.md",
        "capability_traceability.csv",
        "capability_traceability_summary.json",
    }
    with tempfile.TemporaryDirectory() as folder:
        generated = Path(folder)
        with patch.object(report, "OUT", generated):
            assert report.main() == 0
        assert {path.name for path in generated.iterdir()} == expected
        drift = [
            name
            for name in sorted(expected)
            if not (committed / name).is_file()
            or (committed / name).read_bytes() != (generated / name).read_bytes()
        ]
    assert not drift, f"Run python scripts/ci/capability_traceability_report.py to refresh {drift}"


@pytest.mark.parametrize(
    "name",
    [
        "CAPABILITY_TRACEABILITY_REPORT.md",
        "capability_traceability.csv",
        "capability_traceability_summary.json",
    ],
)
@pytest.mark.parametrize("damage", ["corrupt", "remove"])
def test_traceability_check_detects_each_artifact_without_repair(
    name, damage, tmp_path, monkeypatch, capsys
):
    from scripts.ci import capability_traceability_report as report

    monkeypatch.setattr(report, "OUT", tmp_path)
    assert report.main() == 0
    original = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    target = tmp_path / name
    if damage == "remove":
        target.unlink()
    else:
        target.write_bytes(b"damaged report\n")
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}

    assert report.main(check=True) == 1
    assert name in capsys.readouterr().err
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in tmp_path.iterdir()}, (
        "Checking drift must not repair or touch artifacts"
    )

    assert report.main() == 0
    assert original == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert report.main(check=True) == 0
